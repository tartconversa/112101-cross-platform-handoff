"""Silver 层：从 Bronze 不可变消息规范化出可信业务表。

- 完整重算（deterministic rebuild）：任何时候都由 Bronze 重新生成，Silver 自身无状态；
- 自然键去重已在 Bronze 完成，这里只做类型规范化与参照完整性检查；
- 参照断裂的消息进入 silver 隔离区，不参与 Gold 汇总；
- 回执保留全部原始行（含纠正链），"最新有效回执"在 Gold 层按业务口径选取，
  纠正前的原始状态不会被覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .csvio import write_csv
from .domain import (
    ACTION_SOURCE,
    FINDING_SOURCE,
    NOTICE_SOURCE,
    RECEIPT_SOURCE,
    SILVER_DIR,
)
from .ingest import BronzeStore
from .timeutil import parse_iso8601, to_iso8601

ACTION_HEADER = (
    "action_id",
    "revision",
    "opened_at",
    "scope_ref",
    "coordinator",
    "state",
    "change_note",
    "ingest_batch",
    "record_id",
    "source_file",
    "source_row",
)
NOTICE_HEADER = (
    "action_id",
    "revision",
    "platform_id",
    "measure_code",
    "measure_label",
    "notified_at",
    "notice_state",
    "ingest_batch",
    "record_id",
    "source_file",
    "source_row",
)
FINDING_HEADER = (
    "finding_id",
    "action_id",
    "action_revision",
    "platform_id",
    "local_object_ref",
    "object_type",
    "content_fingerprint",
    "matched_at",
    "match_state",
    "ingest_batch",
    "record_id",
    "source_file",
    "source_row",
)
RECEIPT_HEADER = (
    "receipt_id",
    "finding_id",
    "action_code",
    "measure_code",
    "receipt_state",
    "correction_ref",
    "received_at",
    "ingest_batch",
    "record_id",
    "source_file",
    "source_row",
)


@dataclass
class SilverResult:
    counts: dict[str, int]
    referential_quarantine: list[dict]


class SilverStore:
    def __init__(self, lake_root: Path) -> None:
        self.lake_root = Path(lake_root)
        self.root = self.lake_root / SILVER_DIR
        self.ref_quarantine_path = self.root / "referential_quarantine.jsonl"

    # ------------------------------------------------------------ 读取入口
    def actions(self) -> list[dict[str, str]]:
        return _read(self.root / "action_versions.csv")

    def notices(self) -> list[dict[str, str]]:
        return _read(self.root / "coordination_notices.csv")

    def findings(self) -> list[dict[str, str]]:
        return _read(self.root / "platform_findings.csv")

    def receipts(self) -> list[dict[str, str]]:
        return _read(self.root / "receipts.csv")

    # ------------------------------------------------------------ 全量重算
    def rebuild(self, bronze: BronzeStore) -> SilverResult:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.ref_quarantine_path.exists():
            self.ref_quarantine_path.unlink()

        raw_actions = bronze.load_landing(ACTION_SOURCE)
        raw_notices = bronze.load_landing(NOTICE_SOURCE)
        raw_findings = bronze.load_landing(FINDING_SOURCE)
        raw_receipts = bronze.load_landing(RECEIPT_SOURCE)

        action_keys = {
            (item["payload"]["action_id"], int(item["payload"]["revision"]))
            for item in raw_actions
        }

        quarantined: list[dict] = []

        # 通知 -> 行动版本
        valid_notices = []
        for item in raw_notices:
            payload = item["payload"]
            key = (payload["action_id"], int(payload["revision"]))
            if key not in action_keys:
                quarantined.append(
                    _ref_failure(item, f"通知引用了不存在的行动版本 {key}")
                )
                continue
            valid_notices.append(item)

        # 映射 -> 行动版本
        valid_findings = []
        finding_keys: set[str] = set()
        for item in raw_findings:
            payload = item["payload"]
            key = (payload["action_id"], int(payload["action_revision"]))
            if key not in action_keys:
                quarantined.append(
                    _ref_failure(item, f"对象映射引用了不存在的行动版本 {key}")
                )
                continue
            valid_findings.append(item)
            finding_keys.add(payload["finding_id"])

        # 回执 -> 映射 + 行动（action_code 必须与映射所属行动一致）
        finding_action = {
            item["payload"]["finding_id"]: item["payload"]["action_id"]
            for item in valid_findings
        }
        valid_receipts = []
        for item in raw_receipts:
            payload = item["payload"]
            finding_id = payload["finding_id"]
            if finding_id not in finding_keys:
                quarantined.append(
                    _ref_failure(item, f"回执引用了不存在的对象映射 {finding_id}")
                )
                continue
            if payload["action_code"] != finding_action[finding_id]:
                quarantined.append(
                    _ref_failure(
                        item,
                        f"回执行动码 {payload['action_code']} 与映射所属行动 "
                        f"{finding_action[finding_id]} 不一致",
                    )
                )
                continue
            valid_receipts.append(item)

        counts = {
            ACTION_SOURCE: write_csv(
                self.root / "action_versions.csv",
                ACTION_HEADER,
                (_action_row(item) for item in raw_actions),
            ),
            NOTICE_SOURCE: write_csv(
                self.root / "coordination_notices.csv",
                NOTICE_HEADER,
                (_notice_row(item) for item in valid_notices),
            ),
            FINDING_SOURCE: write_csv(
                self.root / "platform_findings.csv",
                FINDING_HEADER,
                (_finding_row(item) for item in valid_findings),
            ),
            RECEIPT_SOURCE: write_csv(
                self.root / "receipts.csv",
                RECEIPT_HEADER,
                (_receipt_row(item) for item in valid_receipts),
            ),
        }

        for record in quarantined:
            self._append_ref_quarantine(record)
        return SilverResult(counts=counts, referential_quarantine=quarantined)

    def _append_ref_quarantine(self, record: dict) -> None:
        import json

        with self.ref_quarantine_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            stream.write("\n")


def _read(path: Path) -> list[dict[str, str]]:
    from .csvio import read_csv

    return read_csv(path)


def _ref_failure(item: dict, reason: str) -> dict:
    return {
        "source_file": item["source_file"],
        "source_row": item["source_row"],
        "record_id": item["record_id"],
        "ingest_batch": item["ingest_batch"],
        "reason": reason,
        "payload": item["payload"],
    }


def _lineage(item: dict) -> dict:
    return {
        "record_id": item["record_id"],
        "source_file": item["source_file"],
        "source_row": item["source_row"],
        "ingest_batch": item["ingest_batch"],
    }


def _action_row(item: dict) -> dict:
    payload = item["payload"]
    return {
        "action_id": payload["action_id"],
        "revision": int(payload["revision"]),
        "opened_at": to_iso8601(parse_iso8601(payload["opened_at"])),
        "scope_ref": payload["scope_ref"],
        "coordinator": payload["coordinator"],
        "state": payload["state"],
        "change_note": payload["change_note"],
        **_lineage(item),
    }


def _notice_row(item: dict) -> dict:
    payload = item["payload"]
    return {
        "action_id": payload["action_id"],
        "revision": int(payload["revision"]),
        "platform_id": payload["platform_id"],
        "measure_code": payload["measure_code"],
        "measure_label": payload["measure_label"],
        "notified_at": to_iso8601(parse_iso8601(payload["notified_at"])),
        "notice_state": payload["notice_state"],
        **_lineage(item),
    }


def _finding_row(item: dict) -> dict:
    payload = item["payload"]
    return {
        "finding_id": payload["finding_id"],
        "action_id": payload["action_id"],
        "action_revision": int(payload["action_revision"]),
        "platform_id": payload["platform_id"],
        "local_object_ref": payload.get("local_object_ref", ""),
        "object_type": payload["object_type"],
        "content_fingerprint": payload["content_fingerprint"],
        "matched_at": to_iso8601(parse_iso8601(payload["matched_at"])),
        "match_state": payload["match_state"],
        **_lineage(item),
    }


def _receipt_row(item: dict) -> dict:
    payload = item["payload"]
    return {
        "receipt_id": payload["receipt_id"],
        "finding_id": payload["finding_id"],
        "action_code": payload["action_code"],
        "measure_code": payload["measure_code"],
        "receipt_state": payload["receipt_state"],
        "correction_ref": payload.get("correction_ref", ""),
        "received_at": to_iso8601(parse_iso8601(payload["received_at"])),
        **_lineage(item),
    }

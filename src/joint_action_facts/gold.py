"""Gold 层：按行动版本呈现接续状态的汇总事实表。

关键口径：
- 共同汇总不抹除单个平台的判断：每个 (行动, 平台) 独立成行，状态只来自平台证据；
- 外观相似的内容不合并：相同 content_fingerprint 仅用于关联展示，
  平台本地对象（local_object_ref）与映射记录始终独立保留；
- 重复回执不计作多次独立处置：处置每平台每行动只有一条，
  重复投递数单独统计；
- 范围变更可追溯：以最新行动版本判定 withdrawn，旧版本目标在版本覆盖表中保留；
- 每行携带来源 record_id 与批次，可逐级回溯到 Bronze 原始消息。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .csvio import read_csv, write_csv
from .domain import (
    COVERED_DISPOSITIONS,
    DISP_EVIDENCE_NEEDED,
    DISP_EXECUTED,
    DISP_NOT_REACHED,
    DISP_UNDER_REVIEW,
    DISP_WITHDRAWN,
    DISPOSITION_LABELS,
    GOLD_DIR,
    PENDING_DISPOSITIONS,
    RECEIPT_ACCEPTED,
    RECEIPT_CORRECTED,
)
from .silver import SilverStore
from .states import derive_disposition
from .timeutil import lead_time_hours, parse_iso8601

DISPOSITION_HEADER = (
    "action_id",
    "platform_id",
    "latest_revision",
    "coordinator",
    "notified_measure_code",
    "disposition_state",
    "disposition_label",
    "finding_id",
    "local_object_ref",
    "content_fingerprint",
    "match_state",
    "matched_at",
    "latest_receipt_id",
    "latest_receipt_state",
    "latest_received_at",
    "receipt_count",
    "correction_count",
    "executed_at",
    "lead_time_hours",
    "duplicate_delivery_count",
    "evidence_record_ids",
    "evidence_batches",
    "as_of_batch",
)

COVERAGE_HEADER = (
    "action_id",
    "revision",
    "coordinator",
    "scope_ref",
    "state",
    "opened_at",
    "target_platform_count",
    "covered_count",
    "pending_count",
    "executed_count",
    "evidence_needed_count",
    "not_applicable_count",
    "under_review_count",
    "not_reached_count",
    "withdrawn_count",
    "coverage_ratio",
    "pending_platforms",
    "as_of_batch",
)

INBOX_HEADER = (
    "platform_id",
    "action_id",
    "latest_revision",
    "disposition_state",
    "disposition_label",
    "measure_code",
    "measure_label",
    "notified_at",
    "latest_received_at",
    "open_issue",
    "evidence_record_ids",
    "as_of_batch",
)

FINGERPRINT_HEADER = (
    "content_fingerprint",
    "action_id",
    "platform_id",
    "finding_id",
    "local_object_ref",
    "match_state",
    "source_record_id",
)


@dataclass
class GoldResult:
    disposition_rows: int
    coverage_rows: int
    inbox_rows: int
    fingerprint_rows: int
    as_of_batch: str


class GoldStore:
    def __init__(self, lake_root: Path) -> None:
        self.lake_root = Path(lake_root)
        self.root = self.lake_root / GOLD_DIR

    # ------------------------------------------------------------ 读取入口
    def dispositions(self) -> list[dict[str, str]]:
        return read_csv(self.root / "platform_dispositions.csv")

    def coverage(self) -> list[dict[str, str]]:
        return read_csv(self.root / "action_coverage.csv")

    def inbox(self) -> list[dict[str, str]]:
        return read_csv(self.root / "platform_inbox.csv")

    def fingerprints(self) -> list[dict[str, str]]:
        return read_csv(self.root / "fingerprint_links.csv")

    # ------------------------------------------------------------ 汇总构建
    def build(
        self,
        silver: SilverStore,
        as_of_batch: str,
        duplicate_counts: dict[tuple[str, str], int],
    ) -> GoldResult:
        self.root.mkdir(parents=True, exist_ok=True)

        actions = silver.actions()
        notices = silver.notices()
        findings = silver.findings()
        receipts = silver.receipts()

        latest_revision = {
            row["action_id"]: max(
                entry["revision"]
                for entry in actions
                if entry["action_id"] == row["action_id"]
            )
            for row in actions
        }
        action_meta = {
            (row["action_id"], row["revision"]): row for row in actions
        }

        # 每个 (行动, 平台) 的全部通知与最新版本通知。
        notices_by_target: dict[tuple[str, str], list[dict]] = {}
        for row in notices:
            notices_by_target.setdefault(
                (row["action_id"], row["platform_id"]), []
            ).append(row)
        latest_notice: dict[tuple[str, str], dict] = {
            key: sorted(
                rows, key=lambda r: (int(r["revision"]), r["notified_at"])
            )[-1]
            for key, rows in notices_by_target.items()
        }
        earliest_notice: dict[tuple[str, str], dict] = {
            key: sorted(rows, key=lambda r: parse_iso8601(r["notified_at"]))[0]
            for key, rows in notices_by_target.items()
        }

        # 每个 (行动, 平台) 的平台映射（同一平台同一行动可能有多条，取事件时间最新）。
        findings_by_target: dict[tuple[str, str], list[dict]] = {}
        for row in findings:
            findings_by_target.setdefault(
                (row["action_id"], row["platform_id"]), []
            ).append(row)
        latest_finding: dict[tuple[str, str], dict] = {
            key: sorted(
                rows, key=lambda r: (parse_iso8601(r["matched_at"]), r["finding_id"])
            )[-1]
            for key, rows in findings_by_target.items()
        }

        # 回执按映射分组，全部保留；最新有效回执按事件时间排序选取。
        receipts_by_finding: dict[str, list[dict]] = {}
        for row in receipts:
            receipts_by_finding.setdefault(row["finding_id"], []).append(row)
        for grouped in receipts_by_finding.values():
            grouped.sort(
                key=lambda r: (parse_iso8601(r["received_at"]), r["record_id"])
            )

        disposition_rows = self._build_dispositions(
            actions=actions,
            latest_revision=latest_revision,
            latest_notice=latest_notice,
            earliest_notice=earliest_notice,
            latest_finding=latest_finding,
            receipts_by_finding=receipts_by_finding,
            duplicate_counts=duplicate_counts,
            as_of_batch=as_of_batch,
        )

        coverage_rows = self._build_coverage(
            actions=actions,
            notices=notices,
            action_meta=action_meta,
            dispositions=disposition_rows,
            as_of_batch=as_of_batch,
        )

        inbox_rows = self._build_inbox(
            disposition_rows, latest_notice, as_of_batch
        )
        fingerprint_rows = self._build_fingerprints(findings)

        return GoldResult(
            disposition_rows=write_csv(
                self.root / "platform_dispositions.csv",
                DISPOSITION_HEADER,
                disposition_rows,
            ),
            coverage_rows=write_csv(
                self.root / "action_coverage.csv", COVERAGE_HEADER, coverage_rows
            ),
            inbox_rows=write_csv(
                self.root / "platform_inbox.csv", INBOX_HEADER, inbox_rows
            ),
            fingerprint_rows=write_csv(
                self.root / "fingerprint_links.csv",
                FINGERPRINT_HEADER,
                fingerprint_rows,
            ),
            as_of_batch=as_of_batch,
        )

    # ------------------------------------------------------------ 处置事实
    def _build_dispositions(
        self,
        actions: list[dict],
        latest_revision: dict[str, str],
        latest_notice: dict[tuple[str, str], dict],
        earliest_notice: dict[tuple[str, str], dict],
        latest_finding: dict[tuple[str, str], dict],
        receipts_by_finding: dict[str, list[dict]],
        duplicate_counts: dict[tuple[str, str], int],
        as_of_batch: str,
    ) -> list[dict]:
        # 处置目标 = 收到过统一通知的全部 (行动, 平台)，含后来退出的平台。
        targets = sorted(latest_notice.keys())
        rows: list[dict] = []
        for action_id, platform_id in targets:
            revision = latest_revision[action_id]
            notice = latest_notice[(action_id, platform_id)]
            coordinator = next(
                row["coordinator"]
                for row in actions
                if row["action_id"] == action_id
                and row["revision"] == revision
            )
            # 最新版本通知中消失 = 牵头单位通过范围调整将该平台移出。
            withdrawn = int(notice["revision"]) < int(revision)
            finding = latest_finding.get((action_id, platform_id))
            target_receipts = (
                receipts_by_finding.get(finding["finding_id"], []) if finding else []
            )
            latest_receipt = target_receipts[-1] if target_receipts else None
            receipt_state = latest_receipt["receipt_state"] if latest_receipt else None
            match_state = finding["match_state"] if finding else None

            state = derive_disposition(
                match_state=match_state,
                receipt_state=receipt_state,
                withdrawn=withdrawn,
            )

            executed_receipts = [
                row
                for row in target_receipts
                if row["receipt_state"] in (RECEIPT_ACCEPTED, RECEIPT_CORRECTED)
            ]
            executed_at = (
                executed_receipts[0]["received_at"] if executed_receipts else ""
            )
            lead_time = (
                lead_time_hours(
                    parse_iso8601(earliest_notice[(action_id, platform_id)]["notified_at"]),
                    parse_iso8601(executed_at),
                )
                if executed_at
                else ""
            )

            evidence_record_ids = [notice["record_id"]]
            evidence_batches = [notice["ingest_batch"]]
            if finding:
                evidence_record_ids.append(finding["record_id"])
                evidence_batches.append(finding["ingest_batch"])
            for row in target_receipts:
                evidence_record_ids.append(row["record_id"])
                evidence_batches.append(row["ingest_batch"])

            rows.append(
                {
                    "action_id": action_id,
                    "platform_id": platform_id,
                    "latest_revision": revision,
                    "coordinator": coordinator,
                    "notified_measure_code": notice["measure_code"],
                    "disposition_state": state,
                    "disposition_label": DISPOSITION_LABELS[state],
                    "finding_id": finding["finding_id"] if finding else "",
                    "local_object_ref": (
                        finding["local_object_ref"] if finding else ""
                    ),
                    "content_fingerprint": (
                        finding["content_fingerprint"] if finding else ""
                    ),
                    "match_state": match_state or "",
                    "matched_at": finding["matched_at"] if finding else "",
                    "latest_receipt_id": (
                        latest_receipt["receipt_id"] if latest_receipt else ""
                    ),
                    "latest_receipt_state": receipt_state or "",
                    "latest_received_at": (
                        latest_receipt["received_at"] if latest_receipt else ""
                    ),
                    "receipt_count": len(target_receipts),
                    "correction_count": sum(
                        1
                        for row in target_receipts
                        if row["receipt_state"] == RECEIPT_CORRECTED
                    ),
                    "executed_at": executed_at,
                    "lead_time_hours": lead_time,
                    "duplicate_delivery_count": duplicate_counts.get(
                        (action_id, platform_id), 0
                    ),
                    "evidence_record_ids": "|".join(evidence_record_ids),
                    "evidence_batches": "|".join(evidence_batches),
                    "as_of_batch": as_of_batch,
                }
            )
        return rows

    # ------------------------------------------------------------ 版本覆盖
    def _build_coverage(
        self,
        actions: list[dict],
        notices: list[dict],
        action_meta: dict[tuple[str, str], dict],
        dispositions: list[dict],
        as_of_batch: str,
    ) -> list[dict]:
        disp_index = {
            (row["action_id"], row["platform_id"]): row for row in dispositions
        }
        rows: list[dict] = []
        for action in sorted(
            actions, key=lambda r: (r["action_id"], int(r["revision"]))
        ):
            action_id = action["action_id"]
            revision = action["revision"]
            targets = sorted(
                {
                    row["platform_id"]
                    for row in notices
                    if row["action_id"] == action_id
                    and row["revision"] == revision
                }
            )
            states = [
                disp_index[(action_id, platform_id)]["disposition_state"]
                for platform_id in targets
                if (action_id, platform_id) in disp_index
            ]
            total = len(targets)
            covered = sum(1 for state in states if state in COVERED_DISPOSITIONS)
            pending_platforms = sorted(
                platform_id
                for platform_id in targets
                if (action_id, platform_id) in disp_index
                and disp_index[(action_id, platform_id)]["disposition_state"]
                in PENDING_DISPOSITIONS
            )
            count = lambda wanted: sum(1 for state in states if state == wanted)  # noqa: E731
            rows.append(
                {
                    "action_id": action_id,
                    "revision": revision,
                    "coordinator": action["coordinator"],
                    "scope_ref": action["scope_ref"],
                    "state": action["state"],
                    "opened_at": action["opened_at"],
                    "target_platform_count": total,
                    "covered_count": covered,
                    "pending_count": len(pending_platforms),
                    "executed_count": count(DISP_EXECUTED),
                    "evidence_needed_count": count(DISP_EVIDENCE_NEEDED),
                    "not_applicable_count": count("not_applicable"),
                    "under_review_count": count(DISP_UNDER_REVIEW),
                    "not_reached_count": count(DISP_NOT_REACHED),
                    "withdrawn_count": count(DISP_WITHDRAWN),
                    "coverage_ratio": (
                        f"{covered / total:.2%}" if total else "0.00%"
                    ),
                    "pending_platforms": "|".join(pending_platforms),
                    "as_of_batch": as_of_batch,
                }
            )
        return rows

    # ------------------------------------------------------------ 平台收件箱
    def _build_inbox(
        self,
        dispositions: list[dict],
        latest_notice: dict[tuple[str, str], dict],
        as_of_batch: str,
    ) -> list[dict]:
        open_issue = {
            DISP_NOT_REACHED: "通知已触达，等待平台核实反馈",
            DISP_UNDER_REVIEW: "平台核实中，等待处置回执",
            DISP_EVIDENCE_NEEDED: "回执需补证，等待平台补充材料",
            DISP_EXECUTED: "",
            DISP_WITHDRAWN: "平台已随版本调整退出本行动",
            "not_applicable": "平台核实无对应内容，不适用",
        }
        rows = []
        for row in sorted(
            dispositions, key=lambda r: (r["platform_id"], r["action_id"])
        ):
            notice = latest_notice[(row["action_id"], row["platform_id"])]
            rows.append(
                {
                    "platform_id": row["platform_id"],
                    "action_id": row["action_id"],
                    "latest_revision": row["latest_revision"],
                    "disposition_state": row["disposition_state"],
                    "disposition_label": row["disposition_label"],
                    "measure_code": row["notified_measure_code"],
                    "measure_label": notice["measure_label"],
                    "notified_at": notice["notified_at"],
                    "latest_received_at": row["latest_received_at"],
                    "open_issue": open_issue[row["disposition_state"]],
                    "evidence_record_ids": row["evidence_record_ids"],
                    "as_of_batch": as_of_batch,
                }
            )
        return rows

    # ------------------------------------------------------------ 相似对象关联
    def _build_fingerprints(self, findings: list[dict]) -> list[dict]:
        """仅按内容指纹建立"关联线索"，绝不合并平台本地对象。"""
        rows = []
        for row in sorted(
            findings,
            key=lambda r: (
                r["content_fingerprint"],
                r["action_id"],
                r["platform_id"],
                r["finding_id"],
            ),
        ):
            rows.append(
                {
                    "content_fingerprint": row["content_fingerprint"],
                    "action_id": row["action_id"],
                    "platform_id": row["platform_id"],
                    "finding_id": row["finding_id"],
                    "local_object_ref": row["local_object_ref"],
                    "match_state": row["match_state"],
                    "source_record_id": row["record_id"],
                }
            )
        return rows

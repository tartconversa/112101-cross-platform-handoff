"""Bronze 层：合成协同消息的原始落盘。

设计原则：
- 已接受的原始消息以 JSONL 不可变追加保存，保留来源文件、来源行号与投递批次；
- 同一 (来源文件, record_id) 的重复投递直接跳过，保证批次可安全重跑；
- 自然键已存在时，内容完全一致记为"重复投递"（不计作第二次独立处置），
  内容冲突则进入隔离区，等待人工裁决而不是静默覆盖；
- 结构性坏消息（缺列、空值、非法枚举、坏时间）进入隔离区，不中断整批摄入。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .domain import (
    ACTION_STATES,
    BRONZE_DIR,
    MATCH_STATES,
    NATURAL_KEYS,
    NULLABLE_COLUMNS,
    RECEIPT_STATES,
    REQUIRED_COLUMNS,
    SOURCES_DIR_NAME,
)
from .timeutil import parse_iso8601

NOTICE_STATES = frozenset({"delivered"})
INT_COLUMNS = {"revision", "action_revision"}
TIMESTAMP_COLUMNS = {"opened_at", "notified_at", "matched_at", "received_at"}
ENUM_COLUMNS = {
    "state": ACTION_STATES,
    "notice_state": NOTICE_STATES,
    "match_state": MATCH_STATES,
    "receipt_state": RECEIPT_STATES,
}
# 判定重复/冲突时不参与内容比较的投递信封元数据列。
# ingest_batch 属于投递批次信息：同一业务消息在新批次重投仍为重复投递。
DELIVERY_METADATA_COLUMNS = frozenset({"record_id", "ingest_batch"})


@dataclass
class QuarantinedMessage:
    source_file: str
    source_row: int
    record_id: str
    reason: str
    payload: dict[str, str]
    ingest_batch: str


@dataclass
class DuplicateDelivery:
    source_file: str
    record_id: str
    natural_key: dict[str, str]
    duplicate_of_record_id: str
    ingest_batch: str


@dataclass
class IngestResult:
    batch: str
    accepted: dict[str, int] = field(default_factory=dict)
    duplicate_deliveries: list[DuplicateDelivery] = field(default_factory=list)
    quarantined: list[QuarantinedMessage] = field(default_factory=list)
    skipped_rerun: int = 0

    @property
    def accepted_total(self) -> int:
        return sum(self.accepted.values())


def _canonical_payload(row: dict[str, str]) -> dict[str, str]:
    """剥离投递信封元数据后的业务内容，用于重复/冲突判定。

    同一业务消息在后续批次重投（record_id、ingest_batch 不同）时，
    只要业务内容一致即认定为重复投递，而不是新的独立处置。
    """
    return {
        key: value
        for key, value in sorted(row.items())
        if key not in DELIVERY_METADATA_COLUMNS
    }


def _natural_key(row: dict[str, str], source_file: str) -> dict[str, str]:
    return {key: row[key] for key in NATURAL_KEYS[source_file]}


def _validate_row(row: dict[str, str], source_file: str) -> str | None:
    """返回错误原因；None 表示通过结构校验。"""
    required = REQUIRED_COLUMNS[source_file]
    missing = [column for column in required if column not in row]
    if missing:
        return f"缺少列: {','.join(missing)}"
    for column in required:
        value = (row.get(column) or "").strip()
        if not value and column not in NULLABLE_COLUMNS:
            return f"必填列 {column} 为空"
        if column in INT_COLUMNS and value:
            try:
                int(value)
            except ValueError:
                return f"整数列 {column} 格式非法: {value!r}"
        if column in TIMESTAMP_COLUMNS and value:
            try:
                parse_iso8601(value)
            except ValueError:
                return f"时间列 {column} 格式非法: {value!r}"
        if column in ENUM_COLUMNS and value:
            allowed = ENUM_COLUMNS[column]
            if value not in allowed:
                return f"枚举列 {column} 取值非法: {value!r}（允许 {sorted(allowed)}）"
    return None


class BronzeStore:
    """Bronze 湖分区的读写入口。"""

    def __init__(self, lake_root: Path) -> None:
        self.lake_root = Path(lake_root)
        self.bronze_root = self.lake_root / BRONZE_DIR
        self.landing_root = self.bronze_root / "landing"
        self.duplicate_path = self.bronze_root / "duplicate_register.jsonl"
        self.quarantine_path = self.bronze_root / "quarantine.jsonl"
        self.manifest_path = self.lake_root / "manifest.json"

    # ------------------------------------------------------------ 基础读写
    def ensure_dirs(self) -> None:
        self.landing_root.mkdir(parents=True, exist_ok=True)

    def _append_jsonl(self, path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            stream.write("\n")

    def _landing_path(self, source_file: str) -> Path:
        return self.landing_root / f"{Path(source_file).stem}.jsonl"

    def load_landing(self, source_file: str) -> list[dict]:
        path = self._landing_path(source_file)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def load_duplicates(self) -> list[dict]:
        return self._load_jsonl(self.duplicate_path)

    def load_quarantine(self) -> list[dict]:
        return self._load_jsonl(self.quarantine_path)

    @staticmethod
    def _load_jsonl(path: Path) -> list[dict]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {"batches": [], "deliveries": {}}
        with self.manifest_path.open(encoding="utf-8") as stream:
            return json.load(stream)

    def _save_manifest(self, manifest: dict) -> None:
        self.lake_root.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)

    # ------------------------------------------------------------ 批次摄入
    def ingest_batch(
        self,
        project_root: Path,
        source_files: tuple[str, ...],
        batch: str,
    ) -> IngestResult:
        """摄入一个批次。批次名取自消息自身的 ingest_batch 列并做一致性检查。"""
        self.ensure_dirs()
        manifest = self.load_manifest()
        deliveries: dict[str, list[str]] = manifest.setdefault("deliveries", {})
        result = IngestResult(batch=batch)
        landed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for source_file in source_files:
            source_path = project_root / SOURCES_DIR_NAME / source_file
            result.accepted.setdefault(source_file, 0)
            delivered = set(deliveries.setdefault(source_file, []))
            landing = self.load_landing(source_file)
            key_index = {
                tuple(item["natural_key"][key] for key in NATURAL_KEYS[source_file]): item
                for item in landing
            }

            with source_path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                for source_row, row in enumerate(reader, start=2):
                    record_id = (row.get("record_id") or "").strip()
                    row_batch = (row.get("ingest_batch") or "").strip()

                    # 来源文件按批次持续投递：不属于当前批次的消息跳过，等待后续批次处理。
                    if row_batch and row_batch != batch:
                        continue

                    reason = _validate_row(row, source_file)
                    if reason is None and not row_batch:
                        reason = "批次标记缺失：ingest_batch 为空"
                    if reason is not None:
                        result.quarantined.append(
                            QuarantinedMessage(
                                source_file=source_file,
                                source_row=source_row,
                                record_id=record_id or f"<row {source_row}>",
                                reason=reason,
                                payload=dict(row),
                                ingest_batch=batch,
                            )
                        )
                        self._append_jsonl(
                            self.quarantine_path,
                            {
                                "ingest_batch": batch,
                                "landed_at": landed_at,
                                "source_file": source_file,
                                "source_row": source_row,
                                "record_id": record_id,
                                "reason": reason,
                                "payload": dict(row),
                            },
                        )
                        continue

                    if record_id in delivered:
                        # 同一投递的安全重跑：幂等跳过，不产生任何新记录。
                        result.skipped_rerun += 1
                        continue

                    natural_key = _natural_key(row, source_file)
                    key_tuple = tuple(natural_key[key] for key in NATURAL_KEYS[source_file])
                    existing = key_index.get(key_tuple)
                    if existing is not None:
                        if existing["payload"] == _canonical_payload(row):
                            dup = DuplicateDelivery(
                                source_file=source_file,
                                record_id=record_id,
                                natural_key=natural_key,
                                duplicate_of_record_id=existing["record_id"],
                                ingest_batch=batch,
                            )
                            result.duplicate_deliveries.append(dup)
                            self._append_jsonl(
                                self.duplicate_path,
                                {
                                    "ingest_batch": batch,
                                    "landed_at": landed_at,
                                    "source_file": source_file,
                                    "record_id": record_id,
                                    "natural_key": natural_key,
                                    "duplicate_of_record_id": dup.duplicate_of_record_id,
                                    "reason": "natural_key 已存在且内容一致，重复投递不计作独立处置",
                                },
                            )
                        else:
                            reason = "自然键冲突：同一自然键对应内容不同，隔离等待裁决"
                            result.quarantined.append(
                                QuarantinedMessage(
                                    source_file=source_file,
                                    source_row=source_row,
                                    record_id=record_id,
                                    reason=reason,
                                    payload=dict(row),
                                    ingest_batch=batch,
                                )
                            )
                            self._append_jsonl(
                                self.quarantine_path,
                                {
                                    "ingest_batch": batch,
                                    "landed_at": landed_at,
                                    "source_file": source_file,
                                    "source_row": source_row,
                                    "record_id": record_id,
                                    "reason": reason,
                                    "natural_key": natural_key,
                                    "payload": dict(row),
                                },
                            )
                        delivered.add(record_id)
                        continue

                    envelope = {
                        "record_id": record_id,
                        "ingest_batch": batch,
                        "landed_at": landed_at,
                        "source_file": source_file,
                        "source_row": source_row,
                        "natural_key": natural_key,
                        "payload": _canonical_payload(row),
                    }
                    self._append_jsonl(self._landing_path(source_file), envelope)
                    key_index[key_tuple] = envelope
                    delivered.add(record_id)
                    result.accepted[source_file] += 1

            deliveries[source_file] = sorted(delivered)

        manifest["batches"].append(
            {
                "batch": batch,
                "ran_at": landed_at,
                "accepted": result.accepted,
                "accepted_total": result.accepted_total,
                "duplicate_deliveries": len(result.duplicate_deliveries),
                "quarantined": len(result.quarantined),
                "skipped_rerun": result.skipped_rerun,
            }
        )
        self._save_manifest(manifest)
        return result

    def ingested_batches(self) -> list[str]:
        return [entry["batch"] for entry in self.load_manifest()["batches"]]

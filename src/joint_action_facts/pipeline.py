"""流水线编排：按批次持续摄入 -> Silver 重算 -> Gold 快照。

批次顺序来自来源消息自身的 ingest_batch 标记（字典序即时间序：B1..B6）。
每个批次结束后重算 Silver/Gold 并将 Gold 快照固化到
gold/snapshots/<batch>/，从而保留"任意历史时点看到的接续状态"。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .domain import (
    RECEIPT_SOURCE,
    SOURCES_DIR_NAME,
    SOURCE_FILES,
)
from .gold import GoldStore
from .ingest import BronzeStore
from .silver import SilverStore


@dataclass
class BatchOutcome:
    batch: str
    accepted_total: int
    duplicate_count: int
    quarantined_count: int
    skipped_rerun: int
    gold: GoldStore


def discover_batches(project_root: Path) -> list[str]:
    """扫描全部来源文件，按出现顺序收集批次名并排序。"""
    batches: set[str] = set()
    for source_file in SOURCE_FILES:
        path = project_root / SOURCES_DIR_NAME / source_file
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                batches.add(row["ingest_batch"].strip())
    return sorted(batches)


def _duplicate_counts_by_target(bronze: BronzeStore) -> dict[tuple[str, str], int]:
    """把重复投递登记折算到 (行动, 平台) 维度；重复不产生新处置。"""
    # 回执 finding -> (action, platform) 映射，借助 silver 已清洗表。
    silver = SilverStore(bronze.lake_root)
    findings = {row["finding_id"]: row for row in silver.findings()}
    counts: dict[tuple[str, str], int] = {}
    for entry in bronze.load_duplicates():
        if entry["source_file"] != RECEIPT_SOURCE:
            continue
        # 重复登记的 record_id 是被拒的重复投递，需按自然键找到先到的原始回执。
        target_receipt_id = entry["natural_key"]["receipt_id"]
        for landed in bronze.load_landing(RECEIPT_SOURCE):
            if landed["natural_key"]["receipt_id"] == target_receipt_id:
                finding_id = landed["payload"]["finding_id"]
                finding = findings.get(finding_id)
                if finding:
                    key = (finding["action_id"], finding["platform_id"])
                    counts[key] = counts.get(key, 0) + 1
                break
    return counts


class Pipeline:
    def __init__(self, project_root: Path, lake_root: Path) -> None:
        self.project_root = Path(project_root)
        self.lake_root = Path(lake_root)
        self.bronze = BronzeStore(self.lake_root)
        self.silver = SilverStore(self.lake_root)
        self.gold = GoldStore(self.lake_root)

    def run_batch(self, batch: str) -> BatchOutcome:
        result = self.bronze.ingest_batch(
            self.project_root, SOURCE_FILES, batch
        )
        self.silver.rebuild(self.bronze)
        duplicate_counts = _duplicate_counts_by_target(self.bronze)
        gold_result = self.gold.build(
            self.silver,
            as_of_batch=batch,
            duplicate_counts=duplicate_counts,
        )
        self._snapshot(batch)
        return BatchOutcome(
            batch=batch,
            accepted_total=result.accepted_total,
            duplicate_count=len(result.duplicate_deliveries),
            quarantined_count=len(result.quarantined),
            skipped_rerun=result.skipped_rerun,
            gold=self.gold,
        )

    def run_remaining(self) -> list[BatchOutcome]:
        """摄入全部尚未处理的批次；已完成批次自动跳过（幂等续跑）。"""
        done = set(self.bronze.ingested_batches())
        outcomes = []
        for batch in discover_batches(self.project_root):
            if batch in done:
                continue
            outcomes.append(self.run_batch(batch))
        return outcomes

    def run_all(self) -> list[BatchOutcome]:
        return [self.run_batch(batch) for batch in discover_batches(self.project_root)]

    def _snapshot(self, batch: str) -> None:
        snapshot_root = self.lake_root / "gold" / "snapshots" / batch
        snapshot_root.mkdir(parents=True, exist_ok=True)
        for name in (
            "platform_dispositions.csv",
            "action_coverage.csv",
            "platform_inbox.csv",
            "fingerprint_links.csv",
        ):
            source = self.lake_root / "gold" / name
            target = snapshot_root / name
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

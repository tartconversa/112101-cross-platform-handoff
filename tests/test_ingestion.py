from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401

from joint_action_facts.domain import (
    FINDING_SOURCE,
    RECEIPT_SOURCE,
    SOURCE_FILES,
)
from joint_action_facts.ingest import BronzeStore
from joint_action_facts.pipeline import Pipeline, discover_batches

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PipelineFixture:
    """在临时目录构建完整数据湖的测试夹具。"""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.lake_root = Path(self.tmp.name) / "lake"
        self.pipeline = Pipeline(PROJECT_ROOT, self.lake_root)

    def run_all(self) -> list:
        return self.pipeline.run_all()

    def close(self) -> None:
        self.tmp.cleanup()


class IngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PipelineFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_all_batches_ingested_in_order(self) -> None:
        self.fixture.run_all()
        self.assertEqual(
            self.fixture.pipeline.bronze.ingested_batches(),
            ["B1", "B2", "B3", "B4", "B5", "B6"],
        )

    def test_bronze_landing_is_immutable_and_complete(self) -> None:
        self.fixture.run_all()
        bronze = self.fixture.pipeline.bronze
        for source_file in SOURCE_FILES:
            with (PROJECT_ROOT / "sources" / source_file).open(
                encoding="utf-8", newline=""
            ) as stream:
                source_rows = list(csv.DictReader(stream))
            landed = bronze.load_landing(source_file)
            # 减去被识别为重复投递的那一条。
            duplicates = [
                entry
                for entry in bronze.load_duplicates()
                if entry["source_file"] == source_file
            ]
            self.assertEqual(len(landed), len(source_rows) - len(duplicates))
            for item in landed:
                # 原始信封必须保留血缘定位信息。
                self.assertTrue(item["record_id"])
                self.assertGreaterEqual(item["source_row"], 2)
                self.assertIn("landed_at", item)

    def test_duplicate_delivery_is_registered_not_double_counted(self) -> None:
        outcomes = self.fixture.run_all()
        b5 = next(outcome for outcome in outcomes if outcome.batch == "B5")
        self.assertEqual(b5.duplicate_count, 1)
        register = self.fixture.pipeline.bronze.load_duplicates()
        self.assertEqual(len(register), 1)
        entry = register[0]
        self.assertEqual(entry["record_id"], "receipts-12")
        self.assertEqual(entry["duplicate_of_record_id"], "receipts-07")
        # Silver 回执中 RC-9 只存在一条，重复投递未产生第二次独立处置。
        silver_receipts = self.fixture.pipeline.silver.receipts()
        rc9 = [row for row in silver_receipts if row["receipt_id"] == "RC-9"]
        self.assertEqual(len(rc9), 1)

    def test_ingest_is_idempotent_on_rerun(self) -> None:
        self.fixture.run_all()
        landing_counts_before = {
            source: len(self.fixture.pipeline.bronze.load_landing(source))
            for source in SOURCE_FILES
        }
        # 再跑一次全部批次：所有消息都应被幂等跳过。
        outcomes = self.fixture.pipeline.run_remaining()
        self.assertEqual(outcomes, [])
        landing_counts_after = {
            source: len(self.fixture.pipeline.bronze.load_landing(source))
            for source in SOURCE_FILES
        }
        self.assertEqual(landing_counts_before, landing_counts_after)

    def test_bad_message_is_quarantined_without_stopping_batch(self) -> None:
        # 构造一份含坏行的来源副本：非法枚举 + 缺失必填列。
        tmp_root = Path(self.fixture.tmp.name) / "project"
        shutil.copytree(PROJECT_ROOT / "sources", tmp_root / "sources")
        bad_path = tmp_root / "sources" / RECEIPT_SOURCE
        with bad_path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(
                "receipts-bad1,RC-X,F-21,2026-08-09T10:00:00Z,ACT-7,restrict,"
                "not_a_state,,B6\n"
            )
            stream.write(
                "receipts-bad2,,F-21,2026-08-09T11:00:00Z,ACT-7,restrict,"
                "accepted,,B6\n"
            )
        pipeline = Pipeline(tmp_root, self.fixture.lake_root / "bad")
        outcomes = pipeline.run_all()
        quarantined = pipeline.bronze.load_quarantine()
        bad = [
            entry
            for entry in quarantined
            if entry["record_id"].startswith("receipts-bad")
        ]
        self.assertEqual(len(bad), 2)
        # 同批合法消息仍然完成摄入。
        self.assertTrue(pipeline.bronze.load_landing(RECEIPT_SOURCE))


if __name__ == "__main__":
    unittest.main()

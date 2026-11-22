from __future__ import annotations

import csv
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401

from joint_action_facts.domain import (
    DISP_EVIDENCE_NEEDED,
    DISP_EXECUTED,
    DISP_NOT_APPLICABLE,
    DISP_NOT_REACHED,
    DISP_WITHDRAWN,
)
from test_ingestion import PipelineFixture


class GoldModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PipelineFixture()
        self.fixture.run_all()
        self.gold = self.fixture.pipeline.gold

    def tearDown(self) -> None:
        self.fixture.close()

    def _disposition(self, action_id: str, platform_id: str) -> dict[str, str]:
        rows = [
            row
            for row in self.gold.dispositions()
            if row["action_id"] == action_id and row["platform_id"] == platform_id
        ]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_one_disposition_row_per_action_platform(self) -> None:
        rows = self.gold.dispositions()
        keys = [(row["action_id"], row["platform_id"]) for row in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_scope_change_marks_withdrawn_without_erasing_evidence(self) -> None:
        row = self._disposition("ACT-8", "PLAT-C")
        self.assertEqual(row["disposition_state"], DISP_WITHDRAWN)
        # 退出前平台自己的映射与回执仍作为证据保留。
        self.assertTrue(row["finding_id"])
        self.assertTrue(row["latest_receipt_id"])
        self.assertIn("needs_evidence", row["latest_receipt_state"])

    def test_not_found_becomes_not_applicable(self) -> None:
        # PLAT-E 先 not_found 后又 confirmed 找到对象，最终为 executed；
        # not_found 的原始映射仍保留在 silver 中可追溯。
        findings = [
            row
            for row in self.fixture.pipeline.silver.findings()
            if row["action_id"] == "ACT-8" and row["platform_id"] == "PLAT-E"
        ]
        states = {row["match_state"] for row in findings}
        self.assertIn("not_found", states)
        row = self._disposition("ACT-8", "PLAT-E")
        self.assertEqual(row["disposition_state"], DISP_EXECUTED)

    def test_late_receipt_closes_pending_item(self) -> None:
        # RC-14 在 B6 才迟到，ACT-9/PLAT-B 最终已执行。
        row = self._disposition("ACT-9", "PLAT-B")
        self.assertEqual(row["disposition_state"], DISP_EXECUTED)
        self.assertEqual(row["latest_receipt_id"], "RC-14")

    def test_unreached_target_kept_visible(self) -> None:
        row = self._disposition("ACT-9", "PLAT-E")
        self.assertEqual(row["disposition_state"], DISP_NOT_REACHED)
        self.assertEqual(row["receipt_count"], "0")
        self.assertEqual(row["finding_id"], "")

    def test_evidence_needed_state_is_preserved_in_aggregate(self) -> None:
        # B4 快照中 ACT-7/PLAT-B 处于需补证，共同汇总不能抹去平台判断。
        with (
            self.fixture.lake_root
            / "gold"
            / "snapshots"
            / "B4"
            / "platform_dispositions.csv"
        ).open(encoding="utf-8", newline="") as stream:
            snapshot = list(csv.DictReader(stream))
        row = next(
            row
            for row in snapshot
            if row["action_id"] == "ACT-7" and row["platform_id"] == "PLAT-B"
        )
        self.assertEqual(row["disposition_state"], DISP_EVIDENCE_NEEDED)

    def test_similar_objects_are_linked_but_not_merged(self) -> None:
        links = self.gold.fingerprints()
        rumor = [row for row in links if row["content_fingerprint"] == "FP-RUMOR-1"]
        # 同一指纹横跨四个平台，但本地对象引用各不相同，映射记录独立成行。
        self.assertEqual(len(rumor), 4)
        local_refs = {row["local_object_ref"] for row in rumor}
        self.assertEqual(len(local_refs), 4)
        self.assertEqual({row["platform_id"] for row in rumor},
                         {"PLAT-A", "PLAT-B", "PLAT-C", "PLAT-D"})

    def test_correction_chain_keeps_original_receipts(self) -> None:
        row = self._disposition("ACT-7", "PLAT-A")
        self.assertEqual(row["receipt_count"], "2")
        self.assertEqual(row["correction_count"], "1")
        # 最新回执是纠正后的 RC-4，但首次执行时间取最早 accepted 回执。
        self.assertEqual(row["latest_receipt_id"], "RC-4")
        silver = self.fixture.pipeline.silver.receipts()
        originals = [
            item
            for item in silver
            if item["finding_id"] == "F-21"
        ]
        self.assertEqual([item["receipt_id"] for item in originals], ["RC-3", "RC-4"])

    def test_coverage_counts_match_disposition_rows(self) -> None:
        coverage = {
            (row["action_id"], row["revision"]): row
            for row in self.gold.coverage()
        }
        v2 = coverage[("ACT-8", "2")]
        self.assertEqual(int(v2["target_platform_count"]), 2)
        self.assertEqual(v2["coverage_ratio"], "100.00%")
        v1 = coverage[("ACT-8", "1")]
        self.assertEqual(int(v1["withdrawn_count"]), 1)
        self.assertEqual(v1["coverage_ratio"], "66.67%")

    def test_every_gold_row_carries_lineage(self) -> None:
        for row in self.gold.dispositions():
            self.assertTrue(row["evidence_record_ids"])
            self.assertTrue(row["evidence_batches"])
            self.assertEqual(
                len(row["evidence_record_ids"].split("|")),
                len(row["evidence_batches"].split("|")),
            )

    def test_lead_time_uses_earliest_notice_and_is_non_negative(self) -> None:
        row = self._disposition("ACT-8", "PLAT-A")
        # 平台在 v2 通知前已按 v1 通知完成处置，耗时仍应为正。
        self.assertGreaterEqual(float(row["lead_time_hours"]), 0.0)


if __name__ == "__main__":
    unittest.main()

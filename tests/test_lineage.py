from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401

from joint_action_facts.lineage import LineageExplorer
from test_ingestion import PipelineFixture


class LineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PipelineFixture()
        self.fixture.run_all()
        self.explorer = LineageExplorer(self.fixture.lake_root)

    def tearDown(self) -> None:
        self.fixture.close()

    def test_trace_returns_evidence_from_all_layers(self) -> None:
        nodes = self.explorer.trace_action_platform("ACT-8", "PLAT-C")
        layers = {node.layer for node in nodes}
        self.assertEqual(layers, {"silver", "bronze"})
        source_files = {node.source_file for node in nodes}
        # 行动版本、协同通知、对象映射、回执四类证据齐备。
        self.assertIn("actions.csv", source_files)
        self.assertIn("coordination_notices.csv", source_files)
        self.assertIn("platform_findings.csv", source_files)
        self.assertIn("receipts.csv", source_files)

    def test_trace_covers_revision_history(self) -> None:
        nodes = self.explorer.trace_action("ACT-8")
        record_ids = {node.record_id for node in nodes}
        # v1 与 v2 两个行动版本都可追溯。
        self.assertIn("actions-03", record_ids)
        self.assertIn("actions-04", record_ids)

    def test_bronze_envelope_points_back_to_source_row(self) -> None:
        nodes = self.explorer.trace_action_platform("ACT-9", "PLAT-D")
        bronze = [node for node in nodes if node.layer == "bronze"]
        self.assertTrue(bronze)
        for node in bronze:
            self.assertIn("来源行", node.summary)
            self.assertTrue(node.ingest_batch)


if __name__ == "__main__":
    unittest.main()

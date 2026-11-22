from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _bootstrap  # noqa: F401

from joint_action_facts.cli import build_parser
from test_ingestion import PipelineFixture, PROJECT_ROOT


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PipelineFixture()
        self.fixture.run_all()
        self.parser = build_parser()

    def tearDown(self) -> None:
        self.fixture.close()

    def _run(self, *argv: str) -> str:
        args = self.parser.parse_args(
            [
                "--project-root",
                str(PROJECT_ROOT),
                "--lake-root",
                str(self.fixture.lake_root),
                *argv,
            ]
        )
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = args.func(args)
        self.assertEqual(code, 0)
        return buffer.getvalue()

    def test_status_command_lists_actions_and_dispositions(self) -> None:
        output = self._run("status", "--action", "ACT-9")
        self.assertIn("ACT-9", output)
        self.assertIn("未触达", output)

    def test_inbox_command_filters_by_platform(self) -> None:
        output = self._run("inbox", "--platform", "PLAT-E")
        self.assertIn("PLAT-E", output)
        self.assertNotIn("PLAT-A", output)

    def test_lineage_command_prints_evidence_chain(self) -> None:
        output = self._run("lineage", "--action", "ACT-7", "--platform", "PLAT-A")
        self.assertIn("bronze", output)
        self.assertIn("silver", output)
        self.assertIn("RC-4", output)

    def test_report_command_writes_markdown(self) -> None:
        output = self._run("report")
        report_path = Path(output.split("：")[1].strip())
        self.assertTrue(report_path.exists())
        text = report_path.read_text(encoding="utf-8")
        self.assertIn("跨平台协同治理接续状态报告", text)
        self.assertIn("重复投递登记：1 条", text)

    def test_batches_command_reports_history(self) -> None:
        output = self._run("batches")
        for batch in ("B1", "B2", "B3", "B4", "B5", "B6"):
            self.assertIn(batch, output)


if __name__ == "__main__":
    unittest.main()

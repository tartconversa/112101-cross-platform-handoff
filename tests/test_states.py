from __future__ import annotations

import unittest
from pathlib import Path

import _bootstrap  # noqa: F401  # 将 src/ 加入 sys.path

from joint_action_facts.domain import (
    DISP_EVIDENCE_NEEDED,
    DISP_EXECUTED,
    DISP_NOT_APPLICABLE,
    DISP_NOT_REACHED,
    DISP_UNDER_REVIEW,
    DISP_WITHDRAWN,
)
from joint_action_facts.states import derive_disposition


class StateMachineTests(unittest.TestCase):
    def test_no_evidence_means_not_reached(self) -> None:
        # 牵头单位的统一安排本身不能证明平台已触达或执行。
        self.assertEqual(
            derive_disposition(match_state=None, receipt_state=None),
            DISP_NOT_REACHED,
        )

    def test_confirmed_without_receipt_stays_under_review(self) -> None:
        self.assertEqual(
            derive_disposition("confirmed", None), DISP_UNDER_REVIEW
        )

    def test_uncertain_without_receipt_stays_under_review(self) -> None:
        self.assertEqual(
            derive_disposition("uncertain", None), DISP_UNDER_REVIEW
        )

    def test_not_found_is_not_applicable(self) -> None:
        self.assertEqual(
            derive_disposition("not_found", None), DISP_NOT_APPLICABLE
        )

    def test_accepted_and_corrected_mean_executed(self) -> None:
        self.assertEqual(
            derive_disposition("confirmed", "accepted"), DISP_EXECUTED
        )
        self.assertEqual(
            derive_disposition("confirmed", "corrected"), DISP_EXECUTED
        )

    def test_needs_evidence_overrides_match(self) -> None:
        self.assertEqual(
            derive_disposition("confirmed", "needs_evidence"),
            DISP_EVIDENCE_NEEDED,
        )

    def test_withdrawn_is_a_scope_fact_not_a_platform_judgement(self) -> None:
        # 即使平台已经有回执，版本退出仍按范围事实标记。
        self.assertEqual(
            derive_disposition("confirmed", "accepted", withdrawn=True),
            DISP_WITHDRAWN,
        )


if __name__ == "__main__":
    unittest.main()

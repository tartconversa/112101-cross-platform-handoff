"""平台处置状态机：从平台自己的映射与回执推导处置状态。

推导只依据平台侧证据，绝不使用牵头单位的通知来替代平台判断。
"""

from __future__ import annotations

from .domain import (
    DISP_EVIDENCE_NEEDED,
    DISP_EXECUTED,
    DISP_NOT_APPLICABLE,
    DISP_NOT_REACHED,
    DISP_UNDER_REVIEW,
    DISP_WITHDRAWN,
    MATCH_CONFIRMED,
    MATCH_NOT_FOUND,
    MATCH_UNCERTAIN,
    RECEIPT_ACCEPTED,
    RECEIPT_CORRECTED,
    RECEIPT_NEEDS_EVIDENCE,
)


def derive_disposition(
    match_state: str | None,
    receipt_state: str | None,
    withdrawn: bool = False,
) -> str:
    """根据平台对象映射状态与最新回执状态推导处置状态。

    优先级（回执是平台对自身处置的最终表达）：
      1. 行动版本已将该平台移出范围 -> withdrawn（范围事实，非平台判断）
      2. 最新回执 needs_evidence -> evidence_needed（已触达但证据不足）
      3. 最新回执 accepted/corrected -> executed
      4. 无回执时按映射状态：
         not_found -> not_applicable（平台核实后确认本平台无对应内容）
         uncertain -> under_review（映射尚不确定，正在核实）
         confirmed -> under_review（已发现内容但尚无回执，处置在途）
         无映射   -> not_reached（通知已发，平台尚未反馈）
    """
    if withdrawn:
        return DISP_WITHDRAWN
    if receipt_state == RECEIPT_NEEDS_EVIDENCE:
        return DISP_EVIDENCE_NEEDED
    if receipt_state in (RECEIPT_ACCEPTED, RECEIPT_CORRECTED):
        return DISP_EXECUTED
    if match_state == MATCH_NOT_FOUND:
        return DISP_NOT_APPLICABLE
    if match_state in (MATCH_CONFIRMED, MATCH_UNCERTAIN):
        return DISP_UNDER_REVIEW
    return DISP_NOT_REACHED

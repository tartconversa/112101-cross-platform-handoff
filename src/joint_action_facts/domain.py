"""领域常量、状态码与处置状态判定。

状态模型严格区分两个层级：

1. 牵头单位的统一安排（行动版本 + 协同通知）只证明"该平台被要求做什么"，
   不能证明平台确实发现内容或执行措施。
2. 平台侧的对象映射（finding）与回执（receipt）才是平台自己的判断与证据。

五个平台处置状态覆盖业务要求，另设两个辅助状态表达范围事实：
not_reached（未触达）、under_review（正在核实）、not_applicable（不适用）、
executed（已执行）、evidence_needed（需补证）；
withdrawn（目标已随行动版本退出）仅用于表达范围变更，不计入待办。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 来源文件
SOURCES_DIR_NAME = "sources"
ACTION_SOURCE = "actions.csv"
NOTICE_SOURCE = "coordination_notices.csv"
FINDING_SOURCE = "platform_findings.csv"
RECEIPT_SOURCE = "receipts.csv"
SOURCE_FILES = (
    ACTION_SOURCE,
    NOTICE_SOURCE,
    FINDING_SOURCE,
    RECEIPT_SOURCE,
)

# ---------------------------------------------------------------- 湖区分层
BRONZE_DIR = "bronze"
SILVER_DIR = "silver"
GOLD_DIR = "gold"
REPORTS_DIR = "reports"
MANIFEST_FILE = "manifest.json"

# ---------------------------------------------------------------- 匹配状态
MATCH_CONFIRMED = "confirmed"
MATCH_UNCERTAIN = "uncertain"
MATCH_NOT_FOUND = "not_found"
MATCH_STATES = frozenset({MATCH_CONFIRMED, MATCH_UNCERTAIN, MATCH_NOT_FOUND})

# ---------------------------------------------------------------- 回执状态
RECEIPT_ACCEPTED = "accepted"
RECEIPT_CORRECTED = "corrected"
RECEIPT_NEEDS_EVIDENCE = "needs_evidence"
RECEIPT_STATES = frozenset(
    {RECEIPT_ACCEPTED, RECEIPT_CORRECTED, RECEIPT_NEEDS_EVIDENCE}
)

# ---------------------------------------------------------------- 行动状态
ACTION_ACTIVE = "active"
ACTION_AMENDED = "amended"
ACTION_STATES = frozenset({ACTION_ACTIVE, ACTION_AMENDED})

# ---------------------------------------------------------------- 平台处置状态
DISP_NOT_REACHED = "not_reached"
DISP_UNDER_REVIEW = "under_review"
DISP_NOT_APPLICABLE = "not_applicable"
DISP_EXECUTED = "executed"
DISP_EVIDENCE_NEEDED = "evidence_needed"
DISP_WITHDRAWN = "withdrawn"

DISPOSITION_LABELS = {
    DISP_NOT_REACHED: "未触达",
    DISP_UNDER_REVIEW: "正在核实",
    DISP_NOT_APPLICABLE: "不适用",
    DISP_EXECUTED: "已执行",
    DISP_EVIDENCE_NEEDED: "需补证",
    DISP_WITHDRAWN: "已退出",
}

# 覆盖口径：已产生平台侧实质判断的处置（不适用也是一种判断）。
COVERED_DISPOSITIONS = frozenset(
    {
        DISP_EXECUTED,
        DISP_EVIDENCE_NEEDED,
        DISP_NOT_APPLICABLE,
    }
)
# 待办口径：尚未形成终局判断的处置。
PENDING_DISPOSITIONS = frozenset(
    {DISP_NOT_REACHED, DISP_UNDER_REVIEW, DISP_EVIDENCE_NEEDED}
)

# ---------------------------------------------------------------- 各来源自然键
NATURAL_KEYS = {
    ACTION_SOURCE: ("action_id", "revision"),
    NOTICE_SOURCE: ("action_id", "revision", "platform_id"),
    FINDING_SOURCE: ("finding_id",),
    RECEIPT_SOURCE: ("receipt_id",),
}

REQUIRED_COLUMNS = {
    ACTION_SOURCE: (
        "record_id",
        "action_id",
        "revision",
        "opened_at",
        "scope_ref",
        "coordinator",
        "state",
        "change_note",
        "ingest_batch",
    ),
    NOTICE_SOURCE: (
        "record_id",
        "action_id",
        "revision",
        "platform_id",
        "measure_code",
        "measure_label",
        "notified_at",
        "notice_state",
        "ingest_batch",
    ),
    FINDING_SOURCE: (
        "record_id",
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
    ),
    RECEIPT_SOURCE: (
        "record_id",
        "receipt_id",
        "finding_id",
        "received_at",
        "action_code",
        "measure_code",
        "receipt_state",
        "correction_ref",
        "ingest_batch",
    ),
}

# 除 object 引用（not_found 允许为空）和 correction_ref 外，其余列不得为空。
NULLABLE_COLUMNS = frozenset({"local_object_ref", "correction_ref"})

"""跨平台协同治理数据湖。

分层：
- bronze：不可变原始协同消息（JSONL）+ 重复登记 + 隔离区
- silver：去重规范化的行动版本、协同通知、平台对象映射、回执
- gold：平台处置事实、行动版本覆盖快照、平台收件箱、相似对象关联线索
"""

from __future__ import annotations

from .domain import DISPOSITION_LABELS
from .pipeline import Pipeline
from .states import derive_disposition

__all__ = ["Pipeline", "derive_disposition", "DISPOSITION_LABELS"]

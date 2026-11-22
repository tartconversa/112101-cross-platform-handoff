"""带时区的 ISO 8601 时间工具（仅标准库）。"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_iso8601(value: str) -> datetime:
    """解析 ISO 8601 时间，无时区信息时按 UTC 处理；返回带时区的 datetime。"""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_iso8601(value: datetime | None) -> str:
    """统一输出为 UTC 的 ISO 8601（Z 后缀）。"""
    if value is None:
        return ""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lead_time_hours(start: datetime | None, end: datetime | None) -> str:
    """计算两个时间点之间的小时差，保留一位小数；缺值返回空串。"""
    if start is None or end is None:
        return ""
    return f"{(end - start).total_seconds() / 3600:.1f}"

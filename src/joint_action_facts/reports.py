"""人类可读报告：接续状态 Markdown 与平台收件箱视图。"""

from __future__ import annotations

from pathlib import Path

from .csvio import read_csv
from .domain import DISPOSITION_LABELS, GOLD_DIR, REPORTS_DIR


class ReportBuilder:
    def __init__(self, lake_root: Path) -> None:
        self.lake_root = Path(lake_root)
        self.report_root = self.lake_root / REPORTS_DIR

    def build_all(self) -> Path:
        self.report_root.mkdir(parents=True, exist_ok=True)
        coverage = read_csv(self.lake_root / GOLD_DIR / "action_coverage.csv")
        dispositions = read_csv(
            self.lake_root / GOLD_DIR / "platform_dispositions.csv"
        )
        inbox = read_csv(self.lake_root / GOLD_DIR / "platform_inbox.csv")
        fingerprints = read_csv(
            self.lake_root / GOLD_DIR / "fingerprint_links.csv"
        )
        quarantine = _load_jsonl_optional(
            self.lake_root / "bronze" / "quarantine.jsonl"
        )
        duplicates = _load_jsonl_optional(
            self.lake_root / "bronze" / "duplicate_register.jsonl"
        )
        as_of = coverage[-1]["as_of_batch"] if coverage else "-"

        lines: list[str] = []
        lines.append("# 跨平台协同治理接续状态报告")
        lines.append("")
        lines.append(f"- 数据时点（最新批次）：`{as_of}`")
        lines.append("- 处置状态仅来自各平台自己的映射与回执，牵头通知不替代平台判断")
        lines.append("")

        lines.append("## 1. 行动版本覆盖")
        lines.append("")
        lines.append(
            "| 行动 | 版本 | 牵头单位 | 目标平台数 | 已覆盖 | 待办 | 已执行 | 需补证 | 不适用 | 正在核实 | 未触达 | 已退出 | 覆盖率 | 待办平台 |"
        )
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in coverage:
            lines.append(
                "| {action_id} | v{revision} | {coordinator} | {target_platform_count} | "
                "{covered_count} | {pending_count} | {executed_count} | {evidence_needed_count} | "
                "{not_applicable_count} | {under_review_count} | {not_reached_count} | "
                "{withdrawn_count} | {coverage_ratio} | {pending_platforms} |".format(
                    action_id=row["action_id"],
                    revision=row["revision"],
                    coordinator=row["coordinator"],
                    target_platform_count=row["target_platform_count"],
                    covered_count=row["covered_count"],
                    pending_count=row["pending_count"],
                    executed_count=row["executed_count"],
                    evidence_needed_count=row["evidence_needed_count"],
                    not_applicable_count=row["not_applicable_count"],
                    under_review_count=row["under_review_count"],
                    not_reached_count=row["not_reached_count"],
                    withdrawn_count=row["withdrawn_count"],
                    coverage_ratio=row["coverage_ratio"],
                    pending_platforms=row["pending_platforms"] or "—",
                )
            )
        lines.append("")

        lines.append("## 2. 平台独立处置判断（每平台每行动一行）")
        lines.append("")
        lines.append(
            "| 行动 | 平台 | 处置状态 | 措施要求 | 映射 | 本地对象 | 匹配 | 最新回执 | 回执时间 | 回执数 | 纠正数 | 重复投递 | 执行耗时(小时) | 证据 record_id |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---|")
        for row in dispositions:
            lines.append(
                "| {action_id} | {platform_id} | {disposition_label} | "
                "{notified_measure_code} | {finding_id} | {local_object_ref} | "
                "{match_state} | {latest_receipt_id} | {latest_received_at} | "
                "{receipt_count} | {correction_count} | {duplicate_delivery_count} | "
                "{lead_time_hours} | {evidence_record_ids} |".format(
                    action_id=row["action_id"],
                    platform_id=row["platform_id"],
                    disposition_label=row["disposition_label"],
                    notified_measure_code=row["notified_measure_code"],
                    finding_id=row["finding_id"] or "—",
                    local_object_ref=row["local_object_ref"] or "—",
                    match_state=row["match_state"] or "—",
                    latest_receipt_id=row["latest_receipt_id"] or "—",
                    latest_received_at=row["latest_received_at"] or "—",
                    receipt_count=row["receipt_count"],
                    correction_count=row["correction_count"],
                    duplicate_delivery_count=row["duplicate_delivery_count"],
                    lead_time_hours=row["lead_time_hours"] or "—",
                    evidence_record_ids=row["evidence_record_ids"],
                )
            )
        lines.append("")

        lines.append("## 3. 平台收件箱（待办视图）")
        lines.append("")
        lines.append("| 平台 | 行动 | 状态 | 待办说明 | 通知措施 | 通知时间 | 最新回执时间 | 证据 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for row in inbox:
            lines.append(
                "| {platform_id} | {action_id} | {disposition_label} | "
                "{open_issue} | {measure_code}（{measure_label}） | "
                "{notified_at} | {latest_received_at} | {evidence_record_ids} |".format(
                    platform_id=row["platform_id"],
                    action_id=row["action_id"],
                    disposition_label=row["disposition_label"],
                    open_issue=row["open_issue"] or "—",
                    measure_code=row["measure_code"],
                    measure_label=row["measure_label"],
                    notified_at=row["notified_at"],
                    latest_received_at=row["latest_received_at"] or "—",
                    evidence_record_ids=row["evidence_record_ids"],
                )
            )
        lines.append("")

        lines.append("## 4. 外观相似内容的关联线索（仅关联，不合并对象）")
        lines.append("")
        lines.append("| 内容指纹 | 行动 | 平台 | 映射 | 本地对象 | 匹配状态 | 来源 record_id |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in fingerprints:
            lines.append(
                "| {fingerprint} | {action_id} | {platform_id} | {finding_id} | "
                "{local_object_ref} | {match_state} | {source_record_id} |".format(
                    fingerprint=row["content_fingerprint"],
                    action_id=row["action_id"],
                    platform_id=row["platform_id"],
                    finding_id=row["finding_id"],
                    local_object_ref=row["local_object_ref"] or "（空）",
                    match_state=row["match_state"],
                    source_record_id=row["source_record_id"],
                )
            )
        lines.append("")

        lines.append("## 5. 数据治理登记")
        lines.append("")
        lines.append(f"- 重复投递登记：{len(duplicates)} 条（不计作多次独立处置）")
        for entry in duplicates:
            lines.append(
                f"  - `{entry['record_id']}`（{entry['source_file']}，批次 {entry['ingest_batch']}）"
                f" 与 `{entry['duplicate_of_record_id']}` 自然键一致且内容相同"
            )
        lines.append(f"- 隔离区消息：{len(quarantine)} 条")
        for entry in quarantine:
            lines.append(
                f"  - `{entry['record_id']}`（{entry['source_file']} 行 {entry['source_row']}）：{entry['reason']}"
            )
        lines.append("")

        lines.append("## 状态码对照")
        lines.append("")
        for code, label in DISPOSITION_LABELS.items():
            lines.append(f"- `{code}` — {label}")
        lines.append("")

        report_path = self.report_root / "status_report.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path


def _load_jsonl_optional(path: Path) -> list[dict]:
    import json

    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]

"""命令行入口：本地运行数据湖的摄入、查询与血缘追溯。

用法示例：
    python -m joint_action_facts.cli ingest --batch B3
    python -m joint_action_facts.cli run-all
    python -m joint_action_facts.cli status
    python -m joint_action_facts.cli status --action ACT-7 --revision 2
    python -m joint_action_facts.cli inbox --platform PLAT-C
    python -m joint_action_facts.cli lineage --action ACT-8 --platform PLAT-C
    python -m joint_action_facts.cli report
    python -m joint_action_facts.cli batches
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .csvio import read_csv
from .domain import DISPOSITION_LABELS, GOLD_DIR, SOURCE_FILES
from .lineage import LineageExplorer
from .pipeline import Pipeline, discover_batches
from .reports import ReportBuilder

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAKE_ROOT = DEFAULT_PROJECT_ROOT / "lake"


def _print_table(rows: list[dict[str, str]], columns: list[str]) -> None:
    if not rows:
        print("（无记录）")
        return
    widths = {
        column: max(
            [len(column)] + [len(str(row.get(column, ""))) for row in rows]
        )
        for column in columns
    }
    header = " | ".join(column.ljust(widths[column]) for column in columns)
    print(header)
    print("-+-".join("-" * widths[column] for column in columns))
    for row in rows:
        print(
            " | ".join(
                str(row.get(column, "")).ljust(widths[column]) for column in columns
            )
        )


def _pipeline(args: argparse.Namespace) -> Pipeline:
    return Pipeline(
        project_root=Path(args.project_root),
        lake_root=Path(args.lake_root),
    )


def cmd_ingest(args: argparse.Namespace) -> int:
    pipeline = _pipeline(args)
    available = discover_batches(Path(args.project_root))
    if args.batch not in available:
        print(f"批次 {args.batch} 不存在；来源中的批次：{', '.join(available)}")
        return 2
    done = pipeline.bronze.ingested_batches()
    if args.batch in done:
        print(f"批次 {args.batch} 已摄入，幂等跳过（如需重算请使用 rebuild）。")
        return 0
    outcome = pipeline.run_batch(args.batch)
    print(
        f"批次 {outcome.batch} 完成：接受 {outcome.accepted_total} 条，"
        f"重复投递 {outcome.duplicate_count} 条，"
        f"隔离 {outcome.quarantined_count} 条。"
    )
    return 0


def cmd_run_all(args: argparse.Namespace) -> int:
    pipeline = _pipeline(args)
    outcomes = pipeline.run_remaining()
    if not outcomes:
        print("没有新的批次（全部批次已摄入）。")
        return 0
    for outcome in outcomes:
        print(
            f"批次 {outcome.batch}：接受 {outcome.accepted_total} 条，"
            f"重复投递 {outcome.duplicate_count} 条，"
            f"隔离 {outcome.quarantined_count} 条。"
        )
    report_path = ReportBuilder(Path(args.lake_root)).build_all()
    print(f"\n报告已生成：{report_path}")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    pipeline = _pipeline(args)
    pipeline.silver.rebuild(pipeline.bronze)
    from .pipeline import _duplicate_counts_by_target

    latest = pipeline.bronze.ingested_batches()[-1]
    pipeline.gold.build(
        pipeline.silver,
        as_of_batch=latest,
        duplicate_counts=_duplicate_counts_by_target(pipeline.bronze),
    )
    print(f"Silver/Gold 已基于 Bronze 全量重算（时点 {latest}）。")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    lake_root = Path(args.lake_root)
    coverage = read_csv(lake_root / GOLD_DIR / "action_coverage.csv")
    if not coverage:
        print("湖为空，请先运行 run-all。")
        return 1
    if args.action:
        coverage = [row for row in coverage if row["action_id"] == args.action]
    if args.revision is not None:
        coverage = [row for row in coverage if row["revision"] == str(args.revision)]
    columns = [
        "action_id",
        "revision",
        "coordinator",
        "target_platform_count",
        "covered_count",
        "pending_count",
        "executed_count",
        "evidence_needed_count",
        "not_applicable_count",
        "under_review_count",
        "not_reached_count",
        "withdrawn_count",
        "coverage_ratio",
        "pending_platforms",
        "as_of_batch",
    ]
    _print_table(coverage, columns)

    dispositions = read_csv(lake_root / GOLD_DIR / "platform_dispositions.csv")
    if args.action:
        dispositions = [
            row for row in dispositions if row["action_id"] == args.action
        ]
    print("\n平台处置明细：")
    _print_table(
        dispositions,
        [
            "action_id",
            "platform_id",
            "disposition_state",
            "disposition_label",
            "finding_id",
            "latest_receipt_id",
            "executed_at",
            "duplicate_delivery_count",
        ],
    )
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    lake_root = Path(args.lake_root)
    rows = read_csv(lake_root / GOLD_DIR / "platform_inbox.csv")
    if args.platform:
        rows = [row for row in rows if row["platform_id"] == args.platform]
    _print_table(
        rows,
        [
            "platform_id",
            "action_id",
            "latest_revision",
            "disposition_label",
            "measure_code",
            "notified_at",
            "latest_received_at",
            "open_issue",
        ],
    )
    return 0


def cmd_lineage(args: argparse.Namespace) -> int:
    explorer = LineageExplorer(Path(args.lake_root))
    if args.platform:
        nodes = explorer.trace_action_platform(args.action, args.platform)
    else:
        nodes = explorer.trace_action(args.action)
    if not nodes:
        print(f"未找到 {args.action} 的证据。")
        return 1
    for node in nodes:
        print(
            f"[{node.layer}] {node.source_file} :: {node.record_id}"
            f"（批次 {node.ingest_batch}）"
        )
        print(f"    {node.summary}")
    return 0


def cmd_batches(args: argparse.Namespace) -> int:
    pipeline = _pipeline(args)
    import json

    manifest = pipeline.bronze.load_manifest()
    available = discover_batches(Path(args.project_root))
    print(f"来源批次：{', '.join(available)}")
    print(f"已摄入批次：{', '.join(pipeline.bronze.ingested_batches()) or '（无）'}")
    for entry in manifest.get("batches", []):
        print(
            f"  {entry['batch']} @ {entry['ran_at']}：接受 {entry['accepted_total']}，"
            f"重复 {entry['duplicate_deliveries']}，隔离 {entry['quarantined']}，"
            f"重跑跳过 {entry['skipped_rerun']}"
        )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    path = ReportBuilder(Path(args.lake_root)).build_all()
    print(f"报告已生成：{path}")
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    print("来源文件：")
    for name in SOURCE_FILES:
        path = Path(args.project_root) / "sources" / name
        rows = read_csv(path)
        print(f"  {name}: {len(rows)} 条记录")
    print("\n处置状态码：")
    for code, label in DISPOSITION_LABELS.items():
        print(f"  {code}: {label}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="joint_action_facts",
        description="跨平台协同治理数据湖（纯标准库，本地运行）",
    )
    parser.add_argument("--project-root", default=str(DEFAULT_PROJECT_ROOT))
    parser.add_argument("--lake-root", default=str(DEFAULT_LAKE_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="摄入单个批次")
    p_ingest.add_argument("--batch", required=True)
    p_ingest.set_defaults(func=cmd_ingest)

    p_all = sub.add_parser("run-all", help="按顺序摄入全部尚未处理的批次并生成报告")
    p_all.set_defaults(func=cmd_run_all)

    p_rebuild = sub.add_parser("rebuild", help="基于 Bronze 全量重算 Silver/Gold")
    p_rebuild.set_defaults(func=cmd_rebuild)

    p_status = sub.add_parser("status", help="查看行动版本覆盖与平台处置")
    p_status.add_argument("--action")
    p_status.add_argument("--revision", type=int)
    p_status.set_defaults(func=cmd_status)

    p_inbox = sub.add_parser("inbox", help="查看平台收件箱/待办")
    p_inbox.add_argument("--platform")
    p_inbox.set_defaults(func=cmd_inbox)

    p_lineage = sub.add_parser("lineage", help="追溯汇总结果的各方证据")
    p_lineage.add_argument("--action", required=True)
    p_lineage.add_argument("--platform")
    p_lineage.set_defaults(func=cmd_lineage)

    p_batches = sub.add_parser("batches", help="查看批次摄入历史")
    p_batches.set_defaults(func=cmd_batches)

    p_report = sub.add_parser("report", help="生成 Markdown 接续状态报告")
    p_report.set_defaults(func=cmd_report)

    p_sources = sub.add_parser("sources", help="列出来源文件与状态码对照")
    p_sources.set_defaults(func=cmd_sources)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

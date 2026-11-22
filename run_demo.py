#!/usr/bin/env python3
"""端到端演示：从零构建数据湖并打印接续状态。

运行：
    python run_demo.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from joint_action_facts.cli import build_parser  # noqa: E402


def main() -> int:
    lake_root = ROOT / "lake"
    if lake_root.exists():
        shutil.rmtree(lake_root)

    parser = build_parser()
    base = ["--project-root", str(ROOT), "--lake-root", str(lake_root)]

    print("=" * 72)
    print("步骤 1：按批次持续摄入合成协同消息（B1 -> B6）")
    print("=" * 72)
    args = parser.parse_args(base + ["run-all"])
    args.func(args)

    print("\n" + "=" * 72)
    print("步骤 2：查看 ACT-8 的版本覆盖与平台独立处置（含范围退出）")
    print("=" * 72)
    args = parser.parse_args(base + ["status", "--action", "ACT-8"])
    args.func(args)

    print("\n" + "=" * 72)
    print("步骤 3：平台 PLAT-E 的收件箱（含未触达待办）")
    print("=" * 72)
    args = parser.parse_args(base + ["inbox", "--platform", "PLAT-E"])
    args.func(args)

    print("\n" + "=" * 72)
    print("步骤 4：追溯 ACT-8/PLAT-C 汇总结果的各方证据")
    print("=" * 72)
    args = parser.parse_args(
        base + ["lineage", "--action", "ACT-8", "--platform", "PLAT-C"]
    )
    args.func(args)

    print("\n" + "=" * 72)
    print("步骤 5：批次历史与数据治理登记")
    print("=" * 72)
    args = parser.parse_args(base + ["batches"])
    args.func(args)

    print(f"\nMarkdown 报告：{lake_root / 'reports' / 'status_report.md'}")
    print(f"历史快照目录：{lake_root / 'gold' / 'snapshots'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

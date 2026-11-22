"""证据血缘追溯：从 Gold 汇总行逐级回溯到 Bronze 原始消息。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .domain import (
    ACTION_SOURCE,
    FINDING_SOURCE,
    NOTICE_SOURCE,
    RECEIPT_SOURCE,
)
from .ingest import BronzeStore
from .silver import SilverStore


@dataclass
class EvidenceNode:
    layer: str
    source_file: str
    record_id: str
    ingest_batch: str
    summary: str


class LineageExplorer:
    def __init__(self, lake_root: Path) -> None:
        self.bronze = BronzeStore(Path(lake_root))
        self.silver = SilverStore(Path(lake_root))

    def trace_action_platform(
        self, action_id: str, platform_id: str
    ) -> list[EvidenceNode]:
        """返回支撑某个 (行动, 平台) 处置判断的全部证据节点，按层级排序。"""
        nodes: list[EvidenceNode] = []

        for row in self.silver.actions():
            if row["action_id"] == action_id:
                nodes.append(
                    EvidenceNode(
                        layer="silver",
                        source_file=ACTION_SOURCE,
                        record_id=row["record_id"],
                        ingest_batch=row["ingest_batch"],
                        summary=(
                            f"行动版本 v{row['revision']}（{row['state']}，"
                            f"范围 {row['scope_ref']}，牵头 {row['coordinator']}）：{row['change_note']}"
                        ),
                    )
                )

        for row in self.silver.notices():
            if row["action_id"] == action_id and row["platform_id"] == platform_id:
                nodes.append(
                    EvidenceNode(
                        layer="silver",
                        source_file=NOTICE_SOURCE,
                        record_id=row["record_id"],
                        ingest_batch=row["ingest_batch"],
                        summary=(
                            f"v{row['revision']} 协同通知：要求措施 {row['measure_code']}"
                            f"（{row['measure_label']}），通知时间 {row['notified_at']}"
                        ),
                    )
                )

        findings = [
            row
            for row in self.silver.findings()
            if row["action_id"] == action_id and row["platform_id"] == platform_id
        ]
        finding_ids = {row["finding_id"] for row in findings}
        for row in findings:
            nodes.append(
                EvidenceNode(
                    layer="silver",
                    source_file=FINDING_SOURCE,
                    record_id=row["record_id"],
                    ingest_batch=row["ingest_batch"],
                    summary=(
                        f"平台对象映射 {row['finding_id']}：本地对象 "
                        f"{row['local_object_ref'] or '（无）'}，匹配状态 {row['match_state']}，"
                        f"指纹 {row['content_fingerprint']}，映射时间 {row['matched_at']}"
                    ),
                )
            )

        for row in self.silver.receipts():
            if row["finding_id"] in finding_ids:
                correction = f"，纠正引用 {row['correction_ref']}" if row["correction_ref"] else ""
                nodes.append(
                    EvidenceNode(
                        layer="silver",
                        source_file=RECEIPT_SOURCE,
                        record_id=row["record_id"],
                        ingest_batch=row["ingest_batch"],
                        summary=(
                            f"平台回执 {row['receipt_id']}：状态 {row['receipt_state']}，"
                            f"措施 {row['measure_code']}，接收时间 {row['received_at']}{correction}"
                        ),
                    )
                )

        # Bronze 原始信封（含来源行号、落地时间），证明 Silver/Gold 结论可回溯到原始消息。
        silver_ids = {node.record_id for node in nodes}
        for source_file in (
            ACTION_SOURCE,
            NOTICE_SOURCE,
            FINDING_SOURCE,
            RECEIPT_SOURCE,
        ):
            for envelope in self.bronze.load_landing(source_file):
                if envelope["record_id"] in silver_ids:
                    nodes.append(
                        EvidenceNode(
                            layer="bronze",
                            source_file=source_file,
                            record_id=envelope["record_id"],
                            ingest_batch=envelope["ingest_batch"],
                            summary=(
                                f"原始消息信封：来源行 {envelope['source_row']}，"
                                f"落地时间 {envelope['landed_at']}"
                            ),
                        )
                    )
        return nodes

    def trace_action(self, action_id: str) -> list[EvidenceNode]:
        platforms = sorted(
            {
                row["platform_id"]
                for row in self.silver.notices()
                if row["action_id"] == action_id
            }
        )
        nodes: list[EvidenceNode] = []
        for platform_id in platforms:
            nodes.extend(self.trace_action_platform(action_id, platform_id))
        return nodes

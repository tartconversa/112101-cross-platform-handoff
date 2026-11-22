# 跨平台协同治理接续状态报告

- 数据时点（最新批次）：`B6`
- 处置状态仅来自各平台自己的映射与回执，牵头通知不替代平台判断

## 1. 行动版本覆盖

| 行动 | 版本 | 牵头单位 | 目标平台数 | 已覆盖 | 待办 | 已执行 | 需补证 | 不适用 | 正在核实 | 未触达 | 已退出 | 覆盖率 | 待办平台 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ACT-7 | v1 | UNIT-1 | 3 | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 100.00% | — |
| ACT-7 | v2 | UNIT-1 | 4 | 4 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 100.00% | — |
| ACT-8 | v1 | UNIT-2 | 3 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 1 | 66.67% | — |
| ACT-8 | v2 | UNIT-2 | 2 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 100.00% | — |
| ACT-9 | v1 | UNIT-1 | 3 | 2 | 1 | 2 | 0 | 0 | 0 | 1 | 0 | 66.67% | PLAT-E |

## 2. 平台独立处置判断（每平台每行动一行）

| 行动 | 平台 | 处置状态 | 措施要求 | 映射 | 本地对象 | 匹配 | 最新回执 | 回执时间 | 回执数 | 纠正数 | 重复投递 | 执行耗时(小时) | 证据 record_id |
|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---|
| ACT-7 | PLAT-A | 已执行 | restrict | F-21 | OBJ-51 | confirmed | RC-4 | 2026-08-03T08:00:00Z | 2 | 1 | 0 | 29.0 | notices-04|platform_findings-01|receipts-01|receipts-02 |
| ACT-7 | PLAT-B | 已执行 | restrict | F-22 | OBJ-93 | confirmed | RC-12 | 2026-08-08T10:00:00Z | 2 | 0 | 0 | 169.0 | notices-05|platform_findings-02|receipts-03|receipts-10 |
| ACT-7 | PLAT-C | 已执行 | restrict | F-24 | OBJ-77 | confirmed | RC-7 | 2026-08-04T18:00:00Z | 1 | 0 | 0 | 55.0 | notices-06|platform_findings-04|receipts-05 |
| ACT-7 | PLAT-D | 已执行 | restrict | F-23 | OBJ-104 | confirmed | RC-6 | 2026-08-04T16:00:00Z | 1 | 0 | 0 | 79.0 | notices-07|platform_findings-03|receipts-04 |
| ACT-8 | PLAT-A | 已执行 | takedown | F-25 | OBJ-31 | confirmed | RC-8 | 2026-08-05T10:00:00Z | 1 | 0 | 0 | 45.0 | notices-11|platform_findings-05|receipts-06 |
| ACT-8 | PLAT-C | 已退出 | takedown | F-29 | OBJ-41 | uncertain | RC-11 | 2026-08-07T09:00:00Z | 1 | 0 | 1 | — | notices-09|platform_findings-09|receipts-09 |
| ACT-8 | PLAT-E | 已执行 | takedown | F-28 | OBJ-58 | confirmed | RC-10 | 2026-08-06T15:00:00Z | 1 | 0 | 0 | 74.0 | notices-12|platform_findings-08|receipts-08 |
| ACT-9 | PLAT-B | 已执行 | restrict | F-31 | OBJ-82 | confirmed | RC-14 | 2026-08-15T09:00:00Z | 1 | 0 | 0 | 190.0 | notices-13|platform_findings-11|receipts-13 |
| ACT-9 | PLAT-D | 已执行 | restrict | F-30 | OBJ-66 | confirmed | RC-13 | 2026-08-09T11:00:00Z | 1 | 0 | 0 | 48.0 | notices-14|platform_findings-10|receipts-11 |
| ACT-9 | PLAT-E | 未触达 | restrict | — | — | — | — | — | 0 | 0 | 0 | — | notices-15 |

## 3. 平台收件箱（待办视图）

| 平台 | 行动 | 状态 | 待办说明 | 通知措施 | 通知时间 | 最新回执时间 | 证据 |
|---|---|---|---|---|---|---|---|
| PLAT-A | ACT-7 | 已执行 | — | restrict（限流） | 2026-08-02T11:00:00Z | 2026-08-03T08:00:00Z | notices-04|platform_findings-01|receipts-01|receipts-02 |
| PLAT-A | ACT-8 | 已执行 | — | takedown（下架） | 2026-08-06T10:00:00Z | 2026-08-05T10:00:00Z | notices-11|platform_findings-05|receipts-06 |
| PLAT-B | ACT-7 | 已执行 | — | restrict（限流） | 2026-08-02T11:00:00Z | 2026-08-08T10:00:00Z | notices-05|platform_findings-02|receipts-03|receipts-10 |
| PLAT-B | ACT-9 | 已执行 | — | restrict（限流） | 2026-08-07T11:00:00Z | 2026-08-15T09:00:00Z | notices-13|platform_findings-11|receipts-13 |
| PLAT-C | ACT-7 | 已执行 | — | restrict（限流） | 2026-08-02T11:00:00Z | 2026-08-04T18:00:00Z | notices-06|platform_findings-04|receipts-05 |
| PLAT-C | ACT-8 | 已退出 | 平台已随版本调整退出本行动 | takedown（下架） | 2026-08-03T13:00:00Z | 2026-08-07T09:00:00Z | notices-09|platform_findings-09|receipts-09 |
| PLAT-D | ACT-7 | 已执行 | — | restrict（限流） | 2026-08-02T11:00:00Z | 2026-08-04T16:00:00Z | notices-07|platform_findings-03|receipts-04 |
| PLAT-D | ACT-9 | 已执行 | — | restrict（限流） | 2026-08-07T11:00:00Z | 2026-08-09T11:00:00Z | notices-14|platform_findings-10|receipts-11 |
| PLAT-E | ACT-8 | 已执行 | — | takedown（下架） | 2026-08-06T10:00:00Z | 2026-08-06T15:00:00Z | notices-12|platform_findings-08|receipts-08 |
| PLAT-E | ACT-9 | 未触达 | 通知已触达，等待平台核实反馈 | restrict（限流） | 2026-08-07T11:00:00Z | — | notices-15 |

## 4. 外观相似内容的关联线索（仅关联，不合并对象）

| 内容指纹 | 行动 | 平台 | 映射 | 本地对象 | 匹配状态 | 来源 record_id |
|---|---|---|---|---|---|---|
| FP-IMPERSONATION-2 | ACT-8 | PLAT-A | F-25 | OBJ-31 | confirmed | platform_findings-05 |
| FP-IMPERSONATION-2 | ACT-8 | PLAT-C | F-26 | OBJ-40 | confirmed | platform_findings-06 |
| FP-IMPERSONATION-2 | ACT-8 | PLAT-C | F-29 | OBJ-41 | uncertain | platform_findings-09 |
| FP-IMPERSONATION-2 | ACT-8 | PLAT-E | F-27 | （空） | not_found | platform_findings-07 |
| FP-IMPERSONATION-2 | ACT-8 | PLAT-E | F-28 | OBJ-58 | confirmed | platform_findings-08 |
| FP-REDIR-3 | ACT-9 | PLAT-B | F-31 | OBJ-82 | confirmed | platform_findings-11 |
| FP-REDIR-3 | ACT-9 | PLAT-D | F-30 | OBJ-66 | confirmed | platform_findings-10 |
| FP-RUMOR-1 | ACT-7 | PLAT-A | F-21 | OBJ-51 | confirmed | platform_findings-01 |
| FP-RUMOR-1 | ACT-7 | PLAT-B | F-22 | OBJ-93 | confirmed | platform_findings-02 |
| FP-RUMOR-1 | ACT-7 | PLAT-C | F-24 | OBJ-77 | confirmed | platform_findings-04 |
| FP-RUMOR-1 | ACT-7 | PLAT-D | F-23 | OBJ-104 | confirmed | platform_findings-03 |

## 5. 数据治理登记

- 重复投递登记：1 条（不计作多次独立处置）
  - `receipts-12`（receipts.csv，批次 B5） 与 `receipts-07` 自然键一致且内容相同
- 隔离区消息：0 条

## 状态码对照

- `not_reached` — 未触达
- `under_review` — 正在核实
- `not_applicable` — 不适用
- `executed` — 已执行
- `evidence_needed` — 需补证
- `withdrawn` — 已退出

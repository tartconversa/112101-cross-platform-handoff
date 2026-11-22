# 协同治理行动数据湖（joint_action_facts）

面向"多家平台 + 牵头治理单位"共同处理跨平台网络治理事项的本地数据湖。
项目仅使用 **Python 标准库**，无需网络、无需安装第三方包，用合成数据完整演示：
统一行动的共同范围如何与每个平台的独立处置判断分开管理、修订如何持续投递、
汇总结果如何追溯到各方原始证据。

## 业务口径（建模原则）

1. **统一安排 ≠ 平台执行**。牵头单位的行动版本与协同通知只证明"某平台被要求做什么"，
   不能证明该平台发现了内容或执行了措施；平台处置状态只由平台自己的对象映射与回执推导。
2. **相似 ≠ 同一**。跨平台外观相似的内容只通过 `content_fingerprint` 建立关联线索，
   各平台本地对象（`local_object_ref`）与映射记录始终独立，绝不合并。
3. **原始状态全部保留**。每次范围变更、每条回执（含纠正前状态、迟到回执）都不可变落盘；
   回执纠正链（`accepted` → `corrected`）保留全部历史，不覆盖原始记录。
4. **重复投递不计作多次处置**。同一业务消息（自然键相同、业务内容一致）在后续批次重投时
   进入重复登记，Silver/Gold 中每个 (行动, 平台) 始终只有一条处置事实。
5. **共同汇总不抹除平台判断**。Gold 表每个平台独立成行，可按行动版本查看覆盖、待办、
   执行时间与尚未确认的关联，并沿证据链回溯到 Bronze 原始消息。

### 平台处置状态机

| 状态码 | 中文 | 含义 | 推导依据 |
|---|---|---|---|
| `not_reached` | 未触达 | 通知已发，平台尚无任何映射反馈 | 无平台证据 |
| `under_review` | 正在核实 | 已建立映射（confirmed/uncertain），尚无回执 | 平台映射 |
| `not_applicable` | 不适用 | 平台核实后确认本平台无对应内容 | 映射 `not_found` |
| `executed` | 已执行 | 平台回执 accepted/corrected | 平台回执 |
| `evidence_needed` | 需补证 | 平台回执要求补充证据 | 回执 `needs_evidence` |
| `withdrawn` | 已退出（辅助） | 平台随行动版本调整退出范围，属范围事实而非平台判断 | 版本对比 |

## 合成来源（`sources/`，UTF-8 CSV，ISO 8601 时间）

| 文件 | 角色 | 自然键 |
|---|---|---|
| `actions.csv` | 牵头单位的行动版本（含范围调整 `amended`） | `(action_id, revision)` |
| `coordination_notices.csv` | 牵头单位 → 平台的协同通知（统一安排与措施要求） | `(action_id, revision, platform_id)` |
| `platform_findings.csv` | 平台对象映射（本地对象、指纹、匹配状态） | `finding_id` |
| `receipts.csv` | 平台回执（接受/纠正/需补证、纠正引用、重复投递） | `receipt_id` |

行内 `ingest_batch`（B1–B6）标记消息应在哪个批次投递。合成剧情覆盖：
范围调整新增/退出平台、迟到回执（B6）、回执纠正链、重复投递（`receipts-12` 重发 `RC-9`）、
不适用（先 `not_found` 后找到）、需补证、未触达。

## 数据湖分层（运行后生成于 `lake/`）

```
lake/
├── manifest.json                     # 批次摄入历史（幂等依据）
├── bronze/
│   ├── landing/<source>.jsonl        # 不可变原始消息信封（含来源行号、落地时间、自然键）
│   ├── duplicate_register.jsonl      # 重复投递登记
│   └── quarantine.jsonl              # 结构性坏消息 / 自然键冲突隔离区
├── silver/                           # 去重规范化 + 参照完整性检查（可随时全量重算）
│   ├── action_versions.csv
│   ├── coordination_notices.csv
│   ├── platform_findings.csv
│   ├── receipts.csv                  # 回执原始行全部保留
│   └── referential_quarantine.jsonl
├── gold/
│   ├── platform_dispositions.csv     # 处置事实：每 (行动, 平台) 一行 + 证据血缘列
│   ├── action_coverage.csv           # 按行动版本的覆盖/待办/各状态计数
│   ├── platform_inbox.csv            # 平台收件箱（待办视图）
│   ├── fingerprint_links.csv         # 相似内容关联线索（不合并对象）
│   └── snapshots/<batch>/            # 每个批次结束时的 Gold 快照（接续状态可回放）
└── reports/
    └── status_report.md              # 中文接续状态报告
```

## 运行

需要 Python 3.10+（开发环境为 3.14）。

```bash
# 一键端到端演示（清空并重建 lake/，逐批摄入并打印各视图）
python run_demo.py

# 或使用 CLI
PYTHONPATH=src python -m joint_action_facts.cli run-all           # 逐批摄入全部来源并出报告
PYTHONPATH=src python -m joint_action_facts.cli ingest --batch B3 # 只摄入单个批次
PYTHONPATH=src python -m joint_action_facts.cli status --action ACT-7 --revision 2
PYTHONPATH=src python -m joint_action_facts.cli inbox --platform PLAT-C
PYTHONPATH=src python -m joint_action_facts.cli lineage --action ACT-8 --platform PLAT-C
PYTHONPATH=src python -m joint_action_facts.cli batches           # 批次历史与治理登记
PYTHONPATH=src python -m joint_action_facts.cli rebuild           # 基于 Bronze 全量重算 Silver/Gold
PYTHONPATH=src python -m joint_action_facts.cli report            # 重新生成 Markdown 报告
```

摄入是**幂等**的：重复执行 `run-all` 会跳过已完成批次；同一批次重跑不会产生重复消息。
新批次到达后再次执行 `run-all` 即可持续接收修订，Gold 快照按批次保留全部历史时点。

## 测试

```bash
python -m unittest discover -s tests -v
```

33 个测试覆盖：状态机口径、Bronze 不可变性与重复/隔离、摄入幂等、坏消息不阻断批次、
Gold 处置事实、版本覆盖计数、相似对象不合并、纠正链保留、迟到回执、快照接续状态、
全链路血缘与 CLI 视图。

## 目录

- `src/joint_action_facts/`：数据湖包（`domain` 常量、`states` 状态机、`ingest` Bronze、
  `silver`、`gold`、`pipeline` 编排、`lineage` 血缘、`reports` 报告、`cli` 命令行）
- `sources/`：合成协同消息来源
- `tests/`：unittest 测试
- `run_demo.py`：端到端演示

# 后端体检报告

**检查时间**：2026-10-20（Asia/Tokyo 本地时钟，日志内为 UTC）
**检查范围**：`backend` 全部业务模块、数据库 schema、pgvector、AI 供应商配置、知识库存储、运行中的服务
**检查方式**：初始体检采用静态检查、直连数据库查询、运行时 HTTP 探测和日志审计；随后按体检结论完成 RAG 分块、混合召回和 Rerank 输入优化，并重新处理全部知识文档后复测。

---

## 一、结论摘要

**当前后端可以正常演示和继续开发。** 核心链路（登录、预约、知识库 RAG、AI 对话与工具调用）都有真实数据或真实请求作为证据，不存在阻塞性问题。

- ✅ 13 个迁移已全部应用，`alembic check` 无漂移，模型与数据库完全一致。
- ✅ 知识库 110 份文档已重新处理，**全部 completed、0 失败**；1295 条 chunk 维度统一为 1024。
- ✅ 线上服务健康：`/health/live`、`/health/ready`、`/docs` 均 200，未授权访问正确返回 401。
- ✅ 真实端到端调用已被日志证明：embedding → rerank → MiniMax 两次响应（含工具循环）全部 200。
- ✅ **RAG**：长制度文档召回盲区已经修复；真实 25 条 A/B 评测中，Rerank 将 Hit@1 从 72% 提升到 92%，Hit@5 从 96% 提升到 100%，见 2.8。
- ⚠️ 初始体检发现 3 个 P1、4 个 P2；其中 RAG 召回盲区和 Windows 评测脚本已解决。当前剩余 2 个 P1、3 个 P2，主要涉及花费统计、密钥生命周期、磁盘残留和部分图片覆盖缺口。

**关于历史遗留的「文档全部处理失败」**：已用数据证否。日志里曾有 19 条 `knowledge ingestion business failure`，集中在 `document_id` 32–51；该区间的 20 份文档现在全部是 `completed` 且有正常 chunk 数，说明根因修复真实生效，不是只改了静态代码。

---

## 二、通过项（含证据）

### 2.1 代码与迁移

| 项目 | 结果 | 证据 |
|---|---|---|
| 静态检查 | 通过 | `ruff check .` → `All checks passed!` |
| 迁移版本 | 最新 | `alembic current` → `e2227d0a500f (head)` |
| schema 漂移 | 无 | `alembic check` → `No new upgrade operations detected.` |
| 应用装配 | 正常 | `import app.main` 成功，OpenAPI 生成 39 条路径 / 48 个操作 |

### 2.2 数据库与向量

| 项目 | 结果 | 证据 |
|---|---|---|
| 数据库连通 | 正常 | psycopg 直连成功，`app` schema 可读 |
| pgvector | 已安装 | `0.8.7` |
| `embedding` 列类型 | 正确 | `USER-DEFINED / vector`，非空 |
| 向量维度 | 全部 1024 | `min(vector_dims)=1024, max=1024`（1295 条） |
| HNSW 索引 | 存在且正确 | `USING hnsw (embedding vector_cosine_ops)` |
| 外键级联 | 正确 | `knowledge_chunks.document_id` 的 `confdeltype = c`（CASCADE） |
| 损坏向量 | 无 | 零向量 0 条，空正文 0 条 |

### 2.3 知识库数据

| 项目 | 结果 | 证据 |
|---|---|---|
| 文档状态 | **110 全部 completed** | `status` 分组只有 completed，`failed/processing/queued` 均为 0 |
| 处理阶段残留 | 无 | `stage IS NOT NULL` = 0 条 |
| 空文档 | 无 | `chunk_count = 0` = 0 条 |
| Chunk 总量 | 1295 | text 1091 + image 204 |
| Chunk 长度 | 已显著收敛 | 全部平均 143.6、P90 255、最大 999；其中文字块最大 788，图片融合块最大 999 |
| 原文件一致性 | **完全一致** | DB 110 条 `storage_key` ↔ 磁盘 `originals/` 110 个文件，双向差集为空 |
| 图片引用完整性 | 无缺失 | DB 引用的 204 个 `image_storage_key` 全部存在于磁盘 |
| 历史失败文档 | **已修复** | 日志中 19 条 `knowledge ingestion business failure` 集中在 `id` 32–51；该区间 20 份文档现全部 completed |

### 2.4 运行时

| 项目 | 结果 | 证据 |
|---|---|---|
| 服务实例 | 运行中 | `.venv\Scripts\python.exe -m app --reload`（本地 14:47 启动），本次未另起服务 |
| `/health/live` | 200 | `{"status":"alive"}` |
| `/health/ready` | 200 | `{"status":"ready"}`（含 `SELECT 1`） |
| `/docs` | 200 | Swagger 页面可访问 |
| 未授权保护 | 401 | `/api/user/me`、`/api/lab/list` 无 Token → `{"code":401,"message":"Not authenticated"}` |
| 线上路由 | 与代码一致 | 线上 `/openapi.json` = 39 路径 / 48 操作，与 `app.openapi()` 完全相同 |
| 后台任务 | 正常启动 | 启动日志 `Application startup complete`，无 task 异常；孤儿任务恢复生效（日志 `requeued stale knowledge tasks count=1` ×3） |
| 真实端到端 | 已跑通 | 06:04:55–06:05:06 UTC 一次请求：multimodal-embedding 200 → text-rerank 200 → MiniMax responses 200 ×2 |

### 2.5 AI 能力配置

5 项能力全部已配置、启用、有密钥：

| capability | provider | model | is_active | has_key | timeout |
|---|---|---|---|---|---|
| chat | minimax | MiniMax-M3.1-Flash | true | true | 60s |
| vision | minimax | MiniMax-M3.1-Flash | true | true | 60s |
| ocr | bailian | qwen3.5-ocr | true | true | 60s |
| embedding | bailian | qwen3-vl-embedding | true | true | 60s |
| rerank | bailian | qwen3-vl-rerank | true | true | 60s |

真实调用次数（`ai_usage_records`）：embedding 489、ocr 138、vision 67、chat 46、rerank 37。

### 2.6 业务数据

users 94 / labs 10 / equipments 40 / reservations 6 / chat_sessions 6 / ai_pending_actions 0。

### 2.7 RAG 优化前基线（旧的 6 条用例 `evals/rag_cases.json`）

**Recall@5 = 3/6 = 50%**，耗时 15.0 秒。

| # | 问题 | 结果 | 期望文档 | 实际 top-5 |
|---|---|---|---|---|
| 1 | 人工智能实验室在哪里，开放时间是什么 | ❌ | 人工智能实验室-综合介绍 | 基础信息总表.xlsx、平面导览.pdf、开放时间表.xlsx ×2、综合开放实验室导览.pdf |
| 2 | 六轴机械臂使用前需要做哪些检查 | ✅ | 六轴机械臂-操作手册 | **09-六轴机械臂-操作手册.docx**、资产总表、应急物资表… |
| 3 | 实验室预约取消有哪些限制 | ❌ | 实验室预约管理办法 | 14-预约取消记录.xlsx **×4**、Markdown 通知与指南.zip |
| 4 | 发生火情时应该怎样疏散 | ❌ | 消防与用电安全 | 应急处置速查卡.pdf、各实验室疏散图 ×4 |
| 5 | 设备发生故障后如何上报 | ✅ | 设备故障 | Markdown 通知与指南.zip、**07-设备故障报修与停用制度.docx**… |
| 6 | 3D打印机开始打印前要确认什么 | ✅ | 3D打印机-操作手册 | **40-3D打印机-操作手册.docx**、安全隐患整改表… |

**关键事实**：6 条用例的期望文档**全部真实存在于库中**（已逐条核实），所以 50% 是检索质量本身的问题，不是评测集过期。

失败原因分两类：

1. **同一文档挤占多个名额**（用例 3 最典型：`14-预约取消记录.xlsx` 占了 4/5）。向量召回 + ILIKE 补召回合并后没有「单文档限额」，导致相关但单一的表格式文档淹没真正该命中的制度文档。
2. **语义近邻压过目标文档**（用例 1、4）：问「开放时间」，命中的是「开放时间表」而不是「综合介绍」；问「疏散」，命中的是「疏散图」而不是「消防与用电安全」。这两条从语义上看并不算离谱，说明**评测口径偏严**——`expected_source_contains` 只认单一文档，而这些用例的答案实际分散在多份文档里。

### 2.8 Rerank A/B 对照（25 条扩展用例 `evals/rag_cases_ab.json`）

**复测时间**：2026-10-20。全部 110 份文档已使用新分块策略重新处理完成。

**方法**：同一条问题只算一次 embedding，构建与生产完全一致的候选池（向量 Top20 + 关键词补召回 Top20，按 chunk 去重）。A 组取候选原顺序前 5 条；B 组把**同一批候选**的「来源文件名 + 章节 + 正文」交给真实的 `rerank_documents` 排序后取前 5。两组候选完全相同，指标差异只来自排序方式。

| 指标 | A 无 rerank | B 有 rerank | 差值 |
|---|---|---|---|
| Hit@1 | 0.720 | **0.920** | **+0.200** |
| Hit@3 | 0.880 | **1.000** | **+0.120** |
| Hit@5 | 0.960 | **1.000** | **+0.040** |
| MRR@5 | 0.798 | **0.953** | **+0.155** |
| 前 5 条的去重文档数 | 3.36 | 2.68 | -0.68 |

逐条结果：**提升/提前 5 条，持平 20 条，变差 0 条**。Rerank 单次调用平均 1.017 秒，最长 1.182 秒。

**结论**：本轮优化同时改善了候选召回和候选排序。新分块与关键词补召回让「预约取消限制」进入候选池，Rerank 再把它从第 3 提到第 1；给 Rerank 补充文件名和章节后，「示波器」「可编程电源」不再被无关文档降序。Hit@5 达到 100%，说明 25 条用例的期望资料均进入最终上下文。

**多样性说明**：去重文档数下降不等于召回变差，而是排序模型会把同一高相关文档的多个片段同时排进 Top5。当前 Hit@5 已满分；若实际回答出现同源片段重复，再增加每份文档最多 2 条的多样性约束，不应只为提高这个辅助指标而提前改动。

**评测标注修正**：用例 13「设备故障报修」原先只承认《设备故障报修与停用制度》，但《Markdown通知与指南》的“设备故障上报流程指南”同样直接、完整回答问题。评测已把两份资料都列为有效来源，避免把正确检索误判为失败。


---

## 三、问题清单

### P1-1 rerank 花费未计入统计

- **现象**：`GET /api/ai/usage/cost` 中 rerank 的 `cost` 返回 `null`，37 次调用、326,693 tokens 不计入总花费。
- **根因**：价格表键名与实际配置的模型名不一致。
  - 价格表：[ai_usage_services.py:158](../app/services/ai_usage_services.py#L158) 写的是 `("bailian", "qwen3-rerank")`
  - 数据库实际配置：`qwen3-vl-rerank`
  - `_cost_of()` 查不到键就返回 `None`，[get_cost_summary()](../app/services/ai_usage_services.py#L187) 于是不计入。
- **影响**：管理员花费页会低估成本；不影响聊天与检索功能。
- **建议**：在 `PRICING` 中增加 `("bailian", "qwen3-vl-rerank")` 键（保留旧键以兼容历史数据）。
- **注意**：这不是「改一行就好」的小事——单价需要你按百炼控制台的实际计费确认后填写，我不擅自猜价格。

### P1-2 聊天思考预算与正文共享输出上限

- **现象**：chat 能力配置 `reasoning_effort = max`，同时 `BAILIAN_CHAT_MAX_OUTPUT_TOKENS = 4096`。思考 token 与正文共享这 4096。
- **影响**：长回答（如「对比多个实验室 + 列出依据文档名」）仍有被截断风险。历史上 `max_output_tokens=1024` 时已经真实发生过一次截断（正文停在「依据：《0」）。
- **位置**：这不是代码写错，而是数据库里的运行时配置；代码侧见 [ai_services.py:392](../app/services/ai_services.py#L392) 把 `max_output_tokens` 固定取全局配置。
- **建议**（三选一，需你决定）：
  1. 在 AI 配置页把 chat 的 `reasoning_effort` 调为 `medium` 或 `high`；
  2. 把 `BAILIAN_CHAT_MAX_OUTPUT_TOKENS` 提到 8192（成本按实际生成量计，调高上限不增加固定成本）；
  3. 维持现状，接受长回答偶发截断。
- **说明**：MiniMax 与 Qwen 的思考 token 是否计入 `max_output_tokens` 口径不同，这条属于「风险提示」而非「已复现的 bug」——本次未构造长回答去复现。

### 已解决：原 P1-3 长制度文档召回盲区

> 2026-10-20 已完成代码修复、110 份文档全量重处理和付费 A/B 复测。

- **原现象**：优化前 25 条扩展用例中唯一全错的是「实验室预约取消有哪些限制」——A/B 两组都未命中，且期望文档**根本没进入候选池**。
- **原根因**（两个叠加，都与 rerank 无关）：
  1. **分块过大**：`_split_text` 按空行聚合、上限约 2000 字符（[document_parser_services.py:101](../app/services/document_parser_services.py#L101)）。制度类 docx 全文 500–1400 字且中间没有空行分段，于是整篇压成**一个 chunk**（`01-实验室预约管理办法` 就是 1338 字 / 1 chunk）。chunk 越长，1024 维向量被稀释得越厉害；而表格类 xlsx 每块只有几十字、数量又多，很容易在向量 Top20 里把它挤出去。
  2. **关键词召回实际失效**：补召回拿**整句**做 ILIKE（[knowledge_retrieval_services.py:121](../app/services/knowledge_retrieval_services.py#L121)），`%实验室预约取消有哪些限制%` 在原文里永远匹配不到，所以这条通道对自然语言提问基本不起作用。
- **处理结果**：
  1. 文字分块改为章节、段落、句子三级切分，目标上限 800 字；文字 Chunk 实测最大 788 字。
  2. 字面补召回改为提取有限关键词、按命中数排序，并与向量候选去重合并。
  3. 生产检索和 A/B 脚本共用 `build_candidate_rows()`，避免评测逻辑漂移。
  4. 110 份文档全部重处理成功；Chunk 从 550 增至 1295，预约管理办法从 1 个 1338 字大块拆成 8 个 97–283 字小块。
  5. 原失败用例「实验室预约取消有哪些限制」现在无 Rerank 第 3、Rerank 第 1。

### P2-1 AI 配置加密密钥未独立配置

- **现象**：`.env` 无 `AI_CONFIG_ENCRYPTION_KEY`，今日日志中该 warning 出现 **33 次**。
- **影响**：库中所有 AI Key 由 `JWT_SECRET_KEY` 派生密钥加密。一旦轮换 JWT 密钥，**所有已保存的 AI Key 全部无法解密**，5 项能力同时失效。
- **位置**：[settings.py:89](../app/core/settings.py#L89)、回退逻辑见 [ai_provider_services.py:59](../app/services/ai_provider_services.py#L59)。
- **建议**：在 `.env` 增加 `AI_CONFIG_ENCRYPTION_KEY`（≥32 字符，与 JWT 密钥不同），重启后在配置页重新保存一遍各能力的 Key（否则旧密文仍走回退分支，虽然能解但没达到隔离目的）。
- **补充**：代码里已有「主密钥失败后回退旧密钥」的兼容逻辑，切换不会导致历史数据立刻失效。

### P2-2 61 个孤儿图片文件（8.79 MB）

- **现象**：`storage/knowledge/images/` 下有 265 个文件，但数据库只引用 204 个，**61 个无任何 chunk 引用**，合计 8.79 MB。
- **时间特征**：全部生成于 `2026-10-20 05:38–05:46`（Codex 中断/重启期间）。
- **根因**：入库流程在「图片已从 working 目录发布到 images 目录」之后、`commit` 之前被进程终止，`finally` 只清理 working 目录，发布出去的图片失去引用。代码的正常清理逻辑本身是对的（[knowledge_ingestion_services.py:217](../app/services/knowledge_ingestion_services.py#L217) 会删除 `old_image_keys - new_image_keys`），但它只能处理「抛异常」，处理不了「进程被 kill」。
- **影响**：只占磁盘，不影响检索与回答。
- **建议**：加一个孤儿清理命令（对比 `images/` 与 `knowledge_chunks.image_storage_key` 差集后删除），供管理员手动执行；不建议做成启动时自动删除，误删代价高于收益。

### P2-3 部分 DOCX 内嵌图片不可读，被静默跳过

- **现象**：日志中 `skipping unreadable DOCX image` 出现 38 条（38 个不同图片）。
- **影响**：这些图片没有 OCR/视觉结果，对应文档仍能完成入库，但图片内容不进入知识库——属于**知识覆盖缺口**，不是故障。
- **建议**：属于数据质量问题，建议先确认这些图片在 Word 里是否能正常打开；若要修，需在解析器里记录到 `knowledge_documents.error_message` 或单独的表，让管理员看得见。当前只写日志，页面上看不到。

### 已解决：原 P2-4 `scripts/evaluate_rag.py` 在 Windows 上无法运行

- **现象**：直接执行 `python -m scripts.evaluate_rag` 立即崩溃：
  `psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode.`
- **根因**：脚本末尾用的是裸 `asyncio.run(main())`（[evaluate_rag.py:44](../scripts/evaluate_rag.py#L44)），没带项目自己的 `loop_factory`。Windows 默认事件循环是 Proactor，psycopg 异步驱动不支持。
- **对照**：[run_knowledge_worker.py:24](../scripts/run_knowledge_worker.py#L24) 用的是 `asyncio.Runner(loop_factory=loop_factory)`，写法是对的。两个脚本不一致。
- **处理结果**：脚本入口已改为 `asyncio.Runner(loop_factory=loop_factory)`，与应用和知识库 Worker 保持一致，可直接在 Windows PowerShell 执行：
  ```powershell
  uv run python -m scripts.evaluate_rag
  ```

### P3 类（不阻塞）

| 问题 | 说明 |
|---|---|
| `logs/app.log` 残留 | 8,923 字节，最后修改 10-06，属于新日志规范（按 UTC 日期分目录）之前的历史文件，可删 |
| `intent` / `decision` 能力 | 已登记在 `VALID_CAPABILITIES` 但未配置、无调用点，属预留设计，非缺陷 |
| `README.md` / `docs/ARCHITECTURE.md` 过期 | README 仍称「暂时比较明文密码」，实际已是 Argon2id + JWT；ARCHITECTURE 只描述了登录链路，中间件顺序图漏了 CORS |
| 历史 `chat degraded without RAG` | 5 次，发生在 embedding 能力尚未配置的时期，现配置已齐，属历史记录 |

---

## 四、已验证 / 未验证

### 已验证

- 静态检查、迁移一致性、数据库连通、pgvector 与 HNSW 索引、向量维度。
- 知识库全量数据完整性（文档状态、chunk 维度、原文件与图片引用）。
- 历史「文档全部处理失败」已修复（同批文档现全部 completed）。
- 服务健康检查、Swagger、未授权 401、线上路由与代码一致。
- 后台任务启动正常、孤儿任务恢复生效。
- AI 五项能力配置齐全，且 5 类能力都有真实调用记录。
- RAG 全量重处理与 25 条真实 A/B 评测已跑通：Rerank 后 Hit@1 = 92%，Hit@5 = 100%，MRR@5 = 0.953。

### 未验证（本次没做，需要单独授权）

| 项目 | 原因 | 预估成本 |
|---|---|---|
| 新上传文档的完整 ingestion | 会向知识库新增测试文档，需你决定是否污染现有数据 | 按图片数计费 |
| 长回答截断复现（P1-2） | 需构造长提问，会消耗较多思考 token | 单次约 ¥0.01–0.05 |
| 前端联调 | 不在本次范围（前端由另一 agent 负责） | — |

---

## 五、复核命令

以下命令可独立复现本报告的结论。静态、迁移和健康检查为只读；两条 RAG 评测会真实调用云端 embedding/rerank，并写入用量记录、产生费用：

```powershell
# 静态与迁移
.venv\Scripts\ruff.exe check .
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic check

# 路由清单（39 路径 / 48 操作）
.venv\Scripts\python.exe -c "import app.main as m; s=m.app.openapi(); print(len(s['paths']))"

# 健康检查（服务已在 8000 运行时）
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready

# RAG 检索评测（Windows 事件循环已在脚本入口处理）
uv run python -m scripts.evaluate_rag

# Rerank A/B 对照（25 条扩展用例，见 2.8）
uv run python -m scripts.eval_rerank_ab
```

数据库侧核心查询：

```sql
-- 文档状态分布（期望只有 completed）
select status, count(*) from app.knowledge_documents group by status;

-- 向量维度（期望 min=max=1024）
select min(vector_dims(embedding)), max(vector_dims(embedding)) from app.knowledge_chunks;

-- 能力配置（期望 5 行且 is_active=true、有 key）
select capability, provider, model, is_active,
       (api_key_encrypted is not null) as has_key
from app.ai_provider_configs order by capability;
```

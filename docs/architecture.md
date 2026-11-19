# 系统架构

## 1. 组件视图

```text
Browser
  │ fetch / SSE
  ▼
FastAPI API (api.py)
  │ session cookie, validation, task endpoints
  ▼
ReviewService (service.py)
  ├─ LiteratureRetriever (retrieval.py)
  │    ├─ arXivProvider
  │    ├─ PubMedProvider
  │    └─ FixtureProvider
  ├─ SQLite Repository (repository.py)
  ├─ CrewAIReviewRunner (crew.py)
  │    ├─ Retrieval / Evidence Audit Agent
  │    ├─ Paper Analysis Agent
  │    ├─ Comparison Agent
  │    └─ Writing Agent
  ├─ EvidenceIndex (rag.py)
  └─ CitationValidator (validation.py)
```

## 2. 检索与确认

1. 用户提交主题、年份、来源和候选上限。
2. API 按 BR01 校验字段；合法时创建唯一任务并立即返回 `task_id`。
3. 后台检索线程调用选定来源，来源错误相互隔离。
4. 强标识（DOI、arXiv ID、PubMed ID）命中时合并来源记录；弱标识（标题 + 首作者 + 年份）命中时仅标记疑似重复。
5. 候选和证据片段持久化，状态进入 `awaiting_confirmation`。
6. 用户确认至少一篇有证据文献后，选择集合写入不可变快照。

## 3. CrewAI 协作

生成阶段由同一个 CrewAI `Crew` 顺序执行四个任务：

| 顺序 | Agent | Task | 输出 |
| --- | --- | --- | --- |
| 1 | 文献检索与证据整备代理 | 保持 paper/evidence/locator 标识一致 | EvidencePack |
| 2 | 单篇文献分析代理 | 方法、实验、创新、局限与证据 | AnalysisArtifact |
| 3 | 跨文献对比与融合代理 | 分类、异同、演进、问题与 caveat | ComparisonArtifact |
| 4 | 结构化综述撰写代理 | 四章节声明与证据绑定 | DraftArtifact |

无模型密钥时，CrewAI 使用 `DeterministicReviewLLM`。它读取 Task 描述中的输入标记，返回与真实 LLM 相同 Pydantic 结构的 JSON，因此本地验收仍真实走 CrewAI Agent/Task/Context/Callback 机制。

## 4. RAG 证据链

- 证据单元来自实际取得的摘要句子，保存 `evidence_id`、`paper_id`、原文与 `locator`。
- `EvidenceIndex` 使用 BM25 与 CRC32 哈希字符向量余弦得分进行混合检索。
- 检索查询覆盖主题背景、方法分类、技术演进和未解决问题四个方向。
- 撰写任务收到 RAG 召回片段和完整证据包；真实生成结果的引用仍要通过独立结构校验。

## 5. 报告校验

`CitationValidator` 检查：

- 四个章节是否齐全；
- claim_id 是否唯一；
- 事实性声明是否有证据；
- evidence_id 是否能解析；
- 证据归属是否落在 `subject_paper_ids` 内；
- 方法章节声明是否标明对应文献；
- 词面支持度是否过低（仅生成人工抽查提示）。

出现致命问题时只进行一次校正：移除无法通过引用/归属检查的声明，缺失章节加入明确的证据不足说明。第二次校验仍失败则任务进入 `failed`，不发布报告。

## 6. 状态与持久化

```text
pending
  └→ retrieving
       ├→ awaiting_confirmation
       │    └→ analyzing
       │         └→ writing
       │              └→ validating
       │                   ├→ completed
       │                   └→ failed
       ├→ failed
       └→ failed
```

- 状态只能按允许方向迁移。
- `task_events` 保存阶段事件。
- `agent_tasks` 保存四个专业角色的待执行/执行中/成功/失败状态和输出引用。
- `reports` 保存最终结构化报告。
- `evaluations` 保存报告、评审人、量表版本、五维分值和评语。

## 7. 访问与安全

- 每次浏览器会话使用 HttpOnly Cookie 标识。
- 任务、报告和评价读取均校验 `owner_session`。
- 外部摘要被视为数据，不作为系统指令执行。
- LLM 密钥只从环境变量读取，不出现在 HTML、报告、API 响应或普通日志中。
- 服务重启时，执行中的未完成任务标记为失败，避免“已完成但无报告”的不一致。

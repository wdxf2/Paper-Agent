# 需求追踪矩阵

需求基线：`需求分析/科研文献智能综述生成系统_需求分析设计.docx`，版本 1.1。

## 功能需求

| 编号 | 实现位置 | 验证 |
| --- | --- | --- |
| FR01 | `models.TaskCreateRequest`、`repository.create_task`、`api.POST /api/v1/tasks` | `tests/test_models.py`、`tests/test_api.py::test_invalid_input_returns_field_errors` |
| FR02 | `retrieval.py` Provider 与 `deduplicate_and_finalize` | `tests/test_retrieval.py` |
| FR03 | `repository.confirm_selection`、`CandidateListView`、Web 候选页 | `tests/test_api.py::test_end_to_end_review_and_evaluation` |
| FR04 | `crew.py` 四 Agent/Task、`agent_tasks`、`service._run_generation` | `tests/test_api.py` 的 agent 状态与端到端；CrewAI 运行验收 |
| FR05 | `deterministic.build_analysis`、`build_comparison`、真实 LLM Pydantic 输出 | `tests/test_api.py` 分析接口 |
| FR06 | `rag.EvidenceIndex`、`build_writer_rag_context`、`crew` 写作任务 | `tests/test_validation.py`、`tests/test_api.py` 报告四章节 |
| FR07 | `validation.CitationValidator`、`prepare_report`、`service._run_generation` | `tests/test_validation.py` |
| FR08 | `repository.ALLOWED_TRANSITIONS`、`task_events`、`service`、SSE | `tests/test_api.py` 状态轮询；`api /events` |
| FR09 | `ReportView`、`static/app.js` 报告与证据抽屉 | `tests/test_api.py` 报告与 evidence 映射 |
| FR10 | `EvaluationRequest/View`、`repository.create_evaluation`、评价页面 | `tests/test_models.py`、`tests/test_api.py` |

## 非功能需求

| 编号 | 实现 |
| --- | --- |
| NFR01 | 本地 SQLite 任务创建/查询不等待外部服务；外部检索与生成在线程池执行 |
| NFR02 | HTTP 检索最多重试 2 次；生成失败进入 `failed`；校验只校正一次 |
| NFR03 | API 字段错误、检索错误、证据不足、引用失败使用不同消息与阶段 |
| NFR04 | 完成报告前全量解析 evidence_id；引用悬空或归属错配阻止发布 |
| NFR05 | Cookie 会话范围、密钥仅环境变量、外部文本提示注入隔离 |
| NFR06 | Provider、Agent、Repository、Validator 通过明确模型与接口隔离；记录 task/agent 标识 |

## 项目约束

| 编号 | 实现 |
| --- | --- |
| C01 | CrewAI `Agent + Task + Crew + Process.sequential` |
| C02 | `ArxivProvider`、`PubMedProvider`、来源记录与来源错误隔离 |
| C03 | BM25 + 字符向量 RAG，证据 ID 传入写作并绑定正文 |
| C04 | FastAPI Web 原型 + 5 维评价量表 |

## 业务规则

| 规则 | 落点 |
| --- | --- |
| BR01 | `TaskCreateRequest` 字段与模型校验 |
| BR02 | `normalize_doi/arxiv/pmid`、强标识合并、弱标识疑似重复 |
| BR03 | 仅摘要句生成 EvidenceFragment；缺失字段写“未报告或无法判断” |
| BR04 | `confirm_selection` 要求至少一篇证据文献并保存快照 |
| BR05 | 对比任务保留条件差异；不根据年份推断技术继承；不直接排名 |
| BR06 | 四章节、引用解析、证据归属检查通过后才 `completed` |
| BR07 | Provider 重试上限、失败终止、`create_retry_task` 新任务关联原任务 |

## 未纳入本原型

- 注册、付费、团队协作
- PDF 上传与多格式导出
- 真实学术正确性自动认定
- 生产级队列与多实例部署

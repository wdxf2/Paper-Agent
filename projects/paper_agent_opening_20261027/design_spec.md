<!-- ppt-master-schema: design-spec/v1 -->
# 论文智能综述系统 - Design Spec

## I. Project Information

| Item | Value |
| --- | --- |
| Project Name | 基于多智能体协同的科研文献智能综述生成系统 |
| Canvas Format | PPT 16:9, 1280 × 720 |
| Page Count | 17 |
| Primary Language | zh-CN |
| Target Audience | 软件学院开题答辩老师、评审专家及同组同学 |
| Communication Intent | 先讲清研究问题与项目价值，再说明多智能体、RAG、系统设计与评测方案，最终争取评审认可选题的可行性与工作量 |
| Desired Audience Outcome | 能准确复述“CrewAI 多智能体 + 可追溯 RAG”的核心思路，理解四项要求如何落地，并认可 24 周实施计划 |
| Core Message / Ask / Action | 把文献综述从一次性生成改造成“任务图 + 证据绑定 + 引用校验”的可追溯工作流 |
| Delivery Context | 现场开题答辩，10—12 分钟主讲；会后供导师审阅和组内讨论 |
| Artifact Afterlife | 开题答辩、导师审阅、组内讨论和后续技术报告复用 |
| Reading Mode | balanced |
| Content Strategy | 均衡重组：保留报告中的事实、数字、技术关系和约束，将 34 页报告重构为 14 页答辩叙事，不逐页照搬正文 |
| Design Style | 研究蓝图：浅色技术图纸、工程标注、深青主色、琥珀色关键路径 |
| AI Image Acquisition Path | 不适用：本方案不使用 AI 图像 |
| Generation Mode | continuous |
| Spec Refinement | disabled |
| Speaker Notes | enabled — Stage-2 确认的主动备注方案，生成 10—12 分钟讲稿 |
| Custom Animations | disabled — Stage-2 确认的主动动画方案 |
| Narration Audio | disabled — Stage-2 确认的主动旁白方案 |
| Created Date | 2026-10-27 |

## II. Canvas Specification

| Property | Value |
| --- | --- |
| Format | PPT 16:9 |
| Dimensions | 1280 × 720 |
| viewBox | `0 0 1280 720` |
| Margins | 64px page margin; 48px top title zone; 40px footer zone |
| Content Area | x=64..1216, y=64..656 |

## III. Visual Theme

### Theme Style

- **Mode**: custom
- **Mode References**: pyramid, instructional
- **Mode Behavior**: 结论先行：开场直接给出“可追溯工作流”的项目判断；中段采用教学式顺序拆解检索、分析、对比、写作与校验机制；结尾回到可行性、评测与实施计划，以明确结论收束。
- **Visual style**: custom
- **Visual Style References**: blueprint
- **Visual Style Behavior**: 采用工程图纸式细线网格、精确对齐和标注语言；矩形与线框承担主要结构，深青线条构成系统骨架，琥珀色只标记当前关键路径或风险；标题为粗体判断句，正文中性克制，强调可读性而非装饰。
- **Theme**: 研究蓝图与工程档案
- **Tone**: 技术、冷静、可信、具有推进感

### Color Scheme

| Role | HEX | Purpose |
| --- | --- | --- |
| Background | #F7F9F6 | 主页面底色，近白带轻微纸面感 |
| Secondary background | #E8EFEA | 分区、模块底色与图纸网格带 |
| Primary | #0E3B43 | 标题、主结构线、重点节点 |
| Accent | #D97706 | 关键路径、风险提示、重点数字 |
| Secondary accent | #2F6F7E | 辅助流程、次级标签与连接 |
| Body text | #1F2933 | 正文、标题说明与主要标签 |
| Secondary text | #5B6770 | 注释、页脚、来源说明 |
| Divider | #BED0C5 | 细规则线、分隔线与网格 |

## IV. Typography System

### Font Plan

| Role | Character (Reference) | Primary | English if non-English | Fallback tail |
| --- | --- | --- | --- | --- |
| Title | 稳定、清晰、工程报告感 | Microsoft YaHei | Arial | sans-serif |
| Body | 中性、易读、适合投影 | Microsoft YaHei | Arial | sans-serif |

- **Title stack**: Microsoft YaHei, Arial, sans-serif
- **Body stack**: Microsoft YaHei, Arial, sans-serif

### Font Size Hierarchy

| Purpose | Anchor Size (px) |
| --- | ---: |
| Body | 24 |
| Title | 46 |
| Subtitle | 26 |
| Lead | 30 |
| Annotation | 18 |
| Footnote | 14 |
| Display | 64 |

## V. Layout Principles

### Deck-wide Direction

- **Hierarchy direction**: 先看断言标题，再看关键路径或主图，最后读取说明、指标和来源；每页只保留一个主导阅读方向。
- **Composition tendency**: 以技术图纸的标题栏、坐标标签、节点框、细线和空白为基本语汇；信息密集页采用不对称栅格，关键页保留大面积留白。
- **Cross-page continuity**: 统一使用左上角小坐标码、右下角页号、细网格和一条可延续的深青/琥珀色路径；章节间以不同图纸比例和密度变化。
- **Spacing posture**: 整体开放；机制页和评测页可提高信息密度，封面、核心判断页和结论页保留呼吸感。
- **Spacing anchors**: 64px 页边距；32px 区块间距；24px 列间距；12px 圆角；34px 正文行距

## VI. Icon Usage Specification

- **Primary bundled library**: tabler-outline
- **Stroke Width**: 2

| Icon Path | Suitable Scenarios |
| --- | --- |
| tabler-outline/search | 文献检索、主题输入、研究背景 |
| tabler-outline/database | RAG、证据库、向量索引 |
| tabler-outline/binary-tree | 任务 DAG、任务分解、系统结构 |
| tabler-outline/link | 证据绑定、引用链、可追溯性 |
| tabler-outline/shield-check | 引用校验、质量门、可靠性 |
| tabler-outline/layout-dashboard | Web 原型、界面、任务监控 |
| tabler-outline/checklist | 功能需求、验收标准 |
| tabler-outline/target-arrow | 研究目标、评测目标、结论 |
| tabler-outline/calendar | 24 周进度、阶段计划 |
| tabler-outline/file-text | 综述草稿、报告、导出 |
| tabler-outline/report-analytics | 评测指标、实验分析 |
| tabler-outline/robot | 智能体角色、多智能体协作 |
| tabler-outline/network | 系统架构、协作网络 |

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Image pattern | Crop Policy | Acquire Via | Status | Reference | text_policy | page_role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## IX. Content Outline

### Part 1: 问题与判断

#### Slide 01 - 封面

- **Audience move**: 从进入答辩现场 → 明确项目名称、研究定位与本次汇报的核心判断
- **Relationships**: none
- **Composition**: 左侧标题块与右侧技术图纸坐标网格并置；标题是唯一大焦点，底部保留一句短断言；构图 Reference。
- **Title**: 基于多智能体协同的科研文献智能综述生成系统
- **Core message**: 用 CrewAI 与可追溯 RAG，把文献综述生成改造成可验证的工作流。
- **Content**:
  - 主标题：基于多智能体协同的科研文献智能综述生成系统
  - 英文副标题：A Multi-Agent Collaborative System for Intelligent Literature Review Generation
  - 工程领域：软件工程 / 智能软件工程与大语言模型应用
  - 汇报类型：开题报告 · 2026 年 10 月
  - 短句：不是写得更快，而是引得更准、查得到。
- **Cover impact**: 绑定钩子为“不是写得更快，而是引得更准、查得到”；技术图纸坐标作为可调整的视觉语汇。

#### Slide 02 - 研究背景

- **Audience move**: 从知道文献增长很快 → 理解真正阻碍综述质量的是检索分散、整理耗时和引用不可核验
- **Relationships**: contrast — 文献供给侧的压力与研究者需求侧的要求；order — 从检索到写作的四段人工流程
- **Composition**: 上方一句判断标题，下方三组“压力—要求”对照字段；右下用一条简短流程线把检索、筛选、比较、写作串联起来。
- **Title**: 文献越来越多，综述却仍难“说得准、查得到”
- **Core message**: 问题的核心是证据链，不是生成速度。
- **Content**:
  - 供给侧：论文数量增长、跨库分散、全文与元数据质量不一
  - 需求侧：快速建立方法分类、代表工作、实验条件与演进脉络
  - 人工流程：检索 → 筛选 → 抽取 → 对比 → 写作
  - 关键缺口：引用可追溯、观点可比较、过程可复现

#### Slide 03 - 核心判断

- **Audience move**: 从把自动综述理解为“直接生成一篇文章” → 接受“可追溯工作流”的项目定义
- **Relationships**: contrast — 一次性生成与可追溯工作流的前后对比；order — 从任务分解到引用校验的连续路径
- **Composition**: 左右对照：左侧是灰阶的单次提示词链路，右侧是深青/琥珀色的六段工作流；底部一句大号判断。
- **Title**: 把综述从“一次性生成”改造成“可追溯工作流”
- **Core message**: 综述质量来自任务分解、证据绑定和验证，而不是单次生成长度。
- **Content**:
  - Before：主题 → LLM → 草稿；过程不透明，引用难核验
  - After：规划 → 检索 → 分析 → 对比 → 写作 → 校验
  - 项目等式：综述 = 任务图 × 证据链 × 验证
  - 目标：可交互、可追溯、可复现

### Part 2: 现状与方案

#### Slide 04 - 现状与缺口

- **Audience move**: 从知道已有 RAG、多智能体和自动综述研究 → 看清三条路线的共同缺口
- **Relationships**: contrast — 三条研究路线的能力与局限并列；link — 三条局限共同指向“细粒度证据、任务融合、跨域评测”
- **Composition**: 三列技术档案卡，每列一个研究线；底部一条横向缺口带把三项结论合并。
- **Title**: 三条研究线各有进展，但都留下同一个缺口
- **Core message**: 现有工作解决了部分能力问题，尚未形成证据级、可复现的端到端闭环。
- **Content**:
  - RAG：能引入外部证据，但引用常停留在段落/文献级
  - 多智能体：能分工协作，但自由对话易造成上下文膨胀和错误级联
  - 自动综述：已有端到端探索，但跨领域评测和冲突处理不足
  - 本项目切口：claim–evidence–locator + 任务 DAG + 可复现 Web 原型

#### Slide 05 - 总体方案

- **Audience move**: 从理解问题 → 看懂三项技术如何组成一个完整系统
- **Relationships**: parent — 一个系统目标分解为协作层、证据层和应用层；link — 三层之间的输入输出关系
- **Composition**: 三层层叠结构：底层混合 RAG 与数据，中层 CrewAI 智能体协作，上层 Web 应用；右侧用一条纵向路径标记主数据流。
- **Title**: 三层协作：智能体、证据与应用闭环
- **Core message**: 三层各司其职，最终把研究过程变成可操作、可检查的工作流。
- **Content**:
  - 协作层：协调、检索、分析、对比、撰写、引用校验
  - 证据层：arXiv/PubMed 接入、章节切分、BM25 + 稠密检索、重排序、证据库
  - 应用层：Web 配置、进度、证据面板、报告编辑与导出
  - 支撑层：LLM 网关、PostgreSQL/pgvector、Redis/Celery、对象存储

#### Slide 06 - 多智能体任务图

- **Audience move**: 从“多智能体就是多个角色聊天” → 理解以任务 DAG、类型化产物和失败恢复为核心的工程编排
- **Relationships**: order — 六类智能体的执行顺序；link — 上游产物传递给下游；parent — 协调智能体拆分子任务
- **Composition**: 横向任务图：协调器居中上方，检索/分析/对比/撰写/校验沿路径展开，产物标签挂在节点之间；底部用细线标出重试回边。
- **Title**: 六类智能体按任务图协作，避免自由对话的状态漂移
- **Core message**: 关键不是角色数量，而是任务契约、结构化产物和可恢复执行。
- **Content**:
  - 协调：解析约束、生成 DAG、分配预算
  - 检索/分析/对比/撰写/校验：各司其职
  - 产物：Plan / Retrieval / Analysis / Comparison / Draft / Verification Artifact
  - 机制：schema 校验、重试、检查点、共享黑板

#### Slide 07 - 可追溯 RAG

- **Audience move**: 从“检索增强就是先搜再写” → 理解每条关键声明如何绑定原文证据
- **Relationships**: order — 从文献接入到引用发布的证据流水线；link — chunk、evidence、claim、citation 的绑定关系
- **Composition**: 一条从左到右的证据流水线，关键节点用深青框，evidenceId 用琥珀色标签；底部一条小字说明定位字段。
- **Title**: 每条关键声明都绑定 evidenceId，形成可追溯引用链
- **Core message**: 引用不是一个编号，而是一条可以从结论回到原文的路径。
- **Content**:
  - 论文规范化 → 章节感知切分 → 混合召回 → 重排序 → 证据卡片
  - 证据字段：论文、章节、页码/段落、原文片段、支持度
  - 写作约束：claim 只能引用 evidenceId
  - 校验失败：补充检索或定向改写，不静默通过

#### Slide 08 - 结果融合与引用校验

- **Audience move**: 从担心多智能体会“互相说服” → 理解系统如何保留条件、冲突和人工复核
- **Relationships**: contrast — 相似观点与冲突观点并列；parent — 多源分析结果归并到统一产物；order — normalize → dedup → cluster → conflict → write
- **Composition**: 左侧三步融合流程，右侧一个“冲突保留”小面板；底部用两条高低不同的支持度线表示自动通过/人工复核/拒绝。
- **Title**: 结果融合保留条件与冲突，不做盲目投票
- **Core message**: 可信的融合不是强行一致，而是让读者看到证据、条件和分歧。
- **Content**:
  - 归一化：DOI/arXiv ID、标题/作者/年份、版本合并
  - 融合：按方法/任务聚类，缺失字段保留空缺
  - 冲突：保留双方实验条件与证据，标注“待判断”
  - 门槛：支持度 ≥0.75 自动通过；0.50—0.75 人工复核；<0.50 拒绝写入

### Part 3: 工程与验证

#### Slide 09 - 系统设计与 Web 原型

- **Audience move**: 从理解算法 → 相信项目具备可实现的软件工程结构
- **Relationships**: membership — 系统分为表现、应用、智能体、数据四层；link — API、任务队列、证据库和前端视图的交互
- **Composition**: 左侧四层系统剖面，右侧 Web 原型四视图缩略；UML 小标签放在页脚上方，不占据主视觉。
- **Title**: 分层架构把研究流程封装成可操作、可恢复的 Web 原型
- **Core message**: 从输入主题到导出报告，每一个阶段都有界面、状态和证据可查。
- **Content**:
  - 前端：主题配置、任务进度、报告工作区、证据面板
  - 后端：FastAPI、SSE、Celery/Redis、PostgreSQL/pgvector、MinIO
  - UML：用例、组件、顺序、领域/证据类图
  - 体验：可取消、可重试、可编辑、可导出

#### Slide 10 - 需求与验收

- **Audience move**: 从看到功能列表 → 理解需求已被收敛为可验收的工程指标
- **Relationships**: parent — 项目需求分解为功能与非功能两类；contrast — P0 必须项与 P1 增强项
- **Composition**: 左侧 12 项功能需求的 P0/P1 分组，右侧 8 项非功能指标和四项关键验收数字。
- **Title**: 需求收敛为 12 项功能、8 项非功能指标
- **Core message**: 先保证证据链和任务可恢复，再优化编辑体验与界面细节。
- **Content**:
  - P0：主题、检索、去重、切分、混合检索、分析、对比、写作、引用校验
  - P1：证据查看、报告编辑、导出、任务监控
  - NFR：性能、可靠性、可追溯、可复现、安全、可维护、易用、成本
  - 关键目标：证据绑定 100%、引用精度 ≥85%、任务成功 ≥95%、专家评分 ≥4.0/5

#### Slide 11 - 三领域评测

- **Audience move**: 从担心“只是做一个演示” → 看到质量、引用、时延和成本都可以被比较
- **Relationships**: contrast — 三个子方向与四类基线；link — 自动指标与人工盲评共同支撑结论
- **Composition**: 左侧三列领域卡片，右侧四行基线矩阵；底部一条“自动指标 + 人工评分”的双轨评测带。
- **Title**: 三领域、四基线、两层评测：质量必须可核验
- **Core message**: 评测不只看文本是否流畅，而要看引用是否成立、证据是否覆盖、成本是否可控。
- **Content**:
  - 领域：RAG、LLM 多智能体系统、软件漏洞检测
  - 基线：Direct LLM；Single-agent + RAG；Multi-agent without RAG；Ours
  - 自动：引用精度/召回、覆盖率、定位准确率、nDCG、时延、token 成本
  - 人工：3 名评分者盲评；报告 Krippendorff's α；目标 α≥0.70

#### Slide 12 - 24 周进度

- **Audience move**: 从担心时间不足 → 看到阶段目标、交付物和可验证的推进路径
- **Relationships**: order — 四个阶段按先后推进；parent — 24 周总目标分解为调研、实现、评测、结项
- **Composition**: 4 段等宽阶段带，不按工期比例绘制；每段上方写阶段编号，下方写成果；右侧用竖排小字标注“连续可交付”。
- **Title**: 24 周完成从 RAG 到 Web 原型再到三领域评测
- **Core message**: 每个阶段都有可运行增量，风险在评测前暴露，而不是留到最后。
- **Content**:
  - 第 1—2 周：调研与需求冻结 → 需求规格 v1
  - 第 3—8 周：架构、数据接入与 RAG → 索引流水线
  - 第 9—15 周：多智能体编排与 Web 原型 → Alpha
  - 第 16—20 周：三领域评测与优化 → 评测报告
  - 第 21—24 周：技术报告、演示与答辩 → 最终交付

#### Slide 13 - 预期成果

- **Audience move**: 从理解计划 → 明确项目最终交付什么、如何判断完成
- **Relationships**: membership — 系统、评测、报告、演示材料组成最终成果包；contrast — 目标值与当前承诺边界
- **Composition**: 四个交付块围合一个中心结论；关键目标值以大字和短标签呈现，底部保留“目标值待实验验证”的限定。
- **Title**: 交付一套可运行、可评测、可复现的综述系统
- **Core message**: 项目不只交付页面，而是交付可复用的证据工作流和一套诚实的评测材料。
- **Content**:
  - 系统：Web 原型、API、RAG 流水线、Docker 部署
  - 评测：三领域主题、关键点清单、引用核验样本、脚本
  - 文档：技术报告、UML 源文件、接口文档
  - 演示：端到端视频、答辩 PPT、失败案例
  - 目标：证据绑定 100%、引用精度 ≥85%、覆盖 ≥80%、专家评分 ≥4.0/5；均以实测为准
- **Closing impact**: 绑定结论为“把综述生成变成证据工作流”；最终页保留评审建议与下一步讨论入口，不放置空泛致谢页。

#### Slide 14 - 结论

- **Audience move**: 从听完方案 → 记住一句话并愿意给出改进意见或通过开题
- **Relationships**: none
- **Composition**: 大面积留白 + 一句主结论 + 三个小结论 + 底部“请评审指正”；采用图纸标题块收尾。
- **Title**: 让每一次综述结论，都能回到原文证据
- **Core message**: 这是一个可落地、可评测、可逐步扩展的可信科研辅助系统。
- **Content**:
  - 价值：降低综述整理成本，提升引用可追溯性
  - 方法：CrewAI 任务图 + 混合 RAG + 引用校验
  - 计划：24 周分阶段交付，三领域验证
  - 请求：请评审指正研究边界、评测设计和实施风险

#### Slide 15 - UML 用例视图

- **Audience move**: 从把系统功能理解为文字列表 → 看清参与者、系统边界和必需用例之间的 UML 关系
- **Relationships**: association — 研究者与主流程用例；association — 管理员与配置/监控用例；include — 生成综述必须包含检索文献与校验引用；external — arXiv/PubMed 作为外部参与者
- **Composition**: 左侧研究者、右侧管理员，中间系统边界；主流程用例沿上排展开，管理用例置于下排；include 关系用虚线箭头标出。
- **Title**: UML 用例：研究者的主流程与系统边界
- **Core message**: 用例明确谁发起什么，以及生成综述必须包含哪些系统行为。
- **Content**:
  - 参与者：研究者、系统管理员、学术数据库
  - 研究者用例：提交主题、生成综述、查看证据、编辑导出
  - 管理用例：配置数据源与模型、监控任务与重试
  - include：生成综述 → 检索并规范化文献；生成综述 → 校验声明与引用

#### Slide 16 - UML 类图

- **Audience move**: 从理解“claim–evidence–locator”概念 → 看到它在领域对象、字段和多重性上的具体落点
- **Relationships**: composition — ReviewProject 包含 ReviewDraft；composition — Paper 包含 Evidence；association — Evidence 支撑 Claim；association — Claim 绑定 Citation；association — Citation 指向 Evidence；composition — Draft 包含 Claim
- **Composition**: 上方横向展示 Paper → Evidence → Claim → Citation 的证据链，下方展示 ReviewProject → ReviewDraft 的项目结构；多重性标在连线上。
- **Title**: UML 类图：证据、声明与引用的关系
- **Core message**: 类图把可追溯性落到数据对象和多重性上。
- **Content**:
  - Paper：paperId、title、doi、year
  - Evidence：evidenceId、quote、locator、confidence
  - Claim：claimId、text、section、supportScore
  - Citation：citationId、styleKey、locator
  - ReviewProject、ReviewDraft：项目版本与报告结构
  - 关键关系：Paper 1 *-- 1..* Evidence；Evidence 0..* -- 0..* Claim；Claim 1 -- 1..* Citation；ReviewProject 1 *-- 0..* ReviewDraft

#### Slide 17 - UML 顺序图

- **Audience move**: 从知道系统有哪些模块 → 看清主题输入、检索、生成、校验和失败回退在时间线上的交互
- **Relationships**: order — 从研究者输入到报告完成的消息顺序；link — 各参与者之间的同步调用与返回；alt — 引用校验通过/不通过的分支
- **Composition**: 顶部六个参与者生命线，主体按时间从上到下排列；校验分支用 alt 框包住，返回消息用虚线箭头。
- **Title**: UML 顺序图：从主题输入到引用校验
- **Core message**: 顺序图把主流程、返回值和失败分支放在同一条时间线上。
- **Content**:
  - 参与者：研究者、Web UI、编排器、检索/RAG、撰写智能体、引用校验
  - 主流程：输入主题 → 创建任务 → 检索证据 → 生成初稿 → 校验引用 → 返回报告
  - 失败分支：unsupportedClaims → 定向改写或补充检索 → 重新校验
  - 工程映射：REST 创建任务、SSE 推送进度、证据库持久化

## X. Speaker Notes Requirements

- **Generation**: enabled
- **Filename**: match each SVG filename under `notes/`
- **Content**: 每页以“结论先行 + 一至两个支撑点 + 过渡句”组织；引用报告事实，不添加新的研究结论；对目标值说明“为项目初期目标，最终以实验为准”。
- **Total duration**: 10—12 分钟主汇报 + 3—5 分钟 UML 附录问答
- **Notes style**: 正式、清晰、略带讲解感；关键页给出一句可直接口述的过渡。
- **Presentation purpose**: 让评审理解并认可“CrewAI 多智能体 + 可追溯 RAG”的选题价值、技术可行性和 24 周实施计划。


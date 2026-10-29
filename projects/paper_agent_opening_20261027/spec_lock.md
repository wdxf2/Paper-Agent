<!-- ppt-master-schema: spec-lock/v1 -->
# Execution Lock

## canvas
- viewBox: 0 0 1280 720
- format: PPT 16:9

## communication
- primary_language: zh-CN
- audience: 软件学院开题答辩老师、评审专家及同组同学
- objective: 论证以 CrewAI 多智能体与可追溯 RAG 生成科研综述的选题价值、技术可行性和 24 周实施计划，使评审理解并认可项目可继续推进。
- core_message: 把文献综述从一次性生成改造成“任务图 + 证据绑定 + 引用校验”的可追溯工作流。
- consumption_mode: balanced

## mode
- mode: custom
- mode_references: pyramid, instructional
- mode_behavior: 结论先行：开场直接给出“可追溯工作流”的项目判断；中段按检索、分析、对比、写作与校验顺序拆解机制；结尾回到可行性、评测和实施计划，以明确结论收束。

## visual_style
- visual_style: custom
- visual_style_references: blueprint
- visual_style_behavior: 工程图纸式细线网格与精确对齐；矩形和线框承担结构，深青线条构成系统骨架，琥珀色只标记当前关键路径或风险；标题为粗体判断句，正文中性克制，强调可读性而非装饰。

## colors
- background: #F7F9F6
- secondary_bg: #E8EFEA
- primary: #0E3B43
- accent: #D97706
- secondary_accent: #2F6F7E
- body_text: #1F2933
- secondary_text: #5B6770
- divider: #BED0C5

## typography
- font_family: Microsoft YaHei, Arial, sans-serif
- title_family: Microsoft YaHei, Arial, sans-serif
- body_family: Microsoft YaHei, Arial, sans-serif
- body: 24
- title: 46
- subtitle: 26
- lead: 30
- annotation: 18
- footnote: 14
- display: 64

## icons
- library: tabler-outline
- stroke_width: 2
- inventory: tabler-outline/search, tabler-outline/database, tabler-outline/binary-tree, tabler-outline/link, tabler-outline/shield-check, tabler-outline/layout-dashboard, tabler-outline/checklist, tabler-outline/target-arrow, tabler-outline/calendar, tabler-outline/file-text, tabler-outline/report-analytics, tabler-outline/robot, tabler-outline/network

## page_rhythm
- P01: anchor
- P02: dense
- P03: breathing
- P04: dense
- P05: dense
- P06: dense
- P07: dense
- P08: dense
- P09: dense
- P10: dense
- P11: dense
- P12: dense
- P13: breathing
- P14: anchor
- P15: dense
- P16: dense
- P17: dense

## pptx_structure
- mode: flat

## forbidden
- `mask`, `<style>`, `class`, external CSS, `<foreignObject>`, `textPath`, `@font-face`, `<animate*>`, `<set>`, `<script>` / event attributes, `<iframe>`
- HTML named entities in text; write typography as raw Unicode and escape XML reserved characters



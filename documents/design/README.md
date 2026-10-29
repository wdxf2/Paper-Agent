# 开题报告 UML 设计材料

本目录保存《基于多智能体协同的科研文献智能综述生成系统》开题报告中的 UML 图源文件与渲染图。

## 文件清单

| 源文件 | 渲染图 | 报告中的图号 | 用途 |
| --- | --- | --- | --- |
| `uml/use_case.puml` | `uml/use_case.png` | 图 1 | 系统用例图 |
| `uml/component.puml` | `uml/component.png` | 图 2 | 系统组件图 |
| `uml/activity_rag.puml` | `uml/activity_rag.png` | 图 3 | RAG 与引用校验活动图 |
| `uml/domain_model.puml` | `uml/domain_model.png` | 图 4 | 综述项目领域类图 |
| `uml/evidence_model.puml` | `uml/evidence_model.png` | 图 5 | 证据、声明与引用类图 |
| `uml/sequence.puml` | `uml/sequence.png` | 图 6 | 综述生成顺序图 |
| `uml/class_model.puml` | `uml/class_model.png` | 备选 | 完整类图备选版本（含 SearchingPlan、Chunk 等扩展实体） |

## 重新生成图片

使用 PlantUML 1.2026.9 或更新版本：

```powershell
# 先下载 PlantUML 1.2026.9 或更新版本的 plantuml.jar，并将 $jar 指向该文件。
$jar = "C:\tools\plantuml.jar"
$dir = "E:\learning\courses\Paper-Agent\documents\design\uml"
Get-ChildItem $dir -Filter *.puml | ForEach-Object {
    java -Dfile.encoding=UTF-8 -jar $jar -charset UTF-8 -tpng -o $dir $_.FullName
}
```

若只修改某一张图，可直接指定对应的 `.puml` 文件。中文标签使用 Microsoft YaHei，Windows 环境可直接渲染。

## UML 建模约定

- 用例图：参与者置于系统边界外；`<<include>>` 表示基用例必然执行的复用行为；外部学术数据库作为参与者处理。
- 组件图：组件表示可替换的软件单元，依赖箭头表示编译期或运行期依赖；不把数据流误画成 UML 用例关系。
- 顺序图：实线箭头表示同步消息，虚线箭头表示返回消息；`loop` 表示检索循环，`alt` 表示校验通过/失败分支。
- 类图：标出关联多重性；实心菱形表示组合关系；领域类名与后端数据对象保持可追踪。
- 活动图：使用泳道、判定节点、循环回边和终止节点，表达 RAG 从采集到发布的控制流。


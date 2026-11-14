# 固定 CPU 研究协议阅读

研究页对已登记的 `research.retrieval-fixed-pair`、`research.relevance-fixed-pair`、`research.weighted-interval-fixed-pair` 展示原方法与捕获范围，点击“读取固定协议摘要”再加载协议摘要。这里没有 CSV/Ridge 绑定、改进或导入操作，也不会自动请求表格设计目录。其他方法沿用现有设计编辑路径。

`GET /api/project/fixed-protocol.json?project_id=<原项目ID>&snapshot_ref=<原64位快照SHA>` 返回 `fixed-cpu-protocol-view-v1`。两个选择器必须各出现一次且非空；查询最多1024 UTF-8字节。不接受路径、方法或执行参数。读取前后核对宿主绑定项目与快照，变化返回409；其他方法返回404且不读取其来源。非法选择器返回400。

读取器核对原项目的 `source.json`、注册SHA、原生适配器schema、来源快照与范围。它不依赖报告或已完成行动，不创建项目、推进控制器、排名、评分、拟合或求解。服务仍会读取并验证完整的有界来源；减少的是响应传输，不是承诺减少来源验证工作。

响应最多128 KiB，包含以下字段：

| 字段 | 含义 |
|---|---|
| `binding` | 原项目、run、快照、state版本、primary方法、**原项目保存的**代码身份、来源快照和原文件SHA，共8字段 |
| `adapter_version/evaluation_ref` | 对应原生固定方法的版本及评价合同 |
| `source_spec_identity` | 原spec字节数和SHA |
| `declared_spec` | schema、数据名、来源、署名、许可声明、provenance、文件声明、comparison、limits，共9字段 |
| `scalar_scope` | 原范围中的JSON标量；不传大数组或嵌套输入身份 |
| `input_identities` | 每个原资产的字节数与SHA |
| `splits` | 检索的声明查询数与**原有序ID数组**的canonical JSON SHA（`fingerprint(ids)`），或调度的原case/job分组计数 |
| `projection_notice` | 省略内容与机械核验边界 |

查询数组、原文、Base64、完整jobs和缺失正例ID列表不随摘要传输；原完整输入和历史报告保留。声明分区计数不是实际完成次数，不能由摘要推断研究已执行或成功。捕获的许可/provenance也不等于独立许可审查、科学批准或sealed评价。

来源缺失、变化或过大保留原生错误。当前网关将服务生成的过大摘要 `READER_TOO_LARGE` 映射为500；它不应被显示为成功或空协议。失败可重新读取同一项目，不触发研究重算。旧项目即使因代码身份不同而禁止编辑，仍可只读查看原协议；不升级其producer或重开预算。

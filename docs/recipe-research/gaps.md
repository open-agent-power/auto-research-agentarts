# 已知、未知与会改变下一决定的材料

核查日期：2026-11-03；共同代码基线：`7e8ffd90ed6826df7ea1487660645152b533045a`。本次只读补件、更新缺口并复用原工程记录，不扩展综述、不重跑测试或研究行动。原数据、历史 context/运行目录和第三方全文不提交。既有三项来源及支持范围见 [sources.csv](sources.csv)。

## 已经知道

- 原宿主只允许从封印 context 的合法候选中选择，方法参数、预算、科学评价由宿主维护；配方只能改变有限候选的优先顺序。
- 已收到 `队友补件-科研配方-20261103.zip`，151,403 bytes，SHA-256 `ab7649c4db5e93629551c7ebea4db0f6c9db1b7fe2a66a21c7ea6cf783a9c780`。只读 ZIP 条目与保存结果，没有执行附件代码。此前“未取得 CSV/spec、保存结果和 11 月 1 日笔记”的记录已被本补件更新，不再作为当前缺口。
- 默认真实案例改为 **hiMSC（A16 / himsc-final）**。钢材 A16 CSV/spec/source/quality 也已收到：312 行，目标 `yield_strength_MPa` 零值为 0，范围 1005.9–2510.3 MPa。CSV 是宿主对 Matbench gzip 两列按原序投影并重命名目标，不是作者原始发布的 CSV；不混用 A18 spec。钢材仅作为目标无零的输入条件对照。
- 代码 [`datasets.py`](../../src/autoresearch/datasets.py) 的 `_parse_composition` 对未在公式出现的元素使用 `amounts.get(element, 0.0)`。这是派生特征规则，不能解释 hiMSC 的目标零值，也不证明实验测得元素绝对不存在。
- 原有固定与条件选择比较见 [`policy-comparison.md`](../policy-comparison.md)：限定任务没有观察到优势。本轮不重跑旧比较，不把工程配置分歧写成收益。

## 补件身份与已保存反馈

以下路径均为 ZIP 内相对路径，哈希是**文件原字节 SHA-256**；原件留在本机，不随 PR 公开复制。

| 条目 | SHA-256 |
|---|---|
| `inputs/steel/data.csv` | `309f9e652ab9e4a49d701e9e9b09c7fa16a03489734379fdff65a83722d735f0` |
| `inputs/steel/spec.json` | `85bfde65e0bd589f12bc97b27e4e18ea4f435a9896c9260b49aa85cc39f12276` |
| `inputs/himsc/data.csv` | `880485da61b3d850dc53d03746b7f6068229bf2ec94d510a69fa0c45f049118b` |
| `inputs/himsc/spec.json` | `321850eb218e2289c23fddfe45d58e807007748012084cd0806629ba533de7de` |
| `saved-results/himsc-quality.json` | `1f339a7e145a9f12a85724aa3e6145476cc857f19d9c77a95c7587bfba84dc56` |
| `saved-results/himsc-grouped.json` | `41b3de848dd5a13ae9966e1c8acfa15d791125dc22856ae1148c4e3842e5b3eb` |
| `saved-results/himsc-source-selection.json` | `573b3eca932c1c2fc06006991f9ba26c8cf47b8195bde7d4df808483160b356d` |

hiMSC 的 `source.json` 声明来源为 Mendeley 数据集 `57nrc49stj/1`；原工作簿声明 SHA-256 为 `690c8eaf745e817f99bd7f2910bb0339ac0dea3e2c8dc1df6aa2153b03c348fe`，来源包快照为 `a5c138e33d60644e050191f94be1bc20134f6c61620436e95361536318c42ba2`。本次未取得完整原工作簿，也未重新在线核验许可；归档中的 CC BY 4.0 仅作为来源声明，不据此公开复制数据。

投影范围为 **B8S1!A1:F973 的已保存单元格**，972 条数据记录，第 n 条对应原表第 n+1 行；不求值公式、不删除 0 或重复行，空单元格保留为空。字段为 `Topo`、`Chem`、`Coordinate`、`Count`、`Mean_Red_Intensity`、`Mean_Green_Intensity`。这不是作者直接发布的原 CSV。

保存结果给出的机械统计：三个数值列 `Count`、`Mean_Red_Intensity`、`Mean_Green_Intensity` **各有 59 个零值**；声明的 `Topo/Chem` 分组为 **288 组**，每组 3–6 行，完整重复的额外记录为 **3 条**。保存分组结果中，各数值列的零值分别落在 **56 组**，单组最多 2 个。相同零值数量不能证明逐行共现或成因一致；本轮没有重算联合分布。这些计数也不证明实验批次、独立重复或零值编码意义。

| 保存反馈 | action ID | result 内容封印（不是上述文件字节哈希） |
|---|---|---|
| 主质量 | `action-facaebadfa80797142cff0d676050118` | `188feabce012db6950665c254be9cc00679032e829818b074b22a975799c9c28` |
| 分组质量 | `action-bcccd8ce0641fb66f5add2d4cffd836d` | `6a678b651f27cc3a23e956d998c9ae5493f8d5cea50c21d42d3716a42b144ce8` |

分组反馈的 predecessor 绑定上述主质量 action/result。主质量与分组的代码身份分别为 `b6fbe14b6308d4c4b99fee3faea2123f037ff2442b23c6fead7570bd9e8bc0c5`、`09032982c3bf0a575ef46dff6c5bd5fd4f41407017f40cf40d412a4dee451a6b`。这里只核对已保存链路，不宣称在当前代码上重新执行。

`research.source-selection` 的保存行动 `action-167ef41a26d982e38c0a8daeda77dde0` 只抽取了**宿主 spec 的声明**（`text_lines` 1–28），不是作者采集/导出说明。结果仍为 `mapping_status=unresolved`、`endpoint_eligibility=unknown`、`scientific_validation:false`。目标 `Mean_Red_Intensity` 的单位为 `unknown raw intensity proxy`，`target_status=declared_unconfirmed`，不能改称 ALP 或已获科学批准的终点。

11 月 1 日的 `research-notes/README.md`、`evidence/01-workflow-optimization.md`、`02-science-evaluation.md`、`03-transfer-rag-rsi.md` 和 `sources.json` 已收到。README 及三份 evidence 文件 SHA-256 依次为 `84006977190903cb6d08f29336c8504b4f1a5b218bfdc7452c9932c0997f05d6`、`974b7f90cb5ebe17e3a5e002b3ae5215d871101cd3d504308e4ebee4e33e5be8`、`90d0de4bf2eb70aae019e05012032cf60bbcdd102ccbe3fa5dbd62b10d65580d`、`602e3de101d9209a2a783e09a33940b5ad4c126b30a37bd15a9f1b8f84593b63`。仅用于核对既有设计的支持边界；协议通过、合法引用和来源抽取都不等于科学结论，不引入新综述。

## 仍然不知道，补什么才会改变决定

| 缺口 | 已检查位置/材料 | 需要谁给什么 | 取得后会改变什么 |
|---|---|---|---|
| hiMSC 零值的采集或编码意义 | 已有 CSV、质量和分组计数；source-selection 仅回读宿主声明，映射未解 | 数据负责人/作者给此工作簿版本的采集、计数为零时强度导出、缺失/检测下限规则及原文定位 | 才可能区分真零、缺失、计数条件或导出占位；目前原因未知，不改值、不删行 |
| 试样、重复与分组定义 | Topo/Chem 声明 288 组；完整重复额外记录 3 条，不能据此解释其原因 | 领域队员/作者给 Coordinate、重复测量、独立实验和批次映射及重复记录来由 | 决定可否将声明组用于科学比较；Topo/Chem 组合不能直接当独立批次 |
| 红色强度的单位和终点资格 | spec 明示 unknown raw intensity proxy、declared_unconfirmed | 该版本字段字典、染色/测量与归一化说明，及领域核对 | 才能解释强度及终点适用性；不能自行叫 ALP，当前 endpoint_eligibility 仍 unknown |
| 原始工作簿与来源许可核验 | 已有投影范围、原工作簿声明哈希和来源快照；完整工作簿未交付，许可未在线复核 | 可分享原工作簿或对应单元格/导出说明，以及原来源许可页 | 核对保存单元格与导出规则，不将宿主转换误当作者发布；不阻塞本轮工程审阅 |
| 真实策略分歧、领域反馈与公平收益 | 已交三个历史 context 只有 0/1 候选；无领域确认，人工耗时未测 | 后续若要评价收益，先冻结未见真实任务、相同资料/工具/预算和专业评判方案 | 决定是否有帮助；当前不能从工程夹具或不同历史状态推导真实优势 |

## 一条完整的真实反馈记录

问题及原件：hiMSC 的 Count 和红/绿色强度中的零值各表示什么，声明分组是否有实验含义？使用上述 A16 / himsc-final 投影及已保存反馈，完整工作簿未取得。

输入与检查：2026-11-03 只读补件，核对 ZIP 条目字节哈希、投影声明、保存质量/分组结果、前序绑定、来源抽取内容与历史 context；没有重新运行质量、分组或 source-selection 工具。

反馈及出处：保存质量/分组反馈提供了 972 行、各列 59 零、288 组及零值分布；保存 source-selection 仍不能解决来源到字段的语义映射。数据身份与机械分布缺口关闭，采集/导出解释和科学判断没有关闭。这不是作者或领域队员的私下确认。

反馈前下一决定：先找对应 CSV/spec 和已有结果，再考虑是否需要按声明组数零。

反馈后下一决定：已有分布不能解释零值成因，下一份有效材料应是该版本采集/导出说明或针对具体字段的领域核对；不重复索要已收到文件，不为得到结论再读一遍同份宿主 spec，不补值、不删行、不运行旧模型。此为取证建议，不是未经当前 context 授权的可执行提案。

核对者和范围：开发助手只读核对身份、保存计数与链路；没有老师、作者或领域队员确认零值、重复记录、分组独立性或终点意义。**零值原因未知**。

是否有帮助：补件减少了“文件尚未取得”和“分布尚未读取”的取证缺口；是否改善真实科研决定仍无法判断，不凑正面结论。

成本：本次仅本地读取、哈希与文档更新；新增研究行动、模型、拟合、付费/云调用均为 0，读取/核对有 I/O 与人工成本，耗时未测量。保存结果是历史行动，不计为本轮新执行；原工程夹具的两次工具行动仍单独保留，历史成本及现金结算未知。

## 历史 context 不构成真实双候选

同一历史项目 `project-65671214b80b43f5beef174101b11a4e` 的原样 context 如下。封印均指 context 内容封印，不是文件字节哈希；只读，不改 context 或提交过期提案。

| ZIP 内 context | state_version | 合法候选 | 内容封印 |
|---|---:|---|---|
| `contexts/himsc-before-source.json` | 5 | 1，source-selection | `7406fd62ff1563f672533e860e0290e7055d9c50a65dd430b84a05b888600158` |
| `contexts/himsc-no-candidate-after-source.json` | 9 | 0 | `12e296e75ef9791852577e604d56b0499327c922fc8732dc05d1a3ff4715351f` |
| `contexts/himsc-before-grouped.json` | 11 | 1，grouped-quality-profile | `dd36a122a26b5c090ee430d0f873a4fef21c7b2a2931d0cc142d3993d9d02a47` |

三个不同状态不能拼接成同一真实双候选，不能证明两配方在真实任务上产生分歧或收益。工程双候选证据继续使用原人工夹具；不编辑历史 context、不换项目重置预算。

## 反例与停止条件

1. 钢材目标没有零，派生组成特征有零；两者不能混为同一问题，更不能解释 hiMSC 强度的零。
2. `group_columns=[]`、组成组或 hiMSC 的 Topo/Chem 声明组，均不能自动解释独立实验/批次。分组无合法候选就看下一项，全部不匹配则 wait。
3. materials/保存模型项目不是 data/tabular-quality-v1；即使同名也不能绕过范围检查。历史 context 或无候选状态不能手工增加候选。
4. 来源读取成功只说明按协议抽取了内容；宿主 spec 不是作者导出说明。引用只能支持对应版本和具体声明。当前保持 `mapping_status=unresolved`、`endpoint_eligibility=unknown`、`scientific_validation:false`。

当前三项来源已足够限定一次工程选择与上述反例，停止扩展综述。GEPA v2、迁移/RAG/RSI 的泛化及自改进尚未纳入本次证据，不能写成本轮已验证能力。

## 交付与最小后续材料

此前目录/ZIP 续查未找到材料是补件前的历史事实，不再代表当前状态。CSV/spec、保存结果/context 和 11 月 1 日笔记已经到位；不重复索要，不扩大检索。

当前只需针对**这份 hiMSC 版本**补充可定位的采集/导出规则、字段单位与终点说明，以及分组/重复定义的领域核对。原因查不清则保留未知；不要求为了本轮 PR 重跑真实研究或补造双候选。

工程原型已有依赖说明 PR #1 的 PR #2；复用原 9 项专项测试、人工双候选、实际执行与相同父请求重放记录。原前端 format/lint/typecheck 均退出 0，format 为 32 文件、0 改动；初次缺依赖和 UNSAFE_PATH 失败保留。**本次未重跑以上测试、门禁或实验**，仅检查文档差异和附件身份。运行目录/SQLite/真实数据不提交，PR 附原人工夹具证据供审阅；工程通过不改变真实科学效果未知的结论。

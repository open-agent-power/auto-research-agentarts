# hiMSC：零值与作者图像元数据核对

2026-11-04。当前结论：宿主 CSV 与原工作簿保存值一致，但新增作者元数据有 **216 条相同行序记录的化学编号不同**。A32 已找到作者材料标签的对应线索：工作簿的 Chemistry 0 标为 TMPMP/TEGDA，论文编号 28 标为该 Base。完整的图像、对象导出与工作簿连接仍未建立，不能据此自动换码；保留原值，继续核对适用版本与运行来源。

## 这次取得了什么

从 [Nottingham 作者数据条目](https://doi.org/10.17639/nott.7080)取得此前本地未捕获的 [CTC_Image_Metadata.xlsx](https://repository.nottingham.ac.uk/server/api/core/bitstreams/015975e6-a155-446b-93c8-473aab87c976/content)。它有 20 张工作表、70,056 个保存单元格、无公式；其中 `iMSC_B8S1` 有 972 条数据，表头为 `Series/Topo/Chem/Row`。仓库描述其用途是记录原 `.czi` 图像的化学和纹理信息，并说明原图需联系作者。

本次比较的文件身份固定如下；CSV 是宿主投影，作者文件的原发布入口分别为 Nottingham 和 [Mendeley V1](https://data.mendeley.com/datasets/57nrc49stj/1)。

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| 宿主 `data.csv` | 51,633 | `880485da61b3d850dc53d03746b7f6068229bf2ec94d510a69fa0c45f049118b` |
| 作者 `hiMSC_Raw_Data.xlsx` | 1,281,702 | `690c8eaf745e817f99bd7f2910bb0339ac0dea3e2c8dc1df6aa2153b03c348fe` |
| 作者 `CTC_Image_Metadata.xlsx` | 440,330 | `2600412f5ea578933a13c9d9051a82d69c6f5e55377951ae9a7ef39cdffe05fb` |

## 已能直接核对的事实

CSV 的 972 条记录、6 列、5,832 格全部与 `B8S1!A2:F973` 严格对应；4,860 个数值保留原 XML 缓存文本，972 个文本保留解码内容。没有用舍入、补值或重排行取得一致。

逐行检查三列 `Count/Mean_Red_Intensity/Mean_Green_Intensity`，59 条记录三列同时为零，其余 913 条三列均非零；没有仅部分列为零的记录。这一结论来自逐行联合掩码，原来的“各列都是 59 个零”本身不能证明共现。

元数据的 `Series` 保存值为 0…971，`Row` 为 1…9，各出现 108 次。原始数据没有这两个字段，`Coordinate` 972/972 条均为 `Topo_Chem` 标签。`Row` 的保存值不能充当 CSV 行号。

## 216 条化学编号差异

按相同行序核对 `Topo/Chem`，756/972 条两键相同，216 条不同。全部差异都是原表 `Chem=0`，元数据同序位置 `Chem=28`：

| CSV 数据记录号 | 两工作簿中的行号 | 元数据保存的 Row | 差异条数 |
|---|---|---:|---:|
| 433–540 | 434–541 | 5 | 108 |
| 865–972 | 866–973 | 9 | 108 |

可直接查看的例子：原工作簿 `B8S1!A434:C434` 为 `Topo=1, Chem=0, Coordinate=1_0`；元数据 `iMSC_B8S1!A434:D434` 为 `Series=432, Topo=1, Chem=28, Row=5`。这里比较的是保存位置和字段值，尚没有实际图像文件或对象导出将两行绑定。

59 条全零记录中，42 条同序两键相同，另 17 条落在第一块编码差异区。元数据没有 `Chem=0`，这 17 条按原 `Topo/Chem` 没有候选。不能自行把 0 改为 28。

即使两键相同，连接也有多解：元数据的 288 个 `Topo/Chem` 键全部重复，最多 6 条候选；加上 `Row` 后的 324 个键仍全部重复，最多 3 条候选。连续且唯一的 `Series` 只建立了保存序数的关系，尚不是已确认的采集 frame 或对象导出 ID。

## 公开原件查到了哪里

Nottingham 首页只展示两件文件。本次沿实际 `next` 链接核对 5 页、每页 2 件，最后没有下一页，取得全部 10 件 `ORIGINAL`。再沿条目的 bundle 链接核对，三个 bundle 共 18 条：`ORIGINAL=10`、`LICENSE=1`、`TEXT=7`；库端派生文本与作者原文件分别保留。

Mendeley V1 的目录响应为空，根文件接口返回 6 件，低于其实现的 1,000 件翻页条件，已到末尾。两处指定目录没有独立列出的 `CellsGreen/CellsRed/Image` CSV 或单独的运行导出说明。原 `.czi` 没有取得，本轮未联系作者。这项清单结论不覆盖作者私有文件、其他网站或管线内部可能保存的内容。

当前 Nottingham 条目和 Mendeley V1 标注 CC BY 4.0。原 URL、日期、页面、接口分页与收据在本机 [public-sources](../runs/a31-source-linkage-20261104/public-sources/)；Tavily 调用与普通 HTTP 分开记录，检索服务结算未知。

## A32：作者材料标签补充

同一固定 SHA 的 `hiMSC_Raw_Data.xlsx`，作者汇总表 `DataForClustering!A1:D3` 提供了直接标签：B1 为 `Polymer`，D1 为 `Chemistry`；A2:D2 为 `2_0 / TMPMP/TEGDA / 2 / 0`。这明确说明该作者表中的 Chemistry 0 对应材料名称 TMPMP/TEGDA。原论文 PDF 第5页 Fig.2 的结构图明确标出 `28) Base:`，并列出 TMPMP 和 TEGDA；已提取原图、渲染整页并实际看图确认，原文身份与入口见[论文核对](p02-mapping-audit.md)。

因此，“原工作簿的 0 与论文编号 28 都指向这一基材”已有作者材料名称支持，不再是完全没有出处的编号猜测。适用范围是该原件的作者汇总标签及该论文的图示编号；仍未取得作者直接说明“本版原始行 Chem 0 应转换为 metadata Chem 28”的规则，也没有把汇总标签、`B8S1` 原始行及实际图像逐一绑定。A31 的 216 条差异、其中 17 条全零和总计 59 条全零记录仍原样保留，不能自动执行 0→28。

为查找补充标签，沿 A31 已观察的 Nottingham content 和页面 download 链接尝试取得 `MacrophageData_ForPaper_withLabels.xlsx`，两次均返回 HTTP 500，未取得该文件。第二次的 210 字节错误原文、UTC/URL/响应头与身份已保存；首次只保留异常状态，未补造缺失的响应。此结果不证明文件或相关作者资料不存在，也未用命名相近的 hMSC 原件替代当前 hiMSC，未把 feature ID 说明当作 Chem 字典。

本轮局部取证没有重跑旧数值审计、求值公式或执行作者代码，出处和边界见本机[编码证据](../runs/a32-current-evidence-report-20261104/encoding-evidence/evidence.md)与[机器记录](../runs/a32-current-evidence-report-20261104/encoding-evidence/evidence.json)。材料命名线索不确认 ALP、测量单位、零值原因或独立样本。

## 下一份材料要回答什么

1. **材料命名线索能否用于本版行对应。** 已有 Chemistry 0=TMPMP/TEGDA、论文 28=Base 的作者标签；仍需针对上述两块各 108 条记录的编码/版本说明，明确它们与 metadata 的关系，是否允许逐行对应。
2. **从保存行到实际导出。** 请解释 `Series/Row` 的含义，提供原图文件、图像/对象 ID、实际 `CellsGreen/CellsRed/Image` 列头与样例，再连接到 `B8S1` 行。单靠标签或行序不能唯一连接。
3. **全零如何产生。** 请针对 59 条原坐标解释 Count 和两强度的赋值规则，区分无对象、有效零、缺失替代、检测下限及 QC。共现本身不决定原因。
4. **红色强度的测量身份。** 请给出同次运行的靶标、染料、采集通道、对象/图像特征、背景和归一化处理及单位。已有[论文方法与保存配置](p02-mapping-audit.md)仍作为部分证据。

团队可以直接带着 [zero-rows.csv](../runs/a31-source-linkage-20261104/linked-audit/zero-rows.csv)、[zero-metadata.csv](../runs/a31-source-linkage-20261104/linked-audit/zero-metadata.csv)和差异坐标核对；不需要再索要已经取得的原工作簿或重跑旧模型。

## 怎样复现

复用现有只读 ZIP/XML 工作簿读取器，不增加依赖、不执行公式或 CellProfiler。输出目录必须尚不存在：

```powershell
.venv/Scripts/python.exe -B scripts/inspect_himsc_source_linkage.py --csv runs/a16-tabular-20261103/inputs/himsc/data.csv --workbook ../../references/auto-research/10-chemotopochip/2026-10-31/hiMSC_Raw_Data.xlsx --metadata runs/a31-source-linkage-20261104/public-sources/CTC_Image_Metadata.xlsx --output runs/my-himsc-source-audit
```

输出 `audit.json/README.md/zero-rows.csv/zero-metadata.csv`。全部原格、差异和多候选在 JSON 与 CSV 中。命令发现不完整对应时保留结果并非零退出。本轮 `linked-audit` 的 `ok=false` 是 216 条差异的实际结果，不能写成完整连接已通过；工具观察退出 1，未单独捕获 native 退出码，详细记录见 [execution-observations.json](../runs/a31-source-linkage-20261104/linked-audit/execution-observations.json)。

一项必要测试使用“各列零数相同但分别出现在不同行”的小 CSV/XLSX，并包含错行、重复键及重复 Series 反例。测试通过与实际数据拒绝完整连接分别记录。原先不带 metadata 的 [local-audit](../runs/a31-source-linkage-20261104/local-audit/)结果保留，未以新目录覆盖差异。

## 同一研究项目的接续

A31 沿用 A30 的 [18793 项目](http://127.0.0.1:18793/#/research)，从 v12 的等待继续。先登记新证据，再由原 `tabular-group-first` 配方选择新来源。首次文本选区误用冒号语法，产生终结的 `INVALID_LOCATOR` 失败并计次；保留原收据后，按正式 `N/N-M` 格式登记修正选区，在同一项目读取完成，A31 结束时为 v23、再次等待。原声明的 A31 一次读取上限，在修正前通过独立记录改为两次尝试；核心累计上限仍为 8，没有重置预算或替换项目。

A31 来源累计为 **3/8**：A30 成功一次、A31 失败一次和修正后成功一次。本地数值工具仍 2/2，未派发项目模型或拟合；五个原登记/读取/等待 ID 重放均不改变状态、行动或预算。对 `Series` 和 `216` 的只读 FTS 检索已能返回新增作者元数据和明确标为操作者派生的摘要，当时选择上下文也含新增引用；这不表示模型已读取。

A31 当时的四文件报告包保留六次配方决定、原失败、修正收据、作者原件、完整审计/坐标表及审计源码附件。四个 HTTP 下载与保存文件一致，18 份捕获附件逐字节核对，六页 PDF 已逐页检查。原 A30 报告保持原样，较早的钢材、hiMSC、A25/A27/A29 项目及用户原有修改未改。

A32 在同一项目成功读取上述新增作者标签证据一次，读取完成时为 **v28、source 4/8**；新增数值行动、模型调用及拟合均为 0，本地数值工具保持 2/2。它推进的是编码语义的来源核对，没有修改原表、完成图像唯一连接或确认科学终点。

原项目随后仅为新检索代码显式升级到v29，再按原配方等待至v30，没有新的子行动或额度变化。新索引优先后，默认5条引用含3条新材料证据；四个原登记/读取/升级/等待ID重放均不改变状态或用量。当前8页PDF首页呈现本次主张与未决问题，四文件经18793下载核对、23份输入附件逐字节核对，旧报告保持原样，见[A32结果](../runs/a32-current-evidence-report-20261104/README.md)。

## A37：默认查询遗漏了已保存的编号冲突

hiMSC v30的默认解释上下文没有返回`metadata-conflict`，但原索引中保留着该片段。同一冻结索引只读查询`Chem 28`能找回`iMSC_B8S1!A434:D436`，其中C434的保存值为28；原引用ID仍为`cea5e743b421551e51dce464c994dcf3189741182590b982045bbfbaff5ee342`。这次未发现引用窗口剪掉目标值：知识片段窗口为1400字符，解释引用上限为4000字符。

保存的首个未决问题含`Chem0`和`Chem28`。原问题原样检索没有返回冲突片段；保留原问题并追加`Chem 0 / Chem 28`别名后，同一5条结果能包含原冲突引用；拼接宽泛的基础问题不能解决该缺口。查询对比见[query-comparison.json](../runs/a37-source-quote-window-20261104/query-comparison.json)。默认查询的通用契约见[资料进入研究循环](knowledge.md)，不为hiMSC硬编码字段或换码规则。

原项目显式登记兼容代码后为v31，默认5条上下文已含上述原冲突引用与作者命名线索；quote、位置和原件SHA与冻结索引一致，三个索引未重建。升级原ID重放不改变状态，本地2/2、来源4/8和host日志保持原样，未追加模型、拟合或来源行动。3项定点检查与必要前端门禁通过，见[A37核对](../runs/a37-source-quote-window-20261104/validation.json)。原A32报告随代码身份升级已过期，本轮没有重导PDF；旧服务尚未重启载入修复。

找回原文方便队员同时核对作者命名线索与原始冲突；它不消除Chem 0与28的版本和逐行对应疑问，不修改任何零值、编号或原表，也不构成科学批准。

## A38：已保存的导出配置，尚缺实际运行连接

作者归档的[`hMSC_Analysis.cpproj`原件](https://data.mendeley.com/public-files/datasets/57nrc49stj/files/9ba7a96b-c903-4e9c-b8d7-30681b57f192/file_downloaded)含已保存的`ExportToSpreadsheet`配置。该父文件为1,718,802字节，在字节偏移475730与507314各有一段相同的31,568字节ASCII文本；本次取第一段，仅将字面`\n`转换为换行，其他转义保持原样。完整父文件身份、区段和配置记录见[projection.json](../runs/a38-delegated-source-20261104/projection.json)。没有反序列化HDF，也未启动CellProfiler或执行作者源码。

投影文本[372–395行](../runs/a38-delegated-source-20261104/bundle/sources/pipeline-static.txt#L372)保存的设置为：

| 设置 | 保存值 |
|---|---|
| `ExportToSpreadsheet`模块启用 | `True` |
| 计算每幅图像的对象测量均值／中位数／标准差 | 均为`Yes` |
| 导出所有测量类型 | `Yes` |
| `Representation of Nan/Inf` | `NaN` |
| 文件名前缀 | `B10Pos` |

这些配置此前已经归档，A38将其作为明确标注的派生文本资料，新登记到同一hiMSC项目v32，形成合法来源候选；登记内容与选区见[资料包清单](../runs/a38-delegated-source-20261104/bundle/manifest.json)，转换方法与父文件出处另存于[provenance.txt第1–10行](../runs/a38-delegated-source-20261104/bundle/sources/provenance.txt#L1)。这份资料约束了零值解释需要核对的环节：保存设置写的是`NaN`和`B10Pos`，若要解释B8S1的Count及双强度为0，仍需对应的真实运行、导出和工作簿转换记录。

尚未建立这份保存配置与B8S1实际运行的对应，不能据此写成“导出把NaN变成0”，也不能批准ALP通道身份或Chem 0→28换码。CellsGreen／CellsRed／Image导出与B8S1、图像对象、Series／Row及单位的唯一连接仍需原始记录。

A38随后实际派发一个子代理，只向其提供冻结context/prompt。原回答引用作者汇总标签、Fig.2操作者视觉记录和来源核对摘要三项，选择唯一合资格来源；未直接引用C434单元格本体，不能据此推断内部注意力或完整证据使用。原回答未经改写导入，再由原控制器完成两份选区读取，项目至v36、来源5/8、本地2/2。新导出设置已进入下一context，目前无新候选；四个原ID核对没有新增调用、行动或状态。

当前[8页报告](../runs/a38-delegated-source-20261104/downloads/report.pdf)已逐页看图，30份捕获附件逐字节核对，四个18793下载均与发布文件相同。报告纳入原回答、冻结引用、控制器结果与用量；子代理内部模型/次数/费用仍unknown，核心导入声明仍为`execution_verified=false`。协作工具实际派发记录另见[dispatch.json](../runs/a38-delegated-source-20261104/dispatch.json)与[本轮核对](../runs/a38-delegated-source-20261104/validation.json)。本轮没有调用CLI、拟合、重跑旧数值实验或重启服务。

## Limitations

已取得原件、确认投影与零值共现，定位化学编号差异，并取得作者基材名称的跨表示线索。自动换码、零值原因、唯一图像/对象导出连接、ALP 身份、单位和独立样本仍未确认。A38新增一次实际子代理选择，没有拟合或执行作者代码，未取得独立领域/用户收益评价。开发者的机械核对与模型解释不替代作者、数据负责人或领域队员的确认。通用PDF只展示有限节选；完整A31差异、A32标签与A38导出配置应结合本页、报告Markdown/JSON和原件坐标阅读。报告沿用原分页，部分页留白较多；旧服务没有重新加载新Python代码，本轮由有限本地命令导出后经原服务下载。子代理、检索服务内部用量及现金结算仍未核实。

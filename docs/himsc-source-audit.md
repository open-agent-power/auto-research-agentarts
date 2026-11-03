# hiMSC：零值与作者图像元数据核对

2026-11-04。当前结论：宿主 CSV 与原工作簿保存值一致，但新增作者元数据有 **216 条相同行序记录的化学编号不同**，完整的图像、对象导出与工作簿连接尚未建立。保留原值，先核对编码和运行来源。

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

## 下一份材料要回答什么

1. **`Chem=0` 与 `Chem=28` 的关系。** 请针对上述两块各 108 条记录，给出该版本的编码表、转换或版本说明，明确是否允许对应。
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

本轮沿用 A30 的 [18793 项目](http://127.0.0.1:18793/#/research)，从 v12 的等待继续。先登记新证据，再由原 `tabular-group-first` 配方选择新来源。首次文本选区误用冒号语法，产生终结的 `INVALID_LOCATOR` 失败并计次；保留原收据后，按正式 `N/N-M` 格式登记修正选区，在同一项目读取完成，最终 v23 再次等待。原声明的本轮一次读取上限，在修正前通过独立记录改为两次尝试；核心累计上限仍为 8，没有重置预算或替换项目。

来源累计为 **3/8**：A30 成功一次、A31 失败一次和修正后成功一次。本地数值工具仍 2/2，未派发项目模型或拟合；五个原登记/读取/等待 ID 重放均不改变状态、行动或预算。对 `Series` 和 `216` 的只读 FTS 检索已能返回新增作者元数据和明确标为操作者派生的摘要，当前选择上下文也含新增引用；这不表示模型已读取。

当前四文件报告包保留六次配方决定、原失败、修正收据、作者原件、完整审计/坐标表及审计源码附件。四个 HTTP 下载与保存文件一致，18 份捕获附件逐字节核对，六页 PDF 已逐页检查。原 A30 报告保持原样，较早的钢材、hiMSC、A25/A27/A29 项目及用户原有修改未改。

## Limitations

已取得原件、确认投影与零值共现，并定位化学编码冲突。零值原因、唯一图像/对象导出连接、ALP 身份、单位和独立样本仍未确认；没有运行新研究模型、拟合或作者代码，也未取得独立领域/用户收益评价。开发者的机械核对不替代作者、数据负责人或领域队员的确认。通用 PDF 仅展示有限来源节选，完整 A31 差异应阅读本页、报告 Markdown/JSON 和复现附件；检索服务内部用量与结算未核实。

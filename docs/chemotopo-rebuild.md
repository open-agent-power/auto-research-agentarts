# 原始红通道记录：重建与处理敏感性

当前可用的是一项离线数据处理实验，**不是已确认的 ALP 训练或新材料发现**。入口承接[数据资格核验](chemotopo-data.md)；原有归一化红色汇总列的角色冲突继续保留。

## 为什么需要这项实验

作者 hMSC 项目是 HDF5。只扫描固定哈希文件中的可打印管线文本，未加载 HDF、对象序列化、作者代码或 CellProfiler。两份静态拷贝分别从字节 475730、507314 开始，长度均 31568，SHA-256 相同。C2→OrigGreen、C3→OrigRed；强度模块同时测两种对象与两种图像，导出可含每图像对象均值、中位数及 SD。照明校正的三个模块均标为禁用，管线前缀 B10Pos 不能绑定全部12张原始表。

[CellProfiler 3 官方说明](https://cellprofiler-manual.s3.amazonaws.com/CellProfiler-3.0.0/modules/measurement.html#measureobjectintensity)明确区分对象内平均像素强度与积分强度，且对选定对象、图像的所有组合测量。这说明不能仅凭 `Mean_Red_Intensity` 简写推断具体对象、染色或细胞量归一化。原文的 ALP、tubulin、红绿二抗叙述与通道对应相容，但不补上原导出字段到工作簿的缺失映射。

管线头有文本格式 `Version:3`、2016年的 DateRevision 和 GitHash；没有据此认定作者使用了 CellProfiler 3。官方3.0手册只帮助核对统计概念，不能替代实际软件版本、对象输出和通道映射的证据。

12张原始表共11664条记录，其中1012条 `Count=0`，红绿记录均为0；静态管线导出却设置 NaN 表示无效数。整理步骤未知。保留原数值，不把这些0自动解释为有效的“每细胞ALP=0”，也不再除一次 Count。

## 先冻结规则，再做比较

`PROTOCOL` 与四个 `POLICIES` 固定在代码内；协议 SHA-256 为 `7184a95b5fa41887b7cf70eb4134d5d970017ca6bc15462ad0679b96316cc89e`。四规则共用同一原始文件与明确材料键，不使用 `_Normalised`、`RedIntensityAllBatches` 或聚类表的红色值。

| 名称 | 参与技术均值的记录 | 重复汇总 |
|---|---|---|
| recorded_equal_batch（A1） | 照录全部有限红值，包含 Count0/整组0 | 先批次内 section 等权，再批次等权 |
| positive_equal_batch（B1） | 只用 Count>0 的原记录 | 同A1 |
| recorded_equal_section（A2） | 同A1 | 所有可用 section 直接等权 |
| positive_equal_section（B2） | 同B1 | 同A2 |

每个 section 的技术均值除以**本 section 平坦基底 Topography1/Chemistry0**在同一零处理规则下的均值。分母无记录或不大于0时记不可用；B整组无正Count时也不可用，不补零。A整组0仅保留为“照录原表”的假设值，不赋予生物有效身份。两规则条件不同，估计对象也不同，本分析不从结果中挑出“正确”规则。

所有排名比较固定在纹理2…36、化学0…27、四策略共同有 B8/B9/B10 三批次记录的交集。化学/纹理组合不是独立生物重复；批次编号未逐项绑定供者。Spearman 使用未舍入值的精确同值平均秩；最高10的第10位同值并列全部保留。“高”只是数值大，不是疗效好。

## 怎样运行与复用

```powershell
.venv/Scripts/python.exe scripts/rebuild_chemotopo.py --directory ../../references/auto-research/10-chemotopochip/2026-10-31 --output runs/my-red-proxy-study
```

输出目录必须不存在。产物按读取顺序为：

1. `summary.json`：小型入口，含来源哈希、固定协议、覆盖、6对比较及终点门槛。
2. `protocol.json`：完整固定规则；不因成绩修改。
3. `sensitivity.json`：全部section、原始行、入选/排除行、原始均值、对照、批次均值和组合结果。用来源文件名、sheet、row及 `source.raw_columns` 恢复单元格；不要把约13MB追踪全文直接发送给模型。
4. `report.md`：可读研究记录；数值依据与限制分开。
5. `complete.json`：前四份文件的SHA-256及完整输出标志。没有此文件的目录视为未完成，不覆盖重跑。

`--endpoint alp` 实际返回 `ENDPOINT_UNRESOLVED`，在读取与输出前拒绝。当前入口没有fit操作；`endpoint_gate.fit_eligible=false`说明资格，不声称已经给整个产品所有模型入口加了门禁。此研究也尚未接到LLM持续执行器、研究记忆或AgentArts，不能拿离线脚本成功替代这些验收。

## 根据反馈改变下一行动

在这些条件未满足时，已有C01真实模型研究仍可独立继续；新的数据处理证据可作为后续研究工具输入，不自动成为可跨域复用的研究记忆或确认结论。没有把数据不确定性改写成“参数训练已完成”。

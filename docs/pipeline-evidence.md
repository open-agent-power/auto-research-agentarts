# 作者项目中保存的CellProfiler配置

原始公开出处为[Nottingham作者数据](https://doi.org/10.17639/nott.7080)，相关[论文](https://doi.org/10.1016/j.biomaterials.2021.120740)的方法陈述与本配置分别保留。项目SHA256为：

```text
a9544c844fda6c96ef170ceb7e030589a78bce781a3cc96e32640a2a3d63894d
```

HDF5位置为`/Measurements/2017-08-22-09-08-29/Experiment/Pipeline_Pipeline/data`与同级`index`，提取元素0，保存索引`[[0,1,2]]`。管线头存`Version:3`、`DateRevision:20160503183100`、`GitHash:ac0529e`、`ModuleCount:26`；这里的Version是管线格式字段，不能改写成已确认CellProfiler 3.0执行。

## 配置能说明什么

以下只按保存的字段和名称连接陈述，不另推断模块算法。行号指`original-pipeline.txt`按**字面反斜杠+n**拆开的逻辑行；不展开其他转义，不是原文件的物理文本行。

| 模块与逻辑行 | 保存的具体设置 | 仍不能据此确认 |
|---|---|---|
| #3 NamesAndTypes，28–93；关键54–63 | metadata `C=2`命名为`OrigGreen`，`C=3`命名为`OrigRed`；C=0/1对应OrigBF/OrigBlue | 染色蛋白、二抗染料、原始导出列或工作簿简写的对应；名称不是生物身份 |
| #5/#7/#9 CorrectIlluminationApply，100–104、123–127、146–150；#6/#8/#10 Crop，106–121、129–144、152–167 | 三个校正模块均存`enabled:False`，设置为Orig*经Divide输出Corr*；启用的Crop模块仍读Orig*并输出Crop* | 不能称这条保存配置已把Corr*传入测量，更不能由论文的方法概述倒填实际执行校正 |
| #12 IdentifyPrimaryObjects，178–223；#13/#16 IdentifySecondaryObjects，225–262、303–340 | CropBlue→Nuclei；Nuclei配CropGreen→CellsGreen、配CropRed→CellsRed，二者设置Propagation | 实际对象是否成功分割、对象个数及其测量值；需要对象输出或轮廓核对 |
| #14 MaskImage，264–270；#15 ApplyThreshold，272–301；#16，303–307；#17，342–345 | CellsGreen用于遮罩CropRed→MaskRed，再输出ThreshRed；但CellsRed模块仍读CropRed；随后设置移除MaskRed/ThreshRed | 不能把Green掩膜支路认作已连入CellsRed检测或强度测量的输入，也不能称已验证红通道对象含义 |
| #20 MeasureObjectIntensity，365–370 | 图像列表为CropRed、CropGreen，对象列表为CellsRed、CellsGreen | 哪个实际导出特征最终成为原工作簿每列，及平均强度与积分强度的具体选择 |
| #21 ExportToSpreadsheet，372–394；关键377–379、385、387–394 | 每图像对象测量的mean、median、std均为Yes；all measurement types为Yes；NaN/Inf表示为NaN；前缀B10Pos、按对象名命名 | 导出文件是否生成、实际列名、批次/section/控制对应和后续汇总公式；NaN表示设置也不等于Count=0的转换规则 |
| #21，376、386 | 测量选择开关为No，保存的长选择列表仍含Cells/ER、CorrAGP/CorrER等名称 | 不能拿残留列表当作当前CellsRed/CellsGreen的已执行列清单；应取得真实导出头与样例行核对 |

这比“只知道有红通道”增加了明确配置线索，但没有解除[项目清点](chemotopo-project.md)的边界：当前捕获文件只存Experiment/Image测量组，没有已存对象Count/Intensity输出。配置存在与测量输出存在是两种证据。

## 到哪里核对、下一步交回什么

```text
acee523c0b17372c0c40447a46b8070a33ac8cd3bc733957a2bdf5c5dafddf8f
```

最终提取快照为`276218d1641a5c50146e3f0e1e5db655f680894de7a14cb9abc18c42dc18606e`；JSON定位包括`/source`、`/stored_index`、`/header_lines`、`/modules`与`/selected_excerpts`。这些工件不随普通源码克隆自动分发，需取得对应封存材料后核对。

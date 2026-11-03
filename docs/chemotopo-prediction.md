# P02 未见纹理的数值预测诊断

## 拟合前固定的协议

目标沿用[四种固定处理规则](chemotopo-rebuild.md)：从原始红值重建，分子和同section平坦基底分母使用同一零处理规则，再按既定批次／切片权重聚合。四规则全部报告，不挑一个成绩最佳的规则。

评价限定四规则均具三批次覆盖的870个`(Topography, Chemistry)`组合，Topography=2…36；平坦Topography=1只作已测控制，不进入预测行。这个完整案例集合已使用全部记录的覆盖信息筛选，且先前已查看响应，因此不称盲测，也不外推为全部980组合的成绩。

按Topography整组留出35折，同一纹理的全部化学组合只在该折测试集。每折须确认训练／测试纹理无交集，且每个测试化学类别已在训练出现。批次与section重复先聚合，不扩成独立预测样本。

| 预定方法 | 输入及固定处理 |
|---|---|
| train_mean | 每折训练目标均值，DummyRegressor(mean) |
| chemistry_ridge | 训练折拟合的稠密化学独热编码，Ridge(alpha=1, solver=svd) |
| chemistry_geometry_ridge | 相同化学编码＋10个预声明几何字段；几何仅用训练折均值／尺度标准化，Ridge(alpha=1, solver=svd) |

几何字段来自`Modelling_Descriptors.xlsx`，以Topography键连接，不使用该编号作预测变量。固定的`GEOMETRY_CANDIDATES`为：

```text
Perimeter_Area, Pattern_Count_Pattern, Pattern_Area_mean,
Pattern_Perimeter_mean, Pattern_Compactness_mean, Pattern_Eccentricity_mean,
Pattern_FormFactor_mean, Pattern_MajorAxisLength_mean,
Pattern_MinorAxisLength_mean, Pattern_Solidity_mean
```

## 指标与解释范围

每条记录只用所属留出折的预测计分。每规则分别报告：合并全部留出组合的MAE、RMSE、Spearman精确同值平均秩相关，以及每个纹理折MAE的等权平均。前者按组合等权，后者按纹理等权；折大小不同，不能混称同一个成绩。

`skill = 1 − 方法的合并MAE / 逐折训练均值基线的合并MAE`。正值表示低于该基线，负值保留；基线误差为0时skill未定义，不填0。秩相关无变异时同样保留未定义。合并Spearman可能反映化学类别之间的差异，不自动证明同一化学类别内的纹理排序能力。

目标构造使用同section已观察的平坦对照，与训练／测试目标共享这类测量条件。整纹理留出检验的是**这些已有对照可用时**的条件预测，不检验未来批次、未见化学、独立供者或新实验室表现。几何超出训练范围也应原样记录，不能凭留出折成绩称为任意新纹理泛化。

## 可复核工件与复用

需要独立复用时从产品根运行，输出目录须不存在；脚本先预留新目录、保存协议再拟合，完整清单最后写入。失败残留目录不能当完成结果，重跑使用新目录：

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python.exe scripts/predict_chemotopo_proxy.py --source ../../references/auto-research/10-chemotopochip/2026-10-31 --output runs/my-p02-proxy-prediction
```

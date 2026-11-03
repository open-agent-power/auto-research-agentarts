# P02 作者项目：有界 HDF5 读取

本入口继续核对[原始通道重建](chemotopo-rebuild.md)中固定ASCII片段无法回答的问题：实际项目保存了哪些测量组、图像引用和通道配置。它读取HDF5结构及少量白名单值，不执行CellProfiler，不解包对象或恢复作者实验。

## 固定来源与运行

来源为作者`hMSC_Analysis.cpproj`，1,718,802字节，SHA-256：

```text
a9544c844fda6c96ef170ceb7e030589a78bce781a3cc96e32640a2a3d63894d
```

读取器使用可选`sources`依赖（h5py 3.16.0）。环境尚未安装时，从产品根安装后运行；CLI拒绝覆盖已有输出，须选新的本机文件名：

```powershell
.venv/Scripts/python.exe -m pip install -e '.[sources]'
.venv/Scripts/python.exe scripts/inspect_chemotopo_project.py --source ../../references/auto-research/10-chemotopochip/2026-10-31/hMSC_Analysis.cpproj --output runs/my-project-inventory.json
```

## 这个捕获项目实际保存了什么

本次完整结构清点为247个对象，跳过链接0项。`/Measurements`只有一个实例`2017-08-22-09-08-29`，其下为`Experiment`和`Image`两组，分别14、62个feature。

| 实际保存内容 | 可以核对的事实 | 仍不能据此推断 |
|---|---|---|
| `ImageNumber`与`FileName_OrigRed` | 图像编号1…4，对应`MAm-26032018-ALP-POS1.czi`至`POS4.czi` | 文件名中的ALP、日期和POS不能替代染色通道身份、采集日期或全部原始表映射 |
| `Channel_OrigRed` / `Frame_OrigRed` / `Series_OrigRed` | 四项分别存为−1 / 3 / 0 | 不把−1自行解释为通道缺失，不把frame直接改写为生物染色身份 |
| `CellProfiler_Version` | 存储字符串`2016-05-03T18:31:00 ac0529e` | 不是“已确认CellProfiler 3”，也不是实验日期 |
| `Run_Timestamp` | 存储值`2019-10-17T11:45:47.108000` | 不等同图像采集、生物实验日期或测量组名称中的日期 |
| FileList的文件名、index与OME XML | 按索引行取得4个原图文件各自的采集元数据，保留数据集路径、偏移及SHA | 不是原图像素、对象分割或测量结果 |
| `Pipeline_Pipeline`、`ImageSet_Zip_Dictionary` | 数据集存在，可保留结构信息 | 未读取／未解包的字段不算已取得其语义内容 |

**在这个固定捕获项目的测量实例中，没有对象测量组，也没有已存的Count或Intensity测量feature。** 管线模板中的对象名、强度模块及导出选项只是配置文本，不能据此生成“已测量输出”。这个结论仅限当前文件与实际清点范围，不代表其他作者项目、原图或导出文件也没有这些结果。

### 新取得的原图OME元数据

`ome_filelist`按FileList索引行分别绑定POS1…POS4文件名与XML的`Image Name`，不按原始拼接字节顺序配对。4份XML均为单个Image，存储尺寸1500×1500、SizeC=4、SizeZ=1、SizeT=1、uint16，维度顺序XYCZT；这只是元数据，未加载图像像素。

| XML通道ID | Name | 激发／发射波长（nm） |
|---|---|---|
| Channel:0:0 | TL Brightfield | 未提供 |
| Channel:0:1 | DAPI | 353／465 |
| Channel:0:2 | Alexa Fluor 488 | 493／517 |
| Channel:0:3 | Alexa Fluor 546 | 557／572 |

XML的Fluor字段依次为Dye1…Dye4。染料名、波长与保存的frame信息增加了通道配置证据，仍不证明所标记蛋白、工作簿简写到对象／原导出列的对应，更不能直接把Alexa Fluor 546或OrigRed命名为已确认的ALP终点。

## data/index怎么读

CellProfiler的[官方HDF5实现（固定2.2.0 tag）](https://github.com/CellProfiler/CellProfiler/blob/2.2.0/cellprofiler/utilities/hdf5_dict.py)说明：测量按实例、对象、feature分组，`index`的每行三列是图像编号、`data`起始偏移、结束偏移（不含结束位置）；`Image`和`Experiment`是特殊层级。FileList的二列index属于另一种结构，不能套用这套测量三列解释。这个历史源码用于核对格式，不宣称它就是作者实际运行版本。

同一实现把run group用作一次测量实例的标识，并可默认用创建时刻命名。因此组名、存储的Run_Timestamp和文件名日期分别保留，不选一个冒充实验日期。[CellProfiler 3测量手册](https://cellprofiler-manual.s3.amazonaws.com/CellProfiler-3.0.0/modules/measurement.html#measureobjectintensity)仅帮助区分对象平均强度、积分强度与对象／图像组合，不补齐本文件缺失的已测量输出。

## 读取边界

使用h5py 3.16，只接受固定来源SHA与大小。遍历上限500节点、深度20；白名单测量样本每轴最多4项，字符串最多1024字节。OME另设独立边界：固定FileList字节数据不超过3,000,000字节，单份XML不超过600,000字节、15,000元素；拒绝DOCTYPE／ENTITY及非预期命名空间，要求文件名与单个Image对应。数据集无论是否读值都保留分类：结构元数据不等于实际值已读；从Measurements取得的配置值也不等于对象测量结果。

跳过软／外部／重复硬链接、虚拟数据集、外部存储及非内置过滤器；仅解析固定索引中的有界OME XML，不执行管线，不反序列化pickle或ZIP对象。HDF5读取方法依据[h5py组与链接](https://docs.h5py.org/en/stable/high/group.html)、[数据集](https://docs.h5py.org/en/stable/high/dataset.html)、[字符串](https://docs.h5py.org/en/stable/strings.html)官方说明。未接入模型或平台，页面展示与科学资格需另行验收。

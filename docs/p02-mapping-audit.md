# P02 作者方法与测量映射核对

## 原件与可支持的关系

论文为 [ChemoTopoChip 原论文](https://doi.org/10.1016/j.biomaterials.2021.120740)，使用[大学归档全文](https://eprints.whiterose.ac.uk/id/eprint/172089/1/1-s2.0-S0142961221000922-main.pdf)。本地 `paper-2021.pdf` 为9,678,737字节，SHA256 `7273371527e2ee776e15283b557c20d3f0a21ccc3afc4c85c783de7e36b4f26c`，与2026-10-31捕获清单一致。第3、4、6页已实际渲染并看图；以下页码为PDF的一基页码。

| 定位 | 原文能支持什么 | 仍缺什么 |
|---|---|---|
| 第3页§2.8 | hiMSC第5天ALP免疫荧光；ALP一抗sc137213，1:50；α-tubulin一抗PA120988，2 µg/mL | 二抗仅合称green/red、1:100，未逐一列出hiMSC二抗、染料和实际采集通道 |
| 第3页§2.8、§2.12 | NucBlue染核；方法描述blue图像检测核，再传播检测骨架和ALP | 论文的颜色叙述不是保存项目C2/C3、对象或工作簿列的同图像运行记录 |
| 第3页§2.11 | 列出358/488/561 nm激发及成像设备 | 未给对应发射值、染料逐一配对与原始图像通道元数据；不能借用邻节巨噬染料 |
| 第3页§2.12 | 作者描述照明校正、裁剪、对象检测与强度导出 | 未提供具体运行版本、精确feature、实际CSV头/样例；保存配置中的校正模块为禁用，不能用论文倒填已执行 |
| 第4页Fig.1 | 图例显示ALP为蓝、α-tubulin为黄 | 显示颜色不等于原始采集通道或OrigBlue/OrigRed名称 |
| 第3页§2.13、第4页原印§4.15、第6页§3.1 | 分别保留各slide基底、对应flat及技术重复/批次聚合、flat TMPMP-co-TEGDA的表述 | 不能因此统一实际工作簿处理；原数值列角色冲突、Count=0/NaN和section权重仍未解决 |

§2.12将骨架/ALP与green/red并列，提供候选解释线索；没有据此裁定完整通道映射。当前克隆不含早期本机导出的部分通道CSV，可直接核对本页上表与论文原文。上述观察只指论文明示的事实，作者对完整映射的确认仍未知。

## A31：新增图像元数据与编码差异

2026-11-04已取得作者 `CTC_Image_Metadata.xlsx`，完整取证与复现见[hiMSC来源核对](himsc-source-audit.md)。`iMSC_B8S1` 保存 `Series/Topo/Chem/Row` 四列、972条记录。原B8S1与元数据按同序核对仅756条Topo/Chem相同，216条为原表Chem0、元数据Chem28；59条三列全零记录中17条处于该差异块。Series连续与键值相同仍不足以连接实际对象导出；全部原值保留，不自行做0→28转换。

新的取证优先项是该版本0/28编码、Series/Row含义和原图/对象CSV到工作簿行的唯一连接。已有论文、保存管线、原表和新增metadata各自保留范围，ALP、单位、零值原因及独立性仍待确认。

## 与保存管线、工作簿对照

原工作簿和项目SHA仍与[数据资格](chemotopo-data.md)、[保存配置证据](pipeline-evidence.md)一致。12张原始表A:F为Topo、Chem、Coordinate、Count、Mean_Red_Intensity、Mean_Green_Intensity；名称不足以确认Count来自哪个对象，或Mean列来自哪一种每对象/每图像特征。

保存管线中C2→OrigGreen、C3→OrigRed；Nuclei配CropGreen/CropRed分别生成CellsGreen/CellsRed。强度配置同时列两图像与两对象，不能替真实导出选择唯一组合。ALP字样存在于历史路径和ALP-POS图像名，也不能把路径名当通道身份。Green掩膜支路没有接入CellsRed的输入；保存的导出前缀不证明文件已生成。

下一份能改变资格判断的资料是同一次实际运行的：抗体/染料与图像元数据；CellsGreen、CellsRed及Image导出CSV的列头/样例；导出行到工作簿列、批次、section、flat控制的join；零对象/非有限值和聚合转换。四份[映射空模板](templates/p02-mapping/)保持原样，不填造缺失记录。

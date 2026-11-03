# P02 管线与原始导出：队友取证任务

目标是找到**作者实际导出和运行记录**，再核对通道、工作簿和零对象处理；找不到的项目保留为未知。现有管线是项目中保存的配置，尚未证明执行、实际导出或 ALP 身份。

## 去哪里找

1. [Nottingham 作者数据集](https://doi.org/10.17639/nott.7080)：查看文件清单及版本，寻找实际 CellProfiler 导出 CSV、项目、运行记录和说明。
2. [Mendeley 作者数据集 V1](https://data.mendeley.com/datasets/57nrc49stj/1)：独立核对对应数据、补充文件和版本；同名文件不要假定字节相同。
3. [原论文](https://doi.org/10.1016/j.biomaterials.2021.120740)及[公开全文](https://eprints.whiterose.ac.uk/id/eprint/172089/1/1-s2.0-S0142961221000922-main.pdf)：查方法、补充材料和数据可用性，逐页记录原文坐标。

只使用公开可取得材料；如果作者目录没有目标文件，记录查过的页面、版本及未找到，不根据文件名或论文叙述补写数据。请保留作者原文件；单独标注自己生成的索引或映射表。

## 优先顺序

1. **实际运行和导出**：查找 `CellsGreen`、`CellsRed`、`Image` 的实际 CSV 或等价导出、列头与少量样例行；查找运行版本、日期、batch/section、图像和导出的对应记录。保存的 `B10Pos` 是配置里的文件名前缀，**不是实际文件存在的证明**。管线头 `Version:3` 是格式字段，不能当作已确认的运行软件版本。
2. **通道与染色**：查一抗、靶标、二抗、染料、成像通道及其原文关系，尤其 C2/C3 与 Green/Red。不要直接把红色或染料名称认定为 ALP。
3. **导出到工作簿**：对照实际文件中的对象名、图像名、`Count`、`MeanIntensity`/`IntegratedIntensity` 等真实列头，与工作簿文件、sheet、单元格/列、batch、section 和平坦控制逐项连接；找不到对应时写未知。不要把配置里残留列清单当成实际导出。
4. **零对象与聚合**：寻找 Count=0、缺失值、NaN/Inf 的原始记录、转换或排除规则，以及 section、batch、控制的汇总公式或脚本。配置中的 NaN 表示设置不能推导 Count=0 规则。

## 已有配置线索

- #3 保存 C2→OrigGreen、C3→OrigRed；#5/#7/#9 照明校正模块为禁用，#6/#8/#10 Crop 输入为 Orig 图像。
- #12/#13/#16 保存 Nuclei、CellsGreen、CellsRed 的对象配置。#14/#15/#17 保存 Green 对象掩膜红图像及阈值支路；#16 的 CellsRed 输入仍为 CropRed，**掩膜支路不是其输入**。
- #20 保存强度测量图像和对象列表；#21 保存每图像 mean/median/std、全部测量类型及 NaN 表示等导出设置。这些均不是已生成文件或测量值。

完整记录和边界见[管线证据](pipeline-evidence.md)。

## 怎么记、怎么交回

`docs/templates/p02-mapping/` 提供四份**只有表头的空白辅助表**：`run-export.csv`、`channel-antibody.csv`、`export-workbook.csv`、`zero-aggregation.csv`。按找到的原文填每行的来源文件、真实 URL、文件 SHA-256、页码/行号/单元格或其他准确坐标，标出 `author_confirmation`（是、否或未知）与 `status`（已观察、未解决或冲突）；不确定就写未知。表中结论是提交者整理，除非有可定位的作者明确确认，不写成作者确认。

在工作台领取绑定任务的**领取取证表** ZIP，解压后保持 `task-binding.json` 不变。按包内说明填写 `contributor.json`、`summary.txt`、`sources.csv`、`findings.csv` 和 `questions.txt`；将实际来源原件及本任务的辅助表放入 `sources/` 并登记来源，注明原件或自己整理。辅助表不替代任务要求的 `mapping.csv`、`evidence-index.csv`，也不替代作者原始文件。`sources.csv` 的 SHA 可留空，由接收时按原文件计算；若填写必须与字节一致。参见[填写说明](evidence-return.md)。

寻找约 **50 分钟仍未找到**时，交回已找到的部分、搜索过的位置及未解决问题；不必为了凑齐而补写答案。将整个填写目录交回主团队；主团队使用现有[接收入口](evidence-intake.md)生成不可变收据和可评议材料。接收不表示模型已经读取、作者确认或科学批准，也不会重发旧未知请求。

## 主开发如何生成及接收整包

在产品根目录执行以下入口，输出目录与ZIP必须尚不存在。它复用现有封存读取与空白表生成，不新建研究预算。

交给队友的是整个生成包；队友交回的是填写后的`return/`，只读的`context/`不混入回传来源。主开发使用原有入口：

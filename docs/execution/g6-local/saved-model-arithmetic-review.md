# 保存模型算术：实际2991行结果独立核对

**通过。** root按冻结程序完成一次真实保存参数应用；随后独立审者只读核对全部5份JSONL、2991行和25折摘要，共33282个检查通过。独立复核没有再次执行系数/变换预测公式、fit、predict、transform或原adapter。

这次结果已超出“从storedpred重算误差”：实际运行从原ZIP捕获CSV取输入，应用保存的mean/scale/coef/intercept生成新算术值，再与旧OOF比较。它仍是保存参数应用核验，不是重新学习系数、重训等价、未知数据评价或完整G6。

**准入与执行顺序。** [实物可行性审计](prediction-reconstruction-audit.md)先核齐5CV/25折参数；[数学预审](saved-model-arithmetic-math-review.md)在真实计算前通过作者37项手算fixture与14组独立检查。输出保护曾有old-case外层及冻结worktree漏项，均在真算术前窄修并保留旧脚本/fixtures。最终冻结source `9f6058590a0024c5ef85aaeb49244d2f5f17f7e9`，script SHA `e112e126eca85c1d61dda38c08b9b70c3d73b37fee854b56ac076c9065c6f2fb`，protocol SHA `1e154433c58827cdada1e262bead66393ef66c0e44428e56ca93a23ce6df123d`。

root实际计算使用原77,407,847字节ZIP，SHA `e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58`。固定abs容差1e-10、rel容差1e-12，逐值limit为`max(abs_tol,rel_tol*max(abs(actual),abs(saved)))`；执行后没有调整数据或限值。冻结命令/stdout/stderr在`runs/sprint-006-arithmetic-execution-20261113-01/`，stderr为空。

| 保存CV | 完整行 / 折 | 最大预测绝对差 | 负预测logical IDs（原件与新算术同） |
|---|---:|---:|---|
| Concrete raw v1 | 1030 / 5 | 1.4210854715202004e-14 | 无 |
| Concrete log1p-age v2 | 1030 / 5 | 1.4210854715202004e-14 | 689 |
| Real Estate raw v1 | 414 / 5 | 7.105427357601002e-15 | 无 |
| Real Estate log1p-house-age v2 | 414 / 5 | 7.105427357601002e-15 | 无 |
| Slump raw v1 | 103 / 5 | 7.105427357601002e-15 | 无 |

最大reference差7.105427357601002e-15，最大总体指标差8.881784197001252e-16；全部在原限值内。Concrete候选的唯一负预测保留，没有clip或隐去。logical ID为除header后的1-based原记录，不是新的样本或重新抽样的fold。

**独立post-run核对范围。** 另写的stdlib检查器没有导入作者验证器或产品代码，也没有从feature/coef重新生成预测：

- 从原ZIP中的manifest、SQLite内存只读记录、捕获CSV及五份原CV envelope独立核source/artifact/raw文件SHA、项目/run/action/design/training和折分区hash；以CSV确认每行原target、string groups及physical line locator。
- 五份JSONL逐一确认1030/1030/414/414/103的完整有序唯一row IDs、原OOF与原test fold对应。逐值核actual/saved/signed_diff/abs_diff/固定actual_limit/pass字段；stored值精确对应原工件，行误差与已有actual输出相符。
- 核25折train/test cardinality、全部test IDs、reference对照、最大预测差/实际limit及pass标志均等于各折完整行集合。没有以样本或最大值摘要替代逐行核验。
- 仅从已经完成的输出值独立聚合candidate/reference MAE、relative improvement和negative集合，与五份摘要及原工件一致。未再次求训练reference均值、变换输入或运行Ridge公式；这一限制与前置公式审查相互补充。
- 原实际结果目录的13个manifest条目（5 rows、5 summaries、2 protection、result）及manifest自身共14文件全部SHA/size匹配且在复核前后不变。原494保护文件及ZIP同样匹配并保持原字节。

原SQLite的budget配置中的`new_fits=0`不代表历史研究没拟合；独立逐action计fit_events为Concrete20、Real Estate20、Slump10，合计50，数据库/工件未变。每份旧CV有5Scaler+5Ridge完成事件；实际新验证new_fits=0、estimator predict=0、model/API=0、Guard计数为空。旧两个age单位及Slump无age语义保持，未借用其他课题参数。

| 证据 | SHA256 |
|---|---|
| 实际`/workspace/work/g6-saved-model-arithmetic-20261113-01/result.json` | `f2988acb5de6aa01f1cf31db993722754f891d312c36cf3db67731d3b8436519` |
| 实际`manifest.json` | `ed20e3457fdba87bf109b61abd3a3105707600cda019eb26e6728c347d616905` |
| 独立`runs/sprint006-saved-model-arithmetic-review-20261113-01/actual/receipt.json` | `a34348349bfa6557676f8ef0456cc06d1d991a470120b3b2cdfad6c15be46c97` |
| 前置小fixture`final/receipt.json` | `7fbb4ee75a1997cffd25f3860bab27717595de66863c0252b543749f262aa342` |

全部per-model核对值在独立`actual/model-output-audit.json`，完整逐行实际值仍在原五份JSONL。此通过不推翻先前sklearn1.9分折兼容失败，也不意味着原隔离/runtime Gate已通过；本次直接使用原保存折和参数，不做新的split或fit。

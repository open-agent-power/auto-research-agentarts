# 从归档重建保存模型预测

固定源码`9f6058590a0024c5ef85aaeb49244d2f5f17f7e9`下，单次核验完成全部 **2,991 条 OOF 预测、25 个折模型、5 份真实 CV 结果**。最大预测绝对差`1.4210854715202004e-14`，全部满足事前固定的绝对`1e-10`／相对`1e-12`规则；没有跑后调整误差限。

这是保存参数的独立算术核验。先前原案例验算已有同类公式；本轮新增的是从已校验归档取原 CSV、设计、SQLite 和系数，以纯标准库实现覆盖三课题五版本，逐行保留差异与完整身份链。不是新模型收益、重新训练或完整 G6 验收。

## 输入与实际公式

唯一研究输入为旧77MB ZIP，SHA`e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58`；其固定 manifest、各原件、原 action/request/envelope/design/fold/fit lineage 均核对。CSV、spec、参数从归档读取；SQLite 仅在内存 deserialize 并 query-only。真实原目录读取只用于独立的494文件保护检查，不提供重建输入。

核验器从原 CSV token 按原列顺序取值，仅对明确声明列使用`math.log1p`，随后应用保存的mean/scale和系数：

`prediction = math.fsum(((mapped_x[j] - saved_mean[j]) / saved_scale[j]) * saved_coef[j]) + saved_intercept`

原保存预测值只在独立计算之后作为比较输出。参考均值另从每个原训练折的目标值以`math.fsum`计算。没有重估scaler统计或Ridge系数，不调用生产mapper、fit、transform、predict或模型API；产品／NumPy／SciPy／sklearn导入和socket均被守卫拒绝，实际无触发。

## 完整结果

| 原课题 / 版本 | 行／维度 | 重建MAE | 相对保存MAE的绝对差 | 最大预测绝对差 | 负预测 |
|---|---:|---:|---:|---:|---|
| Concrete raw | 1030／8 | 8.383388056181742 MPa | 0 | 1.4210854715202004e-14 | 0 |
| Concrete log1p(age days) | 1030／8 | 5.702072514528066 MPa | 0 | 1.4210854715202004e-14 | 第689行，1个 |
| Real Estate raw | 414／6 | 6.42509288532858，万元新台币／坪 | 0 | 7.105427357601002e-15 | 0 |
| Real Estate log1p(house_age years) | 414／6 | 6.287279461085385，同上单位 | 8.881784197001252e-16 | 7.105427357601002e-15 | 0 |
| Slump raw | 103／7 | 2.257091754242374 MPa | 0 | 7.105427357601002e-15 | 0 |

这是1547条原始输入在五个已保存版本上的2991次对应输出，不是2991个独立样本或新实验。各原组、物理行定位、折覆盖和raw/candidate保存分区均核对；组仍只是原声明的配合比／位置代理，不能升级为已证明的物理独立性。

轻微末位差来自独立求和算术；没有写成跨环境bitwise一致。Concrete负预测、原两课题恶化行、Slump无age拒绝路线及旧报告全部保持，没有裁剪或改选样本。

## 可复核入口和边界

- [预登记协议](saved-model-arithmetic-protocol.md)：固定数据、公式、数值限和输出，实际计算前提交并审查。
- [源实物审计](prediction-reconstruction-audit.md)与[数学／小夹具预审](saved-model-arithmetic-math-review.md)：作者37项手算／路径夹具与独立14组检查，均在真实2991行之前。
- 执行前命令与源码冻结：`runs/sprint-006-arithmetic-execution-20261113-01/frozen-command.json`。
- 实际结果：`/workspace/work/g6-saved-model-arithmetic-20261113-01/result.json`，五份完整JSONL、25折最大误差、逐行实际误差限、所有负预测及完整输出manifest。

源码SHA`e112e126eca85c1d61dda38c08b9b70c3d73b37fee854b56ac076c9065c6f2fb`，协议SHA`1e154433c58827cdada1e262bead66393ef66c0e44428e56ca93a23ce6df123d`。原ZIP及494保护文件／路径集前后完全一致，旧研究仍累计50次estimator尝试；本轮新fit、estimator predict、模型/API调用为0，CPU和工程工作不称为零成本，金额/token未知。

没有证明保存系数是重新训练的解、最优系数、跨版本训练等价或新的科学有效性；也没有重新执行分折器或修复OS隔离。另一成员的逐输出行／指标审查单列，不以手算夹具代替真实结果。

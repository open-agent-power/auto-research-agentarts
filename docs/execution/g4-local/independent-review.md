# G4-L 独立总审

当前状态：**一次闭合解释器内的G4-L代码候选评测、原件完整性及无执行恢复总审通过。仅accepted_for_future_review，不晋级生产，不通过原完整G4。**

审查者不编写候选。能力解释器全代码由独立成员专审；本总审负责冻结身份、完整工作树／diff边界、
评价阈值、单attempt、结果／lineage／恢复及旧研究保护。用户已接受可信本地继续，无需重复要求补隔离Worker。
这不构成OS隔离、sealed评测、原完整G4通过或生产晋级。

## 冻结准入

- fixed runner SHA：`787eae6dc8e710fc12ad9f3a02f6ff42f442c109d2cb96386f43bca71aff18f2`。
- closed capability SHA：`422e57f6145e85bb384cb52b6433b81ca16a523c2b49d0371ffc6af483263e71`。
- [协议](protocol.md) SHA：`7820a4c4f77059ae5dba3f08fff43f065eedd5d615f83e9a831f72ad7dab7147`。
- 独立能力审查：`/workspace/work/g4-independent-review/capability-review.json`，SHA
  `0b4486472259aab8592dfc11834b0a76e3a9c2edf4f6693f907d4c773f679ab6`，
  28项独立检查通过；仅准入狭窄闭合语言，不批准任意Python或未来候选。

`37b70c2`仅存在于独立detached baseline worktree。
其diff将原`dict.fromkeys`／`list.index`表达式提取为`encode_groups`并在原处转换为`np.array`，
没有优化算法、改模型／划分或修改main及原G1/G3账本。
baseline适配与后续优化diff必须分别保留，不能混作一次已获收益的修改。

已核定的操作顺序：提交固定evaluator／能力／协议 → prepare冻结完整树和三个原输入 →
baseline-only三次解释器调用及原保存fold精确核对 → 保存诊断 → 作者提交单个候选diff →
独立exact binding审查 → 一次正式配对batch → 本地决定及无执行replay。
该次初始准入止于baseline-only，当时候选代码仍未提供或执行；实际后续顺序及单独候选审查见下文。

## 已关闭的runner审查意见

1. 原稿在inspect之后重新读取未校验候选，存在review绑定与实际执行字节错配风险。
   最终版在执行前捕获受限module／helper精确SHA，运行该快照，并在完成时复查候选整树。
2. 原稿只校验result本身，原始timing／correctness／dataset结果未被replay绑定。
   最终完成receipt保存这些原件的SHA和长度，replay逐项核对。
3. helper-only门补充完整tracked内容、Git及文件系统mode、全部untracked（含ignored）及link拒绝，
   module／文件／整树读入有上限；模块helper以外字节必须与baseline相同。
4. 恢复核对依赖、baseline commit／整树身份、固定控制代码／协议及输入；
   来源envelope使用canonical指纹复核，不仅比较两个保存SHA字段。
5. baseline-only与诊断独立于候选阶段，候选review绑定baseline评估及诊断SHA；
   未决attempt不允许换ID重派或重置已发生的batch。

## 本次预冻结评价含义

三个完整真实label数组用于回归，原数据均已见，不是隐藏新科研课题；输入仅有有限字符串组标签，
没有目标值、模型系数、文件路径、凭据、预算或评价器对象。
旧case和控制文件SHA提供变更检测，不能声称同UID写权限被操作系统撤销。

固定每臂每数据集5次warmup、100次交替顺序配对计时，只有一个优化候选／一个正式batch。
local接受阈值：完整正确性及保护通过；Concrete解释器路径中位至少1.5倍、节省至少500,000ns；
两个目标均不能同时出现超过10%且超过50,000ns的中位减速。
不达阈值、慢、小或不确定结果均保留，可拒绝；不依据结果重新调阈值、候选或重复次数。

计时针对该closed AST解释器及其已说明的receipt／guard路径，**不是native Python分组、完整CV或端到端科研速度**。
`accepted_for_future_review`仅表示可进入另一次源代码审查，不更新main／默认Recipe、迁移旧case或产生fit授权。
拟合／产品模型/API额度保持0；开发Agent费用未知。

## 初始验收范围（实际证据见后文）

真实baseline评估／诊断、候选exact diff与独立binding、全部计时／正确性／操作计数、
criterion逐项决定、baseline→candidate→decision lineage、失败与unknown记录、
禁止helper执行的原ID恢复，以及旧case／工作树／控制原件前后身份。
这些实际结果出现前不宣称完成代码改进或收益；后文实际结果仍不证明完整RSI。

## 实际baseline、候选准入及唯一batch

固定评测代码提交`7846ec5`后，在 `runs/g4-local-group-20261113-01/` 完成prepare。
baseline manifest SHA为
`af504f90ca10d75ec7bf5207e7f5c9031650ddc4f09802c395f482daff8e19c8`。
baseline-only对Concrete1030行、RealEstate414行、Slump103行各调用固定helper一次；
全部ID、int64形状、保存fold一致，原case全SHA保持，candidate调用0、fit/API0。
其评估SHA`33beae8d184b37aab8dea450418fe2bc0e9116ad84ca11166677a3455c1ee769`
与baseline-attempt及诊断引用一致。

之后才产生作者回执和候选commit `58ee7c1`，父提交为`37b70c2`。
独立读取真实diff并重新运行**无helper执行**的inspect确认binding，优化仅将helper改成：

```python
lookup = {label: index for index, label in enumerate(dict.fromkeys(labels))}
return [lookup[label] for label in labels]
```

完整tracked树、mode及helper外字节保持，native callsite不变。
此映射按首次出现顺序编号，语义上与baseline一致；正确性仍须由实际固定评测核对。
候选module SHA`ec965e31c7b148c24f11910d93ecc03e474504333548156a23575a39cf269711`，
helper SHA`c021c1ebf275ed42e07936c0b31a675d3017b7e7bef06b2c26318d5adf41358b`。
独立准入文件 `independent-diff-review.json` SHA
`63913f92338476dd259912c0ba25643c3658dc4d5a3ae556f6ed0dd8a27d1cc0`，
只批准一个冻结闭合AST batch，未批准native导入、完整模块执行或生产变更。

实际唯一batch约52.944秒墙时／52.914秒CPU，attempt1 completed，无error，0fit/API。
十项工程边界结果（三个真实输入之外的五case×两臂）、六份完整真实ID／保存fold结果及
**600份正式配对计时**原件保留。每次操作计数都在固定cap内。

| 输入 | baseline解释器路径中位 | candidate解释器路径中位 | 本路径速度比 |
|---|---:|---:|---:|
| Concrete | 324.674 ms | 8.459 ms | 38.38× |
| RealEstate | 93.354 ms | 3.877 ms | 24.08× |
| Slump | 12.828 ms | 1.196 ms | 10.73× |

这是同一闭合解释器、其抽象操作收费和receipt／guard路径的测量。
尤其baseline的线性扫描包含解释器逐项计量开销，不能把上表复制成native Python、模型训练、完整CV或科研产出的速度提升。
阈值按冻结规则重算全部满足，因此本地状态为`accepted_for_future_review`；不自动选择新的生产基线。

## 结果、保护与无执行恢复的独立复核

独立读取600行原始计时，核对每数据集100pair及交替顺序、全部输出SHA与计数上限；
重新计算全部中位数、速度比、绝对节省、配对节省及每条接受准则。
对六份真实ID输出独立构造首次出现编号，并用冻结版本GroupKFold重建保存membership，无模型拟合。
结果的全部七份artifact SHA／长度、baseline／候选完整树及保护原件也核验一致。

真实outer执行completed replay和相同request ID的run入口均返回原result；
`execute_group_program`全程patch为抛异常，实际`forbidden_calls=[]`。
审查期间原outer全部文件字节保持，未产生第二helper batch。

只在复制的outer账本中进行拒绝测试：

- 改timings、删correctness或改result均拒绝恢复；
- attempt改为running时拒绝，不补做batch；
- 换request ID或提高candidate attempt上限均拒绝；
- 在内存模拟inspect与再次capture之间候选module字节变化，精确SHA门在写attempt／执行helper前拒绝。

这些工程负例未修改真实controls、候选worktree、原attempt或任何历史case。
总审 **40项全部通过**，证据在 `runs/g4-local-total-review/review.json`，SHA
`1f22954a30c360952cf5e0d5483d0ce19917d1af28b31978c7d1e736abcaeec8`。
本审查没有新fit、模型/API调用或candidate评测。

## Local decision、lineage及下一步边界

随后新增的`decision.json`、`lineage.json`、`next-generation-input.json`透明保存归档关系；
独立核对其八条文件引用SHA全部匹配，实际Git父链为
`0ceb274 → 37b70c2(wrapper) → 58ee7c1(candidate)`，fixed evaluator为`7846ec5`。
原result与完成artifact未被改写；新增归档不充作另一次候选运行。
main的原生adapter仍未改变，所有旧研究预算不变，local decision明示`automatic_production_promotion:false`。

next输入只建议**另行冻结、独立审查后的native纯helper确认**，没有授权研究拟合、自动合并、
任意Python执行或新一代RSI。新的native执行方式须单独审查其能力边界、准入、输入和计量，
不回写本次固定VM controls，也不能预先把VM速度当成native结果。
完整恶意代码／凭据／评价器隔离、sealed独立课题、多代收益和生产晋级均未由此结果证明。

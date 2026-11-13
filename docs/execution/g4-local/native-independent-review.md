# G4-L 原生纯 helper 确认：独立总审

当前状态：**固定原生纯 helper 的单次确认与无执行恢复总审通过；生产集成须独立验收。**

本审查不编写或执行候选，不复用此前 VM 的独审批准。原生编译是新的执行方式，
仅允许此前已审的两份精确 helper 与三个精确 label 输入；不是一般原生代码执行入口。
原 VM controls／结果保持原样，主分支 adapter 尚未晋级，旧研究预算不变。
这里“尚未晋级”是本阶段结束时状态；后续另行集成的实际证据应独立追加，不能反写本次原生批准。

## 固定实现与静态结论

- `scripts/verify_native_group_candidate.py` SHA-256：
  `858e06a22d6e003b465c6003e8567bea6616118e78516c1099d92610824feb54`。
- [本阶段协议](native-confirmation-protocol.md) SHA-256：
  `aae25bcbf3d7562723be2b8bf29ceea2d0c28b66ba48b1c733397fdb9333b5d2`。
- prepare 只校验来源／原件身份、纯 AST／类型、保护快照并生成 pending review，
  不做 VM helper 调用、原生 `compile`、`FunctionType` 或 helper 调用。
- 独立能力专审负责闭合 AST、编译后 code-object／namespace；本总审负责冻结、
  唯一执行根／attempt、原件、预算、失败恢复及后续声明。
- 最终能力专审 24 项通过，且编译／FunctionType／VM／helper 调用均为 0；
  `/workspace/work/native-independent-review/capability-review.json` SHA：
  `f7df7eb1e33b05031de444bc07000427e156317e4d759ed1cca26001d76d7c50`。

报审期间发现并已关闭以下实质问题：

1. manifest／result／input 不能先 hash 再重开解析；现统一解析首次捕获且已校验的同一 raw bytes。
2. 原始独审批准需保存并进入完成 artifact；现恢复逐字节核对 SHA。
   批准若恰写在归档同一路径，先确认同 bytes 复用；冲突在 claim attempt 前拒绝。
3. `integrity-before.json` 需由 freeze 绑定 SHA，当前历史 case 也必须匹配原 VM 完成后的已批准快照。
4. 批准需绑定原始 output root；现 run 拒绝在复制目录或第二空账本执行，复制品只可回读已完成结果。
5. 独审 schema 版本需精确比较，不能仅要求字段存在。
6. 保护检查失败前需先保存 after 明细；现保留 after／failure-after 及阶段、实际调用计数。

run 必须有新 `approved_for_fixed_native_confirmation` 批准，精确绑定具体 freeze、
helpers、inputs、controls。原子创建一个 attempt 后，所有六次完整 VM 资格检查先完成，
才可编译两份精确 helper。成功完整 batch 固定为 636 次原生调用：六次正确性、
30 次 warmup、600 次正式配对计时；不增加候选、重调阈值或补跑失败 epoch。

时间区间仅含原生 helper 调用，输入转换、编译、VM、NumPy／fold、输出校验及 IO 均在区间外。
预定阈值是 Concrete 至少 1.5 倍且节省至少 0.5 ms，两目标均不同时超过 10% 且 0.05 ms 减速。
正确性、dtype／形状、原保存 fold 与保护是硬门。未达到阈值或出现 unknown 均保留负结果。

本次静态审查未调用 prepare／run、原生编译、VM helper、拟合或产品模型／API。
该初始静态结论只允许 root 固定上述版本并生成具体 freeze；后续实际批准见下文。

## 后续验收范围

具体 freeze、批准原件、单 attempt、六次资格回执、六份完整 ID／fold、全部 600 timing、
实际 636 次调用／2 次编译计数、准则重算、完成 artifact／保护明细和禁止执行的原 ID 恢复，
均须由实际结果证明。复制品负例不得改真实 attempt、controls 或任何历史 case。

即使本阶段通过，也仅接受进入下一次源代码集成审查；不自动修改主分支、升级旧项目、
重置预算或授权研究 fit。原生 microfunction 时间不外推完整 adapter／CV、科研准确性、
OS 隔离、sealed 课题或多代 RSI。后续生产集成需另审实际 diff、纯分组回归及旧服务源码 pin。

## 具体冻结、批准与实际结果

固定代码提交 `ffc50f3` 后，root prepare 生成唯一目录
`runs/g4-native-confirmation-20261113-01/`。freeze SHA：
`98da939f8204d25ba4f6f222a082855041060f6d91b1ca2a700fad417f083964`。
独立核对 17 项实际绑定／保护，`compile`、`FunctionType`、VM 及 native factory 全 patch 禁止，
无禁止调用。独审原件 `independent-native-review.json` SHA：
`3891763779795f2b96b32f7b0d133e9e622b2e8bca38acc141c3d2591c62952e`。
其批准只对该唯一根、该 freeze 的一个 batch 有效；静态审查与已完成 VM review 均未替代此批准。

实际单次 batch completed，约 1.90049 s 墙时／1.89605 s CPU；六次新 VM 资格检查后才做两次编译，
636 次原生 helper 调用、600 条正式计时、0 fit／产品模型 API，未搜索新候选。
六份 VM 和六份 native ID／dtype／完整 fold 均一致，五份完成 artifact 由 SHA／长度绑定。

| 完整固定输入 | baseline 原生中位 | candidate 原生中位 | 本 helper 速度比 |
|---|---:|---:|---:|
| Concrete | 2.1955105 ms | 0.0844425 ms | 26.0001× |
| Real Estate | 0.613071 ms | 0.033010 ms | 18.5723× |
| Slump | 0.074247 ms | 0.008207 ms | 9.0468× |

Concrete 中位节约 2.111068 ms；三个 paired 节约中位分别为 2.1050145、0.5822555、0.066064 ms。
固定速度／绝对节约／目标减速准则全部通过，状态 `accepted_for_future_review`。
结果 SHA：`3145b23e43e36d3ea2e0de92fa4336cf037466609f9ae76b8e46b510cc9ae1a0`。
这些是同机、已知输入、重复调用的纯 helper 测量，不是完整 adapter／CV／科研表现。

## 独立结果及恢复核验

`runs/g4-native-total-review/audit_native.py` 重新打开原件，独立重建首次出现 ID、GroupKFold 及
全部 600 条计时摘要／预定准则，核对实际计数、五份 artifact、旧 VM 与 292 个历史 case 文件。
共 **84 项通过**；总审记录 `runs/g4-native-total-review/result-01/review.json` SHA：
`f312d158d05a98863d04ab2a6316bc1f1b929c3df70b8abd6496044701935103`。

原根的 replay 和相同请求的 run 都返回原结果。审查将 native compile、FunctionType、
native factory、VM execution、两种 estimator fit、socket 与 Popen 全部禁止，
`forbidden_calls=[]`，无新增执行、拟合、产品模型 API 或预算消费。原根全部 **10 文件**前后字节相同。

仅复制的 outer 账本用于以下工程负例，原始 controls／attempt／旧 case 均未改动：

- 已完成复制品可只读回放，内容仍逐字节不变；复制品 run 及删掉其 attempt 后的空账本 run 均因原根绑定被拒绝。
- timing、review、result 或 before-image 字节改变均拒绝；缺失 correctness 也拒绝。
- attempt 改成 running 时拒绝，不进行补跑、编译或新 helper 调用。

本审通过的决定仍只是后续集成审查准入。主代码修改、纯分组回归、旧服务 pin 和发布决定属于
下一项实际集成验收；其授权不由本次 native batch 自动产生。

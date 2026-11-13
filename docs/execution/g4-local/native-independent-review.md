# G4-L 原生纯 helper 确认：独立总审

当前状态：**固定实现的静态 prepare 准入通过；具体 freeze 的原生执行批准仍待完成。**

本审查不编写或执行候选，不复用此前 VM 的独审批准。原生编译是新的执行方式，
仅允许此前已审的两份精确 helper 与三个精确 label 输入；不是一般原生代码执行入口。
原 VM controls／结果保持原样，主分支 adapter 尚未晋级，旧研究预算不变。

## 固定实现与静态结论

- `scripts/verify_native_group_candidate.py` SHA-256：
  `858e06a22d6e003b465c6003e8567bea6616118e78516c1099d92610824feb54`。
- [本阶段协议](native-confirmation-protocol.md) SHA-256：
  `aae25bcbf3d7562723be2b8bf29ceea2d0c28b66ba48b1c733397fdb9333b5d2`。
- prepare 只校验来源／原件身份、纯 AST／类型、保护快照并生成 pending review，
  不做 VM helper 调用、原生 `compile`、`FunctionType` 或 helper 调用。
- 独立能力专审负责闭合 AST、编译后 code-object／namespace；本总审负责冻结、
  唯一执行根／attempt、原件、预算、失败恢复及后续声明。

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
**该静态结论允许 root 固定上述版本并生成具体 freeze，不构成真实 run 的批准。**

## 后续验收范围

具体 freeze、批准原件、单 attempt、六次资格回执、六份完整 ID／fold、全部 600 timing、
实际 636 次调用／2 次编译计数、准则重算、完成 artifact／保护明细和禁止执行的原 ID 恢复，
均须由实际结果证明。复制品负例不得改真实 attempt、controls 或任何历史 case。

即使本阶段通过，也仅接受进入下一次源代码集成审查；不自动修改主分支、升级旧项目、
重置预算或授权研究 fit。原生 microfunction 时间不外推完整 adapter／CV、科研准确性、
OS 隔离、sealed 课题或多代 RSI。后续生产集成需另审实际 diff、纯分组回归及旧服务源码 pin。

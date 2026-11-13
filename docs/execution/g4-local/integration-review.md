# 已审分组 helper 的生产集成独立审查

状态：**允许发布本次精确 helper 集成。30 项独立核验通过；旧项目未升级。**

这项发布决定独立于 VM／native 的 `accepted_for_future_review`，没有把实验批准当作自动生产晋级。
审查者不编写候选、不修改产品源代码、不拟合研究模型。主代码由 root 在独立审查准入后复制，
本次检查实际复制内容、纯分组回归、旧服务 pin、代码变更拦截及历史原件。

## 精确代码与行为

原 source `0ceb274` → wrapper `37b70c2` 仅将原分组表达式提取为 `encode_groups`；
wrapper → candidate `58ee7c1` 仅将首次出现列表加 `list.index` 改为首次出现字典编号及查询。
主分支实际 adapter 文件与已审 candidate 完整逐字节相同，SHA-256：
`ec965e31c7b148c24f11910d93ecc03e474504333548156a23575a39cf269711`。
审查时仅该产品源文件有差异，没有修改训练、目标、拟合额度、划分器、误差或 evaluator。

当前调用点传入 `_inputs` 构造的有序 `list[tuple[str, ...]]`。
两种实现均按键首次出现编号；新的 lookup 保持相同 ID，因而保留 NumPy dtype／形状和既有 GroupKFold
成员划分。产品支持最多 2,048 原记录，分组字段可为 0 到 8 个；没有用 native 研究的最多 4 字段
边界替换产品合同。新 helper 不承诺对任意 iterator、自定义对象或外部传入回调提供新 API。

8 项纯分组回归已实际通过，日志 `runs/g4-native-integration/group-regression.log` SHA：
`2e492bc0517b1e562c7602b89d070621f9207b69d8f9ad3683cdd82864596912`。
覆盖首次出现顺序、Unicode／多字段、产品 0／8 字段、空输入、2,048 唯一／重复输入、固定随机差分及
不改输入、NumPy dtype／形状、2／3／5 折精确成员及无组泄漏；不调用模型 execute／fit。
未为本次发布重新跑真实 CV、重新解系数或消耗旧课题剩余预算。

## 实际原生证据及其范围

[原生独立审查](native-independent-review.md) 完成 84 项核验；receipt SHA：
`f312d158d05a98863d04ab2a6316bc1f1b929c3df70b8abd6496044701935103`。
单次固定批次的 600 条原生纯 helper 计时、6 次 VM 资格、2 次编译、636 次原生调用及全部正确性／保护
均通过冻结准则。Concrete／Real Estate／Slump 三个已知输入的 helper 中位速度比分别约 26.00／18.57／9.05。
这是同机纯 helper 的重复调用证据，不是完整 adapter、CV、端到端研究或科学准确性收益。
独立恢复没有重新编译、运行 VM／helper 或拟合；未知／被改工件／复制空账本拒绝执行。

## 旧代码、服务及账本保护

完整旧源码保留在 `work/study-source-0ceb274/`，实际 Git commit
`0ceb2742825a9e95b373260fb39950fcbb48af1b`，工作树干净；旧 adapter SHA：
`5c689576add16d5bd28cdf5c43a5c4599afb257a12f6b239018dcabcb0501090`。
独立读取 live PID 的命令行，确认 18830 服务由该源码的脚本启动；脚本将其自身 `src` 置于导入首位，
不从新 main 导入 adapter。独立 HTTP GET 再核对管理页与模型入口 `enabled:false`，selection context
无 `CODE_CHANGED`。本次没有重启服务或发送研究／模型请求。

新的主代码身份为 `e6ca80b37b57a14098b842f946acf35148226ec4f505b2aa2755daf6659bcf0f`，
旧项目保存身份仍为 `1354f4c077667b3a6df4400515cf1215b3ef97a2a8cef597a72402487032ad17`。
独立从 main 读取三旧课题的 selection context，均正确出现 `CODE_CHANGED`，不默默升级或执行；
旧项目继续使用已保留代码。显式代码修订或旧项目升级不属于这次发布授权。

| 原课题 | state version | 已消费 estimator fit | 保持原字节文件 |
|---|---:|---:|---:|
| Concrete | 32 | 20 | 101 |
| Real Estate | 33 | 20 | 101 |
| Slump | 24 | 10 | 90 |

292 个历史文件在独立 HTTP／context 核验前后均与原 VM 已批准快照逐字节一致。
VM／native 固定脚本、协议及原 native result SHA 仍一致，未用生产集成回写旧实验。
main-context 检查将全部 adapter execute、source execute、Ridge／Scaler fit、socket 及 Popen 禁止，
`forbidden_calls=[]`；没有新增研究 fit 或产品模型 API。

## 发布结论

实际集成核验 30 项通过，原件 `runs/g4-native-integration/independent-review.json` SHA：
`5cf1f170f974d2baeaf4c649fbcb4fcf03fd88c45f6810df2861ad5392b28e5d`。
批准的是精确代码、纯分组回归及已核验的旧源码／服务保护。出现问题时，旧 source 与原 module 字节仍可核对和恢复。
旧研究预算、历史决定、原始输入和原件不因本次发布而重置；完整 G4 的 OS／sealed／多代 RSI 门仍未通过。

## 后续全量工程回归

随后独立成员在同一未提交的精确 adapter／测试树运行全套 unittest：
**1,164 项，1,145 通过、19 skip、0 failure／error**，166.445 s（墙时约 168.225 s）。
总审只读核对日志末尾及全部七份回归 artifact SHA／长度，没有重复运行全套。
`runs/g4-integration-regression-20261113-01/regression-receipt.json` SHA：
`8241da13bfa50aa6413d00065097d603e279c3840fc24e59227ca3a7ba48a3ca`。

回归确实执行了工程 fixture 的 estimator fitting，未计量 fixture fit 总次数，
因此不能把本节或整轮工程验证说成“所有程序 fit 为 0”。实际三研究课题没有重跑，
累计 estimator 尝试仍为 20／20／10，总计 50；292 个研究文件及完整 src／tests 字节前后保持，
没有新增外部产品模型 API。上述 8 项纯分组测试与独立恢复自身仍为 0 fit。

## 后续异版本兼容性反例

G6 clean 环境实际加载 sklearn 1.9.1，而研究冻结版本为 1.8.0。已安装的精确 candidate helper
仍给出相同分组 ID，但 Concrete 的 808／1,030 行、Real Estate 的 252／414 行 fold 不同；
即便忽略 fold 编号，两者 partition 仍不同，Slump 保持一致。独立只读比较完整保存数组确认了该反例，
没有重算模型或筛掉差异行；记录在 `runs/g4-native-integration/cross-version-split-review.json`。

因此本次 helper 的正确性不意味着任意 sklearn 版本可复现旧划分。G6 的严格失败继续保留，
不能把安装成功说成旧研究复现通过。另建的历史用途精确 18 包 pin 环境（原 `0ceb274` wheel）
恢复了全部 1,547 行原分组／fold，但不声称完成 OOF 预测／系数／误差的重新复现。
详见 `../g6-local/final-clean-wheel.md` 和 `../g6-local/frozen-reproduction.md`。

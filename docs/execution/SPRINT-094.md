# S094：Host 计划采用与质量行动引用

现有 Host 计划协议的模型输出只含四项计划文本，普通 `adopt_plan` 不附 S085 的 `quality_feedback_ref`，因此不能由 S086 策略验证所引用的原质量行动。新增显式 Python `HostModelSelection.adopt_quality_plan`：核原 Host response/prompt/context/proposal及质量 action ID 引用，原样保存proposal四文本和理由，由宿主另附同项目已认证质量引用；在 Host 意图和 Project writer 中绑定 nonce/原ID与同事务 plan claim。该入口自身不调用模型或派发研究工具，旧普通采用不自动升级，Workbench/HTTP尚未接新入口。

plan revision 本身不包含“模型/宿主”来源标签，只有 Host 原意图与 Project claim 的组合才提供此关联；引用是宿主附加，不代表模型生成该结构、真实看到或理解材料，也非研究有效性证明。首次intent/core间失配、未知或原件漂移按合同停查；旧 adopt/reject 不能绕过新intent。

作者最终专项16/16、旧合同70/70（真实退出码0）；独审最终Host/原计划/质量plan/v2 41/41。均隔离合成，使用人工构造的保存回复和本地工程工具，无真实模型/API/研究。覆盖原文本、引用与来源/SQL/Host源码漂移、直接core抢占、意图/core中断、claim和双进程竞争、旧入口及合法大型prompt/超限拒绝。独审发现未决新intent可被旧reject覆盖、prompt未绑定原context、末次Host身份漂移等缺口，作者修复并补负例；接近64KiB的合法context转义后prompt超过64KiB，改按原Host文件上限2MiB读取并验证超限拒绝。

扩大回归发现旧 `test_research_plan` 1项错误优先级不符，在干净 `git archive` HEAD `2bb33394f38cb0aeecec523e0bef65d5b1e94443` 单测也独立复现：其他stale manager intent先报 `OPERATION_INCOMPLETE`，测试期望同ID异body先报 `IDEMPOTENCY_CONFLICT`；本轮70项回归明确排除该已知失败。原日志 `runs/s094-host-quality/preexisting-head-plan-failure.log` SHA `1720419730f29410db4d93240d9dd3ef6a3781d1255e552113376408c1a87a2a`。本增量未修改旧Workbench或断言，缺陷单独处理；不将其计入通过。另一次测试启动路径误写，退出127、未运行测试，后改正确路径。

旧真实 Bike Project/claim/pin/2/2预算保持，原云盘和原全局执行者unknown。隔离合成不证明真实模型自主采用、科学收益、断电恢复或OS隔离；开发token/费用unknown。

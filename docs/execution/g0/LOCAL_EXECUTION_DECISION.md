# 待决定：可信本地研究先行

状态：**proposed / needs_user_decision**。本文不改变原G0状态，不授权开始G1，也不把用户一般性的“持续推进”解释为改动阶段门槛。

## 本轮复核与决定来源

环境配置仍为revision 1、UID1000；cgroup由root持有且不可写，subtree controllers未委派，Docker仍为rootless/cgroup driver none，没有可用的外部Worker或环境恢复写入工具。没有重复运行已知失败的资源容器，也没有提权或更改daemon。

原任务包 [README](../pack-v2/README.md) 规定：“每个阶段通过 Gate 后才推进依赖阶段；独立工作流可提前并行。”[G0要求](../pack-v2/06-roadmap/PHASE_DELIVERABLES_AND_GATES.md) 包含Docker资源限制实测；原[ADR](G0-ADR.md)保留CPU/RAM/PID未生效和上游隔离runtime smoke未完成。因此先执行下列可信研究切片是一项**执行顺序修订**，需要用户决定；不是额外的Skill审批，也不是已修复环境。

## 方案A：批准可信本地先行（建议）

原G0保留BLOCKED，另外建立明确的“可信本地研究执行”范围。仅允许已审计、固定代码身份的现有ResearchProject/ProjectController白名单，使用已下载并核验的1030行Concrete数据。既有[研究任务](initial-research-task-spec.md)和[独立评价](evaluation-protocol.md)保持，以下边界逐项记录：

- 新研究lineage，累计至多6次本地工具、20次estimator fits、1次本地来源提取；0次产品模型/API发送，不采购或启用模型CLI。
- 同时仅1个受监督的可信本地研究进程；数值库线程1，明确超时、内存/磁盘观察、工件边界与磁盘余量检查。这些是任务运行约束，不是cgroup硬隔离，也不保证单Worker RSS/PID上限。
- 原控制器实际质量检查、固定分组Ridge基线、保存诊断；据新观察保存计划修订，决定是否执行唯一预声明的log1p龄期对照。不能为了形式上的两轮而伪造分支理由。
- 保存完整输入/代码/评价身份、OOF、失败和不利结果、累计预算、报告与复现附件；独立复算、原ID重放和成员接续。少于两轮有效推进不宣称G1切片验收通过。
- 计划由当前宿主开发Agent/操作者形成并如实标识，不宣称已有产品自主模型runtime、后台无人值守研究或独立未见任务收益。Concrete已有历史成绩，仅为已知结果的真实数据复现与连续性验证。
- 研究运行禁止执行模型自由生成代码或RSI候选代码，工具协议不得接受任意shell/Python；宿主仅调用经审查后的固定白名单接口。完整上游框架、未知插件、RSI、自修改及候选晋级继续禁用。原CPU/RAM/PID/持久盘与上游隔离runtime要求保持未满足；G2及后续依赖阶段不因本切片自动解锁。

用户明确批准后，记录其决定，按上述范围实施和实际评价；报告使用“经批准的可信本地切片”，不回写原G0为PASS。安全隔离与完整自主runtime仍需各自实测。

## 方案B：保持原执行顺序

不执行依赖G0的研究切片。由平台提供支持cpu/memory/pids委派的Docker环境，或另附可强制实施同一合同的Worker；保留控制器余量和工件配额，重跑探针及所需上游隔离PoC。G0验收通过后再开始G1。

## 独立审查

resource_audit只读复核认为方案A在当前CPU/数据规模上可行，但不能替代原隔离要求；independent_review同意将其作为明确的修订选项提交用户，未批准执行。两者均指出：若保持原包严格顺序，当前G1尚未解锁，必须有平台变化。

## 收口与恢复

在用户选择前仅做独立的契约/评价准备；不创建研究项目、不启动fit、不修改既有预算。下一轮首先读取本页决定状态；没有回答不能视为批准。

本轮只读恢复证据：`runs/g0-decision-review-20261113/preflight-reviewed.json`，SHA256 `99fec1df203d4f60a9f220ec2cbc2b84335b437d7f2db760962dab387ddddc03`；不含新的研究行动或容器资源压测。

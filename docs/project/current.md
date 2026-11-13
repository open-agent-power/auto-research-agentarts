# 当前接续

## 当前目标与停点

执行 Master Execution Pack v2。G0审计交付已完成、独立审查已收齐，**G0仍BLOCKED**。G1–G6未开始；没有后台研究进程或定时任务。

## 本轮事实

- 原包23文件已解压并校验，主仓库基线`5d497c8ae22100953f66c3c5b54746ca87e09f01`；本轮开发分支`codex/execution-pack-v2-g0`已合并至`main`。
- 30行能力/验证矩阵、8上游固定版本及源码/许可审查、旧资产缺失清单、Concrete官方1030行与无损输入、评价协议已保存。
- 两处测试可移植性问题已修；最终完整回归1111项：1092通过、19明确跳过，exit0。原两轮失败日志保留；测试通过不等于真实课题或Gate通过。
- Docker实测要求1CPU/512MiB/128PID，实际仍4CPU/16GiB/PID max。rootless无cgroup delegation；其余7项隔离检查通过但不能抵消这3项失败。
- 上游只有静态/源码检查，隔离runtime smoke独立未完成。旧研究账本与私有运行资产未收到，不宣称恢复。

## GitHub交付状态

2026-11-13（Asia/Shanghai）用户完成组织授权后，已确认`open-agent-power`组织的安装包含目标仓库、Contents/Pull requests写权限。分支`codex/execution-pack-v2-g0`已成功推送，首个成功远程提交`257ed278b4ded8d05d21ef7b4f94c29cdc7f5db4`；[PR #1](https://github.com/open-agent-power/auto-research-agentarts/pull/1)已按用户明确指示于2026-11-13合并至`main`，合并提交`269388af8f6d0a3330e5ea0e668459c428071367`。先前403保留为历史失败，当前GitHub交付阻塞已解除。G0资源及上游runtime两个阻塞保持。

## 当前决策节点

本轮只读恢复复核确认环境限制未改变，输入哈希一致；未启动容器资源复测、研究项目或fit。已形成经资源审计及独立审查的[可信本地先行方案](../execution/g0/LOCAL_EXECUTION_DECISION.md)，状态为`needs_user_decision`。原任务包要求先过Gate，故需明确决定是否修订顺序：A允许有限可信本地研究先行、隔离门和G2+保持未通过；B保持原顺序等可用Worker。一般性的“继续推进”不当作选项A的回答。

## 下一动作

在用户回答前仅完成独立的接口/评价准备，不创建研究项目或fit。若批准A，按方案和原课题协议推进；若选择B，按以下原资源恢复路径接续。

由平台提供可强制CPU/RAM/PID与磁盘合同的Worker，再用唯一新输出目录重跑`python scripts/verify_cloud_resources.py --output runs/g0-resources-recheck-<唯一编号>`。完成拟用上游最小隔离PoC并独立复核G0后，沿现有ResearchProject/ProjectController按冻结课题协议执行两轮、观察驱动修订、报告、复现与接续。

[任务板](../execution/README.md) · [G0验收](../execution/g0/G0-review.md) · [基线](../execution/g0/baseline-verification.md) · [本轮复盘](../execution/SPRINT-001.md)。原始日志在ignored `runs/`，公开数据在`/workspace/work/g0-data-research/`；另交付证据包。当前用户权限不能修复平台cgroup委派。

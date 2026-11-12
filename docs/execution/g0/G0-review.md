# G0 Gate review

当前结论：**BLOCKED（资源隔离未通过，上游runtime smoke未执行）**。G1–G6未开始，不得将已完成的G0审计写成产品全功能交付。

## 验收逐项

| 计划要求 | 实际证据 | 结论 |
|---|---|---|
| 核心能力有代码位置和证据状态 | [审计](repository-capability-audit.md)与30行[矩阵](implemented-vs-planned-matrix.csv)（29项核心能力加1条本轮验证），源码/测试源码与本次实跑分开 | 源码审计完成；本轮测试证据另见[基线](baseline-verification.md) |
| ≥3核心上游固定版本并源码阅读 | [清单](upstream/upstream-manifest.json)含8个固定Git上游，[独立审查](independent-review.md)核验HEAD及27个manifest所列许可/README/依赖文件SHA | 源码要求完成；原Clone guide要求的隔离runtime smoke仅有[静态结果](upstream/smoke-test-results.md)（26解析成功/1路径缺失），仍为独立deferred/blocked项 |
| 许可证与运行风险明确 | [上游许可审计](upstream/license-security-audit.md)，不将未核验/受限来源引入产品 | 逐项边界保留；非法律授权意见 |
| Docker CPU/RAM/PID/磁盘限制实测 | [资源报告](cloud-resource-smoke-test.md)，真实内部cgroup与tmpfs输出 | **FAIL**：CPU/RAM/PID均未按Worker请求生效；持久工件配额未证实 |
| 真实课题/来源/评价明确 | [课题](initial-research-task-spec.md)、[数据](research-data-selection.md)、[评价](evaluation-protocol.md) | G1候选已准备；0研究fit/0产品模型发送，非完成G1 |
| 旧本机资产交接需求核对 | [交接](local-assets-handoff.md) | 缺失清单明确；没有伪造旧项目接续 |

## 已保留失败

初始测试缺少h5py导致导入错误；原日志保留，补齐项目虚拟环境后重验。资源探针首版被独立审查发现可造成未来误判，修正版增加真实只读挂载、完整断言及tmpfs ENOSPC检查；首版和修正版原件均保留。当前资源BLOCKED不是测试预期伪造，而是实际cgroup读数不匹配。

## 解锁条件及恢复顺序

1. 提供可实际强制执行独立Worker CPU/RAM/PID及磁盘合同的环境，保留控制器资源余量。
2. 在该环境运行 `python scripts/verify_cloud_resources.py --output runs/g0-resources-recheck-<唯一编号>`；不要覆盖原失败输出。返回0并逐项核对真实内部限制才可标通过，返回2保持阻塞。
3. 在安全隔离与必要runtime条件满足后，为拟用上游机制执行最小PoC。当前只做inspiration_only不构成原guide运行要求的豁免；若正式缩小审计范围，应明确修改Gate决定，不默默把AST检查当运行smoke。
4. 解决基线中实际暴露的可复现运行问题，记录保留跳过/外部资产限制；不能从单个帮助命令成功推导全部产品可用。
5. 独立复核本报告、资源回执及G0-ADR，更新任务板和current，再开展已有控制器上的首个真实课题。

本轮不是持续后台进程或自动化调度，聊天结束后不会自行执行15天任务。接续入口、分支和原始证据为下一轮保留。

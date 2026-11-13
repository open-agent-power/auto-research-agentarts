# G0-ADR — 保留现有控制器，先解决 Worker 资源门

状态：审计决定已记录；G0当前 **BLOCKED**，没有解锁G1。

## 依据

- [仓库审计](repository-capability-audit.md)及[实现矩阵](implemented-vs-planned-matrix.csv)：已有项目/计划/方法/证据/预算/恢复基础足以支撑首课题，无证据需要大规模重写。
- [资源实测](cloud-resource-smoke-test.md)：Docker rootless、cgroup driver=none，请求与实际CPU/RAM/PID限制不一致。
- [真实课题](initial-research-task-spec.md)与[评价协议](evaluation-protocol.md)：使用许可明确的官方数据，在已有确定性方法上验证研究连续性，不冒充新科学发现。
- [资产交接](local-assets-handoff.md)：旧账本和运行附件未收到；新课题不能伪造历史接续。

## G0十项决定

| 项 | 本轮决定 | 尚未满足/不得扩张的范围 |
|---|---|---|
| 1 首课题 | UCI Concrete，1030行、作者I-Cheng Yeh、CC BY4.0、字段与原始来源已核验 | 没有材料领域专家；只作探索性复现，不能批准工程或因果用途 |
| 2 基线 | 原八输入StandardScaler+Ridge alpha1，五折配合比签名分组，训练折均值参考 | 不调参、不删重复、不截断数据、不借历史优势选新赢家 |
| 3 评价 | 独立算术、状态/预算/重放、计划因果顺序；保留坏组与负预测 | 全部是已见公开案例；不能称隐藏任务或跨域收益 |
| 4 模型/runtime | 本轮审计使用宿主agent；产品初始复现0外部API发送；需要时沿现有delegated请求保留真实原回答 | Codex已登录不等于产品已有Codex适配器；无模型API凭据/新增采购，不宣称独立无人值守模型运行 |
| 5 Worker | 默认无网络、非root、只读根、受限临时盘、CPU/RAM/PID/时间限制；重Worker最多1 | CPU/RAM/PID目前未生效；必须先平台修复，不能用inspect请求值或rlimit替代cgroup验收 |
| 6 跨课题数据 | 五个历史公开家族可复现；后续另选独立任务集 | 不用已读历史题宣称sealed transfer/RSI收益 |
| 7 RSI晋级 | 在独立worktree与可隔离Worker、可信评价器条件成立后再制定候选权限和promotion | 当前不创建自修改候选、不自动晋级、不改评价器/账本/权限 |
| 8 本轮范围 | 依计划先G0，通过后完成一个真实表格课题两轮及独立接续；RAG/算法后续 | 时间窗口、Agent数量、测试数不替代Gate |
| 9 旧runs | 明确未交接；使用新云端lineage并保留历史边界 | 不重建旧预算或身份；旧项目恢复需原件 |
| 10 上游引入 | 先固定commit/许可/源码；本轮只机制参考，不安装整合大框架 | 受限许可证、实际不同入口和未公开代码均单独记录，不把名录当集成 |

## 行动与替代方案

当前继续可独立完成的源码、资料、基准、评价与交接工作；不启动依赖G0的实现/研究阶段，不开启不可信候选执行。需要平台提供具有 `cpu memory pids` cgroup delegation 的Docker Worker，或在另一个可强制实施同一合同的执行环境重做相同探针并保留原始证据。

上游8个仓库已固定并源码审读；静态检查尝试27个Python路径，26个解析成功、1个猜测路径缺失并保留，正确实现随后另行源码阅读。Clone guide要求的隔离runtime smoke仍独立未完成：GPU/API/Worker条件不足、尚未确立生产集成需求。仅参考机制不构成擅自豁免；保留deferred/blocked，之后运行拟用机制最小PoC或明确修订审计范围。可选SWE/算法/OTel扩展未全克隆，不计本批核心已覆盖。

当前UID无委派权限且无环境恢复/资源配置写入工具。不会改宿主安全设置、启动竞争daemon或用privileged绕过。仅用宿主4核/16GiB总限制无法约束单Worker、PID或控制器余量。

如果用户决定修改执行计划以允许受信任本地进程先行，需要明确记录新的计划决定与边界，再由独立审查判定；当前没有这种决定，不自行放宽。

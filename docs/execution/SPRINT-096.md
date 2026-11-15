# S096：Host 质量计划采用的真实进程中断

隔离合成 Host 回复与 Project，在管道栅栏确认已持久状态后实际 `SIGKILL` 子进程（退出 -9），以不同 PID 和完全相同原 Host request/registration ID 恢复，并注入禁止模型、`step`、dispatcher和可写 `save_plan` 的守卫：

| 切点 | 原ID恢复 | Project 工程工具 |
|---|---|---:|
| Host nonce意图已写、Project未创建plan/claim | `OPERATION_INCOMPLETE`，原状态保留不派发 | 1/2 |
| Project plan+claim同事务提交、Host applied回执未写 | 核原意图/claim后只读收敛Host applied，Project数据库及原件不变 | 1/2 |

作者及独审分别2/2通过。独审前一切点 killed PID `63407`、恢复 PID `63417`，后一切点 killed PID `63387`、恢复 PID `63397`，两次均 -9；独立核质量 parent/child/action/result、SQL fingerprint、source/工件及原Host context/prompt/proposal/response，恢复前后 Project DB、预算和原文件不变，0新模型/fit/evidence。作者日志 `runs/s096-host-process-recovery/final.log` SHA `4dfb9f2bfc5b2fd562fc4e0cf30e647d368fc4b0b2879199768b6639cc254662`；独审 PID 为另一次实验，不混称同一日志。

最终实际 HEAD `38fd1fd4dcef518dbbfcdeb661fdcbd39b1d7ea8`，测试前后相同；相对 S095 `27c52df4015f1052df504a290824e57d8fc1bfa2` 仅两份 latest-report 文档变动。首次运行时主代理提交了该交接文档，测试期间HEAD变化；首轮结果保留但不以其作为固定HEAD验收，随后在新HEAD重跑。测试文件 SHA `a11dd7c33cd37f303b36f3676db6a33597d22d736d382b6dd8f5d2629e4d38a8`。

上述为选定切点的隔离合成 SIGKILL，不代表断电、所有中断时序、OS隔离或真实模型看过/采纳反馈，也没有新真实研究/模型/API；开发费用/token unknown。原 Bike pin/2/2预算保持。

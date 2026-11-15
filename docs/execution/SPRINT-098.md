# S098：工作台→Host→Project 三层进程中断

在隔离合成 Project 和保存的模拟 Host 回复上，以管道固定三层持久化的四个切点，父进程实际 SIGKILL 子进程（退出 -9），再由不同 PID 使用完全相同的 manager/Host 原ID与body恢复。核 manager 原body/nonce/intent SHA、Host intent/原回复/context/prompt/proposal、Project claim/plan及原质量 action/SQL/工件，守卫禁止新模型、工具、dispatch及Project写入；只允许终态路径原 save_plan(_validate_only=True) 认证和补 manager 回执。

| 中断切点 | 原ID恢复 |
|---|---|
| manager意图已提交、Host前 | OPERATION_INCOMPLETE；三层保留 |
| Host意图已存、Project前 | OPERATION_INCOMPLETE；三层保留 |
| Project plan+claim已提交、Host回执前 | OPERATION_INCOMPLETE；不替Host认领 |
| Host已applied、manager回执前 | 验原Host/Project claim后只读收敛manager回执 |

作者及独审各4/4，独审对应 killed→recovery PID 64502→64512、64482→64492、64522→64532、64462→64472，被杀进程均 -9；各保留已有合成工具1/2，无新增模型/fit/evidence。最终实际 HEAD 前后均 18377f23a6be1d5b3f72bb7d2de0d34213155499，包 identity d97b348659dd1efc6fc020d8d73454f258e16bc64f4103cddbdb57103e950fd4，测试 SHA caf551df3948f294afbf427e3c34b77962233a7e3ea62c8730a9372ab96b7f21；作者日志 runs/s098-manager-host-process/initial.log SHA 7639d8e41f2422204d9bf2e015cf8029bc759aa1737c5f45cea6517f791a704f。独审PID为另一轮，不混称同一日志。

只覆盖选定的进程终止栅栏，非实际断电、全部并发时序或OS隔离；没有新真实研究、真实模型/API、fit，费用/token unknown。旧 Bike 原pin和2/2预算保持。

# S088：质量计划与策略的真实进程中断验证

在隔离合成 Project 中通过管道栅栏固定五个 manager/core 提交位置，再由父进程对真实子进程发送 `SIGKILL`、确认退出码 -9，启动不同 PID 的新进程按完全相同的请求 ID 和 body 恢复。恢复过程对重派和 `step` 设置失败守卫，核原 Project SQLite、claim、parent/child、SQL fingerprint、工件哈希及预算。

| 切点 | 原 ID 恢复结果 | 合成工具用量 |
|---|---|---:|
| 计划 manager 意图已提交、core 未开始 | `OPERATION_INCOMPLETE`，停查 | 1 |
| 计划 core 已终态、manager 回执未写 | 只读核原 claim，回填 completed | 1 |
| 策略 manager 意图已提交、core 未开始 | `OPERATION_INCOMPLETE`，停查 | 1 |
| 策略 core parent 已 prepared、尚未 dispatch | `EXECUTION_UNKNOWN`，停查 | 1 |
| 策略 core 已终态、manager 回执未写 | 只读核原 claim，回填 completed | 2 |

作者、主代理和独审分别运行 5/5，通过时均是实际不同 PID 和真实 `SIGKILL`，不是抛异常模拟。独审执行分别为计划核心前 `56207→56217`、计划终态 `56187→56197`、策略核心前 `56247→56257`、策略 prepared `56267→56277`、策略终态 `56227→56237`；每个被杀进程退出 -9。主代理的原始输出 `runs/s088-process-recovery/owner-validation.log` SHA `c1c465ff2d8789b6da8614e7d7374e6dc2630fd261acddbbd254cb9c369c7946`，测试文件 SHA `197ee1bc790ee97808b7d9f4b8835912b0cc94efafd9b044552807384ad6ff41`。

测试实际 HEAD `cb6f18f0f2cd1184997e0c2289b1ed5cfe811d86`，与 S087 执行源码 `11db75aa76e6c3eb5d1fdbd7cbc257ae0b59b63c` 仅两份 latest-report 文档不同，生产代码一致。测试仅使用新合成项目，本轮无新真实科研行动、模型或fit；本地合成工具及文件 I/O 实际发生，成本/token unknown。验证范围仅五个选择的进程切点，不等于电源故障、所有中断时序、恶意篡改或 OS 隔离测试。旧真实 Bike 项目原pin与2/2预算保持。

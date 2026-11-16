# S132：仅固定合成包的严格质量首行动

这是已独立验收、供隔离合成测试的 opt-in Python 入口；不接 HTTP/UI，不接收真实 UCI 或任意调用者声明的“合成”数据。唯一允许的输入是 [四行人工 packet](../../examples/synthetic-strict-quality-source-v1.json) 的精确原 bytes SHA-256 `dd88f02f49fd94c830ac3ef12ed307f437d52cc12c9b1b298a9585d8082ac799` 和 source snapshot `b4097316500039827e13d11c86691eaef349da52558828600157d3df63f84c29`；其来源描述是工程 fixture，不是数据许可、签名、研究授权或防篡改证明。真实 UCI 仍缺固定站点/时区、来源与许可、时间报告对 source 的锁内认证等前置条件，不可通过本入口执行。

先由操作者为同一原 Project 保存计划并经 S084 完成质量条件登记；调用 `LocalWorkbench.advance_tabular_quality_primary` 必须提供六字段：`request_id`（原登记的 future Controller ID）、`project_id`、`expected_state_version`、`registration_request_id`、`registration_sha256`、`reason`。入口在 manager→Project 锁序下核原 manager 登记意图与 Project claim、原包/计划/候选/预算和未决状态，然后保存独立 manager intent。只有首次接受者可创建带版本 marker 的原 Controller parent 与 parent claim；唯一原 child 的 action 与 child claim 在另一 Project SQLite 事务提交，之后最多首次进入质量工具。三个事务不是跨库原子；任何首次接受后异常、parent/child 缺失、非终态、失败或原件不一致均保留原 ID 并停查，不通过旧 Controller、普通 Project `step`/`resume` 或新 ID 重派。

`resume_tabular_quality_primary` 只接受原 `{request_id, project_id}`，锁内读取原 manager 完整 body，缺原 intent 不创建；仅原 parent 与 child 均 completed、登记/claims/SQL指纹/原 canonical 工件/source/producer 和历史计划完整时返回原结果。若核心已完成但 manager 回执尚未写，可核原 claim 后补回该回执，故恢复不保证零写。质量行动完成后条件值可能合法 `quality_values_unknown`：原行动仍可按 ID 认证回读，反馈保持 unknown；质量关联后继仍须停，不能填0或称通过。代码/工件/SQL/claim损坏导致的未知不被视为合法数值未知。

保留原质量 reader 所需的 `controller.advance_selection` request/child 形状，标记放在 parent 外层。Project 在同一账本连接中双向核对 marker 与独立 SQL claims，缺一或不一致即停止；质量 reader 还核原登记及 parent/child claim。两者均处于同一本地账本，不能检测 marker 与 claims 协同删除、账本整体重写或恶意进程，也不建立跨库签名或 OS 隔离。新身份改变 Project、Controller、reader 和 manager pin；旧 Project 不迁移，旧 wire/无 marker 行为以回归为限。

作者候选合成专项 12/12、旧质量及 staged 回归 92/92 通过，但该92项在最终reader补充交叉校验之前；最终版独立新进程72/72通过（含12项新专项、旧质量reader/策略与旧staged primary），HEAD `b0715cd76b88f7d87b53bfff2970bdaa67fecd4f` 加候选199项清单 SHA `a73a2c8903c5a361d94e66fbadab374712d35bf834d0f0be9a9df6ee4eed8e1f` 前后匹配；第一次专项的两项测试预期与新增严格状态读取门不一致，原失败 `runs/s132-strict-quality-wip/author-v1.log` 保留，测试修为只读原 SQL 记录并明确验证 status 停查。已测注入是函数/SQL 注入，不能宣称实际多进程竞争、SIGKILL 或断电；费用与完整环境隔离 unknown。真实来源适配、时间绑定和真实执行授权仍是后续独立步骤。

# S084：表格质量反馈接入工作台

将已事前登记、原行动认证和显式 Controller 策略接入 `LocalWorkbench` 的 Python 和受保护 HTTP：提供登记、只读反馈、显式推进；旧接口形状保持。工作台保存原 body、项目/source/code 和唯一 nonce/根目录身份，核心 Project 的 SQLite 同事务保存绑定原登记或策略请求的协作式 claim。manager 原意图缺失、claim 不一致、核心缺失或非终态均停查；仅核实原核心终态与归属后按原 ID 收敛外层回执，不重新派发。此关联不防可读写双方账本的恶意进程；不是 OS 隔离。

作者侧七模块66/66合成通过；独审另跑 manager/HTTP专项14/14、直接策略/reader及旧HTTP/选择41/41，并额外注入删除两类外层原意图后重试，均不重建/不派发。测试覆盖原 HTTP 端到端、Origin/CSRF、只读路由限制、两个进程锁竞争、manager意图提交窗口、核心记录与claim事务回滚、claim 缺失/篡改、直接 core 同ID同/异 body 抢先、原终态回执恢复、非终态停查及超过展示上限的 pending。测试使用隔离合成 Project，含本地工程工具和文件 I/O；没有新真实研究/模型/fit，不证明真实断电恢复或科研收益。

审查先发现外层意图丢失时可认领已有 core、首次预检与 core 同ID竞争、缺回执时无法证明归属以及确定性 intent 无法区分多个 manager；分别增加核心未占用检查、Project writer 内保存原意图、核心同事务 claim 和唯一 nonce/manager 根身份，并以最终版本重新验证。初轮一项测试先命中 STALE_STATE，修正夹具；早期版本测试结果不计最终验收。文档把 pending 门过度描述为全局，独审后按实际 `_no_pending_batch` 调用范围修正。

原 Bike Project/manager SQLite 本轮前后 SHA 保持 `26aa23c73e6f50025c7cd0bf4d58196a8f12050c7b65496bc098903911204080`、`0413c121e3e63115fa4140b87c1c24061fadca70f4acd9e0dd73e5271db6d49c`；原 pin clean，原2/2预算不重开。未知开发 token/费用保持 unknown。只读宿主模式尚不提供新反馈 GET；普通活动工作台支持新端点，UI 尚未接入。计划 v2 结构化原行动引用、完整跨领域迁移、模型自主与完整 RSI 仍未证明。

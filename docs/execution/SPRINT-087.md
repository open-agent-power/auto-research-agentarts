# S087：质量引用计划与策略 v2 接工作台

普通活动 LocalWorkbench 新增独立质量引用读取、质量计划保存与显式 v2 策略推进的 Python/HTTP 路径。原普通 `/plan` 和旧策略不隐式升级，`plan-resume` 不处理新质量路径。计划引用实际绑定原质量结果，首次策略使用真实最新直接后继计划，历史计划只供原证据认证；既有预算及候选门仍生效。

manager 保存原 body、nonce、根目录及 Project/source/code 身份；质量 plan revision 与 plan-kind claim、v2 parent 与 policy-kind claim 分别在原 Project SQLite 事务中同时保存。外层原意图缺失、核心/claim 缺失或不匹配、非终态等不造新请求；只有认证原终态/归属后可按原 ID 收敛回执。锁内先提交 manager 原意图，再由核心各自取得 writer；直接core同ID抢先不能被认领。该机制仅约束显式入口，是受信合作归属，不防可改写账本者，非全局低层门禁。

作者八模块90/90、独审新专项15/15及旧质量Workbench/plan/v2/预测40/40合成通过。覆盖实际本地HTTP、Origin/CSRF、双进程锁、manager/core事务回滚、缺claim/原意图/nonce漂移、同异body直接core抢先、核心终态外层回执丢失、非终态停查、预算/计划漂移和只读宿主404。双引用合成计划同时核历史经验及质量行动；独审注入 experience 原件在预检后漂移，拒绝写入且manager DB不变，quality SQL漂移亦拒绝。仅隔离合成及模拟中断，不证明真实断电恢复、OS隔离或科研收益。

本轮原 Bike Project/manager SQLite SHA 分别保持 `26aa23c73e6f50025c7cd0bf4d58196a8f12050c7b65496bc098903911204080`、`0413c121e3e63115fa4140b87c1c24061fadca70f4acd9e0dd73e5271db6d49c`；旧 pin/2/2预算不重开。无新真实研究/模型/fit，开发费用/token unknown。用户界面未接此新入口；只读宿主的新 GET 仍不可用。现有结构化链不证明模型自主采纳、科学许可或跨领域科研收益。

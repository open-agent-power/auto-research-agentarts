# S086：基于质量引用计划的 Controller v2 策略

新增独立显式 Controller Python v2 入口：writer 锁内核当前最新 plan v2、其结构化质量引用、原登记/计划/parent/child/SQL/工件/source/code及行动顺序。已认证的条件满足时，按真实当前 context 和预算选择唯一原质量行动/result 绑定的数值关联候选；不满足等待，未知、漂移或身份异常保守等待或拒绝。历史计划副本仅供原质量证据核验，不作为当前选择/派发状态。旧 v1 不隐式升级，已有原 ID 非终态仍锁内停查；终态使用原冻结 plan/context核验。

作者七模块78/78合成通过；独审新专项14/14与旧策略/计划/selection 29/29合成通过，覆盖双进程同ID、met/not_met、预算不足/候选异常、source/code/SQL/工件漂移、后续计划、v1/v2/旧入口交叉、原拒绝与非终态。独审发现父ID作为 orphan replay target 时可能误认未使用，作者补 parent/child 两方向检查和故障注入并以最终版本重验。相关合成包含本地工程工具与文件 I/O，不证明真实断电恢复、OS 隔离或科研收益。

原 Bike Project/manager SQLite SHA 分别保持 `26aa23c73e6f50025c7cd0bf4d58196a8f12050c7b65496bc098903911204080`、`0413c121e3e63115fa4140b87c1c24061fadca70f4acd9e0dd73e5271db6d49c`；旧 pin/2/2预算保持。此次无新真实研究、模型或 fit，费用/token unknown。Workbench/HTTP 对新计划字段及v2策略尚未接入；下步单独以原manager/core归属和原ID恢复协议接线。新入口不构成所有低层调用的全局质量门，亦不验证许可或模型自主。

# S097：Host 质量计划采用接入工作台

S094 的显式 Host 质量计划采用现已接独立 LocalWorkbench Python/HTTP 入口。manager 的独立原请求ID、Host/Project 原请求ID保持各自身份；manager先保存带nonce、root、完整原body/Project/source/code等的原意图，新版本 Host 意图绑定 manager 摘要，Project在计划修订同一SQLite事务保存绑定 Host 意图的claim。仅完整原链核对后可按原ID补manager回执；意图或claim缺失、Host非终态、直接Host/Project抢先等停查，不重派或认领。该链是受信本地协作式关联，不是跨数据库/文件的原子事务或对抗性隔离。

计划四文本和理由来自原保存Host proposal，质量引用由宿主附加并回查原质量行动；revision本身不带模型来源标签，须结合Host原意图和Project claim。HTTP返回有界状态/计划身份，不返回Host原prompt、原response、nonce或路径；原普通Host/计划接口wire不隐式升级，受限readonly宿主不开放新POST。该入口不发模型请求，不将条件判断解释为科学资格。

作者新专项12/12、旧合同八模块63/63（实际exit 0，日志 `runs/s097-host-quality-workbench/legacy-regression.log` SHA `47b6789ada24a28af15fb580ab7131bcbb28e05c60564f73bd4341d9636048e8`）；独审新+旧合计43/43，冻结文件前后SHA一致。隔离合成覆盖原计划采用后v2策略关联、四个模拟中断窗口、直接Host/Project同异body抢先、真实双进程竞争、三层身份/claim篡改、活动项目/pending、Host/Origin/CSRF、readonly、HTTP脱敏。独审指出manager多表读取须同一SQLite快照，已加只读事务。合成包含本地工程工具/I/O；无新真实研究、模型/API或fit，费用/token unknown。

测试使用人工构造并保存的Host回复，不证明真实模型看到、理解或采纳反馈，也不证明自主科研收益、实际断电恢复或OS隔离。原 Bike pin/预算和旧Project不升级；下一步按实际执行优先级评估三层真实进程中断窗口，不凭单元测试宣称恢复完整。

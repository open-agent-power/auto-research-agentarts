# 研究决定引用已绑定的历史经验

原case已经通过显式导入进入研究上下文，过去只能在rationale文字里提及。source2cdff0a给直接选择提案增加可选`experience_case_refs`，最多四个不同的`case_id/case_version/bundle_sha256`，必须精确匹配同一冻结context中active案例。缺少该字段时旧提案、保存决定和读取视图形状不变。

引用是提交者声明的来源索引。它不把历史case变成当前证据、不证明适用或收益、不新增候选、权限或额度。范围不匹配的active案例可以作为反例引用，原association仍按记录显示；不能用case ID冒充FTS证据。未知、退休、错版本/包SHA、重复或超额引用被拒绝。

Controller将原引用保存到selection_ref，历史selection view核对它与原proposal/冻结context一致，报告JSON保留对应原association。新请求不能使用退休前旧context；已接受的原ID同内容重放继续使用原冻结记录，不根据今天状态改历史。

本阶段只有直接human/external proposal入口支持。内置Host/local-model及recipe仍保留旧格式，不能据此声称它们会主动引用经验。真实工程验证使用两个原CPU经验包、一个新隔离合成目标，等待决策、报告序列化、退休/重放和非法引用47检查通过；工具上限1但实际0调用，fit/model上限0。它证明来源可核对，不证明自主研究或记忆因果收益。[完整S032验收](execution/g5-local/experience-case-citation-verification.json)。旧sourcepins/科学预算和原case不改变；已安装source de20/wheel33287不含此新增接口。

后续[S033](execution/SPRINT-033.md)增加按新context能力标记选择的Host/local-model可选引用消息，旧无标记协议字节保持；recipe未扩。已有模拟日志证明接线，未证明真实模型生成引用。跨源码pending保留原身份门禁，须按原pin恢复，不能把格式兼容当作执行兼容。[当前运行时缺口](model-research-readiness.md)。

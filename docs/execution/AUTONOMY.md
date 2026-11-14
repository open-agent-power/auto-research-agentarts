# 自动检查、对齐与继续开发

用户明确要求云端定期检查成果、与项目要求对齐后继续推进。采用单个每3小时触发的任务；这是平台定时触发的开发轮次，不是24小时不停运行的模型进程。手机应用关闭不应作为执行前提；实际是否启动/完成以平台任务记录为准。环境离线、授权到期或平台暂停时如实报告，不假报成功。

## 每轮入口

1. 检查继承云电脑是否可用、仓库是否为`/workspace/auto-research-agentarts`，origin应为`open-agent-power/auto-research-agentarts`。缺少旧云盘时不重建历史账本、不宣称旧证据已恢复。
2. 使用全局adaptive-agent-workflow与项目AGENTS/research-dev-router导航，读取`docs/project/current.md`、`docs/execution/README.md`及本文件，按需查看pack-v2原始阶段要求、最新Sprint和审查。用户已将dev-system归档停用，不因旧文档引用恢复它；遵循当前授权的准备/执行阶段。
3. 使用`scripts/project_autonomy_guard.py`的status/claim/heartbeat/release协调本地开发。每轮使用独有owner，默认1200秒lease。已有未过期owner时只读检查并报告，不能在同工作树并发写。编辑、执行、提交前heartbeat确认仍持有lease；长步骤前续租，结束后release。该lease只协调配合它的执行者，不是权限或研究预算安全边界。
4. 先检查git状态和已记录活动；保护已有未提交改动，禁止reset/clean或覆盖另一执行者。按原请求ID恢复pending/unknown；不得新ID、复制目录或新项目重置旧研究额度。不得改冻结评价器/协议/原件来迎合分数。
5. 对照原要求与真实证据，明确已实现、已验证、原Gate缺口和下一小步。选一个具体可验收增量完成代码/真实验证/必要独审，不能只输出下一步计划。已有用户授权允许验证后直接合入并推送main，无需草稿PR或例行确认。
6. 保留实际失败、负结果、成本和代码/数据身份。研究预算与工程fixture拟合分开统计；未知金额/token不写0。原隔离未通过已被用户接受，不再反复索要同一Worker；不假称OS/sealed/多代RSI通过。
7. 不新增采购、付费模型/API或外发消息。既有明确0模型/API切片保持；新增研究先冻结范围、预算和评价，旧case与服务source pin保持。只有需要用户选择的新真实阻塞才提问，其余可独立工作继续。
8. 每一大轮更新current/context/Sprint和证据入口，必要检查通过再推送。报告本轮完成、实际测试/结果、尚存边界、下步与具体决策项；时间不足先保存可接续状态。结束清理自己的lease，不删失败原件。

凭据恢复实测：上轮GH_TOKEN曾失效，此次继承环境恢复后的新CLI会话已普通推送成功。先用新进程实际验证登录，不把过往401当永久无权限；无需重复索要既有开发/推送授权。保留失败记录和所有原Git提交SHA，禁止因远端落后reset本地或用新的commit元数据冒充冻结源。

## 持续推进与可复用团队

定时任务是周期检查、对齐和汇报，不是每完成一个增量就结束的指令。已有持续开发授权时，增量验证和必要独审通过后保存里程碑、短报结果并继续下一可做任务；不等待下一定时触发再开始。仅在实际执行窗口结束、环境不可用或确需用户选择的新阻塞时保存接续，不能以后台进程或enabled配置代替真实模型持续执行。

由主代理维护同一团队池，先复用仍可调用的成员、按任务赋角色，可兼任相关实现/验证/打包，不按小目标拆新人。默认团队池包含主代理和各级子代理不超过10人，同时遵守宿主更低的总量与并发限额。新建子代理优先gpt-6.1-terra/ultra，按宿主约束使用fork_turns=none并给必要上下文；不能原位换模型的已有成员继续优先复用。独审由未参与该实现的其他成员承担，不因改角色名自审。成员和角色不扩大产品模型/API、研究额度或文件写入权限；同工作树lease与一文件一writer继续有效。

## 自主研究优先级

用户最新明确提高自主研究能力优先，并允许继续查找、拉取参考项目或探索。默认先选能推进“问题/可证伪假设→实验选择→真实反馈→下一决定→同ID恢复”的产品增量；已有条件允许时，减少非阻塞的界面、包装和报告润色工作。参考必须固定版本、许可与真实代码入口，能用现有能力时先复用，再原生适配并验证；不能把clone、阅读、单元测试或模型自评计作科研收益。

该优先级不重开原研究或模型额度，不授权新增付费API/采购，不复制许可未明代码。后续研究仍先固定输入、评价、有限预算与恢复身份；可独立推进的零模型工程和只读机制研究继续，不因研究模型额度耗尽停止全部开发。

## 参考项目的真实状态

云端参考目录`/workspace/references/upstream/`及`/workspace/references/manifest.json`已存在。2026-11-13再次核对8仓库均为真实Git checkout、HEAD与固定清单一致、工作树clean：autoresearch、AI-Scientist、AgentLaboratory、prime、OpenHands、software-agent-sdk、beir、ragas。核验原件`runs/autonomy-setup-20261113/reference-check.json`。

[G0复用矩阵](g0/upstream/reuse-matrix.md)是当时的决策，不等于安装完成。现有实际路线：

- autoresearch/AIDE²的固定评价、有限候选与keep/reject思想用于自研原生协议；G4已完成真实helper差异/受限与原生确认/独立审查/源码集成，非上游GPU训练复现。
- AI-Scientist、AgentLaboratory的阶段上下文、实验快照与审阅机制已研究；保留我们的JSON/SQLite账本，未引入其任意exec/pickle链路。AI-Scientist许可证限制仍保留。
- OpenHands根目录与canonical SDK分开审计；SDK coding-worker属于后续可选适配，未宣称runtime已集成。
- BEIR的SciFact原件/许可/引用qrels及固定IR指标已有真实CPU对照；现在继续接入同一原生研究框架。Query metadata原始注释保留但不参与当前排名或评分；不把citation retrieval当事实真伪判定。
- Ragas评测接口/成本已经研究，当前使用确定性IR指标；未开启生成模型或LLM judge。
- 提供的Prime地址实际为服务CLI，不能冒称已合入预期训练harness。AIDE²只有论文证据，未定位的源码不宣称拉取/复现。

参考更新先fetch/另存版本并做许可、能力与适用性审查，保留已冻结checkout和运行身份。适合的机制以明确适配/差异/验证合入；不把互不相关仓库整体强行merge，也不因为上游自称成功就标本项目Gate通过。

## 每次触发的工作与汇报

保持现有单个每3小时任务，不把“定期启动一轮”表述为轮间也有常驻模型执行。会话仍有执行时间且有可做增量时继续；需要结束时保存真实交接，不假称后台仍运行。

每次触发都在本会话返回中文报告，包括无新提交、失败、环境不可用、凭据失效或lease被占用。不能因为没有进展而静默。使用Asia/Shanghai北京时间，说明本轮起止、实际代码/commit、验证与负结果、活跃执行状态、阻塞、下一任务及下一计划触发时间。平台没有执行/投递回执时标unknown，不从enabled或触发时间推断完成或手机通知送达。

持有lease的执行者同时更新 docs/project/latest-report.md 与 docs/project/latest-report.json，精确来源留在ignored runs；内容随Git保存版本。lease被占用时只读核对并final汇报，不为保存报告并发写工作树。报告继续使用平台任务回复；没有邮件、Slack或其他外发渠道授权。

## 后台配置与可验证性

调度任务ID、环境继承结果和下一触发时间保存于ignored `.agent/autonomy/automation.json`，配置/结果原件在`runs/autonomy-setup-20261113/`。平台success+enabled只证明配置，首次真实执行与环境可用性另行核验。由任务卡调整或暂停；工作成果与证据继续留仓库/云盘，不依赖手机聊天缓存。

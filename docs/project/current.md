# 当前自主研究开发
Status: resumable

S080 已完成获批的 Bike 2011 真实研究并独立复算：总体/编码0/编码1 Pearson r 为 0.771214/0.762433/0.779847，n 为 365/115/250，预先固定方向条件满足；两项工具 2/2、0 model/fit/native evidence，原计划等待。[结果和限制](../execution/g1-local/bike-2011-results.md)。这是操作者根据质量反馈修订计划的描述性链，不是模型自主或因果/跨年收益。唯一 claim、原 Project 与源码 pin `7926608e981eaf1fdfc94c0d125ae04b7f4423da` 必须保留，不重开额度。

通用表格质量反馈按[设计](tabular-quality-feedback-design.md)继续推进：S081 有界条件、S082 事前登记和原行动认证、S083 显式 Controller 策略之后，S084 已将登记、读取和推进接入 LocalWorkbench/Python/HTTP，并以同事务归属凭据保护两层原ID恢复。隔离合成 HTTP 和故障注入已独审；没有新真实研究、模型自主或科研收益声明。旧项目沿原 pin、原预算保持。[S083](../execution/SPRINT-083.md) · [S084](../execution/SPRINT-084.md)。

S085 Project Python 能保存引用原质量行动的直接后续 plan v2；S086 显式 Controller v2 策略可重新认证原行动与真实最新计划；S087 已通过独立 Workbench/Python/HTTP 入口连接质量引用读取、计划保存和v2推进，原 manager/core 归属同事务绑定。隔离合成和独审通过；旧普通计划入口仍拒新字段，只读宿主新 GET 未开放，context仅校引用形状。[S085](../execution/SPRINT-085.md) · [S086](../execution/SPRINT-086.md) · [S087](../execution/SPRINT-087.md)。

S088 在五个固定 manager/core 节点以独立合成Project真实 SIGKILL 子进程，再由不同进程用原ID/body验证停查或终态回执收敛；作者、主代理和独审各5/5，原Project DB/工件/预算不变。只覆盖选定进程切点，不证明断电或所有恢复时序。[S088](../execution/SPRINT-088.md)。

参考调研：本轮固定并只读审查 MIT 的 Meta Ax `fd8a67a524b063b2615815c638af2c94b034f476`；它允许行动完成但指标缺失，印证本项目应区分完成状态与反馈 unknown。转移/暂停顺序与本项目规则不同，不直接合入或覆盖原预算门；未运行 Ax。[源码对照](ax-transition-review-20261115.md)。

2026-11-15 用户已对 Bike 2011 方案回复“同意”，批准一次独立真实项目，最多 2 次本地工具、0 模型、0 拟合、0 新增原生 evidence-read；不改变其他预算。原云盘和原全局执行者状态仍未知。

S079检索候选元数据筛选未找到可直接准入项；PubMedQA许可未核且搜索返回公开示例，QASPER许可检索亦意外返回公开test示例，现已停止查看样本，不可称完全未曝/盲测；bioCADDIE规模和qrels权利未核。无新数据下载/项目/排序/模型。[审计](retrieval-candidate-audit-20261115.md)。

S078当时完成并独审Bike方案的隔离合成预演：两个合成Project各2/2工具、0 model/fit/evidence，可计算与constant_predictor/unknown、原观察→人工plan v2→关联、作者原ID新进程重放，独审复算并核回执但未自行重放；该轮未下载真实Bike或创建真实项目。之后用户批准且 S080 已完成真实研究，见文首。[SPRINT-078](../execution/SPRINT-078.md)。

S077新表格Project可显式保存操作者描述性研究用途，已独审推送 `3ba33b62a0d8456fb0d04765285e11d0b7e1195c`；默认旧wire/旧pin不变，仅Python创建支持，非授权/领域验证/新研究。原S065只读status字节同与3/3预算保持，pin193项匹配。[SPRINT-077](../execution/SPRINT-077.md)。

S076真实表格候选[Bike 2011预案](bike-sharing-2011-study-proposal.md)当时仅元数据/接口独审；S077补Python创建的显式用途声明，Workbench直接创建不支持该选项。随后用户单独批准，S080 已按独立范围实际执行；勿将 S076 时未取得原件、未授权等历史状态误认为当前事实。

S075已发布后只读S065/S067原保存validation联合分析并独立复算，结果 [S075](../execution/SPRINT-075.md)：S065召回提高3题其中2题MRR下降；S067召回不变198题中24题MRR下降/12上升。已曝数据事后描述、非盲测/总体收益/迁移；无新模型/fit/排名/行动，原3/3预算保持。reader commit `a8207f63c3201eb2e601dc81642d15342943813b`、pin195项匹配，公开结果SHA c0adf1d0edda145af95da1dfdf94f19a85ceb71decb0e290a90fbdd3734e31cb。

**当前执行基线：** [自主研究任务基线（2026-11-15）](research-baseline-20261115.md)，外部证据与适配见[方法调研](baseline-research-20261115.md)。以可复核真实问题、反馈改变下一决定及原身份接续为首要验收；工程测试不替代科研收益。S074已完成限定范围验收，按基线登记并验证下一研究切片；不改旧盘、预算或授权。

S074计划引用UI与原请求恢复已独审推送 `ea8152e595abca322870a9eb6c7fbc0b9e1eebbf`：两真实进程中断窗口同ID恢复、原来源漂移拒绝、脱敏和跨项目pending已验；UI未保存草稿跨项目返回的完整往返独审未完成，旧无body为unknown。原正文仅本地manager，禁止假称零写入/OS隔离；pin195项匹配。[SPRINT-074](../execution/SPRINT-074.md)。

S073可选计划结构化case引用已独审推送 `340e198ec5bc5a45585e4ddd2360d31d6f0741c3`，锁内核active原bytes、历史按接受版本、撤回后原ID可重放，登记后的计划改变不放松原假设绑定；四条长声明逐条完整出现在Markdown/PDF。固定相关33/前版71，独审5+2及旧wire通过，仍无Workbench引用编辑控件；pin193项匹配/1本地probe。[SPRINT-073](../execution/SPRINT-073.md)。

S072原项目wait→经验引用→原登记primary→新conditional闭环已做合成工程验证并推送 `9df7f3ad6743763a2471ac45d9ae6d0982da1b32`；原wait/primary/conditional跨进程原ID重放，3/3正向、额度用尽等待、unknown null及漂移拒绝均核实，作者/独审各3/3。无产品源码/真实科研/模型新增；pin 193项相同，3本机probe不在Git pin。[SPRINT-072](../execution/SPRINT-072.md)。

S071等待经验已独审推送 `49a9274dc243eb311e18eb00615ba873917a11f0`：known反馈绑定原primary，controller_not_started的action/value保持null，final仅当时未测、后续可继续；Memory/目标计划/报告/Workbench接入，项目漂移拒绝。旧工程原件只读；固定版23相关/独审4及真实浏览器两种导入+同ID恢复通过，旧版相关59；真实研究/模型未新增。源码pin 49a9274 196项匹配。[SPRINT-071](../execution/SPRINT-071.md)。

S070修复Workbench拒绝staged v1/v2/v3和错误Ridge卡片，代码推送 `dd7cf66cefe1940d96c08e5e7e7a7388a9439301`；真实Chromium+原后端独立目标导入三版本、原字节与同ID重启恢复通过，加载期间禁用、unknown/单臂与安全文本正确。旧Ridge/CPU独审仅预览；原研究48文件/claim不变，工程目标工具0。隔离构建四产物字节同，pin dd7cf66 238项匹配。[SPRINT-070](../execution/SPRINT-070.md)。

S069可选v3外层比较经验已独审并推送 `5d091b16e45b5b172bf8bee1dc8cbd05c78eccc9`：只对固定S067回源核验后进入Memory/计划/报告，BM25/BM25保留unknown；外层规则是操作者规则，离线不能证明原始绑定和锚前快照。40相关/独审7、旧v1/v2摘要与报告逐字节一致；目标工具used0，原48文件/claim和3/3预算不变。源码pin 5d091b1 的192文件匹配冻结；[SPRINT-069](../execution/SPRINT-069.md)。S068 v2接入见[SPRINT-068](../execution/SPRINT-068.md)。

S067已完成一次真实BoolQ对照并独审：源码pin `5bd9883dd435a1d39b857a51bb6f4d20a53f156b`，project `project-dc1b1b59889f49c0b744254b1a1afd68` / run `run-276475c33d7542509c840bc575005271`；验证集R20差0、MRR差−.023367，A/B均选BM25，final 200题BM25 R20 .97/MRR .858728，双规则比较unknown、TFIDF反事实未测。3/3工具、0model/fit，原ID恢复与48文件相同；公开源/标签曾读取，不盲测、不宣称迁移收益。[SPRINT-067](../execution/SPRINT-067.md)。

S066已完成独审，本提交保存结果：真实S065的事前条件、validation正面和final MRR/nDCG下降已捕获为独立v2 Memory case `s065-hotpot-support-history`，导入工程目标Project并供原计划context；target工具limit1/used0、model/fit/evidence 0，原S065 42文件/claim和3/3预算不变。离线需回源核audit/final，完整bundle/plan留本地；非模型采纳或迁移收益。[SPRINT-066](../execution/SPRINT-066.md)。

S065已按已发布 `5d431097f3b4846ac240745121e56070edd78e86` 和原claim真实完成一次Hotpot支持文档检索：validation R20 +.01/MRR +.0085595/留一最小 +.0050505，事前条件met→原audit→TFIDF；final支持文档R20 .91→.92，但MRR .865984→.830095、nDCG下降。3/3原工具、0model/fit，原ID新进程resume响应及42文件字节相同；费用/token unknown。原project `project-2376ca4a6db64027a1099bd737ca9640` / run `run-a1a631efa41541e2800b43ae047c4c66`，唯一workspace `/workspace/development-continuation-20261114/source-pins/5d43109/runs/s065-hotpot-support-v1`，summary SHA a0eff1bf71981b4a41774e70fcf2fa5aedd0f4c9e421ff250c2bfa52048edcb3。真实实验独立验收已完成；最终是覆盖提升/排名下降的取舍，不宣称整体科研收益或盲测，原语料/报告只留本地。[输入](../execution/g5-local/hotpot-prepared-input.json)。S066已只读捕获这次真实负结果至原生Memory，未重开3/3。

S064经验v2已完成独立验证并推送5e397b2693f2385f26e203af12e7f3f02c6d2507：原事前登记/反馈/audit/freeze/final聚合沿现有Memory绑定目标Project/计划，保留负结果；55相关/独审3+两个目标子例通过，合成原件源状态预算保持，原100文件保持，offline必须回源核原策略及最终聚合。未调用模型/新科研，见[SPRINT-064](../execution/SPRINT-064.md)。

S063已完成固定验证并推送a7f6284cd648e875f2fa309219cfd29e5242706e：新holdout显式事前feedback映射实际控制原freeze选臂，unknown/wait与错误audit不得绕过；专项11/相关92及独审通过，两个合成case正确TFIDF/BM25并原ID新进程恢复，原100文件与v1反馈字节保持。v2经验捕获明确拒绝；无新模型/真实研究收益。[S063](../execution/SPRINT-063.md)。

S062已完成固定验证并推送8090aa7191b3cff8132edd6dcff7e9309ba90e62：staged事前双指标可选单题留一条件，未知整体等待，旧v1/v2及原freeze不变；47相关、5独审，两组实际合成HTTP及异PID原body重放通过，隔离对照中两mean通过但LOO失败正确wait；100原文件未改。见[SPRINT-062](../execution/SPRINT-062.md)。

本轮S061已完成独立验证并推送777f92acaf08ee0c695d94cfd97d70706b308d71：显式plan材料staged_validation_stability供原validation双指标胜负平与单题留一聚合；42相关/5独审、两原案只读对照S060一致，旧freeze/预算和CODE_CHANGED保持。无新模型或科研行动；精确scope见[SPRINT-061](../execution/SPRINT-061.md)。

目标是事前问题/假设→真实实验→反馈→下一决定→原ID恢复。三小时只对齐与汇报，不假称轮间常驻模型。本轮北京时间2026-11-15 07:44:27开始，连续完成S059/S060，精确起止/失败/范围见[最新报告](latest-report.json)。

## 本轮已完成

S059产品/合同 **030af51c4ff06813d08a5f75610dea9f6573ad26** 已推main并回读。新staged-only事前conditions恰2不同validation paired指标，合成AND，单一原primary校验summary供两值，任一未知则整体unknown等待；旧scalar v1不变，新registration/context-v2及混合staged记录明确。原Source/SQL/父子/ID/预算门不放松，S052 freeze仍原Recall20，非全局多目标优化。49相关/6独审纯机制、3真实工程HTTP及新进程原body响应/状态/预算/公开文件精确重放通过，原S054 v1反馈/notice/state/budget旧新进程字节相同。fixed191源SHA4903d279ad6a31045de7b1ec4090cdd29cc67dbfa73c501e050d075d853c98dd/corea05f668cb8de230b134ab4e0394c17297b7aa5cd026c378172bce2001325b4b5；初源兼容微差和HTTP夹具拒绝原件保留。[合同](../hypothesis-feedback.md#显式双指标联合条件s059)。

S060脚本/固定事后方案 **4e17a63af164cd8d0cb49a1e5a3feae458df459d** 在实际计算前推送。原S046/S054各100validation题、R20/MRR两项共400对+400留一均值全量独算通过，3算术边界通过。S054 R20+.01是1胜/0负/99平，移除一题归零；MRR−.00690476为7胜/10负/83平，一题移除可反号。S046 R20−.01是0/1/99，移除一题归零；MRR−.0355556为1/12/87，所有单题移除后仍负。不是新实验/盲确认/总体显著或跨cohort因果收益；没有p/CI，原研究strict freeze未改。[精确输入/分析](../execution/g5-local/saved-validation-stability-results.json)。原输出SHA9c4d2d8bc1297856b89317e4f279cca030f756e3e5e1635ab3d98bece06e7d38留ignored runs/s060-verification。分析reader核public dev+validation、只输出validation，private/final/非primary/Host/执行/写入哨兵；全case完整性hash在guard外读private字节，范围不混。

0新科研project/action/model/fit/rank/score，S059合成HTTP3/1/0工具另计，开发token/费用unknown，工程全dispatch未独立计。原S04636/S05017/S05447共100文件全同，科研预算/永久claim不改。

## 恢复与边界

源码repo /workspace/development-continuation-20261114/auto-research-agentarts，origin open-agent-power/auto-research-agentarts；旧/workspace/auto-research-agentarts、原云盘/参考8库不可见，原全局executorunknown，不重建历史。S054实际研究producer/sourcepin f23de20fb2cfe0cb3ff04117cefc8a8f394186f4，workspace /workspace/development-continuation-20261114/source-pins/f23de20/runs/s054-squad-train-conditional-v1，project-e5200655762d4ae6abca80cfddcf1e3d/run-7f74b125d1ad443e96bbf0f81f0165d9；原core300421…保持，3/3预算满，只原pin --resume已完成只读，无deadline重置，旧CODE_CHANGED执行门保持。S046原pin4a159a9e5a0142c3a69a091aaf1e9a9c110b7be0/3工具/negative保留。旧原50fit及S0353逻辑委派/2工具不重开。

S050仍pin29564822df9705021753a2ad79c156b96fd0d8b1/17文件、prepare b2a2d3fe880e8dffdeb142bdc4a5495e862994b445eb59d1c13301070b7b9e2f。新增一次模型请求仍pending，无approval/launch/Hostgrant，禁止execute，不套S035旧批准。S058前轮本地27816933B/123成员ZIP SHA1c1df555a0a6e3f96b0a73a9d2f8bd22efffe83b0b81b83479bea84412cfedd6已核；GitHub附件07:11上传401/同draft445432218/assets0，远端未交付，本轮无新证据未重试。普通Git/API可用不等于uploads权限。

AAW02e72e3e411bec53db2288651df01afb27d8904d/v0.3.1远端仍同、7安装文件再次同hash，dev-system归档。本轮复用root/engineering/capability_review三人，后两均已交回，无活跃分派，无新增成员/livehook/原生挂载或工具隔离声明。owner root-g5-continuation-20261115T0744提交推送后release，实际receipt runs/s060-closing/lease-release.json；下轮实查guard，永久study claim保留。

下一优先真实模型反馈选择/计划修订，须S050已有申请明确批准；继续独立零模型工作不改旧fullbudget、协议或最终集。附件需新凭据证据后官方上传+下载核SHA。下次计划2026-11-15 10:47:27+08，平台完成/投递unknown。受信local，不声称OS/sealed/RSI完整Gates。

本轮源码pin `/workspace/development-continuation-20261114/source-pins/4e17a63` 为clean detached 4e17a63af164cd8d0cb49a1e5a3feae458df459d，191源与原reader freeze相同；数据仍在原case路径，源pin不等于整套环境已可移植恢复。

本轮S063源码pin `/workspace/development-continuation-20261114/source-pins/a7f6284` 含191源码+1专项，与fixed freeze逐项同；继续S064评估v2结果能否版本化保存在原Memory并绑定下个计划，当前尚未通过。

S064源码pin `/workspace/development-continuation-20261114/source-pins/5e397b2` 与191源码+2test固定清单同，旧研究未迁移。此后S065真实CPU研究和S066经验导入已完成，见文首及对应Sprint。

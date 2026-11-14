# 云端开发上下文

## 目标及授权

用户要求解压执行包，使用 dev-system 严格按计划持续推进；随后明确授权使用 GitHub CLI，并向 `open-agent-power/auto-research-agentarts` 推送。独立分支开发，不强推或覆盖原分支。

执行源：[原始任务包](../execution/pack-v2/README.md)、[产品宪章](../execution/pack-v2/00-charter/PRODUCT_CHARTER.md)、[阶段门槛](../execution/pack-v2/06-roadmap/PHASE_DELIVERABLES_AND_GATES.md)。原上传包及 SHA256SUMS 已核验，[来源记录](../execution/pack-provenance.json) 保留包身份。

## 已确认边界

- 基线为 `5d497c8ae22100953f66c3c5b54746ca87e09f01`。源码克隆不含旧 runs、私人计划、原账本或数据附件。不能根据历史说明认领本次实跑。
- 产品是持续自主研究工作台，复用 Python/SQLite、现有 ResearchProject/ProjectController、TypeScript/X6。先审计，不直接重写。
- G0 未通过前不启动依赖阶段。只读研究、数据核验、评价设计和审计可以继续。
- 后续用户已在具体方案后批准有限可信本地先行；唯一例外范围见 `docs/execution/g1-local/authorization.json`，本地案例已完成且20fit用满。原G0与G2+仍未解锁，不能复制旧预算作为新额度。
- 用户偏好：每轮大任务完成后说明工作/验证/下一步，随后在已授权范围内继续；仅实质决策或外部条件阻塞时询问。GitHub已授权，可验证后直接合并/推送main，不设例行草稿PR审批。
- 当前宿主 agent 可执行调研与审查；产品 HostModelSelection 的 claude_cli/delegated 能力另行核验。检测到 Codex CLI 已登录不代表产品已接线，也不代表外部 API 预算。
- 没有配置模型 API 凭据；未创建密钥或采购服务。未知模型成本保持 unknown。
- 保留原请求身份、预算、工件与失败；不通过新 ID/新目录重置历史预算。RSI 不得修改独立评价器、隐藏数据、晋级控制器或安全限制。

## 接续

先读 [current](current.md)，再按任务板进入当前 Gate。运行资源问题以实际容器内部限制为准，不以 docker inspect 配置宣称生效。具体审计见 [G0](../execution/g0/)。

## 后续环境决定

用户已明确接受无法补Worker并要求继续推荐计划，当前范围以[local-continuation.json](../execution/local-continuation.json)为准。可开展有界可信本地的新课题/分析/CPU基准，单独预登记预算；原G0隔离事实保持，旧Concrete20fit不可重置。无需每个阶段重复询问同一环境限制，实际费用或新的不可逆外部动作另按授权处理。

Sprint003已得到G2无收益对照、G3两目标闭环及负控、G5两类CPU对照、G6离线打包证据；Sprint004完成G4-L有限helper候选及源码集成。最新G5原生两领域从`8e8a206`各执行2tools/0fit/API、3plans waiting，独立9910检查；后置UI`e638b5f`只改只读projection与标签，科研codeidentity保持。新G6 clean1.8产品安装/保存接续继续；以[current](current.md)和对应原始freeze为准。不把用户接受隔离限制解释为sealed通过或模型API/采购授权。

用户要求安排云端周期检查（3h或6h），root选择3h并已创建/启用、readback核同一继承cloud/workspace。平台调度与持续24h模型进程不同，首次执行待验；lease协调本轮与定时轮，不改研究预算。参考库8个固定checkout再次核验全clean/匹配manifest。

继承环境恢复的Sprint006已实际普通push成功并回读main=`477aae3`，上轮token失效不再是当前阻塞；原失败及冻结提交身份保持，不需重复索要登录/Worker授权。平台已有11:43UTC run-time marker，但run/result详情未返回，完成状态不推断。本轮聚焦archive-only保存接续、2991保存参数预测算术（先固定协议再算）、UCI原下载独立补充包；0fit/0model，不重写已验收77MB ZIP或历史课题。

Sprint006实测闭合：新target从归档8原ID恢复，01依赖平台探测失败保留，02仅真实uname1次后strict subprocess/network0；177/187/930物料绑定、1510实际独审过。固定参数算术2991行maxdiff1.42e-14，33282输出断言，负例689保留；补充UCI209918B小包37成员。494原件/50历史fit不变。下一轮做两CPU领域实验页摘要与损失展示，沿既定DESIGN/保存观察，0新研究，别重复已闭合算术或重发driver。


Sprint007已完成两CPU领域保存结果阅读，源码7633792，原state13/3plans/2tools与50历史fit保持，无新增研究/工程fit或产品模型调用。最终桌面+手机五页、38截图、80GET、12下载/读取及末列文字范围实测通过，独立36+63语义/807最终检查。01/02/03视觉缺口与调度启动失败保留，04才完整通过。新只读18836/18837由独立固定checkout服务原manager，旧源码pin clean。下一步已有artifact不利query按需精确阅读，见current及cpu-results-ui.json；平台14:45UTC标记仍无run/result详情。


Sprint008回应用户追问汇报：北京时间00:06检查，前轮23:15推送后等待下一次01:47，尚未超时。原任务轮间无常驻执行；平台run/result仍null、投递unknown。已工具更新并回读同任务/3小时间隔不变/时区AsiaShanghai，新增每次触发无论成功/失败/无进展/lease忙均final报告；持有lease时保存latest-report.md/json。并已真实审计133不利query、920保存rank/metric及18400定位；缺逐doc检索分数，GET/UI仍待实现。494原件保持，新fit/API0，金额tokenunknown。以current和最新报告接续，不把配置修正说成已证明未来触发/投递。


Sprint009从01:47实际接续，读取器0acb05e已实现并经真实HTTP/浏览器限定验收；原输入、预算、sourceidentity保持。之后继续独立23分发项安装，0ac原生CLI帮助/本地保存读取通过但可选runtime帮助缺SDK退出1；保留该负结果和piptarget2RECORD路径边界，窄修8a394e3帮助入口延迟SDK，原runtime.py不改。全部最终安装物/依赖/CLI/HTTP精确scope见reader-release及latest-report。API不补算原件没有的分数，0新fit/模型服务，开发成本unknown；原OS/sealed/多代RSI/完整Gate不扩大。下一任务先做独立检索任务许可/语义/预算与跨任务策略对照预注册，不重置旧案例。


Sprint010：2026-11-14 04:45:53在继承盘实际接续；ArguAna官方Webis/Zenodo CC BY 4.0与106MB原ZIP、BEIR全量文本/配对已审计，5缺正例/1298同ID自文本保留，NFCorpus学术限定未采用。新增独立relevance合同/registry/report/summary，旧citation/lexical与source pins不改；来源prepared并无真实targetranking/score。唯一样本选择arguana-transfer-v1 SHA 80/80/300，原1406query/全8674doc/1406qrels保留；唯一study g5-arguana-source-arm-transfer-v1/output runs/g5-retrieval-transfer-20261114-01。只有正式源码commit+exactfreeze独审批准后才一次2tools；候选等同fixedTFIDF control的结构零不称memorygain。以current和latest-report继续，未知状态不换ID/目录/预算。


Sprint010实际一次研究已完成：source250954e/core867075eb…，unique g5-arguana-source-arm-transfer-v1/output g5-retrieval-transfer-20261114-01/project0940a2e0cbd841e58677d2ecd99a33e2，state13/3plans/waiting/2tools/0reserves/0fit/model/source。testR20 .746667→.896667/nDCG .396192→.503379，仍43nDCG亏损/2R20亏损，all186混合坏例与2缺正例全0保留；candidate=fixedTFIDF无memorycausalgain。原7ID重放+7GET/6附件及572科研文件保持，五页/16截图通过；方法名两label在独立UI树修复，不改变250科研pin。下一增量newrelevance保存坏例queryreader，不能套旧citation语义或重跑预算。详见current/results及latest-report，不从本段缩略SHA启动命令。


同轮继续修复实际UI fallback：仅2个methodName映射/bundle，commit944b5aef970765f7993bbff758b5dc70728ac50f已ff合main；clean工作树/workspace/work/arguana-ui-labels-20261114及只读18841指同manager，4受影响页实测/限定独审通过，174Py/core8670/13manager文件保持。旧250科研pin与18840不动，不能把UI后置提交冒作原研究源码。


Sprint011：2026-11-14 07:51:48实际继承，base11e71a2 clean/lease独有。140d6ec44e293cb6e3c92f3be9f3c3bee4dccf0c完成新relevance保存queryreader及legacy保持，572files/421旧paths+newcase/input、九sourcepins保持；科学8670/旧3945不升级，0新fit/model/rank/goldscore/action/project。52HTTP验证+2startup、237browserGET+20API、43real/2fixture图及限定独审通过，错误/弱帧/补证分开。

同轮继续新wheel标准安装，初140base成品与失配保留；2de2b854bf90404ce6288f8d3fed93e16ccf8581只修reports两声明到已验证22closure，新wheel1237371B/f36cdf8f41ebe2d3f188e3573d9060ecb79aba47821179b3f12b8a867ced3d58及另一fresh标准venv明确[reports,sources]解析/4page4detail保存读取/独审通过。产品180字节同140，23dists/7145RECORD=6711declared+23self+411pipcache实际SHAonly；999moduleentries=99product+900nonproduct，初标签错误保留澄清；bootstrap未知不填0。SDK不装、0付费模型/API、不扩大Gate。下一项按方法收敛固定CPU课题的CSV/Ridge无关绑定提示，原ledger/budget/sourcepin保持；详见current/latest-report及saved-relevance-reader-verification。


Sprint012已完成固定CPU研究页及不依赖报告的紧凑协议GET，源码0775eab、clean pin `/workspace/work/fixed-cpu-protocol-source-0775eab`。214真实GET/0POST、52实际截图、当前181文件wheel离线[reports,sources]新安装已验；最终35组独审通过，按[current](current.md)与原件接续。572原件/421路径/四manager预算及14其他源码pin保持，0新研究/fit/排名/评分/求解/模型API；原producer不升级。新接口只投影已捕获声明，不证明完成研究、许可或科学批准。下步单独CPU经验合同，保留原Ridge-only OOF门，不凭同臂TF-IDF对照宣称记忆收益。环境短暂starting后同盘恢复，不伪造旧执行树；下次配置计划13:47:27北京时间，平台完成/投递unknown。


Sprint013持续推进完成三个原生增量：3ca7 CPU经验完整快照与项目案例资格、cee2概览文案、79b6 CPU知识需求领域路由。真实三原案同知识库恢复/完整包/预算保持，工程目标HTTP/报告/浏览器与三版成品源字节验证通过；当前e731 runtime不升级旧producer，旧Ridge-only校验保持。首次失败browser请求unknown、只记录成功阶段193GET/0POST，API17POST均新工程target。详细范围和原件见[current](current.md)及Sprint013。继续新研究前的来源/预协议准备，第三检索来源尚不合格，小n调度阈值仍假设，先冻预算和独审，不凭代码或查询词宣称新科研/检索收益。


Sprint014在同一13:28 owner下接续，14:49记录正式协议定义，真实研究尚未执行。独立三臂harness的单次预算/全局claim/双阶段审批/unknown保护/同boot持久deadline工程准备中；fake测试不计新科研收益。详见SPRINT-014和current；原50fit、原state/budget/source/负例保持，公共worker仅协调遵守同锁的进程，实际重型窗口由root协调。


Sprint014实际完成（15:41:58，北京时间）：code62f09ed，unique g5-scheduling-threshold-transfer-v1，inputs41ac3517/result9d45e971。小n主终点1.26118/12均慢，拒绝策略不调参、不补测；29gen/1140kernel/29Fenwick/2brute/4352subsets/6080234scan/1primary/1audit，活动12.903s。574/421保持，0fit/model/API/source，old50保持。4完成入口0callback/10文件不变，具体guard/bootstrap范围见结果JSON。standalone3arm不冒称native3arm接线；继续CPU知识实际检索链工程检查。


Sprint015：source404ef977/newcore4b93246c，37SQLite checks+独审+同七文档新旧两入口真实引用对比通过，query字母数字alias局部补漏。原空格OR/TopK/单字词丢失负例不抹去，真实memory8cc9445c保持，无新研究/项目/fit/API。原study62/e731的输入和预算不变；静态胶囊与新成品安装继续，不称旧wheel已带新alias。


Sprint016静态证据胶囊完成：ZIP4671421B/976，SHA3c12efc9…；879源62+10docs93字节绑定、全成员CRC/manifest/安全路径独审过。574/421组装前后保持（独审未再全核，只依自检+8关键抽查），新研究调用0。非可迁移/可执行账本恢复，旧runtime/boot边界及缺依赖原数据明确；继续source404产品安装S017。


Sprint017成品完成：404source、wheel1264600B/SHA c2bba632…、185/179产品四处相同；离线exact22/23项、RECORD195、98origins/42导入后guards0，独审scope和bootstrap/thirdpartyRECORD限制明确。继续S018固定study只读引用，先解决最终audit不在result、经验包超4MiB、原nativeaction不可伪造的真实边界；不混新旧nativeidentity，不新增科研或扩预算。


Sprint018：a1152b4 reader最终pin系统PythonCLI真实一次，12137含换行/27case/16refs/17原件锁字节不变，preimport网络进程与执行写入/formal-verifier guard0，10fake+独审过。读取原final2402链，不重跑审计、不伪造project/action。继续S019只读Controller/Workbench GET，当前未完成，无新研究/预算。


Sprint019完成：e88c3f5 fixed GET→真实Controller/Workbench/reader，22fake+8HTTP+独审；原17/13manager、state13/两completed actions/预算、574/421同。验收__new__绕过原会写constructor、bootstrap仅放行1 uname-p/首失败留存、mockunknown单列，准确限定scope。当前404成品不含reader/API；下一任务先明确无写启动再做独立只读study UI/预算分栏/桌面手机，拒绝新研究/项目/预算，原source62/e731/1audit/50oldfit保持。


Sprint020–022同盘16:44接续，正式factory无写/f85、stored预算投影84、安装CLI与手机分行b1相继完成，旧case17/13manager/574/421保持。真CLI+UI/键盘/异常fixture与独审分scope记录；project3945/外部study62e731/当前core4b区分，无新研究/fit/paidAPI。b1安装wheel91af…188/182，后续S023/S024不在该包；继续原ZIP下载和原协议假设来源可读，不混入项目预算。


S023–025已完成：e0固定原ZIP显式下载byte匹配，792原协议来源/policy逐值相同旧DTO不变，最终wheel3770/189产品/183Py五路/23dist离线装及独立真CLI4GET过。安装无浏览器重跑，源UI证据分开；原case/预算/pins/50fit与primary1/audit1不变，开发成本unknown。继续调查原保存plans/report，不执行/重算/写旧数据，不自动把source关系当科学因果或projectaction。


Sprint026–027：source3b01只读三版计划/完整context/两action/等待null与manager preparing分别展示；保存report身份/currentnessunknown/manifest声明范围闭合。原案110GET/主轮128checks/32图和新wheel3b127/190product/184Py/exact22离线/安装CLI16GET/4图独审通过，见current及精确证据。旧source792/3770包保留；科学50fit/primary1/audit1/预算不改。原4人池继续S028 manager返回core响应后外层收据落盘，必须同ID经core、不重选/不把unknown完成，不主动改旧案。


Sprint028–029：sourcec5bb通过外层manager同ID原status/response落盘，不跳过core或自动遍历历史案；独立合成69checks真实wait/写中断/一次mock后unknown、reserved1保留，原core版本4→5明确。最终a906 wheel/190产品184Py/exact22离线/安装Python53checks98origins独审通过，非CLI/UI。初broader12误发现5既有quality/grouped工程计算，fit/solver未单独计量；原科学50fits/唯一primary/audit和预算保持。继续S030只读canonical语义请求与双purpose SHA，不当原wirebytes或执行许可。


Sprint030–031 source de20/wheel33287，原3请求canonical语义body与core/manager双purpose摘要和生产身份真实核对、51GET/22图及安装17GET/19checks/4图独审通过，不是原wirebytes或执行许可。用户明确需通俗解释目标差距，root承认近期偏页面/追溯/恢复；下一S032转原nativeproposal已绑定经验引用与决策保存/报告核验，旧模型/recipe协议和预算不变，不认领自动记忆或科研收益。差距审计指出CPU候选不因FTS/case新增，P02有FTS改变顺序例外；原50科研fit/预算/producer保持。


Sprint032 source2cdff0a：直接proposal可选最多4 activecase三元组引用，decision/view/report保留原association；scope_mismatch可作反例不改资格。真实原citation/relevance两包+新合成target47工程checks及独审，工具上限1/证据8/fit0/model0但实际0tool/action；2imports/1目标退休，saved-only与17写75读另计。旧Host/model/recipewire不变，旧33287成品不含本接口。继续S033能力marker条件化消息协议，不调用模型或绕旧pending CODE_CHANGED/_fresh，老pin/预算保持。


Sprint033 source78acf，project身份0574266b/controller5c5c86ef/nativejournal6099ede3，新context能力marker可选经验ref，旧4真实contexts八wire独立byte同；合成Host/native日志与省略字段及跨pin门禁已验，0真实model/CLI/API。原4b及producer/pins不迁移，nativefixturecap1/used1 != 实际调用，delegatedcostunknown。Linuxreadiness证Claude/Ollama Windows-only、Codex缺nativeadapter且help未证明全tool禁用/hardUSD；3metadataCLI隐式networkunknown。下一先完成三逻辑委派/2tools的待授权toy工程闭环方案/dispatchguard，再请求新研究模型范围，不把已有开发授权当model预算。


Sprint034：旧AA guard96checks证prefix回滚可重预留；1d19f06独立witness修复单日志回退，54定点/3fork通过，仍非OS/hardcost/实际dispatch证明。用户已在本会话明确批准一次固定3逻辑研究委派/2工具的工程反馈试跑，原0预算不重开；当前未create/auth/claim/execute。产品源78acf/core057，guard1d19，新轮领取新owner后按固定claim/输入/ID推进。19:49新timer只读见旧owner仍活跃，无并发executor；下一计划22:47:27，平台run/result/notification unknown。


Sprint035：用户批准的固定pilot已实际3逻辑委派/2工具；原project943409c583e54a5d88d414bddb997669/run78ce0add28fa454bb0ad72dd9b979bd1，workspace/work/model-feedback-pilot-20261114-v1，产品78acf/guard1d19。primary实际1index/6rank/6metrics，saved audit0新rank/score；两臂3query打平、validation0、qv正例b两空排名。review needs_revision/leave_proposed，原提案不改/不采纳/state11/baseline v1，3/2额度均尽，guard5响应完成仅留存含义。两个root编排故障均同ID只读恢复；最终2终态重放/15项目文件相同。完整精确ID/SHA/费用unknown见S035/results。继续S036产品保存材料显式检索adverse-query投影，不再派研究模型/工具；实现/工程验证/代码独审复用原3成员，开发和研究调用分开。

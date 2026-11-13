# 当前接续

## 执行边界与入口

用户要求持续推进、每大轮报告、验证后直接合并/推送 `open-agent-power/auto-research-agentarts` 的 main；仅新的实质决策阻塞再询问。用户已接受缺失 Docker/cgroup Worker，按 [可信本地授权](../execution/local-continuation.json) 继续，无需重复索要相同环境。原 G0 隔离与上游 runtime 未通过，不宣称 sealed、多代 RSI 或完整原 Gate。

每轮先核同一云盘与仓库，使用 [自动推进规程](../execution/AUTONOMY.md) 和 `scripts/project_autonomy_guard.py` 协调租约；不得覆盖其他轮次的未提交改动。研究 unknown 只按原 ID 恢复，不新发或重置预算。不得采购、增加付费模型/API或向他人发消息。开发 token/金额未知，不能写0。

## 已完成的真实证据

| 轮次 | 结果及边界 | 入口 |
|---|---|---|
| G1-L | Concrete1030行/427组，MAE8.383388→5.702073MPa；313行/129组恶化，负预测1。20estimator/5tools/1来源/0产品模型；state32 waiting | [Sprint002](../execution/SPRINT-002.md)、[结果](../execution/g1-local/results.md)、[复现归档](../execution/g1-local/delivery-manifest.json) |
| G2-L | 16工程测试+独立115检查；同4任务三组织对照无并发收益，保留single，无LLM研究收益主张 | [Sprint003](../execution/SPRINT-003.md)、[结果](../execution/g2-local/results.md) |
| G3-L | RealEstate414行MAE6.425093→6.287279，179行/107组恶化；Slump103行无age，拒绝迁移变换，基线MAE2.257092MPa。两新目标累计30estimator/8tools/2来源/0产品模型 | [结果/恢复](../execution/g3-local/results.md)、[完整交付](../execution/delivery-sprint-003.json) |
| G4-L | 单真实分组helper候选完成VM/原生/生产三段独审并集成；Concrete原生微函数2.195511→0.084443ms，非CV或科学收益。1164项工程回归通过1145/跳过19 | [Sprint004](../execution/SPRINT-004.md)、[原生结果](../execution/g4-local/native-results.md)、[集成审查](../execution/g4-local/integration-review.md) |
| G5-L standalone | SciFact引用检索BM25早排改善伴随Recall5/20下降；合成调度已知精确DP复杂度优化。独立60检查，不自动晋级默认 | [结果](../execution/g5-local/results.md)、[原来源](../execution/g5-local/source-provenance.md) |
| G6-L | 干净环境wheel/HTTP/PDF smoke通过，但sklearn1.9.1相对1.8改变Concrete808/RE252行分折。另建历史1.8环境1547行group/fold全复现，0fit；不等于模型预测复现或完整G6 | [实际边界](../execution/g6-local/runtime-reproduction-boundary.md) |

## 本轮 G5 原生接线

两个显式CPU primary及各自 saved-only audit 已接入同一 ResearchProject/ProjectController/LocalWorkbench/四文件报告，无另建领域控制器或通用exec入口。9项生命周期测试覆盖两个领域、累计预算、unknown、完整工件恢复、精确ID不重算、跨项目前驱拒绝与runtime身份。数值依赖实际loaded版本须与installed metadata一致；新兼容升级拒绝不同或未知旧runtime，历史精确receipt仍可读取。

完整回归1225项：1206通过、19跳过、0失败/错误；真实工程夹具确有拟合，次数未单独计量。183非bytecode源码与tests保持；4个派生pyc变化使原严格全src树回执仍false，另存明确有限验收。292旧研究文件、G4两case和5冻结controls、旧G5输出与累计50研究estimator不变。见[回归](../execution/g5-local/integration-regression.md)、[整层独审](../execution/g5-local/native-core-review.md)。

两个真实新case已实际完成：检索5183文档/1109原queries中80dev+80validation+300test；调度16合成case/20544jobs/80solver runs。两案各2tools、0fit/model/API/source-extraction、3plans、state13 waiting。已知公开结果的原生接线复跑，不是新隐藏评价或重置旧搜索额度。[原生结果](../execution/g5-local/native-results.md)与[独立9910项验算](../execution/g5-local/native-results-independent.md)保留所有亏损；920排名/指标与旧对照相同，16独立Fenwick最优值通过。调度dev-n32-seed102实际慢0.840×；BM25 test Recall5/20下降，不自动采用。

科研源码冻结`8e8a206`、完整清洁checkout在`work/native-cpu-source-8e8a206`；原始freeze/369文件/真实输入与报告在 `runs/g5-native-cases-20261113-01/{retrieval,scheduling}`，不得回写或再次run。只按原ID读取，源packet在 `/workspace/work/g5-native-{retrieval,scheduling}-packet.json`。按[执行协议](../execution/g5-local/native-run-protocol.md)完成预登记/独审后各执行一次；源码保护清单读取14合法空文件的失败与窄修保持。

后置展示增量`e638b5f`只加取证任务可用flag、正常无任务空态、4CPU方法中文名及构建bundle。17相关tests/typecheck/build通过，实际科研codeidentity仍`3945ed0f5ec85b0ce42af0bb9ac0d0c27034bf932dac27fee9f7008ec2d3707e`；不把新UI文件SHA混进原8e冻结，也不重跑研究。旧预览409/最终UI05证据分别保留，见[界面](../execution/g5-local/native-ui-verification.md)。新只读服务18832/18833从`work/native-cpu-ui-e638b5f`固定checkout启动，写与模型关闭。独立pin原/新目录恢复408检查/72次原ID重放通过（早期另72次也保留），[限定总审](../execution/g5-local/native-final-review.md)raw1146/汇总78检查通过。

G6新增量已完成：[当前产品干净安装](../execution/g6-local/native-release.md)在新独立`/workspace/work/g6-native-release-20261113-01/venv`用原18精确观察pins、无systemsite，完整23closure另记。从`e638b5f`对象快照构建wheel，177包文件源/轮子/安装SHA同，两manager副本各4原ID重放、8下载及7/8页PDF parse通过；0新fit/排名/求解/外联API/报告生成。依赖下载有网络，runtime有18loopback连接。旧1.9失败环境与旧1.8环境保持；保存重放不等于主研究模型refit复现或完整G6。

两段[真实只读演示](../execution/g6-local/native-demo.md)已完成（31.28/30.68秒，1440×900），实际指标帧已看，125案例文件与5类API前后字节不变。视频与34文件精确allowlist保存在 `runs/g5-native-demo-20261113-01`，不重复录制假运行。

上述归档重开与保存系数算术已在Sprint006闭合，不重复旧driver或新建同课题。[Sprint007](../execution/SPRINT-007.md)现已完成两CPU领域可读摘要：宏指标、Recall5/20下降、133混合集合含义、唯一慢例及全部16任务直接阅读，原JSON及下载保持。最终源码`7633792`，独立固定checkout `/workspace/work/native-cpu-ui-7633792`，只读预览18836/18837仍用原manager、无写/模型开关。中间2f展示进程已停止，旧0ceb/8e8/e638源码pin均clean。

最终两案五页在1440×900和390×844实测，38截图、80浏览器GET／0POST／错误、4原行动下载＋8报告HTTP读取；API、494保护文件及三根完整421路径集保持。36原件＋63编译语义检查和807项最终独审通过。01/02/03手机布局缺口及02服务启动失败保留，只有04最终完整看图和末列文字边界通过。[UI验收](../execution/g5-local/cpu-results-ui.md)与[精确身份/预算](../execution/g5-local/cpu-results-ui.json)可接续。历史50estimator不变，本轮无新研究/工程fit或产品模型/API；开发成本unknown，非科研收益或原完整Gate通过。

下一可独立增量：已有artifact不利query的按需阅读与精确定位。先核原query/doc/action引用及加载边界，再复用reader用GET展示；投影只有133总数，不硬编码60/73，不重排/重算/新建项目/换ID/扩额。平台14:45UTC触发标记存在但run/result仍null、投递unknown，不据标记推断完成。

## 最新交付与凭据恢复

[Sprint005](../execution/SPRINT-005.md)已闭合；[复现包索引](../execution/delivery-sprint-005.json)对应77,407,847字节ZIP、930成员、源bundle tip `e97c0a6`、独立2864检查/494文件保护，均通过。归档已完成，不需重复生成或重跑研究。

上轮普通push因GH_TOKEN invalid失败，记录保持。此次继承云环境恢复后，新CLI会话实测有效，已普通fast-forward推送并远端回读确认main为`477aae3f89e130f06d497d12d83d8d459def6955`；所有8e8/e638/e97冻结提交原身份发布，无需用户重新登录。后续凭据可能过期时先用新进程实际检查，不把历史失败当永久阻塞、不重置本地领先提交，也不以新Git元数据替换原冻结SHA。

[Sprint006](../execution/SPRINT-006.md)已完成实际验证：从77MB归档复制原已有DB，在`/workspace/work/g6-archive-reopen-20261113-02`新target重开8/8原ID；177产品文件/187完整target/930payload/97产品module origins均绑定。外部依赖透明复用clean1.8，未从ZIP离线安装全依赖。[归档结果](../execution/g6-local/archive-reopen-results.json)与1510项[独审](../execution/g6-local/archive-reopen-independent-review.md)保持0新研究/fit/model/source/报告；一次真实uname依赖bootstrap与后续严格子进程0分开。01在归档产品导入h5py时被守卫挡下，0manager/0ID，原unknown host-attempt及六控制原件保持，不能整体重跑01或02。

保存参数核验按事前源码`9f60585`/固定容差运行完整5CV/25fold/2991输出，最大预测差1.4210854715202004e-14；独立33282项字段/指标核对通过。Concrete负预测689保留，50历史estimator不变，新fit/API0。见[结果](../execution/g6-local/saved-model-arithmetic-results.md)、[机器摘要](../execution/g6-local/saved-model-arithmetic-results.json)、[独审](../execution/g6-local/saved-model-arithmetic-review.md)。只验证保存参数表达，不是重新训练或新科研收益。

原77MB包没有含全部UCI原下载，已单独补齐209918字节/37成员/34payload的[原件补充包](../execution/g6-local/originals-supplement.json)，三原下载/CSV/许可/转换SHA链均核对，旧ZIP身份不变。11项新时间复核有正式receipt。494原件与完整路径集保持，历史源码pin/协议不改。

[Sprint006增量交接包](../execution/delivery-sprint-006.json)已核验：`runs/sprint-006-delivery/sprint006-handover-followup.zip` 7,863,599字节，SHA`f51a25b0ea22a7eeae28e53ea0d7147a50e675ce3a1bd141b9132d84ddbf3efb`，177成员，独立1214文件检查＋6 bundle检查通过，source tip903458e。含新结果/失败/审查与UCI补包，仍需旧77MB研究数据包和外部依赖，不能整体rerun旧driver。

## 历史项目与服务

旧Concrete `runs/cloud-concrete-local-20261113-01/manager`，RealEstate/Slump `runs/g3-local-transfer-20261113-01/{real-estate,slump}/manager`；state分别32/33/24，研究estimator分别20/20/10。原源码冻结 `0ceb274`，旧只读服务18830由 `work/study-source-0ceb274` 启动，actions/models关闭。新main对旧case为CODE_CHANGED，不能upgrade、迁移producer、重拟合或重建其预算。原/新路径独立恢复与原件哈希见对应Sprint报告。

## 平台定时与参考库

已设置单个每3小时平台任务，enabled且继承同一cloud环境(`/workspace`)。以下为Sprint006历史回读：当时出现`2026-11-13T11:43:24.792602+00:00`触发时间标记，下个计划时点为14:47:27UTC；last_run/result详情仍null，不能据此标平台完成/投递成功。Sprint006已实际恢复云盘、领取lease并完成原提交推送，独立记录工作证据。手机无需常开来触发；状态配置位于ignored `.agent/autonomy/automation.json`，不公开私密ID。

云端 `/workspace/references/upstream/` 的 autoresearch、AI-Scientist、AgentLaboratory、prime、OpenHands、software-agent-sdk、beir、ragas 共8个真实Git checkout已再核HEAD=manifest且clean。机制与许可研究见[G0复用矩阵](../execution/g0/upstream/reuse-matrix.md)，当前选择性自研适配；完整上游runtime未全部接入。BEIR数据/固定指标实际使用；Prime地址为服务CLI，AIDE²未定位源码，不能声称复现。

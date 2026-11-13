# G5-L 原生检索与调度结果

两个领域已通过同一个 ResearchProject、ProjectController、LocalWorkbench 和四文件报告服务实际完成。各有三版原生计划、一次固定双方法对照、一次保存结果审计，再进入 waiting。不是调用旧独立脚本生成假行动，也没有为数据集另建控制器。原 G0 隔离／上游 runtime 和完整阶段门仍未通过。

## 固定来源与实际行动

研究源码为 `8e8a206ed0b71479a6e774e36ed91fdb06e21c22`，在 `7f33dcc` 实现基础上只修正保护清单对合法空文件的读取。实际环境 Python3.12.14、NumPy2.5.4、SciPy1.17.0、sklearn1.8.0。旧公开对照结果已知；本次验证原生接线的忠实性、证据与恢复，不是新的隐藏测试、模型研究收益或科学发现。

| 新项目 | 检索 | 合成调度 |
|---|---|---|
| project ID | `project-b0ad79226f0a454b99b604e373e39bbb` | `project-148dac5d531144008498449cb16a54ea` |
| 完整输入 | 5183文档、1109原queries；固定80dev/80validation/300test | 16任务、20544区间；4dev/validation＋12test |
| 主行动实际计算 | 1次索引、920次排名、920次引用标签评分 | 80次DP、95599712次扫描前驱比较、0穷举 |
| 最终状态 | state13、plan3、waiting | state13、plan3、waiting |
| 累计新额度与用量 | 2/2tools；0fit/model/API/来源提取；无预留 | 2/2tools；0fit/model/API/来源提取；无预留 |
| 整个driver实测wall | 17.417秒 | 11.234秒 |

整driver时间包括代码／Git核对、计算、保存审计和报告，不是纯检索或DP核的延迟。主机记录的子进程CPU user/system分别14.617/2.153秒和9.303/1.298秒；peak RSS分别270028/184724KiB。每次独立child有180秒wall、120/130秒CPU、1GiB地址空间、32MiB单文件、线程1与至少5GiB磁盘余量。它们不提供cgroup隔离或总磁盘配额。

两个具体freeze经独立26项身份／覆盖／预算／保护核对后各执行一次。Ridge、Scaler、network、source-extraction guards的实际触发数全部0。来源完整性读取原qrels/metadata允许且发生；不是另一个来源提取行动。排名完整形成内存指纹后才评分，随最终工件一起保存，不冒充先落盘checkpoint或隐藏gold。所有原始输入、原件许可、失败预检、命令／接收目录映射和预算在 `runs/g5-native-cases-20261113-01/{retrieval,scheduling}`。

## 引用文档检索

SciFact/BEIR-test是原SciFact dev；qrels表示cited_doc_ids，不是事实真伪或SUPPORT/CONTRADICT。原metadata中的句级注释原样保存但不用于排名或评分。claims/qrels的CC BY4.0与abstracts的ODC-By来源范围见[原件来源](source-provenance.md)，报告保留每份原件及声明，不能仅靠spec自证许可。

| test宏指标，300queries | TF-IDF | BM25 | BM25−TF-IDF | 胜／平／负 |
|---|---:|---:|---:|---:|
| Recall@5 | .741556 | .724278 | **−.017278** | 8/276/16 |
| Recall@10 | .778500 | .787611 | +.009111 | 12/280/8 |
| Recall@20 | .840278 | .829222 | **−.011056** | 5/286/9 |
| MRR@10 | .594004 | .626970 | +.032966 | 56/208/36 |
| nDCG@10 | .632911 | .660464 | +.027553 | 58/202/40 |

920个arm/query排名及指标与原独立对照逐项一致；各split的完整宏指标、胜平负、输入SHA／行定位与所有排名均在JSON。133条adverse记录包括60条存在某指标损失、73条没有候选指标损失但至少一臂Recall@20不足1；后者65条两臂召回均不足，8条仅基线不足而候选完整召回。不能写成133条全都恶化或73条均为共有漏检。plan2引用实际primary/action/result/feedback SHA后选择保存错误审计，保留覆盖损失，不调整参数或自动采用BM25。

## 合成加权区间调度

比较同一个已知精确DP的扫描前驱与二分前驱实现，固定排序、相邻端点和skip-on-tie规则。80个保存run的完整schedule、目标和可行性一致，16个最优值另经独立坐标压缩Fenwick递推核对。它是合成工程优化，不是新算法、科学样本、RSI或对最先进调度库的比较。

| test任务规模，每规模3seed，各3repeat | case中位倍率的中位数 |
|---|---:|
| 128 | 4.722× |
| 512 | 15.704× |
| 2048 | 64.863× |
| 4096 | 118.176× |

所有12个test任务的候选计时较快；dev-n32-seed102实际较慢，倍率0.839691×、增加约5.669微秒，目标1329和schedule相同，未删除。小任务单次计时噪声及这些固定seed限制外推。full_scan_comparisons=0只表示二分法不全扫描，bisect内部比较数仍未知。保存审计只检查已有jobs／schedule／操作数／计时摘要，不再DP、生成任务或重新计时；没有宣称运行原28个小正确性fixture。

## 核验与恢复

结果前已提交固定的 `scripts/verify_native_cpu_cases.py` 首轮通过9910项检查，源码SHA保持 `ba82a2afe5e765ccf02ac12765cbfb6f2213a0b815f6d0f4f12e539176cf2f0d`。它从原始保存排名和citation标签独立算指标，不重新排名；调度用另一Fenwick实现验证最优、可行性与完整操作记录，不调用生产DP或重计时。见[独立结果与完整JSON](native-results-independent.md)。原369个保护文件含292个历史研究文件、完整旧case根、G4两case与controls和原输入；路径集合及所有字节保持，旧真实研究仍累计50次estimator。

driver已在真实执行中禁止计算重放primary/audit/wait三个原ID，均不新增工具用量。另一成员以完整清洁8e8源码，在原位置／新目录两领域共完成408项检查、72次原ID重放，97个模块均来自pin；此前另有72次成功原ID读取，实际合计144次，均无新计算或预算变化。正文／请求ID不改，接收目录仅按已有DB定位；禁止回退旧case／原packet读取，不能重新create移走的旧目录。见[恢复审查](native-replay-review.md)。

后置展示修复`e638b5f`只增加只读取证任务可用flag、无任务正常空态和四个CPU方法中文名，不改科研code identity。最终只读浏览每项目5桌面＋2手机视图、28GET／0写请求、0页面及HTTP错误，且不存在任务的endpoint实际请求数0；8附件HTTP200/SHA与全部case文件保持。原预览409、工具选择器错误与PDF首末页代表性／字体局限保留，见[UI验收](native-ui-verification.md)。报告包含每项目 `input.json/report.json/report.md/report.pdf`，JSON保留完整数组，PDF／Markdown明确前12坏例只是显示样本。

[限定总审](native-final-review.md)分别核对8e8完整科研freeze与后置e638展示源，1146项raw检查和78项汇总交叉核对通过。首轮总审误以新展示文件对照旧freeze失败也原样保留，改用明确清洁科研源码重新核对，未放宽原清单或重跑科学。机器入口为[native-acceptance.json](native-acceptance.json)。

完整工程回归1225项通过1206、跳过19；4个派生pyc变化和原严格false回执保持，见[工程回归](integration-regression.md)。工程fixture确实拟合、数量未单独计量；上述两个实际研究项目为0fit，开发token／基础设施／金额未知。原始source prepare因14个合法空日志／锁文件失败、可选time命令缺失的发起前失败均另存，均在研究创建／派发前，没有以新研究ID掩盖重试。

本次限定验收不包括生成式RAG、LLM judge、模型自动科研、多Agent收益、真实用户评价、完整G6或封存隔离。

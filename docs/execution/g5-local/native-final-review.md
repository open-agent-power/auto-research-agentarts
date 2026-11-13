# G5-L 原生 CPU 连续课题限定总审

结论：**本轮可信本地 native integration 可交付。两项真实固定课题、保存审计、原 ID／迁移恢复、报告与只读界面证据闭合。原完整 G5／隔离 Gate 不因此通过。**

最终总审原件 `runs/g5-native-final-review/summary.json` SHA：
`3122244782514ffa6a2889b2ba28c2d17ba2dbf93f2df75550bee23175b26ec3`。
本审不编写实现、不重跑真实排名／求解或全套回归；最终 78 项汇总核对引用独立原件，
另有 1,146 项 raw／文件身份／顺序核对、9,910 项数值核验、固定源码重放及只读浏览证据。
这些是不同层的校验项，不是额外科研样本或独立科学实验次数。

## 实际范围、预算和反馈顺序

科学代码／协议／输入固定在提交 `8e8a206ed0b71479a6e774e36ed91fdb06e21c22`，
driver `05b1c5fb…b978c`；独审批准的两个 freeze 各只运行一次。
检索完整原件为 5,183 文档／1,109 保留 query，固定 80／80／300 split，共 460 query pair；
调度为原 4 dev／validation 加 12 test，共 16 合成 workload／20,544 jobs。
两项目都在既有 ResearchProject／LocalWorkbench／ProjectController 中运行，没有新增控制器、模型或外部 harness。

| 项目 | 真实 native actions | 完成状态 | 累计额度 |
|---|---|---|---|
| `project-b0ad79226f0a454b99b604e373e39bbb` | 固定引用检索 pair → 保存错误诊断 | state13／3 plans／waiting | 2 tools，0 reserved／fit／model API／来源提取 |
| `project-148dac5d531144008498449cb16a54ea` | 固定区间调度 pair → 保存结果审计 | state13／3 plans／waiting | 2 tools，0 reserved／fit／model API／来源提取 |

真实 primary 完成后，完整 action／result、observations、paired-summary 指纹及 adverse 数先写入反馈；
plan2 基于 state6，精确引用该 action／result／反馈 SHA。随后 state7 的 audit context 实际带有 plan2，
saved audit 精确绑定该前驱；plan3 基于 state11 引用实际 audit，最终进入 wait。
这是预声明固定 pair→保存分析的连续 native 流程，未证实开放式模型规划或自主科研质量收益。
来源机械校验／计算读取本地原件；“来源提取 0”专指没有 C04 内容提取 action，不是没有读取 corpus／qrels 字节。

wrapper 实际用时约检索 17.417 s、调度 11.234 s，含 schema、Git、生命周期、报告等开销，
不能与内核计时混作平台加速。child 分别使用 180 s wall、CPU120／130 s、AS1 GiB、单文件32 MiB、threads1，
fit／source-extraction／network guards 实际触发数均0。它们不是 cgroup／OS containment。

## 保留的真实负结果和科学边界

冻结独立验证器 `ba82a2af…cf2f0d` 首轮 9,910 项通过：从保存排名与原 citation qrels 独立计算指标，
920 排名／920 逐 query 指标与旧 standalone 定义一致；不重排索引。调度独立 Fenwick optimum 校验
全部 16 workload、80 保存运行、可行性／操作数及原输入身份；不调用生产 DP 内核或重新计时。
原件 `runs/g5-native-independent-20261113-01/verification.json` SHA：
`b6a252e12a4d11e0cd50b596bfd1d1b637054b8f83047d49e84358f0ba761d9c`。

检索 test 的 BM25 nDCG@10 从 TF-IDF 的 0.632911 到 0.660464、MRR@10 从 0.594004 到 0.626970；
与此同时 Recall@5 下降 0.017278、Recall@20 下降 0.011056，均保留，不自动采用候选。
所有 split 的 133 adverse 是“任一指标损失或召回不全”的集合：60 query 有指标损失，
73 没有指标损失但至少一臂 R@20 覆盖不全（65 条两臂均不足，8 条仅 baseline 不足而 candidate 完整），
不能说 133 条全是候选恶化，也不能把这 73 条全称为共有漏检。

调度唯一保存慢例 `dev-n32-seed102`：扫描约 0.029694 ms、二分约 0.035363 ms，
候选多 0.005669 ms、baseline/candidate 比 0.839691；目标 1329 和完整 schedule 相同。
全部慢／平／快例、操作数和每次运行仍在 JSON，没有只留大规模速度比。

SciFact qrels 是 cited-documents，不是 SUPPORT／CONTRADICT 或答案正确性标签；
metadata 可能含句级注释，原样保留但不进入排名／评分。loader 已见公开标签，排名函数只接文本；
先完整排名后内存指纹再评分是程序顺序，不是隐藏 gold 或先落盘 checkpoint。
公开 standalone 结果已知，本轮是已知结果的 native 生命周期复现。调度是已知精确 DP 的合成工程对照，
不是新算法、独立科学发现、完整 RAG 答案系统或多代 RSI。

## 精确恢复与迁移

最终恢复使用干净 `work/native-cpu-source-8e8a206/`：175 个 frozen 文件与 HEAD 完整匹配，
97 个实际导入 module origin 全在该 pin 内。两领域分别在原 manager 与迁移后的 manager 验证，
共 4×102 项／72 次原 ID 调用通过。此前 main 上另做的72次也保留，独立恢复总调用 **144**，
没有把额外核验次数隐去或计作新增 native tool dispatch。

迁移复制的是各自完整 **13 文件 manager**；原 outer case 的 63／62 文件前后字节／mode 不变。
无 request ID 的 create 明确跳过并禁止调用，不重建移走的 unmanaged root；source-cap 路由既存 imported DB，
import 使用原 body／ID 返回旧结果。仅 receiver 存储根在内存迁移，不改请求、绝对 workspace 回执、report 时间戳或科学参数。
relocation 阶段禁止原 case／原 packet 文件及 SQLite fallback，实际从复制的 manager source.json 读取。

rank／index／metrics／solver／brute／generator／audit execute／create／fit／model／network／Popen／report render 全 patch 禁止，
触发0，完整状态／预算／报告4原件保持；只规范 boolean `replayed` 标记。
source HEAD 错／dirty 的负例均在 native import 前拒绝；早期 console 负计数显示错误及其更正原件保留，
没有借更正重跑科学任务。恢复总回执 `/workspace/work/g5-native-replay-20261113-01/summary.json` SHA：
`8ea065bce37fbc29b96b62f25225ee6e6a7266ea003fbac5c792d4b43b1f4c3c`。
这些 Python guard 与 hash 是本次恢复证据，不是 OS sandbox。

## 后置界面与报告

科学 batch 完成后，独立 presentation 提交 `e638b5f` 修复无任务却发409请求，并补4个精确中文方法名。
它只改变 read-only availability projection、前端空态／label、生成 bundle 和两项投影测试。
实际科研 code identity 仍为 `3945ed0f…d3707e`；没有改 registry／core／adapter／report／driver／协议或 case。

总审最初直接比较 current main 与8e清单，正确因 project_workbench 差异停止；失败已保留。
后续显式选择干净科研 pin，继续逐文件核验，**没有声称 current main 的175文件全未变**。
helper 曾误读 native plan 的扁平结构，修正只改字段访问，实际 state／action／result／feedback SHA 条件均保留。

最终 UI05 两 case 各28 GET、0 POST／blocked／pageerror／HTTPerror；
`evidence_task_available=false` 且 task endpoint 请求确为0，不是过滤409。
8 个实际下载 HTTP200、SHA／大小与原 report manifest 和磁盘匹配，125 个 case 文件及 API 前后不变。
本总审再次核8文件并实际看代表 desktop／mobile／PDF首末图片；未重开浏览器或重建报告。
PDF为7／8页，保留 revision-separator box glyph、Latin 紧排及末页留白；不是整份PDF视觉或用户满意度审定。
UI05 summary SHA `5a1c8f2e…d0a1dd`，本总审下载核对 `ui-crosscheck.json` SHA
`c727618bbe63841be513e3417031068234d314d903474b8b00dfa9fd4aed5cb3`。
初始 UI01／02 helper 结构／selector错误、03预期409停点、04完整409基线均保留。

## 工程回归、旧研究和后续 Gate

科研代码的完整工程回归为 **1,225 项：1,206 pass、19 skip，0 failure／error**。
cache-inclusive 整树保护严格回执仍为 false：4个派生 pyc 变化；root 另行有限接受实际183个非bytecode源文件
及整个 tests 树一致。原 false receipt、before／after与具体差异保留，不冒充严格全目录零变化。
工程 fixtures 确实 fit，次数未计量，不能把整轮程序拟合说成0；真实旧课题累计仍20／20／10=50，
本轮两个新 native 课题拟合为0。后置UI另有17项相关检查、typecheck／build；没有重跑科学结果。

369 个 protected 原件、292 个旧研究文件及 G4／旧G5原件保持；旧项目没有升级或预算重置。
依赖加载／安装版本交叉核对和 compatible-upgrade 的 runtime guard 已闭合；旧 G6 sklearn1.9 分区不兼容失败继续保留。
原 G0 cgroup、完整 G4／G5 安全自主／sealed Gate 未由可信本地 slice 通过。
后续 G6 clean-release 是单独增量，不预先由本总审接受；即使安装／保存结果恢复通过，也不是模型重 fit 或完整科学复现。

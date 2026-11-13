# Sprint 009：保存查询阅读器与安装交接

北京时间2026-11-14 01:47在继承云盘接续。仓库/origin与干净main `76d86fc`核对正确，没有其他活跃owner；领取 `root-sprint009-20261114T0147`，分文件委派、持续heartbeat。494保护原件和三根完整421路径集起点一致，8个参考checkout仍为manifest固定HEAD且clean。

## 实际实现

固定源码 `0acb05e253f543ea2483e383c7e2358c81c422bd` 新增`saved_retrieval_reader.py`和`retrieval-reader.ts`，复用原工作台行动卡。两条有界GET路由严格要求当前project/snapshot/action，读前后核活动项目，不接受客户端路径或研究命令；服务端校验原完整封套指纹、audit→primary、原输入SHA、query/doc/qrel和两臂完整保存记录。

点击后才分页读取，每页25条，按原顺序保留133条：60指标损失，73无损失但召回不全（65两臂不足、8仅基线不足）。选择查询后阅读原文本、指标、两臂各最多20个保存文档与行/SHA。原文展示有明确截断标记，不补算未保存的逐文档分数；引用标签不当作事实支持或答案正确性。无自动GET，错误保留已核对分页，失效异步不显示，返回恢复焦点。

没有改科研registry、执行器、评价器或旧producer。实际科研codeidentity仍 `3945ed0f5ec85b0ce42af0bb9ac0d0c27034bf932dac27fee9f7008ec2d3707e`，不升级原项目或预算。[完整接口与用法](../saved-retrieval-reader.md)、[精确代码/输入/证据索引](g5-local/saved-reader-verification.json)。

## 工程与真实保存结果验证

| 层 | 实际结果 |
|---|---|
| 针对性测试 | 17项保存手工夹具测试，损坏/缺失/分页/路径/大小/拒绝计算；0 estimator fit、rank/score/dispatch |
| 原HTTP门禁 | 5项现有HTTP测试通过；临时工程项目不计作真实研究收益 |
| 前端 | format/lint/typecheck/build通过，生成web资产随源码提交 |
| 独立直接读取 | 655项原件/身份/保存值核对，未重新评分/执行 |
| 实际HTTP | 原项目59GET，33成功、18非法400、4未知404、4过期409；12页覆盖原133行，两行动6次样例/240条保存文档读取，1500项核对 |
| HTTP响应独审 | 671项逐保存响应/原件核对，不额外重发HTTP |
| 实际浏览器 | 两已有项目、五页、桌面1440×900/手机390×844，36截图（含2张隔离异常夹具）；4真实上下文92GET（其中32 reader GET），0POST/拦截/页面或HTTP错误 |
| 客户端独立夹具 | 409、错binding、响应前DOM移除三种状态另测，不冒充真实科研结果 |
| 最终读取器独审 | 805项固定178产品文件、原件/完整路径集、浏览器/手机末列文字范围与4张实际看图核对，通过限定展示验收 |

浏览器实际遍历两尺寸的全部133行，读取762/1397/495三类query、审计行动query762和原文；核返回焦点、刷新不自动读取、手机BM25末列Range未被固定首列遮挡。前后五类原API字节一致，state13/3plans/2tools保持。不是原隐藏评价、重训或新算法收益。

## 继续完成的安装验证

读取器验收后未停止于代码提交，继续从相同0ac源码离线构建新wheel，178产品文件源/wheel/target逐字节相同；安装后98个实际产品模块来自新target，12GET读取原列表/查询/报告。轮子1,223,545字节，SHA `dadf9baec9f8acf79e7ed8bd9758af14b4812aa64f1573cba67c5a668ddbea76`。

独审发现pip target两CLI的RECORD相对路径不自洽，且shebang借用旧依赖Python，保留原记录和该范围限制；不把导入target的HTTP smoke说成target/bin CLI独立可用。

随后另建无依赖、无systemsite的标准venv，只验证安装记录：188条路径在新venv内，187哈希/大小＋1无自哈希的RECORD自身，178产品文件与wheel一致、两CLI脚本位置/shebang正确。独立759项核对；该阶段没有产品导入或CLI执行，不能冒充完整运行。[安装阶段与边界](g6-local/reader-release.md)。

## 失败、负结果和预算

浏览器01在首次列表读取后的测试等待中，被现有CSP拒绝Playwright的裸字符串predicate；只改测试为函数predicate，保留01失败和源码，产品CSP未放宽。02完整通过。独审自己的HTTP错误次数先假定30，实际为26；旧检查器/错误记录保留，修正计数后没有重发科研请求。作者初次TypeScript类型错误和测试NameError也各自保留，最终源码及验证已固定。

SciFact原宏Recall下降、133混合集合、调度唯一慢例，以及旧表格恶化/负预测均保留。494原件、421路径集和历史50研究estimator不变；本轮新研究/工程estimator fit及模型服务调用0。确有本地HTTP、字段校验、安装及进程活动；开发token/金额未知。CPU bootstrap的实际uname与后置进程守卫分别计，不声明整轮零网络/子进程。

原G0/完整G5/G6、OS/sealed和多代RSI门槛不因本次工程交付通过。单个3小时任务仍enabled，当前平台触发标记为01:46:53北京时间，run/result详情仍null、通知投递unknown；实际本轮成果另有证据。下次计划04:47:27，不将计划视为已启动/送达。


## 继续完成独立依赖与修复真实CLI缺陷

继续按历史完整23分发项构建本地wheelhouse，再在独立、无systemsite的标准venv离线安装；版本、pip check、全部6732 RECORD及本venv来源的998个site-packages模块（98产品/900第三方）通过，原保存接口12GET通过。公共依赖获取与之后离线安装/回环smoke分开统计。原生CLI帮助退出0，但旧可选runtime帮助因顶层SDK导入退出1；该0ac负结果和两次metadata解析器错误原件保留。

因而继续做了源码窄修 `8a394e316009a035cd5ac2de5fd2f00a3ca0fe79`：stdlib帮助入口延迟导入旧runtime，8项测试通过，原adapter不改。帮助不加载SDK/开socket/建目录，缺少可选SDK时实际启动明确返回2，未引入SDK或扩充任何模型预算。新wheel/标准安装的实际验证按[安装交接](g6-local/reader-release.md)记录，不把旧0ac结果冒称新wheel通过。


独立复核另发现原安装审计将998个site-packages模块总数误标为第三方数量；按原模块路径集合区分为98产品＋900第三方。原receipt和检查器失败保留，公开计数据原路径集合纠正，没有重新导入或伪增模块。


## 最终新安装物实测

新8a wheel为1,224,468字节、SHA `e2941f74f2e93ba15a6f4eda7e8e53c9d539f99f39ac6e030f146b32fc8aa563`；179产品文件与Git/新wheel/新标准安装一致。既有22非产品pins离线复用，23总分发项/pip check/6733 RECORD通过，旧环境与失败不覆盖。两实际帮助返回0/0，缺SDK真实启动返回2且无traceback，安装入口的socket/进程/建目录守卫未触发。

新venv独立读取12GET及原报告通过，所有998个site-packages模块来源在本venv内（98产品/900第三方），科研identity、state13、tools2、全部原件保持。原8a前178个reader/前端/adapter字节不变，原0ac UI/HTTP证明保留其精确source；新包另外实测，不重跑全部已通过的浏览器或研究。阶段回执、环境及标签澄清见安装交接与机器索引。一次执行通道恢复时两个协作任务被中断，重新核旧云盘/lease/未提交文档一致后从原产物接续，没有重建历史。

下一任务是G5剩余跨任务策略迁移的最小预注册：审查独立检索数据的许可、语义/大小和对照可行性，先冻结候选、评价及预算并独审，再考虑新研究执行。旧SciFact/调度预算不能通过复制项目或换ID重置；保持0模型/API切片，当前无需新增用户决策。


最终新安装物独立复核15471项文件/保存值断言通过，无安装/CLI/HTTP重复执行。回执 `runs/sprint-009-independent-20261114/cli-fixed-install-review.json` SHA `60b557a108f91c9b5d81bb86d800ea2c1a48091d7ce527beec7a32f46f3a2930`；第四原生安装独审14772项（含已保留的可选CLI失败），SHA `0cd23a05230f5cdbfcda62dbc2cd72776bcadcb0dc850b1fce171b0ad2b022d5`。这些计数是工程核对，不是新增科研样本。

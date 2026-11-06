# Auto Research 产品定位与能力横向调研

核对于2026-11-06。本文用于确定产品定位、能力取舍和近期开发顺序。当前实现以本仓库代码与已有实际轨迹为准，外部能力依据官方文档、固定版本论文和官方仓库。

## 1 定位建议

**Auto Research 面向已有课题、资料或数据的学生与小型研究团队，帮助他们把一个研究问题推进到有依据的下一步。项目保存问题、计划、实际分析、结论依据和路线变化，研究者能够检查、修订并继续工作。**

首个重点场景建议选择数据支持的探索性研究。用户带入一组可公开使用的表格数据和少量相关资料，提出一个可检验的问题，系统完成必要分析，说明结果支持到哪里，并据此决定继续哪条路线。材料、生物等领域经验可以逐步接入，近期先把这条工作链做深。

选择这一场景，来自我们已有本地资料、计划版本、受约束工具、执行记录和恢复能力，也来自当前分析方法较窄的实现差距。目标用户的需求强度与采用意愿仍属于产品假设。

### 用户真正要拿走什么

- 一项得到回答或范围被缩小的研究问题。
- 能打开原数据、论文位置或实际分析工件的结论。
- 当前采用的路线、改变路线的理由，以及仍需判断的问题。
- 下一次打开项目或交给合作者时，可以接着工作的状态。

对外介绍应围绕这些结果组织。多Agent、配方、画布、记忆和RSI分别说明它们怎样帮助完成上述工作。

## 2 横向对比

以下按用户工作流比较。表中公开能力来自产品方或作者说明，公开资料未说明的能力记为unknown。

### 文献、资料与研究报告

| 产品 | 已公开的主要工作流 | 可以吸收什么 |
|---|---|---|
| Elicit | 从问题、检索和筛选条件进入论文筛选与字段抽取。用户可覆盖判断、返回前一步修改，抽取有支持引文和解释，各阶段可导出CSV，综述支持协作 | 将证据做成可编辑、可核对的工作对象，筛选和抽取的依据随结果呈现。[工作流][elicit-flow] |
| Google NotebookLM / Gemini Notebook | 收集多种资料，也可研究检索后选择导入。Notebook保存来源、聊天与Studio产物，支持报告、数据表及共享。现有产物与后续来源更新分别处理 | 资料选择、阅读和成果组织应简单，当前来源、生成时依据、导出成果之间的关系要清楚。[来源][notebook-sources]、[Notebook][notebook-workflow] |
| Consensus | Research Agent分解问题并串联检索，展示子检索与过滤过程，引用区分全文和摘要。Library组织PDF、Zotero和Collections，官方提供API与MCP入口 | 复用文献发现与证据输入能力，呈现检索条件和全文可用性，核对具体端点后再选择接入。[Research Agent][consensus-agent]、[Library][consensus-library] |
| Perplexity Research | 反复搜索与阅读，使用编码能力调整研究路线，形成报告。Enterprise Spaces提供文件、连接、自定义指令与协作 | 多轮检索和自动改道已有成熟产品，研究入口应显示当前问题、资料范围及最终依据。[Research][perplexity-research]、[Enterprise Spaces][perplexity-spaces] |

这组产品已经覆盖大量资料收集、引用综合、可修改步骤和协作需求。用户若只需要论文汇总或一次报告，成熟产品可以直接承担。我们应将研发资源投入实际分析、研究判断与项目接续之间的连接。

### 通用助手与现成Agent工作环境

| 参照 | 已公开的主要工作流 | 可以吸收什么 |
|---|---|---|
| OpenAI研究API文档 | 展示联网搜索、文件检索、远程MCP与代码工具如何支持带引用研究。当前指南已列出旧deep-research模型的停用与迁移说明 | 检索、代码和引用可以组合复用。正式接入按当前API和工具配置核对，模型名称与旧示例分别处理。[当前指南][openai-research] |
| Claude Research | 官方2025年发布说明已展示跨Web、Workspace和集成来源的分解研究及原文引用 | 通用检索、连接和综合可由Host承担，产品需要提供有明确研究含义的输入与产物。[发布说明][claude-research] |
| Claude Code | 当前官方文档展示多代理研究工作流、保存后重跑的编排，以及项目和子代理记忆 | 直接利用已有Host获取提案、检索和代码产物，把项目当前状态、可用能力和实际反馈提供给它。[工作流][claude-workflows]、[目录与记忆][claude-memory] |

现成Host已经能组织相当完整的研究和编码工作。Auto Research的投入应让研究者更容易设定问题、检查依据、决定路线和接着推进。现有Host桥可以承接这些能力，模型供应商的选择按实际任务和可用资源决定。

### 用户为什么会选择专门的工作台

用户只需要找到相关论文、整理阅读材料或得到一次研究报告时，上述成熟产品与需求直接对应。Auto Research更值得验证的使用时刻，是用户需要持续处理自己的数据和方法，反复核对同一个问题，并向老师或合作者解释路线怎样变化。

与已经使用Claude Code的研究者比较时，需要检验工作台是否减少了手工整理context、查找旧结果和解释当前状态的工作。若用户在Host中已能顺利完成任务，新增界面的价值取决于它是否让这些具体动作更容易。若用户主要卡在领域方法缺失，优先补相应研究能力。

### 科研执行与长期研究系统

| 系统 | 已公开的主要工作流 | 可以吸收什么 |
|---|---|---|
| Kosmos | 2025论文将目标、数据、文献与分析积累到world model，报告关联论文或分析Notebook。2026-05-18官方工程说明进一步描述持久编码Agent、研究中交互反馈、共享文件与子代理 | 持续项目、反馈和可追溯报告已有直接先例。吸收结论与分析工件的关联，以及长期研究状态的组织。[论文v2][kosmos-paper]、[2026工程说明][kosmos-current] |
| Biomni | 从任务与数据路径出发，先检索相关工具、软件、数据库和领域知识，再规划并运行代码。官方仓库提供轨迹导出、领域Know-How与MCP | 先理解任务、匹配实际可用方法，再形成计划。工具目录逐项接通并说明输入、输出和适用条件。[论文v1][biomni-paper]、[官方仓库][biomni-repo] |
| AI Scientist-v2 | 从研究方向进入想法、文献与实验树，节点保存代码、运行、指标、图和错误，包含可行性、调参与消融等阶段 | 保存负面结果与失败分析，说明它们如何改变后续行动，按任务需要再引入实验分支。[论文v1][scientist-paper]、[官方仓库][scientist-repo] |
| Agent Laboratory | 按研究、实验和报告阶段积累产物，Co-Pilot允许人在子任务结束后继续或反馈重做，checkpoint保存接续状态 | 在具体产物处让研究者介入，支持对某一步修订和重做。报告中的研究主张应能找到实际执行依据。[论文v2][laboratory-paper]、[官方仓库][laboratory-repo] |

这些系统将研究进展建立在实际检索、代码或实验产物上。我们的主要能力差距在这里。当前质量核对与来源读取已能推动计划变化，但尚未形成可普遍回答研究问题的数据分析能力。

### 平台与编排参照

AgentArts和LangGraph的职责、自动化入口及首次接通范围见第7节。它们为工具、状态、编排、部署或恢复提供基础能力，产品仍需定义研究问题、方法适用性、结论依据和使用体验。

## 3 哪些概念已经成为共同能力

| 概念 | 一手资料已经展示什么 | 本产品应怎样表述 |
|---|---|---|
| 自适应研究 | Perplexity调整检索路线，Biomni根据工具反馈推进，Kosmos积累研究状态 | 展示某条实际结果如何改变计划及后续行动，描述已发生的具体变化 |
| 人在回路 | Elicit可回改步骤，Agent Laboratory可反馈后重做，当前Kosmos可交互 | 给研究者具体的采纳、修订与局部重做入口，意见与受影响的步骤或结果关联 |
| 长期项目与记忆 | Notebook、Spaces、Claude Code与Kosmos均有相应组织方式 | 说明项目保存了什么，以及重新进入后怎样继续 |
| 多Agent | 科研系统与现成Host均能分工处理任务 | 按检索、分析等实际需要使用，展示输入和产物 |
| 引用与可信度 | 文献产品已提供引文、全文范围和证据抽取 | 进一步关联本项目数据、代码、计算产物和结论适用范围 |
| 配方与RSI | 方法复用和反馈驱动优化已有相关研究，见原概念证据 | 研究内环按当前实现说明。外环采用、回退和后轮版本管理仍待建设 |

可修改计划、真实工具反馈和可恢复执行是现有工程基础。它们组合后的易用性、对研究判断的帮助和具体用户收益，是值得验证的产品主张。上述比较尚不足以证明独有性或优越性。

## 4 当前实现与真正缺口

| 已有基础 | 仍需补上的用户能力 |
|---|---|
| 可保存、编辑和采用计划，已有版本比较与精确引用工具反馈 | 进入项目时把问题缩小到可判定的一步，让成功、反证或停止条件参与计划 |
| 通用表格质量、分组画像、来源完整性、工作簿投影，以及专项已有预测结果分析 | 增加能回答研究问题的实际分析。首项建议为受约束的表格基线比较，明确目标、划分、方法和评价 |
| 原件定位、来源行动、模型理由和报告 | 将主要结论关联到具体原文位置或分析工件，保留支持、冲突和解释范围 |
| 研究者意见保存，能进入后续提示和报告 | 让意见针对某个具体结论或步骤，接通修订、采用及必要的局部重做 |
| 已有Python控制器、SQLite行动与资源记录、Host桥和恢复 | 把新检索与分析能力通过同一正常入口接进项目，产物能再次打开并供后续决策使用 |
| 已有五页导航与X6画布 | 用研究问题、证据、分析结果和路线变化组织现有空间，依据实际使用卡点优化 |

当前实现入口为[方法注册][local-methods]、[Host接入][local-host]和[工作台][local-workbench]。公开diabetes轨迹已完成计划v1、实际质量反馈、计划v2及按v2读来源。PR #19已合并方法卡读取与宿主候选关联。A64配方候选与验证来自独立构造工程项目，候选尚未采用，现由主开发提供[只读接续材料](../recipe-research/a64-rsi-handoff.md)，队友下一份PR补单轮决定和版本接续。它们各自支持已接通的连接。

## 5 能力引进与优化决策

### 优先形成一个能回答问题的研究工作单元

| 优先级 | 能力与取舍 | 用户怎样使用 | 首个完成信号 |
|---|---|---|---|
| P0 | 优化问题与计划表达，复用现有计划对象 | 输入研究问题、资料、想比较的解释，以及什么结果会改变决定。Agent据此给出当前可做的一步 | 用户能说明这一步要判断什么，实际反馈能让计划继续、缩小范围或改道 |
| P0 | 自建一项受约束的表格分析，复用现有NumPy、scikit-learn及方法注册 | 选择目标、字段、合法划分与评价，比较简单基线和一项候选方法。执行后得到指标、图表、方法和实际参数 | 从工作台正常入口完成分析，生成可核对工件，结果进入下一次模型决策和报告 |
| P0 | 自建主要结论与证据的关联，利用现有来源和行动身份 | 点开一条结论，读到支持原文或分析结果，以及它适用的条件和未解问题 | 报告中影响路线选择的主要结论，都能定位到实际依据。没有依据的解释按待核实记录 |
| P0 | 接通已有A64单轮RSI | 消费原提案与验证，显式采用或回退并写明理由，保存有效版本供后轮读取 | 主开发交接只读材料，队友以一份PR交付决定、有效版本和后轮读取记录 |
| P0，本地闭环后 | 引进AgentArts的实际平台链路 | 经平台提出或传递一个任务，调用接好的能力，取得结果并回到同一项目继续 | 留下真实平台运行、工具产物和项目记录，能够录制构建与运行的完整流程 |
| P1 | 引进文献发现与结构化证据输入 | 优先支持可追溯的论文链接、已有报告或CSV抽取结果。按具体任务再接一个官方API或MCP | 一项研究问题可取得带来源的相关材料，进入计划时保留全文或摘要、位置和检索范围 |
| P1 | 优化具体产物上的研究者反馈 | 对某个结论或步骤提出意见，查看修改建议，采用后只重做受影响工作 | 保留原意见、修改理由、实际采用决定及后续结果，重新进入项目能读懂当前路线 |

P0表格分析的初版以一种明确任务类型为限，例如表格回归。目标与划分方式依据数据和问题确定，缺少分组信息时说明能够判断的范围。方法输出应包含实际参数、数据划分、指标及比较结果。第一次执行前核对原项目拟合和工具额度，已有累计资源继续计入。

问题表达和结论依据先利用原计划、来源、行动与报告组织。只有现有表示确实承载不了已确定的用户动作时，再扩展对象和接口。

### 引进边界

- 文献发现优先使用成熟服务或已有导出结果。Consensus公开API/MCP可作为候选，实际端点、访问资格、计费和资料权限在接入前核对。Elicit的CSV等已有结果可以先作为输入。
- 检索、分析代码与建议优先经已有Claude CLI或子代理Host桥取得。模型提案与实际执行结果分别记录。
- AgentArts提供所选平台路径支持的编排、工具连接、运行与观测能力。产品内项目和行动记录继续承担研究成果的归属。
- OKS外置知识库与更大规模Agent集群保留为后续方向，按实际任务确定接入范围。
- 大规模GPU实验树、任意代码环境、自动成文投稿、跨域方法大全和模型权重训练放在后续需求阶段。它们需要对应任务、资源和评价依据。

## 6 开发顺序与阶段结果

| 阶段 | 交付结果 | 怎样确认 |
|---|---|---|
| 第一步，A64交接与本地接续 | 主开发提供只读材料，队友消费已有提案与验证，主开发整合单轮闭环 | 显式采用或回退及理由、有效版本和后轮读取结果可对应，离线zip由用户转交，保留在Git之外 |
| 第二步，平台接通尝试 | 按用户方向自动化搭建一个最小AgentArts链路，明确其与本地项目的职责和连通方式 | 平台对真实项目context产生计划提案，经Host保存、校验和采用后，工作台能读到对应变化 |
| 第三步，研究能力补齐 | 一个可替换的公开数据实例，完成问题、分析、证据、路线调整与继续 | 用户能查看计算产物，解释一项结果怎样支持、缩小或否定原判断，再按修订计划推进 |
| 第四步，使用与提交收口 | 实际使用者反馈、必要优化、AgentArts完整流程视频和初赛材料 | 记录使用者的研究目标、实际卡点和后续决定，材料与冻结版本对应 |

本轮先完成[A64只读交接](../recipe-research/a64-rsi-handoff.md)和下一份单轮RSI接续PR，AgentArts排在本地这段接通之后。11月12日单轮目标与周二、周五PR窗口按实际进度调整。平台尝试可用现有有限工具取得接通记录，研究分析再接入同一链路，最终演示应包含一项有研究含义的结果。

### 演示故事

一位研究者带着数据和两种可能解释进入项目。Agent根据现有资料和可用方法形成计划，实际分析取得结果。研究者点开原数据、计算和相关文献，发现原判断需要缩小或改变。系统说明修改理由，用户采用新计划，下一步取得新的实际结果。再次打开项目，仍能看见目前结论、依据和未决项。

同一任务的研究活动、平台运行和项目保存记录要能相互对应。已有质量检查记录可用于说明机制，最终科学解释以相应分析和领域证据为依据。

### 阶段验证

新增能力通过它的正常入口走通一次完整任务，必要工程检查针对本次改变的连接。已经成立且仍适用的结果直接复用。研究结果看它是否回答了原问题或改变后续决定，用户价值看实际使用者能否检查、判断并继续。若以后比较效率或质量，才设置相同材料和资源条件下的对照。

## 7 AgentArts与编排能力的落点

### 平台能力与产品职责

| 对象 | 官方支持的能力 | 在本产品中的落点 |
|---|---|---|
| AgentArts Runtime | CLI提供init、config、dev、deploy、invoke。部署构建镜像、推送SWR并调用控制平面创建或更新服务，公开API另包含Runtime、Managed Agents、Memory、Gateway等分类 | 作为首次自动化搭建路径，托管接收项目context的计划提案服务。[CLI][agentarts-cli]、[API概览][agentarts-api] |
| AgentArts工具与知识 | 支持多种自定义MCP和General知识库接口，外部服务需要平台可访问地址与鉴权 | 后续逐项连接真正可用的方法和检索服务，本机地址需要明确连通方案。[MCP][agentarts-mcp]、[知识库][agentarts-knowledge] |
| AgentArts低代码 | 支持工作流JSONL导入导出、Dify DSL导入和发布后调用。资源缺失时需要补关联配置 | 已有工作流可作为后续编排候选，完整画布创建、修改与发布管理API尚待确认。[工作流管理][agentarts-workflow] |
| AgentArts观测 | 第三方Python Agent可通过OpenTelemetry上报Trace | 关联平台请求、Host请求及实际工具记录，原生用量未知时如实记录。[Trace][agentarts-trace] |
| LangGraph | Checkpointer、thread、interrupt及不同持久模式，恢复时有节点重执行与副作用处理要求 | 借鉴明确暂停状态、恢复输入和关键结果落账时点。执行位置、项目证据和可复用知识分别保存。[Checkpointers][langgraph-state]、[Interrupts][langgraph-interrupt] |

平台运行、工具连接与观测由所选平台能力承接。Auto Research提供研究问题、计划、方法条件、原始依据、行动和资源记录，以及提案的采用与后续研究判断。这一划分利用现有控制器和Host契约完成集成。

### 首次自动化搭建

1. 从正常产品入口取得一个已有项目的当前context和计划，明确可上传的材料范围。
2. 包装Runtime服务，接收context，调用账号实际可用的模型，返回现有`research-plan-proposal-v1`所需内容。
3. 沿官方CLI配置、部署和调用，保存实际平台请求标识。
4. 将原始回答写入既有Host流程，完成解析、校验和显式采用。
5. 在工作台查看计划变化及引用反馈，保留云端请求与本地项目的对应关系。

这一步取得的是平台提案回到产品的实际接线结果。随后在同一项目接上真实工具结果、依据和后续行动，形成完整研究流程及初赛视频。原独立C01代码节点保留为局部技术依据。

首接之前核对账号区域、服务权限、模型、SWR与构建条件、委托、运行规格、收费和资料上传范围。官方SDK介绍记录v0.1.10，本仓库依赖声明为v0.1.8，按现有版本先核对兼容性。后续改用新依赖时按仓库依赖约定处理。[SDK介绍][agentarts-sdk]

### 尚未确定的技术点

运行时概述要求ARM64，创建API的arch字段却允许arm64和x86_64，首次优先核对ARM64路径及账号实际支持。运行时概述说明沙箱释放会丢失临时磁盘内容，云端研究账本的持久存储方案仍需确定。[运行时概述][agentarts-runtime]、[CreateCoreRuntime][agentarts-create]

通用人工中断后跨进程恢复契约、低代码画布管理API和Trace缺少原生用量时的正常处理方式，均需在对应接入阶段确认，分别影响恢复、自动化和观测范围。

## Limitations

本轮为选择性一手资料调研，未登录外部研究产品实测、复现科研系统或执行云端搭建。外部能力描述和效果主要来自厂商与作者，不能直接推定本项目能够取得相同效果。论文、官方仓库和托管产品分别保留版本范围，仓库main按本次阅读日记录。

文献抽取与自动科研系统本身仍有判断风险。Elicit公开说明可能误读细节和数字，研究质量判断使用有限信息。AI Scientist-v2与Agent Laboratory的论文也讨论引用、方法严谨性或未执行内容进入报告的问题。结论与实际依据的关联因此应进入产品工作流。[Elicit限制](https://support.elicit.com/en/articles/14757928-elicit-s-limitations)、[AI Scientist-v2论文][scientist-paper]、[Agent Laboratory论文][laboratory-paper]

Kosmos的2025论文与2026产品说明分别使用，旧版交互限制不用于描述当前产品。Biomni官方仓库声明公开版本与托管Web存在版本差异。Claude Research发布说明用于确认当时已有机制。OpenAI研究指南包含已停用模型的旧示例，具体接入以当前API与工具文档为准。Google当前帮助页面使用Gemini Notebook名称。Perplexity Spaces的协作来源针对Enterprise。

公开资料未建立竞品与本项目具有同等预算、行动身份和重放契约的证据，这些比较项为unknown。目标用户需求、相对优势、科研收益和持续采用意愿仍需实际使用。已有研究内环与工程配方轨迹分别保留范围，完整RSI外环尚未接通。

## 来源

外部正文在本轮已打开并定向阅读。科研论文同时关注工作流、实际产物及局限，产品文档关注正常入口、来源范围、引用、反馈与共享。以下链接供核对和后续接入使用。

[elicit-flow]: https://elicit.com/blog/systematic-review
[notebook-sources]: https://support.google.com/gemininotebook/answer/16215270?hl=en&co=GENIE.Platform%3DDesktop
[notebook-workflow]: https://support.google.com/gemininotebook/answer/16206563?hl=en
[consensus-agent]: https://docs.consensus.app/core-features/research-agent
[consensus-library]: https://docs.consensus.app/core-features/library
[perplexity-research]: https://perplexity.ai/help-center/en/articles/10738684-what-is-research-mode
[perplexity-spaces]: https://www.perplexity.ai/enterprise/videos/how-to-set-custom-files-and-links
[openai-research]: https://developers.openai.com/api/docs/guides/deep-research
[claude-research]: https://www.anthropic.com/news/integrations
[claude-workflows]: https://code.claude.com/docs/en/workflows
[claude-memory]: https://code.claude.com/docs/en/claude-directory
[kosmos-paper]: https://arxiv.org/html/2511.02824v2
[kosmos-current]: https://advances.edisonscientific.com/research/how-we-built-kosmos
[biomni-paper]: https://www.biorxiv.org/content/10.1101/2025.05.30.656746v1.full
[biomni-repo]: https://github.com/snap-stanford/Biomni
[scientist-paper]: https://arxiv.org/html/2504.08066v1
[scientist-repo]: https://github.com/SakanaAI/AI-Scientist-v2
[laboratory-paper]: https://arxiv.org/html/2501.04227v2
[laboratory-repo]: https://github.com/SamuelSchmidgall/AgentLaboratory
[agentarts-cli]: https://support.huaweicloud.com/highcode-agentarts/agentarts_10_039.html
[agentarts-sdk]: https://support.huaweicloud.com/highcode-agentarts/agentarts_10_037.md
[agentarts-runtime]: https://support.huaweicloud.com/highcode-agentarts/agentarts_10_029.md
[agentarts-create]: https://support.huaweicloud.com/api-agentarts/CreateCoreRuntime.md
[agentarts-api]: https://support.huaweicloud.com/api-agentarts/agentarts_07_0002.html
[agentarts-mcp]: https://support.huaweicloud.com/lowcode-agentarts/agentarts_05_0136.html
[agentarts-knowledge]: https://support.huaweicloud.com/highcode-agentarts/agentarts_05_0245.html
[agentarts-workflow]: https://support.huaweicloud.com/lowcode-agentarts/agentarts_05_0058.html
[agentarts-trace]: https://support.huaweicloud.com/ops-agentarts/agentarts_14_0125.html
[langgraph-state]: https://docs.langchain.com/oss/python/langgraph/checkpointers
[langgraph-interrupt]: https://docs.langchain.com/oss/python/langgraph/interrupts
[local-methods]: ../../src/autoresearch/method_registry.py
[local-host]: ../host-model-selection.md
[local-workbench]: ../local-workbench.md

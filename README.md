# AgentArts Auto Research

目标是让研究者提供课题、材料与约束，由系统按条件选择方法、执行真实工具，并根据反馈调整和继续研究，交付论文式 PDF 与复现附件。医疗、材料和软件工程共用能力接口，方法保留各自的数据与评价含义。

把研究问题、来源证据、模型选择和真实实验连在一起：有依据地提出下一步，执行后按结果继续、修订或停止，并留下可追溯的观察、报告和复现材料。医疗、材料和软件工程共用这套工作链路；当前以公开的材料—细胞案例 P02 ChemoTopoChip 推进。

**[产品计划](docs/plan.md)** · [自适应研究设计](docs/research/adaptive-research.md) · [当前进度](docs/current-progress.md) · [Agent 开发导航](.agent/README.md) · [正式文档](docs/README.md) · [统一 UI](DESIGN.md)

已走通作者资料核验、870个共同材料组合的分组预测、模型选择数值候选、误差诊断、取证任务、资料回传和带原文引用的评议。最新数值候选未改善化学基线MAE；管线读取与工作簿评议均已真实执行，但实际导出映射和ALP身份仍未确认。旧失败与未知请求保留，产品接入AgentArts继续暂缓。

## 打开当前工作台

已有本机交付目录时，先明确选择要看的版本，再使用固定入口：

默认访问 <http://127.0.0.1:18784/>，保持终端运行，结束按 Ctrl+C。以后直接 `serve` 读取保存的选择，不按文件日期猜测“最新”；切换包后重启这个服务并整页刷新。端口占用会提示退出，不杀其他服务。选择保存在 ignored `.agent/current-workbench.json`，绑定实际包清单；查看、选择和启动均不调用模型或拟合。

只克隆 Git 不会得到本机 `runs/` 和参考资料。队员可接收[独立只读包](docs/portable-workbench.md)，解压后按包内说明运行 `python -I -S serve.py --check`、`python -I -S serve.py --port 18784`。它可阅读、下载和复算已有结果，不能继续运行研究。

## 从明确的来源配置制作新包

`config/workbench-p02.json`固定列出当前11份科学来源及综合报告的快照。拥有本机运行材料的主开发可执行：

```powershell
.venv/Scripts/python.exe scripts/publish_workbench.py inspect
.venv/Scripts/python.exe scripts/publish_workbench.py build --output runs/next-delivery --select
```

输出目录须不存在；快照不匹配时停止，不自动寻找“最新目录”。`--select`只在新包完整生成并验证后更新本机选择，服务仍使用上面的`workbench.py serve`。制作和选择不调用模型、不重建研究。该配置不是原始资料，普通Git克隆仍需另外取得运行包。

## 分工与开发入口

最终目标是可继续的研究项目、带依据的论文式 PDF 和复现附件。现阶段没有确认 ALP 生物终点、没有独立生物实验或 LLM 参数训练，也未证明策略自主改进。当前报告对应既有数值实验，新的取证与中断进度单独提供。

参考仓库与作者原件在工作区 `references/`；代码在本目录；分发包在 `ICT/outputs/auto-research/`。凭据、私有数据、运行数据库和浏览器状态不提交 Git。现有免费模型条件、项目新增现金 5 元上限，以及 Codex 剩余 5% 停止保存的规则继续有效。

<details>
<summary>历史 C01、钢材原型与早期运行命令</summary>

以下保留对应阶段的用法与验收边界；当前 P02 的状态以上面的项目进度为准。不要将历史目录或旧端口当成当前工作台，也不要用早期脚本演示替代真实模型证据。

## C01：钛合金与体外成骨细胞

已有完整ICT工作区的本机用户，可在原快照上挂载完成的研究交付和同一冻结资料索引：

打开`http://127.0.0.1:8770/`。这些ignored目录需由主控提供，克隆Git不会自动获得；端口已占用时使用已有服务或另选端口。此命令展示冻结研究、PDF/复现附件、条件记忆与参考资料搜索，不会启动研究或调用模型。其他环境按下面步骤生成独立历史分析，研究与资料库接入分别见上述文档。

C01 是独立的公开数据研究案例，原始资料和队员交接包存放在工作区 `references/auto-research/08-c01-tnzst/`。下列命令生成早期固定两轮分析，不等于上面的持续研究执行器（输出目录必须不存在或为空）：

```powershell
.venv/Scripts/python.exe -m autoresearch.c01 --archive "../../references/auto-research/08-c01-tnzst/案例输入包-C01-TNZST-20261028.zip" --output runs/c01-your-new-run
.venv/Scripts/python.exe -m autoresearch.c01_studio --archive "../../references/auto-research/08-c01-tnzst/案例输入包-C01-TNZST-20261028.zip" --workspace runs/c01-your-new-run --port 8769
```

打开 `http://127.0.0.1:8769/` 查看独立案例及其报告与复现附件。脚本执行两轮本地留一分析，第二轮沿用相同样本，只作敏感性比较；原始标签映射及实验重复等仍待核验。C01 是公开数据上的探索，不是新做的体外实验、临床研究或真实大模型自主研究；不覆盖钢材快照、不使用云或模型服务。原论文已研究该数据，不能把复现关联说成新发现。

后续研究可通过独立账本显式开启（目录必须新建，不能在快照或源文件目录之内）：

```powershell
.venv/Scripts/python.exe -m autoresearch.c01_studio --archive "../../references/auto-research/08-c01-tnzst/案例输入包-C01-TNZST-20261028.zip" --workspace runs/c01-your-new-run --continuation runs/c01-your-continuation --port 8769
```

在“研究推进 → 继续研究”逐步执行两个确定性分析：先检查已有逐折预测的误差集中情况，再探索一个已见数据的材料—细胞变量对对单一合金的敏感性。每步绑定原始快照和观察指纹，记录依据及结果；中途暂停，服务重启仍可继续；到上限后停在人工复核。重复请求不会重复执行，过期观察不推进。后续报告和复现包独立导出，原报告与快照不被覆盖。它不是 LLM 自主决策、独立验证或新增生物实验。

此仓库保存产品代码、工程样例与明确署名的固定公开材料数据；参考库、私有科研数据、凭据、浏览器会话和本地运行产物均不入 Git。

## 研究 Agent 从这里开始

阅读 [研究程序与提案契约](examples/research-program.md)。创建 `external_agent_proposal_v1` 研究，选择 `matbench-steels-v1`，按“观察 → 提案 → 实际训练 → 观察 → 下一提案”推进。当前配方只允许多项式阶数和 Ridge 正则参数；任意 Python 补丁或用户路径不进入协议。

钢材数据共312条，14个成分特征；固定组成分组划分为187/62/63。它是本项目自定义公开材料 holdout，不是官方 Matbench 五折成绩或科研发现。来源、许可和缺少加工条件等局限见 [数据说明](src/autoresearch/data/README.md)。

证据报告从实际记录生成，核对模型哈希后导出 JSON／Markdown：

```powershell
.venv/Scripts/python.exe -m autoresearch report --workspace runs/your-study --campaign-id CAMPAIGN_ID
```

CLI JSON 输入输出统一为UTF-8。终测只在 `finalize_campaign` 执行，之后本研究不能继续优化；终测指标不出现在用于生成提案的观察中。

## 产品持续决策循环

先按下方“运行”安装项目依赖，再执行仅使用localhost的工程探针：

```powershell
.venv/Scripts/python.exe scripts/run_research_probe.py --workspace runs/my-research-probe
```

探针使用4个独立CLI进程，验证首次运行、恢复、停止后再次运行不派工及状态读取。脚本测试端点读取真实观察，提供3次配方和1次停止响应；3次sklearn训练是真实计算，决策响应不是LLM推理。输出包含HTTP记录、持久请求账本、模型哈希、研究过程和论文证据结构。模拟用量／价格仅用于记账验证，真实外部费用为0。

真实模型配置示例与后续最少接入步骤见[持续决策接入说明](examples/autonomous-research.md)。默认禁止live访问；`--allow-live`只在模型、计费上界和资源条件已核实时启用。最多5次实验、8次模型请求和5元配置预留；同一研究始终使用原工作目录，重启不得换目录重置累计额度。该程序账本不等于供应商账户账单，也不覆盖AgentArts关联服务费用。

研究循环导出`exports/research-evidence.json`及`research-progress.md`，组织问题、方法、来源、实际结果与局限。下方工作台使用同一原始试验状态生成论文式PDF及附件；真实模型自主研究、科学增益及平台链路保持待验收。

## 本地研究工作台与论文交付

前端源码位于`frontend/`，使用固定版本X6与TypeScript；设计令牌统一取自`docs/design/tokens.css`。修改界面后在产品根构建：

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
```

构建生成Python包内的`web/index.html`、`app.js`、`app.css`和`vendor-licenses.txt`；这些是本地服务直接交付的资产，勿手改生成文件。源码、依赖锁和生成资产一同版本化；运行已构建版本不需要Node进程或CDN。只改变Python代码时无需重新安装前端依赖。

安装报告依赖，先将**已有**钢材任务制成只读证据快照，再打开本机界面：

```powershell
.venv/Scripts/python.exe -m pip install -e '.[reports]'
.venv/Scripts/python.exe -m autoresearch studio-prepare --source-workspace runs/your-steels-study --campaign-id CAMPAIGN_ID --output runs/your-studio
.venv/Scripts/python.exe -m autoresearch studio --workspace runs/your-studio --port 8766
```

在浏览器打开 `http://127.0.0.1:8766/`。默认总览显示既有研究的目标、进展和边界；研究推进默认显示流程画布，并可切换过程记录与问题表单；实验中心、知识空间、成果与复现各有独立页面。知识资料可以按类型和主题筛选，查看原记录、进入阅读或关系画布。资料原文未进入快照时，阅读内容限于已有摘记，并可访问原始来源。

可选的本地实验入口用于工程验证：在上述命令末尾加 `--local-demo`，到“研究推进 → 本地实验”逐次启动；每次实际拟合一个受限候选，最多两次。它使用独立工作区与本地脚本策略，不访问模型或云，不是大语言模型自主研究。重启服务后继续使用同一目录和累计次数；状态未确认时停止并核查，不自动重跑。该演示与原快照只记录来源关联，不继承原模型或预算。

本地实验的结果当前显示在独立记录里；顶部PDF/ZIP仍来自原冻结快照，不包含本地演示结果。此钢材演示页面未接通真实领域研究、产品自主LLM策略或AgentArts。

可下载PDF和复现附件；保存的人工后续问题跨服务重启保留，状态为待执行。保存不会触发研究。关系画布上的保存／恢复／重置只操作本浏览器布局，按项目ID和证据快照分别保存节点位置与视口；不代表服务端、多人或跨设备同步。当前页面读取既有研究证据，不启动模型、训练或云端调用。关闭服务后用同一条studio命令恢复即可。

没有历史任务时，先运行上文`run_research_probe.py`，从其输出读取campaign_id，准备其钢材研究目录。探针会做3次真实CPU训练；**工作台准备与导出只重建预测，不新增拟合、模型调用或云费用**。准备命令只读源数据库，拒绝覆盖已有非空输出目录；本五页模板目前只接受固定的`matbench-steels-v1`和最多5条试验，不把钢材叙述用于其他数据或静默省略候选。

无需打开界面也可导出：

```powershell
.venv/Scripts/python.exe -m autoresearch paper-export --workspace runs/your-studio
# 解压 exports/reproduction.zip 后，在解压目录执行：
python verify_results.py
```

`exports/research-paper.pdf`为五页中文方法报告，包含来源、假设、真实结果、局限和主张索引；`exports/reproduction.zip`按白名单打包数字参数、62条验证输入、原始状态、计算源文件、图表输入和标准库验证脚本。独立脚本核对哈希并复算全部已保存模型的验证MSE，**范围是验证推理复算，不能替代从头训练、独立终测或科学结论复核**。附件不含工作目录配置、密钥、SQLite数据库或浏览器会话。哈希用于完整性检查，不是签名。

服务仅绑定127.0.0.1，校验Host、Origin与保存请求的CSRF令牌，不提供执行代码、调用模型或任意文件下载接口。这是单操作者本地工具，不具备多人账号或公网部署认证。证据发生变化时拒绝读取和导出。中文字体默认使用本机SimSun；其他系统可通过`AUTORESEARCH_PDF_FONT`指定受信TTF/TTC。没有字体时回退CID，交付前应实际渲染检查。

## 运行

Python 3.11 或以上，在项目目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-demo.lock
.venv/Scripts/python.exe -m pip install --no-deps -e .

# 第一个独立进程：拟合基准，保存后暂停。
.venv/Scripts/python.exe -m autoresearch demo --workspace runs/demo --steps 1

# 第二个独立进程：恢复同一任务，比较两个候选并做终测。
.venv/Scripts/python.exe -m autoresearch demo --workspace runs/demo --steps 2 --finalize

.venv/Scripts/python.exe -m unittest discover -s tests -v
```

输出保存在 `runs/demo/report.json`、SQLite 和各 trial 的 `.model.json` 中。参数工件包含真实系数、特征变换、训练数据哈希和库版本；不使用 pickle。再次运行同一 demo 会返回已存在任务，不重训已完成候选。

## 固定工程演示发生什么

1. 一阶模型建立基准；固定训练集只用于拟合，验证集用于选优。
2. 控制器读取已保存指标，再尝试二阶交互特征。
3. 实际拟合一个强正则候选；若未达到固定改进门槛，保留前一个模型。
4. 终测单独执行并锁定本任务；后续不能继续用该任务调参。

三个候选均执行真实训练。数据是公开可重建的数学工程样例，终测不是秘密科研基准，指标不能外推为医疗、材料或跨领域研究效果。当前也没有证明策略自学习或研究 LLM 参数更新。

## 并发、失败与恢复

- 同一任务串行执行；SQLite 写事务原子预留预算。失败仍消耗一次 trial，幂等重试不会再训练。
- 正常暂停后可跨进程恢复。未知在途工作保留 `running`，不盲目重跑。
- 进程被强制终止后，操作者确认 worker 已停止，再用下面的窄命令标记中断失败。它不终止进程，也不退还已用预算；旧请求仍返回失败结果，重新尝试须使用新请求标识。

```powershell
.venv/Scripts/python.exe -m autoresearch reconcile --workspace runs/demo --campaign-id CAMPAIGN_ID --trial-id TRIAL_ID --confirm-worker-stopped
```

即使误核对时旧 worker 晚到，结果也不能晋升为当前最佳模型。此恢复操作未暴露为模型可调用工具。

## AgentArts 接入与复用

先看 [C01敏感性核验](agentarts/c01-sensitivity/README.md)：包含云端已试运行的纯代码节点、8条公开输入、9项本地测试和控制台重建步骤。3次真实执行分别验证节点、完整工作流与变化后的输入；目前保留为开发草稿，没有发布API或部署实例。

已实现入口 `autoresearch.protocol.handle_request(request, workspace)`；[请求示例](examples/create-campaign.json)及[工具契约与待验收项](agentarts/README.md)。工作目录由操作者设定，请求不能传任意代码、命令、评价器、分数或数据路径。

拟合使用 scikit-learn 与 NumPy，循环机制参考已有研究项目，详见[复用与来源](THIRD_PARTY_NOTICES.md)。没有复制整个研究 Agent 框架。数据ID白名单和数据／划分描述在创建研究时冻结；主案例科研数据和 AgentArts 云端研究决策仍待接入。

安装可选运行时后，可执行真实 HTTP 探针：

```powershell
.venv/Scripts/python.exe -m pip install -r agentarts/requirements-runtime.lock
.venv/Scripts/python.exe -m pip install --no-deps -e .
.venv/Scripts/python.exe agentarts/run_local_probe.py --workspace runs/my-http-probe
```

探针仅在 `127.0.0.1` 临时启动两次服务进程，执行训练、重试、暂停、恢复、候选拒绝和终测，结束后关闭自己启动的服务。请选择新的工作目录，已有证据不会被覆盖。详见[Runtime 接入说明](agentarts/README.md)。基础安装不包含 SDK 时，SDK 专项测试会跳过。

平台体验权益及独立低代码执行已核验。高代码Runtime的持久存储、入站认证、镜像部署、实际请求和Trace仍待验证；本地SDK HTTP通过或低代码草稿试运行都不代表该Runtime已部署。

</details>

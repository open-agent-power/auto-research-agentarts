# AgentArts Auto Research

产品目标是基于AgentArts持续推进科研项目，交付有证据支撑的论文式PDF、复现附件及可继续的项目。当前已实现受控实验与决策底座，以及读取既有钢材实验的本地研究工作台、五页中文报告与验证复算附件；领域主案例、真实模型和云端仍需独立验收。

已实现本地闭环与官方AgentArts SDK的HTTP桥接，以及产品自身的HTTP模型客户端和持续决策控制器。控制器可以读取真实观察、接收模型的实验／暂停／停止决定、训练候选并恢复。调用前预留请求与费用预算，未知请求不自动重发。真实LLM与AgentArts云端尚未验收；用户已明确暂缓平台接入，本轮仅用明确标注的脚本HTTP端点验证流程并执行真实CPU训练。

此仓库保存产品代码、工程样例与明确署名的固定公开材料数据；参考库、私有科研数据、凭据、浏览器会话和本地运行产物均不入 Git。

## 研究 Agent 从这里开始

阅读 [研究程序与提案契约](examples/research-program.md)。创建 `external_agent_proposal_v1` 研究，选择 `matbench-steels-v1`，按“观察 → 提案 → 实际训练 → 观察 → 下一提案”推进。当前配方只允许多项式阶数和 Ridge 正则参数；任意 Python 补丁或用户路径不进入协议。

钢材数据共312条，14个成分特征；固定组成分组划分为187/62/63。它是本项目自定义公开材料 holdout，不是官方 Matbench 五折成绩或科研发现。来源、许可和缺少加工条件等局限见 [数据说明](src/autoresearch/data/README.md)。

历史本地实跑由当前开发 Agent 逐轮读取结果后提交5次配方：后4个候选均未达到固定1%采用门槛，控制器保留基线；其中弱正则一阶候选虽改善约0.15%，仍被拒绝。这只证明提案、判定与恢复链路，不证明策略优于搜索基线或真实材料发现。证据保存在操作者的 `runs/`，不随源码自动分发。

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

安装报告依赖，先将**已有**钢材任务制成只读证据快照，再打开本机界面：

```powershell
.venv/Scripts/python.exe -m pip install -e '.[reports]'
.venv/Scripts/python.exe -m autoresearch studio-prepare --source-workspace runs/your-steels-study --campaign-id CAMPAIGN_ID --output runs/your-studio
.venv/Scripts/python.exe -m autoresearch studio --workspace runs/your-studio --port 8766
```

在浏览器打开 `http://127.0.0.1:8766/`。可查看问题、来源、实际候选、采用／拒绝记录、两张图及论文正文，下载PDF和复现附件；保存的人工后续问题跨服务重启保留，状态为待执行。保存不会触发研究，当前页面是既有研究的证据快照。关闭服务后用同一条studio命令恢复即可。

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

已实现入口 `autoresearch.protocol.handle_request(request, workspace)`；[请求示例](examples/create-campaign.json)及[工具契约与待验收项](agentarts/README.md)。工作目录由操作者设定，请求不能传任意代码、命令、评价器、分数或数据路径。

拟合使用 scikit-learn 与 NumPy，循环机制参考已有研究项目，详见[复用与来源](THIRD_PARTY_NOTICES.md)。没有复制整个研究 Agent 框架。数据ID白名单和数据／划分描述在创建研究时冻结；主案例科研数据和 AgentArts 云端研究决策仍待接入。

安装可选运行时后，可执行真实 HTTP 探针：

```powershell
.venv/Scripts/python.exe -m pip install -r agentarts/requirements-runtime.lock
.venv/Scripts/python.exe -m pip install --no-deps -e .
.venv/Scripts/python.exe agentarts/run_local_probe.py --workspace runs/my-http-probe
```

探针仅在 `127.0.0.1` 临时启动两次服务进程，执行训练、重试、暂停、恢复、候选拒绝和终测，结束后关闭自己启动的服务。请选择新的工作目录，已有证据不会被覆盖。详见[Runtime 接入说明](agentarts/README.md)。基础安装不包含 SDK 时，SDK 专项测试会跳过。

平台权益、持久存储、入站认证、镜像部署、实际云请求和 Trace 尚待验证。本地 SDK HTTP 通过不代表 AgentArts 云端已接通。

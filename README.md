# AgentArts Auto Research

持续跨领域研究的执行底座：研究任务、实验或训练、独立评测、候选保留或拒绝、进度恢复。AgentArts 为产品主编排，领域计算通过受控适配器执行。

已实现本地闭环与官方 AgentArts SDK 的 HTTP 桥接：SQLite 持久化、真实 CPU 参数训练、验证集选优、候选拒绝、暂停恢复与终测锁定。新增外部研究 Agent 提案协议和公开钢材预测数据；每次提案绑定观察指纹、假设、预期影响及证据试验。产品尚未内置自主调用 LLM 的服务，云端部署和平台 Trace 仍待验证。

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

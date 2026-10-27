# AgentArts Auto Research

持续跨领域研究的执行底座：研究任务、实验或训练、独立评测、候选保留或拒绝、进度恢复。AgentArts 为产品主编排，领域计算通过受控适配器执行。

已实现首轮本地闭环：SQLite 持久化、三次真实 CPU 参数训练、验证集选优、拒绝差候选、暂停恢复、终测锁定和结构化工具协议。当前调度策略是固定工程策略，未调用大语言模型或 AgentArts；科研有效性待真实场景验证。

此仓库仅保存产品代码与允许公开的工程样例；参考库、原始科研数据、凭据、浏览器会话和本地运行产物均留在仓库外。

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

## 一轮发生什么

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

拟合使用 scikit-learn 与 NumPy，循环机制参考已有研究项目，详见[复用与来源](THIRD_PARTY_NOTICES.md)。没有复制整个研究 Agent 框架。产品优先保持可替换领域适配器，后续用真实数据和 AgentArts 研究决策替换工程样例与固定策略。

平台登录、资源与费用核查、发布流程、真实请求和 Trace 尚待验证。本地协议通过不代表 AgentArts 已接通。

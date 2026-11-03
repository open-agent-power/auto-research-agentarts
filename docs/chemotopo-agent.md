# P02 来源研究 Agent

本入口让真实模型选择原文件检查、四策略比较、数值记忆与下一步判断。它使用[来源核验](chemotopo-data.md)和[处理敏感性实验](chemotopo-rebuild.md)的方法，仍不具备 ALP 训练资格。新案例的论文式科学论证、模型训练、工作台挂载和 AgentArts 接线分别验收。

后续迭代使用[P02评估口径](chemotopo-agent-evaluation.md)：先验证受影响路径、完成一次定向审查，再冻结版本做一次有界实跑。下一步把真实轨迹和条件记忆挂载到现有工作台，不为补齐recall而追加模型调用。

## 复用与新增边界

- 沿用 `C01LocalLoop` 的请求预留、原始响应落账、未知发送保持、received恢复、工具提交后的幂等消费；沿用 `C01CloudLoop` 的身份核验、免费额度预检、credit hold和 `OwnedCloudOllama` 自有进程管理。
- `ChemoTopoStudy` 仅复用现有研究账本的路径防护与SQLite访问。P02有自己的配置、原始来源、行动、资格与结果，没有八合金输入、C01终点或32折协议。
- 原生工具解析保留单工具、已保存schema、严格参数和不修复响应的规则，只在末端调用明确的P02领域验证器；默认C01解析路径保持。
- 研究记忆复用不可变记录、来源版本、幂等导入、精确召回和撤回事件链。P02单独复算后导入 `diagnostic_observation`，没有伪造C01拟合或通过其数值验证器。

## 模型可以做什么

| 工具 | 实际行为 |
|---|---|
| inspect_source | 从固定SHA作者工作簿复算3312项角色关系，静态读项目ASCII管线；返回当前源引用与原坐标 |
| compare_policies | 读取原文件执行全部四个固定规则，保留完整数值工件与紧凑反馈；不按成绩挑处理规则 |
| remember_evidence | 重算已执行检查与比较，只准备确定的数值记录；先提交研究行动，再幂等写入记忆 |
| recall_evidence | 只召回当前来源/输入/分析/协议完全匹配的active数值记录 |
| review_evidence | 保存模型自己的finding/status/next_check，始终为未获科学批准的解释 |
| check_training_gate | 查看固定未决资格；模型不能改变它 |
| pause / stop | 保存模型原始原因，最后一个请求仅开放这两个预算控制工具 |

模型不能选择路径、代码、参数政策、预算或模型配置；不存在fit工具。直接伪造fit调用会被拒绝。比较、解释及记忆准备须引用已经取得的源ID，以及最新的来源检查或数值比较行动ID。历史记忆ID不会变成当前工具的行动权限。

比较反馈另给逐策略覆盖，以及B8S1/B10S1原行与对照示例，模型不只看到排序成绩。完整原始请求/响应保留在发送账本，完整数值另存内容寻址工件，避免把约13MB的追踪全文直接塞入模型上下文。

## 记忆的适用条件

P02使用明确的四字段条件：

```text
source_manifest_sha256  两份真实作者文件清单（文件名、大小、SHA、数据DOI）
inputs_sha256           清单＋固定policy协议＋raw-red-proxy终点身份
analysis_code_sha256    reader/rebuild/资格推导的代码身份
protocol               四策略协议＋来源资格版本
```

原C01的 `archive_sha256` 条件仍为独立变体；没有借用它的归档身份。两个scope字典即使填相同SHA也不相等。改变来源、终点、协议或分析身份不能召回旧数值观察。

目前只导入“来源角色冲突”和“四策略数值敏感性”两种观察，标记 `derived_not_scientifically_reviewed`。模型理由、解释、最优策略及临床判断不导入这些记录；没有把记忆更新称为模型参数训练。

## 中断与撤回

请求的完整观察（含记忆）与实际body在同一发送账本事务内保存。消费时新读取到记忆撤回后，观察SHA会变化，尚未提交的旧决定因STALE_OBSERVATION拒绝。它不是跨两个数据库的实时撤回租约，不宣称能锁住检查之后发生的并发撤回。已经提交的行动先按原request_id幂等恢复，不因后来撤回而重复计算或重新激活记录。

记忆是第二个数据库，因此记忆准备先成为持久研究行动，随后 `_finish` 才写入记忆。若在任一侧中断，原received响应恢复同一行动和幂等导入。容量、来源冲突或I/O等导入错误通过专门的MEMORY_IMPORT_PENDING保留received与技术hold，不能被标成“模型决定无效”；恢复成功只清理该call自己的技术hold，不解除财务hold。该路径有崩溃、ResearchError、财务隔离及独立子进程fixture测试。未知发送仍保持sending并要求核对，不自动重试或清零预算。

## 运行

首次使用需要两份固定作者文件和新workspace/output；模型资源目录与目标由操作者提供，不能从模型参数取得：

```powershell
.venv/Scripts/python.exe scripts/run_chemotopo_research.py --workspace runs/my-p02-study --output runs/my-p02-process1 --directory ../../references/auto-research/10-chemotopochip/2026-10-31 --goal "核验来源处理不确定性及可复用观察" --model-store <现有Ollama模型元数据目录> --max-requests 8 --max-new-requests 3
```

再次运行用原workspace、新output，省略已冻结的目标、来源和记忆路径；最多保留原8次累计额度：

```powershell
.venv/Scripts/python.exe scripts/run_chemotopo_research.py --workspace runs/my-p02-study --output runs/my-p02-process2 --model-store <同一元数据目录> --max-new-requests 3
```

离线恢复已收到的决定，或读取终态，不启动Ollama、不新发推理：

```powershell
.venv/Scripts/python.exe scripts/run_chemotopo_research.py --workspace runs/my-p02-study --output runs/my-p02-offline --max-new-requests 0
```

当前运输层只支持已核验的 `gpt-oss:120b-cloud → gpt-oss:120b` 官方云别名，不是本地8B权重。实际调用前读取账号免费额度、购买余额与统计周期，保留每次预检和调用后收据；保持至少1美元免费额度，并按每个剩余请求预留0.10美元。这个估算保护不是供应商硬消费上限，也不证明自动计费关闭。购买余额须为0，无购买、登录、换key或付费回退。原5元现金上限结算仍未知；AgentArts及8B下载继续暂停。

原生接口依据：[Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling)、[thinking字段](https://docs.ollama.com/capabilities/thinking)。参考内容不授予执行权限，本地仍检验每次工具参数及源/观察身份。

最终完整525项测试通过（166.845秒），其中21项新增P02专项覆盖原始body改动、伪造拟合、来源/工件变化、跨scope隔离、撤回未提交决定、第二数据库普通异常/进程中断、独立子进程received恢复、未知发送不重试和终态CLI离线读取。初版测试曾有状态断言/输出捕获适配错误；审查发现的postcommit异常漏支与策略上下文缺失在真实推理前修正，失败和两次中止的早期全回归日志仍保留。真实作者文件的最终操作者dry run最大请求40468字节，写入两个条件观察；这些脚本动作不计模型成绩。

### 费用核对与恢复

首次3调用后，第三份推理响应已收到并applied，但随后账号查询失败，触发财务hold。根因收据为`response_received=true`、`CLOUD_REQUEST_UNKNOWN`，不是未知推理发送。先停止新推理，再用独立自有进程只读账号（0chat），核对provider96→99、输入/输出增量及余额/usage差0.00259美元；同账号/周期/模型、purchased0且预留充足。独立复核后，操作者按预期hold/specSHA/3applied/0pending做事务CAS，仅清project的status/reason，未改原响应、请求数、max8或研究记录。intent/applied收据均保留；这不是模型或记忆工具自动解除财务hold。

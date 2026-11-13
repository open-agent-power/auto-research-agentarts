# G1-L 独立审查

审查者：`independent_review`；与执行者、算术验证器作者分工独立，共享工作区，不构成安全隔离或领域专家审查。

当前状态：**经批准的G1-L可信本地切片已独立核验通过。原G0隔离门及上游runtime门仍为BLOCKED，G2及后续阶段未解锁。**

## 授权与边界

用户在收到明确推荐的可信本地先行方案后直接回复“继续推进”，可按具体对话语境接受方案A，不要求机械口令。此次接受范围已保存在 [授权记录](authorization.json)；它与没有具体选项时一般性的“继续”不同，不扩大至完整上游运行、产品模型CLI、RSI或候选晋级。

原G0的资源隔离及上游运行验证仍为BLOCKED，G2及后续依赖不解锁。本切片仅验证已审计白名单在受监督可信本地进程上的真实数据闭环：6次本地工具、20次estimator attempts、1次本地来源提取、0次产品模型/API发送。宿主开发Agent的推理身份/费用与产品模型账本分开；未知费用不记零。

## 执行前审查

审查基线：`5d36424af76fbe50df4ef0476e4f762d6f3138e6`。

- 固定runner仅调用现有 `LocalWorkbench`、`ResearchProject`、`ProjectController`、保存OOF诊断及报告接口，没有外网获取、模型CLI或任意研究代码执行入口。唯一子进程是读取本地Git提交身份。
- 数据使用已核验的1030行Concrete原件与无损映射。已有成绩和唯一log1p候选是预先可见的历史知识；本次必须保留真实新回执，不能称未见任务发现或因果收益。
- 首次运行冻结原输入、产品代码身份、runner/独立算术verifier/控制器、授权、协议、任务定义及两份设计的八项文件哈希；恢复逐项核对，不接受漂移。
- 质量检查、来源提取、固定分组基线和保存诊断先于plan v2。候选阶段先验证已完成的本次baseline及对应诊断、派生年龄诊断完整等值、无未决/unknown行动，才写入计划修订。
- 新设计使用本次独立资源ID，避免与工作台内置历史设计冲突。候选设计的来源改为本次实际行动ID和结果哈希，不把历史“565相邻比较”等说明当作本次观察。
- 每个native操作先固定原request参数；恢复沿原ID交给原账本，不用新ID掩盖未知或重置预算。独立重放会禁止实际fit/execute后再验证这一性质。
- 两项执行前意见已修正：补齐宿主/evaluator/controller冻结与恢复校验；将候选阶段的观察完备性检查移至plan v2保存之前。
- 外层监督应保留实际超时、RSS、磁盘/工件观察与终止记录；这些是任务运行约束，不能冒称cgroup硬配额。后续阶段须保持冻结环境依赖，不升级版本后沿旧freeze继续。

## 本次实际执行与反馈顺序

原运行目录：`runs/cloud-concrete-local-20261113-01/`。项目为
`project-431366b59dac432dabb315d82dee6eae`，最终state32／plan3／waiting。
它是新云端lineage，不是旧本机研究的恢复。

| 检查 | 实际证据与结论 |
|---|---|
| 冻结身份 | 八项冻结文件哈希仍全部匹配；原输入、控制器及独立评价器身份保持。 |
| 第一轮先于计划修订 | baseline请求基于state12，原生保存诊断基于16；baseline快照为20且只含plan1；plan2基于该state20，引用本次baseline和对应诊断的精确行动ID及结果SHA。 |
| 反馈内容真实 | plan2的565个组内相邻龄期比较及3→7、180→360天对照均能定位到本次保存诊断；没有拿历史数值代填本次观察。 |
| 第二轮及最终等待 | 唯一log1p龄期候选基于state22、其保存诊断基于26；plan3基于候选快照30；随后state31请求wait，state32导出。 |
| 累计预算 | 同一项目、同一lineage从10到20次estimator attempts；最终5/6本地工具、20/20拟合、1/1来源提取、0产品模型请求，fit/source/model预留均0，没有未决或unknown研究行动。20次尝试为10次Scaler和10次Ridge，均有完成事件。 |
| 来源 | 一份原生来源收据含2个真实保存来源、3个选区；readme和许可页SHA与独立预核验原件一致。页面Markdown如实标注为派生捕获，不冒称原HTML。 |
| 运行监督 | 三阶段实际exit0，耗时约2.32／2.13／2.85秒；记录到的峰值RSS均低于187 MB，工件约10.1 MB以内，无停止原因。180秒、2 GiB观察阈值、128 MiB工件阈值及磁盘检查是用户态监督，仍不证明cgroup/PID硬隔离。 |
| 原失败保留 | 候选阶段一次监督器在worker启动前因误用宿主Python、缺h5py而失败；原前检记录保留，0新fit，之后使用未变化的冻结venv。没有新ID重发未知研究。 |

流程与来源核验原件：`runs/g1-local-review/chronology-and-provenance.json`，
**15项全部通过**，SHA-256
`5743117fd53c831f6616a9fae5dc40f91c529cec9b84a61813f701dcc20bc9f3`。
这里证明的是共享工作区中保存状态、回执和版本的执行顺序，不是对抗恶意执行者的sealed证明。

## 独立数值复核

独立数值审计由另一成员使用冻结的 `scripts/verify_concrete_reproduction.py`
完成；本审查读取其完整结果、失败列表、评价器哈希及关键对应关系，没有重复拟合。
最终 `runs/g1-local-verification/final/verification.json` 为 **3252项全部通过**，
SHA-256 `0dc7237f0ee7eaa4019456571bc6d3bfa2aac4d0ec3bac56b085e287b8dc1597`。

本次完整1030行／427签名组的同折比较：MAE从 **8.383388056181742** 降至
**5.702072514528065 MPa**，同时 **313行、129组恶化，负预测0→1**。
这些本次结果与历史说明中的数值并不完全相同，已保留本次冻结环境与原始回执，未强制改成历史成绩。
候选只保留为探索性表达比较，不能推导外部实验室泛化、龄期因果、工程采用或自主研究收益。

基线阶段的首次完整verifier因当时只有一个拟合行动而保持exit1：仅
`two_actual_grouped_fit_actions`不满足，其他已完成基线核验通过。该阶段记录保留；
没有修改评价器标准使提前评估变绿。最终父子结果完整后，同一冻结评价器才通过。

## 独立重开与原ID重放

实际命令：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python runs/g1-local-review/reopen_and_replay.py runs/cloud-concrete-local-20261113-01 runs/g1-local-review/final-replay-01
```

退出0。由原始manager重新打开原项目，读取保存问题、plan3、完整预算、报告及下一步等待条件；
没有根据聊天摘要创建替代项目。仅重放具有成功原回执的原参数与原请求ID：
**29次原host/core操作，11项审查全部通过**。

审查将 `Ridge.fit`、`StandardScaler.fit`、全部registry adapter的`execute`、
来源提取、产品模型请求、网络连接、模型/任意子进程及新报告渲染全部patch为抛异常。
实际 `forbidden_calls=[]`，因此这些重放没有拟合、工具执行、来源提取、模型或网络派发。
同时核对原case **96个文件**的全部SHA：重开及重放前后无新增、删除或内容改变；
完整项目状态、Host账本、工件及累计预算也保持。

机器回执：`runs/g1-local-review/final-replay-01/review.json`，SHA-256
`7dc9453a4bb9256010ea559990c438f567181f15197c37db2707bb28d35c4be0`。
成员接续摘要在同目录 `handover.json`；当前明确等待独立实验室／批次数据及领域复核，
这些需求本身不授权新下载、调用API或追加拟合。

## 验收范围与剩余边界

两轮真实推进、观察驱动修订、完整坏结果、证据定位、原生导出及独立技术接续已具备，
因此经批准的可信本地切片通过本次独立审查。这里没有产品内自主模型runtime、无人值守后台进程、
领域专家批准、sealed安全隔离或G2–G4收益证明；原G0状态保持不变。
本审查确认报告文件身份和原生读取路径，不代替实际浏览器/PDF视觉检查或真人用户评价。

## 交付后的新路径恢复验收

随后将完整case按原字节复制到 `runs/g1-local-restored/case/`，另行复制原始九列表格到
`runs/g1-local-restored/data/original.csv`；复制身份保存在父目录的 `copy-manifest.json`。
本轮独立审查没有创建替代研究项目、修改原请求或编辑账本。

冻结算术verifier已针对**新路径**再次执行：
`runs/g1-local-restored/arithmetic-verification/verification.json`，
**3252项全部通过、0新拟合**，SHA-256
`5f5faec6d41cdbc401bbe80d529d71a9b54d557d2626719840d80e1677961fa9`。
该结果指向迁移后的manager及原始CSV副本，输入树字节保持。

随后实际运行独立迁移重开／重放脚本：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python runs/g1-local-review/reopen_relocated.py --repo /workspace/auto-research-agentarts --case /workspace/auto-research-agentarts/runs/g1-local-restored/case --original-case /workspace/auto-research-agentarts/runs/cloud-concrete-local-20261113-01 --output /workspace/auto-research-agentarts/runs/g1-local-review/relocated-replay-01
```

退出0，**18项全部通过，29次原成功操作重放**。复制清单、原始与目标source-bundle全部文件SHA、
原project/run身份、state32／plan3／waiting和5工具／20拟合／1来源／0模型用量均一致。
新路径case **101个文件**在审查前后全部字节不变，原case也全部字节保持。
这次101文件包含原96文件验收后增加的5个图表交付工件；原96文件SHA全部保持，两次验收各自的原件集合和哈希均保留。

唯一迁移映射发生在宿主请求 `concrete-register-source` 的 `bundle` 存储位置：
旧case的 `source-bundle` → 新case的 `source-bundle`，仅在内存构造调用参数时替换。
原 `requests/register-source.json` 的SHA仍为
`adbed14b546cefadd8d352def3bafde75bc3f152c538cd18975c93df56e7d526`，没有写回。
原request ID、项目身份、receipt指纹、科学参数、输入数据与预算均未改变；
原生注册接口对同一内容回执的幂等恢复实际通过，而非绕过其冲突核对。

预检为核对复制一致性读取两份原件SHA；**进入重放后**，除原有全部fit／execute／来源／模型／网络／
子进程／新报告渲染guard，还patch了 `Path.open`、`builtins.open` 和 `sqlite3.connect`，
禁止访问旧case。`forbidden_calls=[]`，因此没有借旧存储位置回退伪装迁移成功。

完整回执：`runs/g1-local-review/relocated-replay-01/review.json`，SHA-256
`dfcc708c5a672d659f3b68a7d90f1972c79b10ede6387bdedd755261e8eeaf7e`。
审查脚本使用显式 `--repo` 定位实际源码，不假装脚本移动后仍能通过相同parents推断仓库。

此次证明的是同一环境中**存储迁移后的原生重开、只读算术和安全原ID重放**。
历史回执内原始绝对路径作为出处保留；必要宿主存储映射已明确记录。
它不证明冻结的whole runner可在任意位置无参数运行，也不代替G6干净环境安装、
跨环境持久卷或灾难恢复验证。原G0和后续阶段边界保持不变。

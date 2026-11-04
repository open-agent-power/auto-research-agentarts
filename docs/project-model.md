# 本地模型选择提案桥

此入口把固定的本地Qwen3:4b接到既有[选择上下文与提案](project-selection.md)：宿主冻结真实候选及FTS引用，模型只返回候选选择或等待、理由、引用ID，宿主再填入context SHA和provider并验证。原[ResearchProject](project-slice.md)与ProjectController负责工具执行、恢复及累计预算，不新建研究控制器。

## 命令与保存边界

在产品根只读检查本地配置与权重：

```powershell
Set-Location 'D:/XiangMuLuoDi/Development/ICT/track2/auto-research'
.venv/Scripts/python.exe -B scripts/run_project_model.py check --cache runs/local-model-cache
```

```powershell
$projectPath = 'PATH_TO_EXISTING_PROJECT'
.venv/Scripts/python.exe scripts/run_research_project.py status --workspace $projectPath

# 只有获准后才执行；owner是声明，CLI不会核验操作者身份或自行创造授权。
# 旧代码项目还须先显式兼容upgrade；不能凭预算命令绕过CODE_CHANGED或未知请求。
.venv/Scripts/python.exe -B scripts/run_project_model.py authorize --workspace $projectPath --request-id local-model-grant-1 --expected-limit 0 --new-limit 1 --owner '实际授权者' --reason '明确批准本项目新增一次现成本地Qwen3:4b推理；不联网、不下载、不增加拟合或付费额度' --expected-state-version CURRENT_VERSION

# 授权会改变版本；读取新版本后再预留。prepare同样是预算写入，不是只读检查。
.venv/Scripts/python.exe scripts/run_research_project.py status --workspace $projectPath
.venv/Scripts/python.exe -B scripts/run_project_model.py prepare --workspace $projectPath --request-id local-model-proposal-1 --expected-state-version VERSION_AFTER_AUTHORIZATION --cache runs/local-model-cache

# 只发送prepare封存的原payload一次，不自动消费或执行工具。
.venv/Scripts/python.exe -B scripts/run_project_model.py request --workspace $projectPath --request-id local-model-proposal-1 --cache runs/local-model-cache --output runs/my-local-model-process-1 --port 11449
.venv/Scripts/python.exe -B scripts/run_project_model.py status --workspace $projectPath --request-id local-model-proposal-1

# 明确离线消费已保存响应，合法提案沿原父/子请求提交；可能执行一个已有合资格工具或保存等待。
.venv/Scripts/python.exe -B scripts/run_project_model.py consume --workspace $projectPath --request-id local-model-proposal-1
```

CLI为JSON stdout，失败输出`code/message`并返回2。`request --output`必须为新目录，不能与原cache/exe重叠；换目录、重开进程或换请求ID均不能绕过项目累计额度。`prepare`绑定完整context、真实state/snapshot、模型身份及原payload；模型不能更改方法参数、目标、评价或预算，也不能把引用原文当作宿主命令。

`status`仅查看保存状态。重复`request`只核对原请求的持久状态，不重发已sending/unknown的推理；已received的响应可离线处理。`consume`也不请求模型，使用原上下文和固定父/子请求，状态漂移或非法输出保留为拒绝/待核对，不能重新生成提案后替换原响应。原预算及未知结果不通过复制目录清零。

本地推理不发生供应商API费用，但不据此把历史现金结算改成0；共享5元上限、未知结算、来源和本地工具额度继续保留。AgentArts接入仍暂缓。完成一次模型提案接线也不证明策略收益、科学解释正确或独立使用者价值。

## 只读核对原请求的工具协议

已有进程证据可离线诊断，无需选择真实项目或重新准备请求：

```powershell
.venv/Scripts/python.exe -B scripts/run_project_model.py check-protocol --process-evidence runs/a22-real-local-model-20261103/process-authorized-call
```

命令只读取该目录保存的 `wire-request.json`、`response-metadata.json`、`transport-receipt.json`、`response.bin` 与 `server/native-show-evidence.json`，核对原请求、响应的SHA与原收据绑定，输出工具/思考能力兼容性及原响应诊断。它不启动Ollama、不调用chat、不读取或校验权重、不改变项目及预算，也不消费响应或重发原请求。缺失或不一致的原件应保留为核对失败，不能用诊断命令补造原证据。

退出码2不一定表示检查未完成：应同时看JSON中的 `inspection_completed` 与 `ok`。`inspection_completed=true, ok=false` 表示原件核对和诊断已完成，但协议兼容性或原响应没有通过，不能当作成功提案或可重试授权。

实际 `request` 在 `/api/show` 返回后、请求worker启动前检查工具能力与 `thinking.values`。固定请求要求 `think:false`，而元数据只支持 `[true]` 时，以 `MODEL_PROTOCOL_INCOMPATIBLE` 拒绝。能够核实尚未派发的预检失败保留原prepared记录与预留，不能自动重发；诊断旧A22证据不会将已经消耗的1/1额度退回prepared或创造新额度。

### A22原响应能说明什么

原 `process-authorized-call` 的请求保留了 `think:false`、system中的 `/no_think` 和工具参数中的 `choice.oneOf`。响应为HTTP200、3,686字节，`done_reason=length`、`eval_count=768`，只有assistant正文，没有原生 `tool_calls`，正文也没有 `<tool_call>`。原响应SHA为 `74f73bcafba6d988a3c3a3cf19859f1bdb67a4c4c2ee9d026ef570078cbdda8f`；不把这段正文补解析成合法提案，原invalid结果和1/1已用状态保留。

保存的show元数据声明 `thinking={default:true,values:[true]}`，其固定Go模板末尾无条件写入 `<think>`；原服务器日志标识模型为 `Qwen3 4B Thinking 2507`。这与要求关闭思考的请求存在可由元数据确认的兼容性问题，但尚未证明它是本次未生成工具调用的唯一原因。模型正文声称 `choice` 为 `{}` 也不能证明Ollama丢失了 `oneOf/const`；本轮不据此改变请求builder或schema。768 token上限截断是已观测结果，增加上限能否成功并无证据，也不构成重试授权。

2026-11-03实际执行上述离线命令，结果为 `inspection_completed=true, ok=false`、退出2：兼容性原因 `THINK_SETTING_UNSUPPORTED`，原响应标记 `OUTPUT_LIMIT_REACHED` 与 `NATIVE_TOOL_CALL_ABSENT`，提案验证仍为 `INVALID_MODEL_RESPONSE`。保存元数据的核对不代表重新验证了当前runtime或完整渲染prompt。输出见 [inspection.stdout.json](../runs/a24-model-protocol-20261103/inspection.stdout.json) 与 [validation.json](../runs/a24-model-protocol-20261103/validation.json)。

上述诊断命令零模型请求、零模型进程启动、零网络请求、未读权重或改变预算。原钢材项目仍为state v19、snapshot `bbb11d57e67d8ee0810b8801a26a8dab42621b7fe1f1edbc4f003dde9bee85fe`；原模型结果invalid、累计1/1已用、预留0保持。共16份文件（含相关原证据、两份项目库与用户脏文件）逐字节不变。

## 实现入口

- [project_local_model.py](../src/autoresearch/project_local_model.py)：现成固定原件身份、禁下载本地进程、工具协议预检、单次原字节响应及收据。
- [run_project_model.py](../scripts/run_project_model.py)：`check / check-protocol / authorize / prepare / request / status / consume`，不隐式串联后续动作；`check`核本地原件身份，`check-protocol`只核已保存的进程证据，两者不等同于成功推理。
- `project_model_protocol.py`：纯值请求schema与严格原生tool-call解析；不接JSON正文后备或任意工具参数。
- `project_model_proposal.py`：同项目模型预留、sending/received/unknown、原件保存和显式离线消费。

## Limitations

实际本地传输、拒绝和终结已验证；合法模型提案→原控制器的真实链路尚未通过。本次不能证明模型能稳定遵守工具协议、选择更好、科学解释正确或真实用户获益。`PermissionError`未复现且原始栈未保存，根因仍未知；已为后续预检保存原始异常，未据猜测改动进程机制。

必需的前端门禁首跑由现有pnpm自动补取4个既有依赖包，整轮不能记为零外网。没有新增依赖声明或改动原package-lock；最终format/lint/typecheck/build以禁自动安装、offline参数通过。模型进程全程仅loopback，未增加付费额度。历史现金unknown及5元上限、独立价值评价与AgentArts暂停边界保留。

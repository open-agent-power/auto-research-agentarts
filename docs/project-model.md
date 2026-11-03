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

## 实现入口

- [project_local_model.py](../src/autoresearch/project_local_model.py)：现成固定原件身份、禁下载本地进程、单次原字节响应及收据。
- [run_project_model.py](../scripts/run_project_model.py)：`check / authorize / prepare / request / status / consume`，不隐式串联后续动作。
- `project_model_protocol.py`：纯值请求schema与严格原生tool-call解析；不接JSON正文后备或任意工具参数。
- `project_model_proposal.py`：同项目模型预留、sending/received/unknown、原件保存和显式离线消费。

## Limitations

实际本地传输、拒绝和终结已验证；合法模型提案→原控制器的真实链路尚未通过。本次不能证明模型能稳定遵守工具协议、选择更好、科学解释正确或真实用户获益。`PermissionError`未复现且原始栈未保存，根因仍未知；已为后续预检保存原始异常，未据猜测改动进程机制。

必需的前端门禁首跑由现有pnpm自动补取4个既有依赖包，整轮不能记为零外网。没有新增依赖声明或改动原package-lock；最终format/lint/typecheck/build以禁自动安装、offline参数通过。模型进程全程仅loopback，未增加付费额度。历史现金unknown及5元上限、独立价值评价与AgentArts暂停边界保留。

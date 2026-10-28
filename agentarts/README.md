# AgentArts Runtime 接入

已实现官方 SDK 0.1.8 的 HTTP 入口，保留现有研究协议。真实本地 HTTP、服务进程重启、幂等和模型参数产物已验证；云端镜像、认证、存储和平台 Trace 尚待验证。

## 启动与复用

```powershell
.venv/Scripts/python.exe -m pip install -r agentarts/requirements-runtime.lock
.venv/Scripts/python.exe -m pip install --no-deps -e .
$env:AUTORESEARCH_WORKSPACE = (Join-Path (Get-Location) 'runs/runtime-state')
.venv/Scripts/python.exe -m autoresearch.runtime
```

默认只监听 `127.0.0.1:8080`；`AGENT_RUN_PORT` 可覆盖端口。工作根目录必须由操作者提供绝对路径，请求无法覆盖它。`GET /ping` 为 SDK 健康检查，`POST /invocations` 接受[请求示例](../examples/create-campaign.json)。调用需带稳定的 `x-hw-agentarts-session-id`；同一次研究及重试使用相同会话，业务 `request_id` 保持稳定。`X-Request-Id` 只是传输关联标识，不能替代业务幂等键或平台 Trace。

协议允许 `create_campaign`、`campaign_status`、`run_trial`、`pause_campaign`、`resume_campaign`、`finalize_campaign`，以及 `observe_campaign`、`submit_proposal`、`research_report`。外部Agent策略必须先观察再提交结构化提案，不能通过 `run_trial` 跳过校验；详情见[研究程序](../examples/research-program.md)。数据只接受固定ID白名单。请求不得包含任意代码、命令、数据路径、评价器或分数；中断核对仍是操作者 CLI 命令，不暴露为 HTTP action。请求体限制 64KiB、64 层 JSON，拒绝非有限数。WebSocket 未开放。会话目录使用 SHA-256 命名，日志仅记录允许的标识、状态和响应摘要，不记录请求头、goal 或模型凭据。

**会话标识仅用于命名空间，不构成身份认证。**本实现面向单一操作者工程验证，未实现多用户授权。容器绑定 `0.0.0.0` 时，必须由部署环境实施并实测入站认证和网络限制，不得直接暴露到公网。

## 可复现的本地 HTTP 验证

```powershell
.venv/Scripts/python.exe agentarts/run_local_probe.py --workspace runs/my-http-probe
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

探针创建两次独立服务进程，依次执行基准、同请求重试、暂停、进程退出、恢复、改进候选、差候选拒绝和终测。输出 `report.json`、实际模型文件与本地服务日志；会核对参数文件 SHA-256。已有输出目录拒绝覆盖。探针只访问回环地址，结束时关闭自己启动的服务，不调用模型或云平台。

响应中的 `transport` 提供 SDK 适配器和关联标识；`platform_trace_verified=false`。核心结果保留 `platform_connected=false`；科学状态由固定数据描述给出，为 `engineering_only` 或 `benchmark_only`。这些标记不能由部署环境变量自行提升。

## 部署包

```powershell
.venv/Scripts/python.exe scripts/build_runtime_bundle.py
```

输出 `.agent/artifacts/runtime-context.zip`，只含允许的源码、项目元数据、Dockerfile、依赖锁、固定公开钢材gzip及署名文件，以及SHA-256清单。排除其他数据、凭据、参考库和虚拟环境。相同输入的 ZIP 字节可重现。解压到独立目录后，以该目录为构建上下文：

```powershell
docker buildx build --platform linux/arm64 --load -t autoresearch-runtime:local .
```

镜像使用 Python 3.12 和非 root 用户 10001，入口读取 `AGENT_RUN_PORT`。依赖锁包含 Windows 条件的 pywin32 和 Linux 条件的 uvloop；跨平台 wheel 可下载不等于镜像已运行。实际镜像构建、ARM64 训练、镜像 digest、SWR 发布均须另取证。不要把整个产品目录作为未经筛选的构建上下文。

## 上云前的明确条件

1. 确认当前套餐剩余 CU、CPU/内存规格、会话存续费用和关联服务费用。免费 CU 用尽后可能自动按需计费；账户余额和告警阈值都不等于费用硬上限。
2. 配置并验证受控入站身份。SDK 提取 context 不会替代云端 IAM/OAuth/API Key 验证；创建新持久凭据须单独确认。
3. 选择真实持久存储。沙箱释放会丢本地 SQLite 和模型；OBS write-back 不能直接当事务数据库。会话存储或 SFS 需实测会话过期、进程/沙箱重启、SQLite 锁与模型哈希。挂载权限应允许容器用户 10001 写入。
4. 记录真实 Runtime、版本、镜像 digest、平台请求与业务请求关联，再执行两轮训练、重试和恢复。只有真实上报并可查询的 trace_id/span_id 才称平台 Trace。

Runtime HTTP 与 Managed Agents 的工具配置是两个独立接入点，目前未证明此入口能自动注册成 Managed Agent 工具。长训练任务的异步提交/查询执行器与科研数据适配仍需后续实现。

官方依据：[SDK](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_041.html)、[运行时与存储](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_031.html)、[计费项](https://support.huaweicloud.com/price-agentarts/agentarts_08_0003.html)、[Managed Agents](https://support.huaweicloud.com/managedagents-agentarts/agentarts_13_0001.html)。

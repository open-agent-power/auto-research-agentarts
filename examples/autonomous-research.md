# 产品持续研究循环

产品控制器读取固定观察，调用非流式模型接口，核对提案再执行真实实验；不依赖开发聊天逐轮发送提案。目前已实现调用、记账与恢复机制，真实LLM和AgentArts云端尚未验证。用户暂缓平台接入期间，不启动live调用。

## 本轮可以直接复算的工程路径

在已有项目虚拟环境运行，选择一个新的空工作目录：

```powershell
.venv/Scripts/python.exe scripts/run_research_probe.py --workspace runs/my-research-probe
```

仅访问127.0.0.1；脚本端点明确标为`fixture`，根据实际训练反馈生成测试响应。它不是语言模型，不能用于验证研究策略质量。探针跨4个CLI进程执行3次真实训练，检查恢复、模型文件哈希、停止后不再派工，并输出请求记录和`summary.json`。它不执行最终测试，不重开既有锁定任务，结束后关闭自己启动的测试端点。

## 将来恢复真实模型接入时

1. 在正常浏览器中登录华为云中国站，选择已开通模型；从API调用说明取得完整endpoint和精确model字段值，不用模型的展示名称代替。
2. 核对该模型最大输入Token数、所有可能长度／时段档位的保守输入和输出单价，以及总输出上限参数。确认API Key的模型权限和费用范围；不在聊天、配置JSON或Git中填写密钥。
3. 将[配置样例](model-config.example.json)复制到忽略的`.agent/model-config.json`，替换占位信息；核对来源与日期，确认价格及上限后再将两个确认项设为true。示例故意不可直接发起调用。
4. 项目默认live禁用。接入重新获准后，才可使用下述本机启动脚本；密钥在隐藏提示中输入，仅临时传给子进程，退出后恢复原环境，不写文件或setx。

```powershell
./scripts/start_research.ps1 -Config .agent/model-config.json -Workspace runs/live-project -Goal "待检验的研究问题" -AllowLive

# 正常暂停后的另一次进程；保持原配置、工作目录和累计预算。
./scripts/start_research.ps1 -Config .agent/model-config.json -Workspace runs/live-project -Resume -AllowLive
```

脚本只在本机需要时使用；本轮没有要求重新处理登录。普通HTTP完整地址示例为`https://api.modelarts-maas.com/openai/v1/chat/completions`；SDK的base_url通常少末尾路径。客户端直接使用操作者给出的完整endpoint，不自动拼路径、不重定向、不自动重试，并采用直接连接，不继承环境代理。

## 配置和预算的真实含义

`connection`只含endpoint、model、密钥环境变量名称、输出限制、请求字节限制、超时和显式测试开关。密钥值只从指定环境变量读取，不写入数据库、请求正文、导出或异常。配置及累计上限在项目内冻结，不能通过重启或改请求重置；修改研究范围或预算须另作明确取舍。

`pricing.input_tokens_ceiling`必须是已核实的模型最大可能输入Token上界；预留使用这一上界，不把字符数或UTF8字节数当供应商精确Token数。请求字节限制只控制输入大小。单价覆盖可能档位并忽略不确定的缓存优惠；检查日期超过7天停止新请求，等待核对。

MaaS当前OpenAI兼容接口中，`max_completion_tokens`控制回答加思维链总量；`max_tokens`只控制回答。默认使用前者，二者互斥。仅已确认非思考或具有其他可信总量限制的服务才能选择后者。usage中的reasoning_tokens是completion_tokens详情，不重复相加计费。

发送前，以最大输入上界、总输出上限和保守单价预留；收到有效usage后按同一保守单价估算，超时、传输失败、缺失usage或未知结果保留全预留。实际usage越界则记录而不裁剪，并停止等待复核。账本是本工作目录的配置预留与用量估算，不是云端真实账单，也不能替代AgentArts关联服务的总费用约束。

## 中断与错误

- 正常`--steps 1`后暂停；`--resume`继续，已经完成的请求和实验不重复运行。
- `--steps 0`只应用已保存的响应，不发新请求；恢复这段工作不需要重新取得模型密钥。
- `sending`表示请求结果未知或仍在执行。先核实worker已停止，再执行下面的操作者命令；请求槽位及预留额不退还，不自动补发原请求。
- HTTP失败进入`needs_review`；非法模型决定计入模型次数，但不计训练次数，后续纠正仍受总请求与预算限制。
- 模型stop或预算结束后，不因迟到pause/resume复活。需要新的研究阶段时另行决定，不能借新目录规避本轮预算。

```powershell
.venv/Scripts/python.exe -m autoresearch research-status --workspace runs/live-project
.venv/Scripts/python.exe -m autoresearch research-reconcile --workspace runs/live-project --call-id CALL_ID --confirm-worker-stopped
```

实验自身仍为running时，沿用README中的`reconcile --campaign-id ... --trial-id ... --confirm-worker-stopped`。这些核对命令不负责杀进程，也不暴露为模型可调用工具。

## 论文证据与限制

每轮保存观察指纹、提案、数据与评价版本、实际结果、模型文件哈希、决定及模型响应来源；`exports/research-evidence.json`按研究问题、方法、来源、假设与结果、局限和后续状态组织。`research-progress.md`供人阅读。完整论文式PDF、研究对话页面、真实跨域主案例、LLM策略效果和基础模型权重训练均另待交付或评估。

官方语义依据：[MaaS OpenAI兼容接口](https://support.huaweicloud.com/model-call-maas/model-call-021.html)、[文本模型计费](https://support.huaweicloud.com/price-maas/price-maas-0002.html)、[计费周期](https://support.huaweicloud.com/price-maas/price-maas-0012.html)。本轮只核对公开文档，未使用账号实际权益或真实付费调用。

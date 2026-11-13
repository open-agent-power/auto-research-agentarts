# Reference Project Catalog

参考项目不是要求全部引入。每项必须先固定 commit、许可证、依赖、运行要求和核心源码，再决定复用、适配、只借鉴或拒绝。

| 项目 | 地址 | 重点研究 | 目标机制 | 处理方式 |
|---|---|---|---|---|
| Karpathy autoresearch | https://github.com/karpathy/autoresearch | program.md、train.py、prepare.py | 固定预算实验、指标、keep/discard、最小修改面 | 机制借鉴；不要求 GPU 训练代码 |
| Sakana AI Scientist | https://github.com/SakanaAI/AI-Scientist | idea generation、templates、experiment runner、review、containerization | 从创意到实验和报告、研究模板 | 隔离运行；重点研究模板和执行链 |
| Agent Laboratory / AgentRxiv | https://github.com/SamuelSchmidgall/AgentLaboratory | agent roles、workflow、copilot、AgentRxiv | 文献/实验/报告流程和研究积累 | 机制借鉴；评估依赖和维护状态 |
| AIDE² | 以论文为准，核验正式论文/代码链接 | outer loop、agent modification、held-out evaluation | RSI 外层改进 | 方法参考；代码可用性需核实 |
| Prime Agent | https://github.com/PrimeIntellect-ai/prime | Harness、RLM、Skills/Prompt/Memory/Subagents | 可变 Harness 和持续上下文 | 机制参考；固定 commit 后评估 |
| OpenHands | https://github.com/All-Hands-AI/OpenHands | SDK、Agent Server、Docker Workspace、Runtime | 可复用 Coding Worker | 优先 PoC，不作为产品核心 |
| OpenHands Benchmarks | https://github.com/All-Hands-AI/benchmarks | task runner、environment、evaluator | 复用评测基础设施 | 核验 SDK 版本兼容 |
| SWE-bench | https://github.com/SWE-bench/SWE-bench | task schema、Docker env、test harness | 真实代码问题评测 | 选择小子集，记录任务版本 |
| SWE-bench Pro | https://scale.com/leaderboard/swe_bench_pro | 长程软件工程任务 | 更复杂软件任务参照 | 核验数据许可、可下载性、成本 |
| OpenTelemetry Demo | https://github.com/open-telemetry/opentelemetry-demo | 微服务、日志、指标、Trace | IT 运维模拟环境 | 可选扩展，不作为主研究任务 |
| BEIR | https://github.com/beir-cellar/beir | retrieval evaluation | RAG 检索指标和数据 | 复用 |
| Ragas | https://github.com/explodinggradients/ragas | RAG evaluation | 检索/生成评价 | 复用并人工抽查 LLM judge |
| Optuna | https://github.com/optuna/optuna | sampler/study/pruner | 参数搜索 | 复用，不把参数优化等同算法发现 |
| Nevergrad | https://github.com/facebookresearch/nevergrad | optimizers | 黑盒优化基线 | 复用 |
| DEAP | https://github.com/DEAP/deap | evolutionary algorithms | 演化搜索基线 | 复用 |

## 核心原则
- 不把第三方项目整仓复制进生产代码。
- 不把项目列入清单等同于已运行。
- 只在明确解决现有缺口时引入依赖。
- 上游许可证、数据许可证和运行环境必须单独核验。

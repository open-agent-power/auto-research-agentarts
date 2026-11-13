# Clone and Audit Guide

## 目录建议
在主仓库工作区的 ignored `references/upstream/` 或独立 sibling 目录克隆，不提交未经审查的第三方源码。

## 拉取流程
1. `git clone`；
2. 记录默认分支和当前 HEAD；
3. 检查 LICENSE、NOTICE、依赖文件、安装脚本；
4. 固定 commit SHA；
5. 阅读核心执行路径；
6. 在隔离环境做最小 smoke test；
7. 形成 reuse decision。

## 必须输出的文件
- `references/manifest.json`：repo、URL、commit、license、retrieved_at、local_path；
- 每个项目一份 `architecture-notes.md`；
- `reuse-matrix.md`；
- `license-security-audit.md`；
- `smoke-test-results.md`。

## 每个项目的源码阅读清单

### Karpathy autoresearch
- `program.md`：Agent 指令和研究组织；
- `train.py`：可修改实验对象；
- `prepare.py`：固定环境与评价；
- 结果记录：如何判断保留/丢弃；
- 安全：Agent 代码执行权限。

### Sakana AI Scientist
- Idea Generation；
- Literature Search；
- Experiment Template；
- Experiment Runner；
- Paper/Review；
- Docker/containerization；
- 模板扩展协议和依赖成本。

### Agent Laboratory
- agent role definitions；
- literature/experimentation/report stages；
- Copilot mode；
- AgentRxiv research artifact upload/retrieval；
- checkpoint / resume；
- model provider abstraction。

### AIDE²
- 论文中的 outer-loop architecture；
- candidate modification mechanism；
- evaluation tasks and held-out tasks；
- reported iterations and limitations；
- code availability and reproducibility status。

### Prime Agent
- Harness mutability；
- Skills/Prompt/Memory/Subagent management；
- RLM/REPL interface；
- persistence and safety;
- license and runtime requirements。

### OpenHands
- SDK and Agent Server;
- Docker Workspace;
- runtime configuration;
- artifact transfer;
- resource limits;
- benchmark adapter compatibility。

## 输出决策
对每个机制选一种：
- `reuse_as_dependency`
- `wrap_with_adapter`
- `copy_small_pattern_with_license_review`
- `inspiration_only`
- `reject`

并写明：解决的缺口、预期收益、集成成本、风险、验证任务、回滚方案。

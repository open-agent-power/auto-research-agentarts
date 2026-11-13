# 云端开发上下文

## 目标及授权

用户要求解压执行包，使用 dev-system 严格按计划持续推进；随后明确授权使用 GitHub CLI，并向 `open-agent-power/auto-research-agentarts` 推送。独立分支开发，不强推或覆盖原分支。

执行源：[原始任务包](../execution/pack-v2/README.md)、[产品宪章](../execution/pack-v2/00-charter/PRODUCT_CHARTER.md)、[阶段门槛](../execution/pack-v2/06-roadmap/PHASE_DELIVERABLES_AND_GATES.md)。原上传包及 SHA256SUMS 已核验，[来源记录](../execution/pack-provenance.json) 保留包身份。

## 已确认边界

- 基线为 `5d497c8ae22100953f66c3c5b54746ca87e09f01`。源码克隆不含旧 runs、私人计划、原账本或数据附件。不能根据历史说明认领本次实跑。
- 产品是持续自主研究工作台，复用 Python/SQLite、现有 ResearchProject/ProjectController、TypeScript/X6。先审计，不直接重写。
- G0 未通过前不启动依赖阶段。只读研究、数据核验、评价设计和审计可以继续。
- 后续用户已在具体方案后批准有限可信本地先行；唯一例外范围见 `docs/execution/g1-local/authorization.json`，本地案例已完成且20fit用满。原G0与G2+仍未解锁，不能复制旧预算作为新额度。
- 用户偏好：每轮大任务完成后说明工作/验证/下一步，随后在已授权范围内继续；仅实质决策或外部条件阻塞时询问。GitHub已授权，可验证后直接合并/推送main，不设例行草稿PR审批。
- 当前宿主 agent 可执行调研与审查；产品 HostModelSelection 的 claude_cli/delegated 能力另行核验。检测到 Codex CLI 已登录不代表产品已接线，也不代表外部 API 预算。
- 没有配置模型 API 凭据；未创建密钥或采购服务。未知模型成本保持 unknown。
- 保留原请求身份、预算、工件与失败；不通过新 ID/新目录重置历史预算。RSI 不得修改独立评价器、隐藏数据、晋级控制器或安全限制。

## 接续

先读 [current](current.md)，再按任务板进入当前 Gate。运行资源问题以实际容器内部限制为准，不以 docker inspect 配置宣称生效。具体审计见 [G0](../execution/g0/)。

## 后续环境决定

用户已明确接受无法补Worker并要求继续推荐计划，当前范围以[local-continuation.json](../execution/local-continuation.json)为准。可开展有界可信本地的新课题/分析/CPU基准，单独预登记预算；原G0隔离事实保持，旧Concrete20fit不可重置。无需每个阶段重复询问同一环境限制，实际费用或新的不可逆外部动作另按授权处理。

Sprint003已得到G2无收益对照、G3两目标闭环及负控、G5两类CPU对照、G6离线打包证据；详见execution/SPRINT-003.md。继续G4-L有限纯helper代码实验，不把用户接受隔离限制解释为sealed通过或模型API/采购授权。

用户要求安排云端周期检查（3h或6h），root选择3h并已创建/启用、readback核同一继承cloud/workspace。平台调度与持续24h模型进程不同，首次执行待验；lease协调本轮与定时轮，不改研究预算。参考库8个固定checkout再次核验全clean/匹配manifest。

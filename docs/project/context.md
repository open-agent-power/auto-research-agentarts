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

Sprint003已得到G2无收益对照、G3两目标闭环及负控、G5两类CPU对照、G6离线打包证据；Sprint004完成G4-L有限helper候选及源码集成。最新G5原生两领域从`8e8a206`各执行2tools/0fit/API、3plans waiting，独立9910检查；后置UI`e638b5f`只改只读projection与标签，科研codeidentity保持。新G6 clean1.8产品安装/保存接续继续；以[current](current.md)和对应原始freeze为准。不把用户接受隔离限制解释为sealed通过或模型API/采购授权。

用户要求安排云端周期检查（3h或6h），root选择3h并已创建/启用、readback核同一继承cloud/workspace。平台调度与持续24h模型进程不同，首次执行待验；lease协调本轮与定时轮，不改研究预算。参考库8个固定checkout再次核验全clean/匹配manifest。

继承环境恢复的Sprint006已实际普通push成功并回读main=`477aae3`，上轮token失效不再是当前阻塞；原失败及冻结提交身份保持，不需重复索要登录/Worker授权。平台已有11:43UTC run-time marker，但run/result详情未返回，完成状态不推断。本轮聚焦archive-only保存接续、2991保存参数预测算术（先固定协议再算）、UCI原下载独立补充包；0fit/0model，不重写已验收77MB ZIP或历史课题。

Sprint006实测闭合：新target从归档8原ID恢复，01依赖平台探测失败保留，02仅真实uname1次后strict subprocess/network0；177/187/930物料绑定、1510实际独审过。固定参数算术2991行maxdiff1.42e-14，33282输出断言，负例689保留；补充UCI209918B小包37成员。494原件/50历史fit不变。下一轮做两CPU领域实验页摘要与损失展示，沿既定DESIGN/保存观察，0新研究，别重复已闭合算术或重发driver。


Sprint007已完成两CPU领域保存结果阅读，源码7633792，原state13/3plans/2tools与50历史fit保持，无新增研究/工程fit或产品模型调用。最终桌面+手机五页、38截图、80GET、12下载/读取及末列文字范围实测通过，独立36+63语义/807最终检查。01/02/03视觉缺口与调度启动失败保留，04才完整通过。新只读18836/18837由独立固定checkout服务原manager，旧源码pin clean。下一步已有artifact不利query按需精确阅读，见current及cpu-results-ui.json；平台14:45UTC标记仍无run/result详情。

# Sprint 004 — bounded code improvement, native check and integration

本轮完成一条真实代码改进链：冻结原版、诊断、独立worktree改动、受限解释器评估、独立原生微函数确认、源码集成、工程回归与旧研究保护。每个阶段单独审批/记账，未回写原研究或把解释器速度当产品速度。

| 阶段 | 实际结果 |
|---|---|
| 固定计算能力门 | 29定点测试、28独立能力检查；只有限primitive标签运算，不向候选提供文件/网络/项目/预算操作 |
| 解释器单候选 | 600配对计时记录、40独立核验，三完整输入全部IDs/folds一致；结果只适用于解释器 |
| 独立原生确认 | 固定同两helper/三输入，新冻结与审批；2compile/6VM资格/636nativecalls，84独立结果检查；三数组全等 |
| 真实源码集成 | 原分组list.index循环改为首次出现字典映射，精确候选module `ec965e31…69711`，30独立集成检查 |
| 纯分组回归 | 8项通过，涵盖空/0字段/8字段/Unicode/2048行/随机差分/数组dtype/GroupKFold |
| 全量工程回归 | 1164项：1145通过、19跳过、0失败/错误，168.225秒；有真实工程fixture拟合，不称全套fits0 |
| 历史研究保护 | 三真实case292文件全SHA不变，state32/33/24，累计estimator20/20/10=50保持；无upgrade/refit/reset |
| 旧只读服务 | 18830已固定运行0ceb274源码，actions/models关闭；新main真实CODE_CHANGED拒旧case执行，pin页面仍可读 |

原生helper的中位耗时：Concrete2.195511→0.084443ms，节省约2.111ms；RealEstate0.613071→0.033010ms；Slump0.074247→0.008207ms。只是分组微函数的局部效率，排除行捕获/NumPy/模型/控制器/报告，不外推CV、科研质量或端到端收益。实现改变新版本代码身份，旧模型证据仍归其原生产源码/依赖。

[解释器结果](g4-local/results.md)、[原生结果与集成](g4-local/native-results.md)、[机器验收](g4-local/native-acceptance.json)、[原生独审](g4-local/native-independent-review.md)、[集成独审](g4-local/integration-review.md)给出原件、实际差异和恢复验证。CLI/动态Python不是公共任意执行接口；原G4的全系统/同UID安全隔离及持续多代RSI仍未证明。

G6也已从system-site smoke推进到[全新依赖环境](g6-local/clean-install.md)：基础/sources/reports从官方PyPI安装、pip check成功，复制项目只读HTTP及28页保存字典PDF渲染通过。clean使用scikit-learn1.9.1，研究冻结仍1.8.0；不同模式与版本明确分开。初次HTML期望断言失败保留，修正固定注入期望后的独立回执通过。最终源码wheel/三完整分组跨版本零拟合核对在下一交付步骤完成，不谎称此刻已跑。

下一步已按计划推进[G5原生检索合同](g5-local/native-integration-contract.md)：同一个ResearchProject/Controller/Workbench内做固定TF-IDF/BM25对照与保存失败诊断，两次本地行动，0fit/模型/API；不另写dataset控制器，保留已知Recall负结果。adapter实现正在进行，真实SciFact新case须在代码/协议/原件冻结和独审后执行。没有重复索要缺失Worker或新增付费服务。

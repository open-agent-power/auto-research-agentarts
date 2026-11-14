# Sprint038：自主研究优先，新参考已实际拉取并阅读

按用户新指示将主线优先转向自主研究，而非更多展示包装。现有4人团队复用职责，实际新增3个浅克隆到`/workspace/references/exploration/20261114/`；旧8参考及manifest不改。[精确版本、许可和原始证据](g5-local/autonomy-reference-exploration.json)。

| 项目 | 固定commit | 关注机制与边界 |
|---|---|---|
| [AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2) | 96bd51617cfdbb494a9fc283af00fe090edfae48 | 父子实验分支/候选选择；自有受限许可，仅借鉴思想。pickle与未证实生效的子阶段上限不能照搬 |
| [LLM-AutoSciLab](https://github.com/scientific-discovery/LLM-AutoSciLab) | 467fa184ba537d26b2228ee3f3a8c052d9bfca58 | 竞争假设/分歧选检查；根MIT不覆盖全部第三方。默认ground-truth反馈和损坏checkpoint回空/费用零记法不能沿用 |
| [POPPER](https://github.com/snap-stanford/POPPER) | 59611864e09dd15d7528e240ad87c7ddbb4a701c | 证伪条件、顺序检验与停止；缺完整独立许可正文，不复制代码；不把聚合实现当任意自适应数据的错误控制证明 |

全部读取的是原源码和许可，没有装依赖、运行上游、请求模型、复制受限代码、改变旧研究预算或sourcepin。源码入口/行号与逐文件SHA见原始审计。拉到云电脑及静态研究不等于runtime已集成或得到科研收益。

对照产品发现：LocalWorkbench已有delegated计划先行与显式采用，真正缺口是行动的HostModelBatch强制CLI，当前Linux不能使用；S035因此仍靠root手写多阶段编排且发生两次类型/字段错误。下一S039直接补原生delegated batch：产品持久准备唯一请求、等待外部原字节、原ID恢复、仅已完成行动才推进、可选反馈计划但不自动采纳，严格原global grant；不另造一套journal。

后续才加入版本化假设/反证与失败分支，使用原候选和真实观察驱动下一项检查；再按独立预协议检验是否减少无效实验、是否在未见任务上改善结论。当前原3委派/2工具试跑已耗尽，不能借此新ID重开；本轮无新增付费模型/API或采购。

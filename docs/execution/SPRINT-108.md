# S108：验证集召回不变但排序下降的损失幅度

## 事后协议，真实计算前固定

针对已曝光的 S065/S067，分别对原 validation 保存配对值计算候选减基线：选 Recall@20 差在 ±1e-12 内且 MRR@10 差 < -1e-12 的题；n≥5 才输出该格数量与 `-fsum(ΔMRR)/n` 四位小数，否则两个值抑制；四位 0.0000 可能仅为舍入。仅该格，其他格幅度、逐题文本/ID/排名/总和不发布。内部复核原 S075 全矩阵/两指标汇总、原 Project/producer/source/primary/SQL 与前后身份，任一不符整批停查。新协议不更改原S075/评估器/研究预算。

原 reader 会读取完整公开 dev/validation 文本、qrels、已存排名/指标和共享corpus（可能含final目标passage），Project status可能读取全部行动元数据及关联case；禁止读取 final query/qrels、final行动工件和private包。不新增ranking、score、fit、模型、研究行动或原账本写。Python级明确路径及工具守卫不是OS隔离，SQLite原生I/O和并发竞态未全面约束；四位聚合也不能保证匿名或不被背景信息推断。数据已曝光，此为事后算术，不是盲测、因果、显著性、跨任务泛化或模型自主收益。

## 发布前验证

作者及两位独立审查各18/18合成通过；冻结脚本 `scripts/audit_unchanged_recall_mrr_loss.py` SHA `910e5715a533483aca7066e92a85591e7a3c351ae265d1d1196479eab0d6f07e`，协议SHA `bef2c9e49cb2323be5d16918703beb09b09aac19271186e059554e5685da1e70`，测试SHA `4efa14705f6b6c76e0d0a7a34c0554527574af15cec23448468924c8e27a4147`。审查发现依赖尾检遗漏、输出目录符号链接与潜在pyc污染，均修复并合成验证；依赖尾检问题为静态发现，不能称修前动态复现。一次独审测试命令模块名误写、exit1并记录，改正后18/18。此提交之前未读取真实逐题或运行实际统计；脚本与协议先推送并核 canonical main/原producer身份，之后才可按原协议授权范围运行。

## 实际只读事后结果与独审

固定分析源码 `a4c2eb01e92526b73e2dee4e24f1ba7aa38d5867` 已先推送；随后在原producer pin上执行，exit 0，原始输出SHA `762d92f53422976fd6b0928f4a7f35d0572fc6803bfb11cb04315cc1176493f8`，与[公开聚合](g5-local/saved-unchanged-recall-mrr-loss-results.json)逐字一致。S065 validation 在 Recall@20 不变且 MRR@10 下降的16题中，MRR平均下降 **0.4026**；S067对应24题、平均下降 **0.3724**。这是所选负向子集的平均差，不是所有100/200题的总体变化，也不说明方法总体更差。

独审以 Decimal 对保存 float 操作数独立复算、核 S075 全矩阵/摘要及原 Project/source/action/SQL，结果一致；两项目完整状态各自在前后相同，各3/3工具、reserved0、原model/fit/evidence 0且无新派发。独审第一次只读复算输出被工具截断，第二次只读执行保存 `/tmp/s108-independent-result-y2O2Xf.json` SHA `cd5b7c0e61c976416019004e960519849bb90612e36cf8491003887af6b6c47d`，独立算法 `/tmp/s108-independent-g2SlOW.py` SHA `fc4f6439fec3039c6cca19bb430117f54b76f78ca6d850dd450e6dc7c4b5d8d5`；两次均无新研究行动。另一独审从发布提交的201源码/依赖blob重建manifest SHA `75d129a08f27096363cbccc996725e1e1c7e712bd093852753a81aed8b44fef0`一致并核输出白名单；未做逐题canary或匿名保证。读取范围仍按前述协议；费用和开发tokens unknown。

解释：这显示 Recall@20 数值不变时，部分问题的 MRR 仍可能下降较多；不能从这些条件筛选后的负例推断整体收益、显著性、因果或跨任务效果，也不能声称模型使用或采纳反馈。下一步考虑把该已保存的负向经验供新计划明确引用，验证何时应等待或避免重复损失，但不重开原项目额度。

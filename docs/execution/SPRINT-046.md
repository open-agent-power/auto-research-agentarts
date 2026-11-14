# S046：真实公开数据的固定阶段研究

源码与协议42100fa79d6f4a6d96b924ba36fba2f769d2c468先发布；受独审的驱动随后以4a159a9e5a0142c3a69a091aaf1e9a9c110b7be0发布并核实际远端后，才于北京时间2026-11-15 01:31:42—01:31:49首次下载、派生、执行。不是旧盘研究恢复。

原始官方SQuAD v1.1 dev 4,854,279字节，SHA256 95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9。原件和本地封装ZIP/许可/选择映射保留在唯一研究目录private；无原始数据入Git。2,067段落；10,570原问题去重为10,530；按事前hash顺序固定开发/验证/最终各100。共享corpus、单正例段落映射，不是QA正确率或盲测。

## 真实结果和恢复

开发Recall@20：BM25/TFIDF均0.99。验证：BM250.96，TFIDF0.95，候选差-0.01（1负/99平/0正）。冻结规则保留BM25。最终100问BM25 Recall@20=0.97、Recall@10=0.93、MRR@10=0.8332896825396826；选中方法即基线，因此差0，实际只排名/评分100次各一次。没有计算最终TFIDF后另选，不能宣称候选收益。

原生项目project-7858ce02138a48e3bdeac39c26f7be06；固定请求s046-primary/audit/final和原child全部completed；恰3/3工具、0来源行动/模型/拟合，原预算不重置。01:32:20—01:32:23按同pin/同ID --resume成功，全部36文件字节与预算不变，输出一致，新增行动0。

唯一workspace：`/workspace/development-continuation-20261114/source-pins/4a159a9/runs/s046-squad-paragraph-retrieval-v1`。禁止在main路径另建同名研究或用新source升级原项目。精确commit/输入/行动SHA/原命令/预算/恢复见[结果索引](g5-local/squad-paragraph-results.json)。独立证据审查通过：逐个重hash全部36文件及11 prepared原件；私有原件只以二进制核SHA，不解码final文本/标签。验证/final摘要由已保存数值复核，不重跑排名/评分；未独立重派生10570/10530采样计数，范围见结果索引。

## 继续推进

保持root原lease并继续S047：把固定阶段接续接入原Workbench/Controller，减少外层脚本对审计→策略冻结→final→报告的手动串联。复用engineering/workbench_continuation/独审成员，不新建团队。不升级S046源pin或复用其已耗尽额度。

边界：原盘未恢复；相同用户的程序性holdout非OS/盲测；无模型研究transport或长期/跨任务自主收益证据；原件目前仅当前云盘，GitHub附件401未解决。开发token/金额unknown。

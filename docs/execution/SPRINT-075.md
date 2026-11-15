# S075 — 已保存验证指标的事后联合分布协议

新增 [固定协议](g5-local/saved-joint-validation-protocol-v1.json) 与 `scripts/audit_saved_joint_validation.py`，为 S065 HotpotQA 和 S067 BoolQ 已保存的 validation 结果分别描述每题 Recall@20 与 MRR@10 的 TF-IDF 减 BM25 差值。两个指标分别按 `1e-12` 划分负、零、正，形成各自 3×3 计数及边际；完整配对的 `math.fsum` 均值和胜负平必须与原保存 summary 相符，不符即停止。100 与 200 题分别报告，不合并样本，不做显著性检验、p 值或置信区间。输出只允许聚合及原件身份，不携逐题文本、查询 ID/哈希、排名或 final 结果。

这两个公开数据集及既有研究结果已在协议前曝光；该补充核算是事后描述，不是盲测、预注册确认、新课题、模型采纳或经验迁移收益。原 S065/S067 项目、行动和各自已用满的 3/3 工具预算保持不变。本 Sprint **没有读取两项研究的真实逐题值，也没有执行真实联合分析**。

脚本默认只报告草案状态。显式执行要求先完成本协议与脚本的独立审查和发布，再指定与当前干净源码一致的完整发布 commit；实际核 canonical GitHub origin 与 main 祖先关系，并在读取项目之前分别核两个原 producer pin 的 HEAD、origin 和源码清洁状态。S067 原 producer core 为 `ca09803b71c2bfd82a3356d428f4f05b8a311da433ea1109019e556b53d7c572`；初稿误用 S069 capture reader 的 `4ee10…`，已依据原 S067 summary 修正。reader commit/core 与 producer 身份分开记录，不迁移原 pin。

每个案例使用一次原 `_checked_primary`，核 Project、source、原 primary、SQLite 和完整 dev/validation 保存记录；计算后重核 source、primary 工件、SQL、reader 源身份和 Project snapshot。代码守卫阻止指定 private/holdout、Host、非 primary 工件及现有索引、排序、评分、部分 fit、模型派发、Project 写入和恢复入口；这是可信本地程序检查，不是 OS 隔离，也不证明对所有可能调用均有哨兵。Project SQLite 中可能含 final 阶段元数据；没有读取 final 工件或 private 包，也不做会读取 private 字节的全目录哈希。

结果写入限定新的验证目录和新文件。脚本先在同目录唯一临时文件写完整 JSON、flush 和 fsync，再以不覆盖已有目标的 hard link 原子发布并 fsync 目录；写入或文件 fsync 失败不会留下部分最终文件。若 link 成功后目录 fsync 失败，完整目标可能已出现但操作报错，落盘持久性未知，应保留检查，不覆盖或视作已确认成功；进程强杀也不保证清理临时文件。这些是程序语义和合成验证，不是断电持久性证明。

固定清单 `runs/s075-verification/source-freeze.json` SHA-256 `d4ca88f1d753444274237fe81541416e2977cf2ddcff2cabf93c744642fa5fa8`，含 192 个产品 Python 源及协议、脚本、专项测试，共 195 项；reader Project core `e4424e6e8b1d0927f1d6dd71d412767b1210a29e4dc84f91`。协议 SHA `575f57346c8c0bd3c4e4f8b6c95a71eb3c70eb50bc8cfc4a467d577b414a925b`，脚本 SHA `ad8091d1b1549a2c6ec02ca21e7680f5b4ec1e784d4d53ce11ae215b22ae14b2`，测试 SHA `79ae4edd694ba77e225bf71136352f731e30c53e6d8c40cb65ff77d105b812ab`。

作者纯合成回归 5/5 通过（`runs/s075-verification/final-synthetic-regression.log`，SHA `e18b439b5db289daeb4b09115dd38d040b411061ac6f6e9fae5c8edeeb23d145`），包括阈值边界、缺失/重复、类型及 summary 错误、producer 身份拒绝、读取中身份漂移和写入失败/目标已存在。独审另以合成输入验证 3×3 九格、SQL 行失败、原 producer 身份和目录 fsync 失败留下完整但未确认的目标，4/4 通过（`runs/s075-review/independent-probe.log`，SHA `82ae1665759c33cf102ae04971f0cb443a724134e8dd19e46e5aee4ff48d4ab4`），并独立重跑作者 5/5。独审发现的 producer 身份、读取窗口和原子发布问题已修，前版和日志保留。测试不产生研究项目、工具行动、模型或 fit；本地工程计算及任何未来费用不据此假称为零。

# S056：读取真实 staged 失败查询及原排名

S054覆盖改善伴随排序亏损，S055保存经验后，实际只读确认旧reader与saved_materials均拒staged family。新增独立dev/validation DTO与原GET显式分派，复用共享primary/source/SQL/坐标/grade/完整覆盖校验，原train/test响应不变；不新建工具、runtime或预算，不把test/final读入开发上下文。

最终root75相关、独立5项通过；独审只用已保存S051合成公共SQLite/source/primary，不新rank/score。SQL指纹、重封错grade、snapshot漂移及坏split/分页拒绝，大小门以mock阈值检验拒绝路径，不冒称真实超1MiB样本。191源码冻结SHA `8d4165764c7820e7f6e2fe2896d57f37dbc2d2c1b43609d11997d05151e095b0`，新core `2b0b552c54f9a7a2c577b405746d61743396090d8c0e24e0e851882694182fa7`。

真实S054两GET成功读取原纽约周收入验证查询及正例原排名：BM25第1、TF-IDF第2，MRR1→.5。原producer core300421与reader实现身份分列；原47文件及完整Project状态/预算3/3不变。源执行仍只在f23de20 pin，不用新core迁移原研究。读取有private路径/执行哨兵，前后完整性hash在guard外读过private原字节，未解析；不声称整个验证零private I/O。

[API合同](../staged-retrieval-reader.md)、[精确验证](g5-local/staged-reader-verification.json)，本轮原件在ignored `runs/s056-verification/` 与 `runs/s056-review/`。初始独审相对路径as_uri定位失败日志保留，不冒称产品故障。新研究行动/模型/fit0，工程总dispatch未单独计量，开发token/费用unknown。

Host/plan/saved_materials和前端未改；下一片应对新staged材料做显式有界接线，不能静默改变旧材料合同或以可读HTTP假称模型已看到原文。

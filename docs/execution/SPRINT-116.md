# S116：staged反馈真实进程中断与竞争

固定源码HEAD `6f4abfe059207c75b042fd09b0abbbd5c805a696`，在各自新建合成Project下事先完成一次S111/S112 primary，分别验证S115 wait与audit的十个manager/parent/child提交窗口，使用真实SIGSTOP(19)、SIGKILL(-9)、SQLite独立连接和不同PID原ID恢复。作者与独立审查十窗均通过；另独立两项旧入口真实进程竞争、四种 met/not_met × wait/audit 非对称分支、原manager intent/终态旧入口10项与16条回执/claim重验通过。

各合成案例先前primary已用1次工具；前7项及wait终态 used/reserved/dispatch=1/0/1，audit child已提交未运行为1/1/2，audit完成及parent终态为2/0/2。audit读取保存结果/共享来源，没有新排名、评分、模型、fit或final。unknown/损坏停查；wait终态认证后可补manager，audit需parent+child completed才收敛。旧Controller抢先时strict不认领/不重派；wait派生ID被旧入口独立占用后原wait停查，不等于全局排他。

作者 `runs/s116-verification/evidence-manifest.json` SHA `76cf350c97c7508807e393aab4ec627726642575d6e721872289698ab527fbae`（354项），四份rollback journal保留；独审 `runs/s116-independent-review` 的cases索引SHA `4633e28603c4fa577472586deb822dbdef19bc44c068b23c5628f2827421c44c`、race `f1625f829e7fd3d698fa7ff7bf646237dccce065160b677e6507e6ea085a2f7d`、branch `24d4105ce6ed228d585a5d39c2ca30df4fa19848e25f07dbf5550f286fdc155c`、intent `55cd14cb597a99f53e6dc55dab6dfab92aa077aca0696971dff1327445e2c54f`。实际worker→resume PID见独审原回执。

仅验证选定合成时序，非任意并发、断电或恶意进程隔离证明；旧pin原项目不迁移。无真实模型/研究行动。下一步工作台显式反馈入口需区分事前分支、实际rationale及unknown停查，audit显示最多1工具且不新rank/score，GET不认证claim。

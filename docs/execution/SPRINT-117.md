# S117：页面显式处理已知 staged 反馈

S111面板新增独立严格反馈操作：按当前Project/snapshot、原登记及已完成primary绑定显示validation总体两指标/条件/实际值和登记met/not_met分支；S108 0.4026/0.3724是历史负向子集而非本次总体/阈值。原分支与服务器实际 wait/audit rationale分别显示；原策略unknown映射等待，但S115严格入口遇unknown/损坏或primary未完成停查，不保存wait。0是有效值。

用户点击前说明 audit 最多1额外工具、读取保存的dev/validation和共享corpus（可含final目标文档），不新rank/score/fit/model或final评估；预算/候选不足时原audit分支可实际wait且保留rationale。首次新feedback ID与完整body先存并读回session；不确定只可原ID resume-only，成功须核原manager/parent/child claims后才清正文；该核对可能补manager回执，不始终只读。新增parent只读投影供与session对照，不认证claim；有新feedback parent项目增加可选字段，旧无parent响应不变。blockers必须是空数组，pending完整计数防截断，切项目/快照停查，旧pin不升级。

作者及独审相关11/11 exit0、frontend lint/build，另独审投影2/2；254项manifest SHA `976246cd573bf3b32da2c32c65a15e97144b1bc51bf97073b64bd6255fff8ae8` 前后匹配。独立Chromium/真实HTTP合成覆盖wait、audit、额度耗尽实际wait、伪resume回执原ID恢复、首包未达、session拒写、手机与实际切项目；双GET unknown、PROJECT_BUSY、缺blockers、9 pending与parent SHA伪造通过mock UI零POST。首次新blocker负例夹具误读继承disabled而超时、独审unknown等待旧文案超时，日志保留并修测试后通过；这些并非产品结果。独审发现修前页面不检查context.blockers，已补fail-closed，预算不足仍可由后端wait。

仅隔离合成和所测浏览器时序，无真实研究/模型或额外真实预算；不证明模型采用、科学收益或跨账本原子。

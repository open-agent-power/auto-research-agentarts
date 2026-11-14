# S051：分阶段检索的事前条件与原反馈分支

用户目标是让实验室依据真实反馈决定下一行动。本轮补实际缺口：S045 的独立 development/validation primary 已能执行，但事前假设和反馈策略此前只接受旧两种含 test 的检索家族。新增窄 staged reader，复用原假设登记、反馈策略、ProjectController、Workbench HTTP、SQLite 和累计预算，不新增执行器或账本。

实现允许对 validation 配对均值差预先登记条件，随后只从原结果选择本家族 saved-audit 或等待。原 source/action/SQL 指纹、双臂覆盖、query/document 坐标和 qrel grades 均须匹配。未知保留 unknown；0 是已知数值。private final、索引/排名/评分不参与反馈。不同 family 的提示说明分别校验；旧消息合同保持。新 reader 纳入原 Project source identity，旧 pin 不迁移。

## 已完成验证

- 冻结 191 个产品 Python 文件，manifest SHA `65969d7f332823198641f06add0f5b17e4d5fce201b12dbc925fb9cec6166ea2`；Project core `c26292e780972ee40637ced8c6b5896eb73d4710a707723ced86162195c48cfa`。
- root 最终相关回归 60 项通过；独立检查 4 项通过，包括实际负值→绑定原结果审计、未知/零值区分、原 child SQLite fingerprint 篡改后 unknown/wait，以及旧两家族代表恢复/篡改回归。未触发 private final/重新排名评分哨兵，191 源文件保持。
- root 用新 reader 只读原 S046 的公开 dev/validation 与保存结果，得到原 Recall20 差 `−0.01`。原 Project 状态/预算不变；S046 的36文件和 S050 的17文件共53份原件字节均相同。没有给旧研究补造预测、修改 source pin 或再运行工具。

实际 HTTP 三组新合成项目通过：+1→met→原 saved-audit，共2工具；−1及0→not-met→wait，各1工具。登记/primary/branch 原 body 在不同 PID 的 server 重放，Project 全部文件字节/状态/预算一致，0模型/fit，未执行 final。primary 前从 HTTP context 读到 unknown 并以原纯 policy 编译 wait；未提前派发等待行动。反馈/重放的 server 路径有 private/index/rank/score 抛错哨兵；验证父进程为核文件哈希读取过 private 原字节，因此不声称整个验证过程零 private I/O，也不据此建立盲测。原件 `runs/s051-verification/http/`。

## 方法、原件与边界

按 Adaptive Agent Workflow v0.3.1（远端已 fetch，`02e72e3e411bec53db2288651df01afb27d8904d`）显式 owner loop；root 集成，复用 engineering 实现/工程 E2E，capability_review 独审。实际读取项目 router/backend/interfaces/evaluation；复用成熟的已有协议校验、SQLite 意图/收据、unittest 和故障哨兵，不加载归档 dev-system，不新建团队。

命令及未公开原件在 ignored `runs/s051-verification/`；独审合同、probe、日志和摘要在 `runs/s051-review/`。新源码工程验证不是科研收益、盲测、OS/sealed 隔离或 Linux 模型 runtime 验收。旧 S046 三工具用满；S050 原唯一输入仍待一次新批准，未执行。产品新研究模型/fit/研究行动均0，开发 token/费用 unknown。

S047 `continue_staged` 的固定流程尚不会自动遵循假设 wait 分支。本轮只使已有 `advance_feedback` 支持新 staged 来源；下一实际增量应明确绑定原登记和原策略决定，不能以任意同方法 audit 冒称策略已执行。

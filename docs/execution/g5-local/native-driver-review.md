# G5-L 真实课题薄运行脚本独立审查

状态：**静态 READY，可提交固定代码并做真实 schema-only prepare。真实运行批准仍待具体 freeze。**

- driver SHA：`3616ab660f90ff6a14677995c45ffba76c6ac1695a2010c35bcef9ed09351301`。
- [运行协议](native-run-protocol.md) SHA：`74e0a73927ba999991041fbe4d6ac56208f76203ee8e9ce06ffa6a0944cb06dd`。
- 本审不编写 driver，不另 claim lease，不运行真实 packet、排名／评分、调度 workload、研究 fit 或模型 API。

driver 只封装既有 ResearchProject／LocalWorkbench／ProjectController，两个 family 的 primary／audit 固定。
已关闭首稿检索 audit ID 拼错、import 后预算 receiver 仍指旧路径、commit 验证遗漏删除的 tracked Python、
输出目录可误入历史树、有界读取仅事后检查、保护仅 manager 子树及只核原文件列表等问题。

最终版先核整个 `src/autoresearch` 对 commit 的 diff，再逐项 track／hash 当前 Python、driver／协议／合同。
真实输出限定新 `runs/g5-native-cases-<unique>/<case>`，fixture 仅显式 scratch，
拒绝 traversal、symlink ancestors、历史 case／source 重叠；源包固定 SHA，fixture 不能冒充真包。
freeze 绑定唯一根、case、HEAD、source／scope／snapshot、实际 runtime、固定 2 tools／0 fit／model／source
额度和资源上限。恢复核对同一批准及原件，复制目录不能启动新 batch。

每个课题在独立 Python 子进程设置 wall 180 s、CPU 120／130 s、AS 1 GiB、单文件 32 MiB、threads 1，
父进程也有 wall timeout。fit、source extraction 和网络 guards 保持；这不等于 cgroup／OS 隔离或总磁盘限额。
运行前至少 5 GiB headroom。一次 exclusive attempt 后失败／unknown 保留，不替换 ID 或重置额度。

真实 primary 的完成 action／result 与 observations 先保存，再写含实际反馈 hash／坏例数的 plan2，
之后只做 saved audit；audit、replay、export 拒绝 primary 重算。完整请求 body、receiver_ref、结果、预算和
plan3／wait／四文件 report 保留。import relocation 映射说明 create 无 request ID：旧 unmanaged 路径移走后，
恢复只能核对并使用既存 managed DB，不能在旧路径重建 lineage。

完整三旧 case、G4 VM／native 两树、冻结 controls、standalone 与准备输入原件纳入保护。
最终保护每次重新枚举根目录，对新增／删除路径也检查，不只比较初始已知文件；当前目标检查为 369 文件。

## 工程 smoke 的证据等级

已独立读取作者两 tiny fixture 的实际子进程回执、child shim 和预算：两 family 各 2 tools，
3 plans／wait／report 完成，fits／model／source 均 0，guards 无触发。因代码当时尚未提交，
**测试 harness 明确 stub 了 committed_identity**；child 只接受 engineering fixture，并在真实资源限制下
做代表性 Git 调用。这不充作真实 committed-source gate 或真实 SciFact／调度课题执行证据。
smoke SHA：`889bc004937801f53215414ccd30c81d31e02d641c47991e1dbcd0ab83facfac`。

最终输出／inventory／bounded-read／receiver 元数据修改另经静态复核与目标检查，9 个不合法输出均拒绝，
合法路径接受，隔离 scratch 的增删 inventory 被发现；没有写旧原件。
目标回执 SHA：`f232a565d79497389d85b4472ea7a8cc5e38a605e6df44119a0c85c97e7e1657`。
按 root 指示不重复两 tiny lifecycle 或全套回归，不将早期回执冒充最终真实工作负载运行。

总审原件：`runs/g5-native-driver-review/review.json`。原 scope 内无剩余静态阻断。
root 提交后，两份具体 freeze 仍须独立只读核 source／HEAD／runtime／预算／输出与保护，再出 exact
`g5-native-cpu-run-review-v1` 批准；当前 READY 不授权提前排名或求解，不意味着真实 native G5 已通过。

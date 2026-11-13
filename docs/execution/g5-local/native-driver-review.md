# G5-L 真实课题薄运行脚本独立审查

状态：**静态 READY，可提交固定代码并做真实 schema-only prepare。真实运行批准仍待具体 freeze。**

- 当前 driver SHA：`05b1c5fba21896ebaf6fb5708d34732babf57e219471e17e8a16f0d3077b978c`。
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

## 合法空原件的窄修与具体冻结批准

初始静态准入版本为 `3616ab66…51301`，其回执保持原绑定。提交 `7f33dcc` 后的真实 schema-only
prepare 在保护清单读取阶段遇到 14 份合法零字节 stderr／lock；reader 的非空条件使其拒绝。
失败未创建 output／freeze／project，没有排名、求解、fit 或预算消费；原记录保留，未伪称通过。

窄修仅为 reader 新增默认 `allow_empty=False`，保护 identities 显式传 true；
source／JSON／review 的非空约束与 `maximum+1` 实际读界限不变。369 个原件身份可读且前后相同，
默认空输入和超限仍拒绝。目标回执 SHA：
`86107aa99025e4d4518806e72ca6a000b58c1922dc74353c8a8a0eb7bfe4b26d`。
本审逐读最小 diff 签收，未因此重复 fullsuite 或真实计算。最终 source 提交为
`8e8a206ed0b71479a6e774e36ed91fdb06e21c22`，协议 SHA 不变。

两份真实 freeze 随后实际生成于 `runs/g5-native-cases-20261113-01/{retrieval,scheduling}/`。
独审共 26 项核对实际 HEAD、175 个提交文件、实际版本／解释器、精确 packet／完整 scope、
2 tools／0 fit／model／source 及 369 个保护文件，源 output 全部字节保持。
核验期间 primary／tokens／index／rank／metrics／solver／brute／fit／socket 全部拒绝；只有白名单本地 Git
元数据命令执行，禁止研究计算调用为 0。

| 课题 | freeze SHA | 独审批准 SHA |
|---|---|---|
| retrieval | `5b85abe2a1b962580befae1525143cbdc53e539dd11d7a426c5b78dbb64aa295` | `77c2243b9e732d9a217d7f54af024b9064722f8f6e2064a112118f7a59c93df5` |
| scheduling | `165aefe48bc2af38aeec071519e3ef30e08a6018be5f45d8bfc93f34583f12b9` | `7b351e9af85d07dc94bdeec74517ad5bcab41ef186e7912e1181516fbc299528` |

两个 exact 8-key 批准分别在 `runs/g5-native-run-reviews/retrieval.json` 与 `scheduling.json`；
总审回执 `freeze-review-receipt.json` SHA：
`e6b2305104d89b70eb0f403d0ae7cdd38c07dc0ae5608cb3e587cc4ee9bf7fb0`。
该批准只允许 root 各按原 freeze 顺序运行一次。真实结果、连续反馈／审计、预算与原 ID 无重算恢复
仍需后续验收，不从 schema 批准推定已成功执行。

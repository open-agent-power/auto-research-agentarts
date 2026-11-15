# S091：工作台可发现的未知 Controller 请求

实际合成链复现普通 manager/Controller/action 均 unknown 时，原 `describe.pending_requests` 不包含普通 advance 系列，可能找不到原请求 ID；测试在 `runs/workbench-unknown-probe/` 保留。已有 saved project summary/report 在各自 snapshot 和容量限制内可以暴露部分或完整原记录，不能概称所有报告均不可见；也不能将它们视为保证可恢复的全量索引。

新增普通活动 LocalWorkbench 的独立只读 `read_unknown_controller_requests` 和 GET `/api/local-workbench/unknown-controller-requests.json`，要求精确 project ID/snapshot，前后核活动项目和快照，最多投影8项并标识总数/截断/历史不完整。重复有效ID合并后 `observed_total` 是投影项数，历史不完整时不等同原记录总数；原/当前身份不同明确 mismatch，损坏记录按 partial/malformed 展示安全范围。只输出有限身份/状态，不输出原 body、自动重派或恢复许可。

作者新专项+旧manager/HTTP 15/15、独审专项+旧HTTP/readonly 13/13均合成通过，覆盖真实合成 unknown child、原 child 已完成、模拟旧版升级身份不一致、损坏/重复记录、截断、快照及当前源码漂移、实际本地HTTP与只读宿主404；未触真实研究。独审发现 `self_consistent` 标签易误称完整认证，改为 `limited_fields_match` 且声明 `limited_state_fields_only_not_sql_or_artifacts`；纯投影不验证原 SQL/工件或恢复资格。文档中 observed_total 范围亦经独审修正。

新增 GET 仅普通活动工作台；受限只读宿主仍不开放（404），现有旧 `describe` wire 不改。旧pin/预算保持；合成工具和文件I/O存在，无新真实科研/模型/fit，费用/token unknown；未证明断电恢复、OS隔离或科学收益。

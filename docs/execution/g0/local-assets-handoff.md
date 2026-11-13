# G0 本机资产交接审计

## 本次实际收到的资产

- 用户上传的 v2 执行包：23个文件，包内22条校验全部通过；原件在 `/workspace/Autonomous-Research-Lab-Master-Execution-Pack-v2/`，版本化副本在 `docs/execution/pack-v2/`。
- 用户指定 GitHub 仓库：完整源码克隆，基线 `5d497c8ae22100953f66c3c5b54746ca87e09f01`，初始工作树无改动。
- 本次独立下载的官方 Concrete 数据、元数据、README、许可页面及转换回执：`/workspace/work/g0-data-research/`，详见 [数据核验](research-data-selection.md)。这些是新捕获，不是原开发者旧项目的交接。
- 新建本轮基线验证日志、资源探针原始输出及 SHA：`runs/g0-baseline/`、`runs/g0-resources/`。工程测试中的拟合不计真实研究课题。
- 固定上游源码在 `/workspace/references/upstream/`；不混入主产品源码或提交整仓。

## 未收到、不能声称已恢复的资产

原开发者 ICT 工作区的 ignored `runs/`、旧 SQLite、Host 请求/响应、累计预算、原始研究附件、私人计划及 `.agent/` 状态不随 Git 克隆分发。根 AGENTS 中引用的 `docs/plan.md`、`docs/current-progress.md`、`docs/research/adaptive-research.md`、`docs/team-handoff.md` 在此不存在；`.agent/README.md` 已说明这是预期分发边界。

版本化的历史案例报告可用于定位和理解，不可当作本云实例的执行工件。不能根据 Markdown 摘要重造旧项目、重置预算、补写旧调用回执或宣称旧项目已接续。若后续要接续某个历史项目，先取得原始账本、输入/代码身份、工件、未决/unknown请求与累计预算的完整只读副本，校验后再按原请求ID恢复。

## 本次执行决定

第一项云端课题采用新 lineage，明确是已知公开案例的工作台闭环复现。它不替代旧项目，也不消费或重置旧预算。G0对旧资产的要求落实为：缺失清单明确、无历史恢复主张、无依赖未收到的旧状态。旧资产不阻止新课题准备，但阻止认领旧研究恢复。

## 持久化边界

当前文件保存在所选云环境，未验证跨环境重建后仍存在的持久卷契约。Git 分支保存可共享的源码、计划、审计与接续入口；原始运行证据和公开数据另打交付包供用户保留。不将临时目录或本地文件存在等同于已验证备份/灾难恢复。G6仍需干净环境复现。

仓库根当前没有独立LICENSE文件；本次用户授权修改/推送其指定仓库不代表为原项目新增开源许可证。后续对外发行前仍需由权利方明确本项目许可；不自行补选许可。第三方源码与数据许可另见各审计。

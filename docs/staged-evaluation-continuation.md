# 原生分阶段检索接续

S047已实现并经合成原生HTTP/跨进程恢复及独审；精确源码身份与范围见[S047](execution/SPRINT-047.md)。它把既有Project/Controller的固定阶段接入原LocalWorkbench意图账本，不提供任意脚本执行或模型计划引擎。

## 一次授权的范围

前置：同一managed staged检索项目已保存计划、事前登记独立holdout、完成原development/validation primary；当前代码/来源/计划仍匹配，没有未决Host/Controller/研究行动。原预算足以容纳尚缺的saved audit和final，最多2工具，freeze/report不增加工具。该命令不扩额度，不重新创建项目或研究。

显式调用 `POST /api/local-workbench/staged-continue`，沿现有loopback Host/Origin/CSRF保护，exact body：

```json
{
  "request_id": "staged-followup-1",
  "project_id": "原managed项目ID",
  "expected_state_version": 7,
  "primary_action_id": "原已完成primary行动ID",
  "reason": "在原项目原预算内完成已固定的检索阶段评价和报告"
}
```

先保存整个意图、源码/来源/原primary绑定和固定阶段ID，随后依次：原saved audit→从保存validation Recall20差值冻结BM25/TFIDF→原预算一次final→原export报告。固定规则仅validation差>0选TFIDF，否则BM25；unknown/损坏不选方法。final选BM25时实际同臂只计算一次，delta0不能解释成最终TFIDF打平。

子ID由exact body SHA前32位及audit/freeze/final/report确定；每阶段完整原body在派发前持久化并受固定方法/参数/原context约束。不能把同一final换顶层ID重算。已有completed阶段只有唯一且同原primary/hash/来源/计划/代码、可核audit→freeze→final顺序才复用；不为不明确的旧阶段补造顺序。

## 原ID接续与读取

`GET /api/local-workbench/staged-continue/<原request_id>.json`读取保存阶段记录；read-only服务只开放读取，不执行续作。再次提交必须使用原exact body，不能用最新版本号替换原expected_state_version。已完成原Controller child或freeze可观察后补外层进度；未知行动保留原请求，不能凭外层重试再次排名。部分报告目录保留，不覆盖或换目录掩盖失败。S049新版本意图若在发布前已预封manifest SHA且五文件完整，可由原report请求只读核验后补回执；旧无版本/预封或不完整报告仍原ID停。

manager现有busy门覆盖本命令；报告阶段可用固定原子报告请求接续，其他命令不能趁锁释放插入。源码/helper/manager/Controller身份改变时，未完成意图要求原source pin。终态重放只读核原报告，不能自动迁移历史项目。

## 结果和范围

返回原stage引用、版本/来源/源码身份、停点和报告manifest；开发source/context/manager记录不携final原文或标签。final原件仍由原Project保护、hash验证，未声称OS隔离或盲测。阶段编排和构造数据验证不等于模型自主提出假设、跨领域科研收益或完整Gate通过。

S046真实研究固定在4a159a9 source pin并已耗尽3工具；S047新源码不能用于升级/续跑它。工程验收用单独明确标注的fixture，不重开旧研究。


## 显式条件模式（S052）

同一 POST 路径可使用原五字段再加唯一 `registration_request_id`，例如 `"registration_request_id": "prediction-1"`。这是明确的条件授权：只在该事前登记根据原 validation 反馈选择本家 saved-audit，并核实它完成后，才继续冻结策略、一次 final 和报告。返回版本 `local-staged-continuation-v2`；原五字段仍为原固定流程 v1，不会静默改变旧请求的行为。

先保存原登记及 SHA、反馈、完整封存 context、policy proposal 和原因。指标/阈值来自原登记，不能用请求临时替换。unknown 或 policy wait 保存 `status=completed, phase=waiting` 的外层收据，`result.status=waiting`、`final_evaluation_performed=false`，不创建阶段行动、冻结策略或报告。外层 completed 只表示本次等待回执已保存；同 exact body 重放原等待结果，不永久占用 manager pending 锁，用户仍可另行明确改变路线。

选择 audit 时，在派发前冻结其原 context/proposal/body，绑定原 primary/action/result SHA。后续先核原 controller parent、普通 child、SQLite 指纹及工件，再进入原 freeze/final/report。审计完成后当前候选通常已无 audit，因此恢复使用原封存决定，不基于新的候选重选或重复审计。原计划/来源/源码/Host 与预算门保持，未知 final 保留原请求，不能换顶层 ID 重算；报告沿 S049 原预封 manifest 与完整文件回执恢复。

本版 v2 在初次接受时拒绝任何已有 audit/freeze/final，避免把另行执行的同方法 audit 冒称来自本策略。旧 v1 的已完成阶段复用继续按原合同核验。新模式不批准模型、扩大工具额度或迁移旧 pending/source pin；它按预声明的数值分支编排，不自动提出科学假设或证明科研收益。

本轮实现/验收完成状态以 [current](project/current.md) 与 [latest-report](project/latest-report.json) 为准；未完成前不据本接口说明认领完成。

S059可选registration-v2把两个事前validation条件作为一个整体outcome交给本显式路径；失败/未知分支按原登记等待或审计，未知必等待。新门不改变本路径后续Recall@20冻结算法，不绕过原source/父子/预算门。详见[双指标合同](hypothesis-feedback.md#显式双指标联合条件s059)。

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

`GET /api/local-workbench/staged-continue/<原request_id>.json`读取保存阶段记录；read-only服务只开放读取，不执行续作。再次提交必须使用原exact body，不能用最新版本号替换原expected_state_version。已完成原Controller child或freeze可观察后补外层进度；未知行动保留原请求，不能凭外层重试再次排名。部分报告目录保留，不覆盖或换目录掩盖失败。

manager现有busy门覆盖本命令；报告阶段可用固定原子报告请求接续，其他命令不能趁锁释放插入。源码/helper/manager/Controller身份改变时，未完成意图要求原source pin。终态重放只读核原报告，不能自动迁移历史项目。

## 结果和范围

返回原stage引用、版本/来源/源码身份、停点和报告manifest；开发source/context/manager记录不携final原文或标签。final原件仍由原Project保护、hash验证，未声称OS隔离或盲测。阶段编排和构造数据验证不等于模型自主提出假设、跨领域科研收益或完整Gate通过。

S046真实研究固定在4a159a9 source pin并已耗尽3工具；S047新源码不能用于升级/续跑它。工程验收用单独明确标注的fixture，不重开旧研究。

# 阶段检索的历史方法案例

使用同一ResearchMemory存储与原Project案例导入/撤回/Controller引用，新增独立`staged-retrieval-experience-bundle-v1`分派。旧Ridge和CPU案例保持各自校验语义。S048已完成相关回归、来源独审及真实案例HTTP目标导入/报告/撤回验收；精确源码和证据见[S048](execution/SPRINT-048.md)。

## 捕获与显式引用

`StagedExperienceMemory.import_project(workspace, primary_action_id)`只读核原source、计划、事前holdout元数据、freeze、三个已完成Controller parent/child和工件及SQLite指纹；兼容原producer code pin与当前capture code不同，记录两者身份，保持原项目和额度。必须存在唯一完整的primary/audit/final及可证明的登记→primary→audit→freeze→final顺序；缺原parent或未知行动明确拒绝，不补造历史。

```python
from autoresearch.staged_project_experience import StagedExperienceMemory

memory = StagedExperienceMemory("新的历史案例存储目录")
receipt = memory.import_project("已完成原项目目录", "原primary行动ID")
entry = memory.recall(receipt["scope"])["entries"][0]["record"]
# export_case沿已有scope/entry_id/case_id/version/method_card/limitations合同。
```

导出包含开发/验证的原保存primary/audit及有限source引用、最终聚合和原行动工件SHA。捕获不打开私有final包，不排名、qrel评分、拟合、发模型或恢复行动。最终部分不带逐query行、query ID或其hash；原始corpus/query/qrels bytes也不随包携带。开发spec保留原dev/validation ID以核保存值，不包含final查询。

包沿既有4MiB上限，经`Project.import_experience`或Workbench `/api/local-workbench/experience-import`显式导入；最多4 active案例，严格原ID重放。Controller只将case关联已有同scope/method/evaluation候选，提案可显式保存`experience_case_refs`三元组。案例导入保留原预算、候选、当前证据和研究方法；retired不因原import重放复活。报告独立显示原验证差和最终选中方法，并说明final基线单臂0差的语义。

## 能证明的范围

case保存指标来自原项目。验证TFIDF较BM25低.01、final选中BM25时的.97/0差，分别是负反馈与一次基线计算；没有最终TFIDF结果可供打平声明。历史案例是后续课题的可追溯参照，跨任务有效性须另行评价。

源端捕获核完整final原工件，便携包只含最终聚合及SHA引用。离线校验可核schema/保存开发算术/绑定自洽，无法单凭自带hash证明被省略原件的最终聚合；`offline_final_binding_unverifiable_without_origin`明确保留。包没有原项目总预算的独立证明；原预算由原账本及执行回执核验。

相同用户的程序性分离不代表OS/盲测。任何后来接触历史案例与重叠任务均须披露已曝光范围。未知来源、failed/unknown或不完整阶段拒绝完整案例导出。源记忆与目标已导入快照分别维护active/retired，后续版本不隐式提升旧科学状态。

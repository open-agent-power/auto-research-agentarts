# 带适用条件的研究记忆

外部资料、实验结果和Agent判断分别保存。资料索引用于查原文，实验账本用于证明做过什么，本模块保存可召回的观察与判断。入库前独立复算数值；入库不代表科学评审通过。

## 使用

```powershell
.venv/Scripts/python.exe scripts/research_memory.py import --workspace runs/my-memory --research runs/my-paper/research.json --reproduction runs/my-paper/reproduction.json
.venv/Scripts/python.exe scripts/research_memory.py recall --workspace runs/my-memory --scope runs/my-scope.json
```

scope使用导入结果中的完整对象，四项必须一致：原包SHA、解析输入SHA、分析代码SHA、协议名称。调用方必须从当前真实输入与评估器取得这些身份，不能用旧scope冒充新条件。相同方法在另一版本源码字节上也会拒绝匹配；本版没有自动判定跨版本等价。

| 记忆角色 | 保存内容 | 如何解释 |
|---|---|---|
| fit_observation | 配方、四终点指标、越界警告 | 固定数据与方法下的数值观察 |
| diagnostic_observation | 误差集中度、逐一排除的关联敏感性 | 描述性诊断，不是因果规律 |
| agent_decision | 暂停／停止原因及依据 | 当时Agent的判断，不是科学事实 |

每项保留原动作、来源引用、原研究观察锚点及来源记录版本。全部标为`derived_not_scientifically_reviewed`，数值重算与科学评审分别记录。不匹配条件时返回空列表，默认最多8项，没有相似匹配降级或付费embedding。

## 更新、撤回与恢复

观察身份按适用条件、角色和原动作固定。研究从前缀推进到完整记录时，旧观察不会获得新身份；仅追加来源版本。相同身份的内容变化被拒绝，必须回查来源。这样已撤回的观察不会因重新导入后续研究而悄悄复活。

```powershell
.venv/Scripts/python.exe scripts/research_memory.py retire --workspace runs/my-memory --entry-id ENTRY_SHA --reason "来源待复核" --request-id withdraw-001
.venv/Scripts/python.exe scripts/research_memory.py restore --workspace runs/my-memory --entry-id ENTRY_SHA --reason "恢复召回资格，科学评审状态不变" --request-id restore-001
```

撤回是软删除：不改原观察，只追加有哈希链的资格事件。恢复也不提升科学状态。相同请求重放不重复改变资格；旧撤回请求在恢复后重放仍不再次撤回。读取使用一致事务，不创建空库、不修改账本。最多2000项观察，原始证据与版本不被覆盖。

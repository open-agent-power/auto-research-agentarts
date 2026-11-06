# 配方与RSI开发示例

这些示例随源码交接，配方读取与改进外环的开发范围见[任务书](../../docs/recipe-research/team-module-handoff.md)及[接口约定](../../docs/recipe-research/team-module-interface.md)。

[方法卡示例](../research-method-cards/feedback-driven.example.json)已可通过下面的入口读取并关联宿主候选；[改进轮次示例](round.example.json)仍是问题、轨迹、候选与待执行验证的草案，不代表RSI已采用。方法卡只读知识，实际采用状态由后续外环运行产生。

```powershell
python -B scripts/compile_research_recipe.py --method-card examples/research-method-cards/feedback-driven.example.json --context examples/research-method-cards/conditions.context.json --output runs/method-card-preview
```

[conditions.context.json](../research-method-cards/conditions.context.json)明确标记构造身份：分组候选适用，来源仍缺版本对应说明和已登记选区。命令只写`match.json`，输出方法、理由、缺条件及卡片全文，不执行工具、不生成提案；自然语言条件没有被自动认定为满足。完整过程与边界见[方法卡设计](../../docs/recipe-research/recipe-design.md)。

`contexts/`保存构造的宿主输入，`start`用于主质量检查候选，`feedback`用于分组及来源候选，`blocked`用于宿主阻断，`scope-mismatch`用于范围不适用。项目与执行身份标记为构造数据，文件采用现有context格式。

在产品根目录可以先使用现有配方编译入口，生成可读的decision和proposal。

```powershell
python -B scripts/compile_research_recipe.py --recipe examples/research-recipes/tabular-group-first.json --context examples/recipe-improvement/contexts/feedback.context.json --output runs/recipe-handoff-preview
```

输出目录首次运行时应尚不存在。开发和PR从最新远端主线开始，按任务书中的文件归属持续推进。

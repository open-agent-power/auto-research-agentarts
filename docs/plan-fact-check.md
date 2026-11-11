# 计划中的数值断言核对

在模型计划卡中展开“核对一条数值断言”，选择原计划字段和原句，再明确指定该句所指的父子比较、MAE高低关系或指标数值。宿主读取原Host请求封存的比较事实，计算这条声明与保存值是否一致。结果可下载JSON；预览不保存研究状态、不请求模型，也不消耗拟合、工具或来源额度。

例如[Auto MPG课题](research/auto-mpg-year-study.md)的含年份父版MAE为3.680201，去掉年份子版为5.285817，同折训练均值参考为9.148626。“候选MAE低于父版”的声明与这个父子比较矛盾，即使候选仍优于训练均值参考。核对选择必须明确给出双方行动，不能用另一个参考对象替换。

## 从原计划核对

1. 打开已有模型计划建议，选择要阅读的原字段，在只读原文框选中实际句子，使用所选原句。
2. 选择该请求封存的父子比较，再指定自己对原句的解释：哪版MAE更低，或该句声称了哪个数值。
3. 明确执行核对，阅读实际保存值和比较双方身份。修改选句、对象或声明后，原结果失效，需要重新核对。
4. 下载需要保留的核对JSON。采用、拒绝和记录研究者意见继续使用各自原入口；预览不会自动进行这些操作。

数字按填写的显示精度核对，例如`5.2858`与保存值`5.28581661484824`相符，`5.28`不符。负预测计数按整数精确核对；相对改善使用比例，`-0.4363`约为`-43.63%`，输入不自动转换百分数。没有用户可调的容差。

结果为`支持所声明的判断`、`与保存事实矛盾`或`当前证据不可核对`。原句的含义、比较对象和结构化声明由标注者指定，系统不会从“降低”“改善”等词推断语义。否定、假设、未来条件及引述仍需按原文判断。

## 只读接口

`POST /api/local-workbench/plan-fact-check`复用本地操作启用、同源与CSRF要求。它与配方预览一样直接计算，不进入命令请求账本，无新增采用状态。

精确body为`project_id / host_request_id / claim`。`claim`包含：

| 字段 | 含义 |
|---|---|
| `field` | `plan.question`、`plan.basis`、`plan.steps`、`plan.expected_feedback`、`reason`或`expected_improvement` |
| `start / end / quote` | 原字段Unicode码点范围，零基、end不含，须与原句精确相同；浏览器UTF-16选区会转换为码点 |
| `comparison` | 精确`check / baseline_action_id / candidate_action_id`，引用该Host封存context内的比较 |
| `assertion` | 下列两种声明之一 |

MAE关系声明为`{"kind":"mae_order","value":"candidate_lower"}`，还可选择`baseline_lower`或`equal`。数值声明为`{"kind":"metric","metric":"candidate_mae","value":"5.2858"}`；指标还包括`baseline_mae / mae_change / relative_improvement / baseline_negative_predictions / candidate_negative_predictions`。

结果`plan-fact-check-v1`保留项目、原Host请求、冻结context及状态身份、原句与码点位置、比较双方、声明、`status / actual / reason_code`和实际匹配的`saved_metrics`。`semantic_mapping="submitter_declared"`、`coverage="selected_span_only"`和`scientific_validation=false`明确其范围。原回答字节、解析参数和封存材料不匹配时拒绝核对。

已采用或拒绝的建议仍可回看，其原状态和原件保持。没有已解析建议时不能选句；旧v1 context没有严格比较，或所选比较不可比、指标缺失时保持不可核对，不从当前项目补入历史未提供的事实。

现有manager也可使用CLI，`claim.json`按上述body填写。命令输出结果JSON；得到矛盾或不可核对也是正常计算结果，退出码0不代表声明成立。

```powershell
.venv/Scripts/python.exe scripts/check_plan_fact.py --root runs/my-local-workbench --input claim.json
```

## Limitations

核对只证明提交者声明的数值关系与所引用保存事实是否相符。精确选句不证明提交者对原句含义的解释正确，也不保证其他错误已被选中；单位、因果、独立性、泛化及完整科学解释均不在本检查范围。它不构成整份计划通过或自动采用许可。

真实Auto MPG两份计划原回答本身均正确。故意选反方向或填写错误数字属于工程反例，不能记录成模型真实失败，更不能据此声称科研判断或研究结果已经改善。

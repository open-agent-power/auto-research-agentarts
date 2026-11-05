# CSV与工作簿保存值的候选投影核对

`data.workbook-projection-check`只读比较项目CSV与已捕获XLSX的保存单元格，评价契约为`workbook-projection-v1`。它回答“哪些工作表的保存值能作为这份CSV的候选投影”，保留相同或不相同的计数、定位和原件身份；不推断作者实际采用了哪条转换或运行链。

## 什么时候出现候选

先完成当前表格主质量检查，取得绑定的前序行动与结果。提交者的`spec.provenance.origin_sha256`须与当前项目已捕获XLSX的元数据匹配；执行前仍重新核验原件身份。该SHA声明本身不证明文件或转换有效，没有匹配的已捕获原件时，先取得实际资料，不能用任意本机路径代替。

候选与参数由原控制器提供，仍受当前代码身份、前序绑定、本地工具预算、未决执行及原请求重放规则约束。它不增加工具、来源、模型或现金额度，也不执行公式、宏或作者代码。

## 怎样明确选择

在产品根目录，先用已有入口只读查看当前项目：

```powershell
$projectWorkspace = 'runs/my-existing-project' # 改为已有项目目录
$projectionContext = .venv/Scripts/python.exe scripts/run_research_project.py selection-context --workspace $projectWorkspace | ConvertFrom-Json
$projectionContext
```

若存在该方法的合法候选，按[选择提案](project-selection.md)保存绑定此context的proposal：`choice`只填`kind=execute`与宿主给出的实际`candidate_id`，不能自行提供method、工作表或工具参数。没有候选时如实记录条件与缺口，不改context凑候选。

```powershell
.venv/Scripts/python.exe scripts/run_research_project.py advance-selection --workspace $projectWorkspace --request-id workbook-projection-1 --proposal runs/workbook-projection-proposal.json --expected-state-version $projectionContext.state_version
```

原ID核对沿用原proposal、need和原版本，不重复行动；unknown执行不换ID重发。这里的命令格式不授予真实项目额度或升级权限。

## 结果怎样读

结果schema为`workbook-projection-check-v1`，观察kind为`workbook_projection_check`。每份结果保存CSV行列数、候选工作表数、完全一致候选数及名称，并绑定前序行动、原件ID和已捕获字节SHA。

每个候选记录比较格数、精确匹配数、数值相等但保存文本不同数、不符数、非精确格数、公式格数及工作簿缺/多行数。三个比较类别互斥：`exact_matches + numeric_equal_text_diff + mismatch_cells = compared_cells`；非精确格数是后两者之和。数值相等但保存文本不同不算精确匹配，公式只使用保存缓存，不求值。

Markdown与PDF摘要至多列6张候选工作表及5处代表定位，不大量复制单元格内容；完整候选、例子和前序身份保留在原行动JSON。现有`report.json/input.json`继续保存行动、收据和已捕获附件，不另取原件或创建第二套报告。

多个完全一致候选仍保留歧义；即使只有一个，也只能说明当前CSV与保存单元格的候选对应。它不证明作者实际转换、图像/对象与运行连接、ALP身份、单位或独立样本，不允许据此改值、删零或执行Chem 0→28。

## 原项目验证

2026-11-05，原hiMSC项目在明确授权后显式升级，并将本地方法上限从2增至3，通过原控制器执行一次本方法。972行、6列CSV与12张列头匹配的工作表比较，唯一完全一致候选为`B8S1`：5,832个单元格逐字一致，没有数值异文、值或类型不符、缺/多行或公式缓存格。原父请求重放未新增行动或用量，项目最终为v42、本地3/3；来源仍5/8，模型和拟合均为0，原现金边界和历史unknown保留。

同次验证仅重载18793加载已提交代码，18791保持原进程；真实桌面/手机页面已查看完整与分段截图，候选表横向滚动和原件详情键盘展开可用。当前报告只导出一次，9页均已实际看图；工作台PDF与JSON下载均为200且与当前报告原字节身份一致。该结果证明原项目的选择、一次执行、原ID重放与当前报告链已连接，原始输入、历史行动和失败继续保留。

## Limitations

保存值一致不证明作者实际运行/导出转换、图像对象逐行连接、ALP身份、单位或独立性。PDF第2至4页留白较多，第7页仅有待办续句；完整候选与原件仍在JSON和输入包中。原hiMSC本地额度现为3/3，后续新执行需单独获准；本机`runs/`证据不随普通Git克隆分发。

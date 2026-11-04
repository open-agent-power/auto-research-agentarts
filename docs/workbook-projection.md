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

## Limitations

生产hiMSC项目的本地方法额度已为2/2；真实执行本方法需要另获显式授权将上限2→3，并按当前代码身份显式升级。本页说明工程入口与证据边界，不表示该生产核对、PDF验收或科学确认已经完成。旧报告和失败继续保留，生成新报告仍须明确操作；本机`runs/`证据不随普通Git克隆分发。

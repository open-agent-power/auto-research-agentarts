# 接收已封存任务的回传证据

`scripts/intake_evidence.py` 将填写好的取证目录接入同一个本地工作区：先绑定已封存交接任务和诊断，创建不可变证据收据，再把支持的定位准备为可供后续评议的片段。它不调用模型、不拟合、不新增模型预算，也不会执行来源文件中的内容。

此入口面向已有的填写包；如何领取、填写来源与发现，见[取证返回填写包](evidence-return.md)。空白包不能直接作为真实证据提交。

当前本地CSV研究项目的`research.source-selection`任务沿[工作台补充资料](local-workbench.md#在同一项目登记资料再明确读取)登记和读取，任务来自`GET /api/project/evidence-task.json`。不要把它改装为本入口的封存交接绑定，也不要复用其他项目的`task-binding.json`；两条既有路径的选择见[返回说明](evidence-return.md)。

## 开始与恢复

在产品根目录，使用**新**工作区并传入已填写目录和对应的封存交付：

默认继续到可评议输入准备阶段。若只需先封存收据，可在 `start` 后加 `--stop-after receipt`；之后使用同一工作区继续：

```powershell
.venv/Scripts/python.exe scripts/intake_evidence.py resume --workspace runs/my-intake
```

`resume` 也支持 `--stop-after receipt`。收据一旦完成，后续恢复以**已封存收据**为准，不因填写目录之后的编辑重新编译或改写原证据。新增材料应使用新的 intake 工作区，保留原草稿、收据和任务绑定。

## 产物与状态

| 目录／状态 | 含义 |
|---|---|
| `receipt/`、`receipt_ready` | 原不可变提交收据：保存声明的来源字节、哈希、提交者和定位，绑定原任务；定位尚未语义验证。 |
| `preparation/` | 存在工作簿／文本选区时，保存派生收据、`packet.json` 和 `preparation.json`；公式不执行。 |
| `publication/` | 对表格准备结果封存 `prepared-input.json`、`prepared-input.md` 和清单；不会自动挂载或启动工作台。 |
| 根目录 `packet.json` | 不含表格选区时，保存 PDF／JSON 片段包；HDF5 定位仍明确排除。 |
| `initialized` / `prepared` | 分别表示工作区已初始化／输入准备完成；两者都不表示模型已读取。 |
| `needs_input` | 当前材料没有可供后续处理的有效片段，或需要补充输入；查看状态与排除原因后提供新材料。 |
| `needs_attention` | 中途状态不完整、身份不匹配或存在需要人工核对的问题；保留现场，不自动重置或覆盖。 |

`status` 返回当前 `status`、`stage`、`intent`、各产物路径与哈希、数量和零模型／零拟合标记；只读取状态，不执行评议。

准备完成表示片段已封存，**不表示模型已读取、作者已确认、任务已完成或科学结论已获批准**。HDF5 路径等未支持的定位会明确列出，不推测其内容；原始 URL、哈希、坐标和未解决问题仍应保留。表格准备会生成本地只读视图；要在当前工作台看到它，仍需显式挂载，详见[表格来源与派生证据](tabular-evidence.md)。

工作区锁用于阻止并发操作；发现残留锁时应先确认原进程和磁盘状态，不自动删除锁或重启未知操作。状态查询不启动模型，不会自动处理需要人工关注的状态。

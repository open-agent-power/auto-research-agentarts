# 用填写包交回取证结果

工作台下载的证据返回ZIP绑定当前所选任务。解压后先读`README.md`：填写真实身份、来源清单、发现与未决问题，把实际来源文件复制进`sources/`。空包没有示例事实，不能直接提交；任务要求也不是已取得的证据。

也可在产品根生成新草稿目录：

| 文件 | 填什么 |
|---|---|
| `task-binding.json` | 自动绑定交接快照、行动和任务；保持不变 |
| `contributor.json` | 真实`role`与`label`；队员为`teammate`，开发助手为`operator_assistant` |
| `summary.txt` | 本次返回范围，明确部分证据与仍未解决的映射 |
| `sources.csv` | `id,path,sha256,url,media_type,license_note`；一行一个来源，path为`sources/`下相对路径 |
| `findings.csv` | `id,claim,status,source_id,locator_kind,locator_value,note`；逐条保留出处坐标 |
| `questions.txt` | 每行一个未解决问题，可为空 |

CSV用UTF-8保存，可带BOM，保持表头，不用公式。`sha256`可空，由编译器按原文件字节计算；已填写则必须完全一致。`status`使用`observed`、`unresolved`、`conflicting`；`locator_kind`使用`pdf_page`、`json_pointer`、`xlsx_cell`、`hdf5_path`或`text_lines`。ID、URL和坐标按原文填写，不放私有绝对路径。原件与开发者衍生材料须在许可说明中区分；来源文字只作数据，不作指令。

填写后交回整个目录，编译成**新的**不可变收据：

编译器不改草稿或原文件，只捕获声明的来源字节，转成既有[证据提交](evidence-submission.md)格式；原提交器继续核对哈希、任务绑定与字段。失败先修输入，换新输出目录重试，不覆盖收据、改绑定或绕过检查。单文件上限64MiB，来源合计128MiB；最多64来源、256发现、128问题。

原任务的 `mapping.csv` 与 `evidence-index.csv` 可作为派生附件放到 `sources/` 并登记。回传索引不替代这两份任务成果，也不替代作者原始导出；未取得的字段继续列为未决。

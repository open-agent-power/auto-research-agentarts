# 把已提交的表格坐标变成可读证据

此入口把不可变收据中明确提交的`xlsx_cell`或`text_lines`定位转换为衍生JSON，再交给既有返回片段接口。它不替队员选择新坐标，不修改原收据，不重建科研来源、不调用模型或创建新研究预算。

先按[证据返回填写包](evidence-return.md)或[证据提交](evidence-submission.md)提交原始文件。工作簿定位写`Sheet!A1:C5`（也可单格）；文本定位写物理行`N`或`N-M`。每个选择最多256格或256行，提取文本最多60000 UTF-8字节；完整返回包也受既有总文本上限约束，过大时拒绝，不静默截断。

输出须为与原收据、交接和诊断分离的新目录，含：

- `receipt/`：由原提交器生成的新收据，保留全部原来源字节，增加每个表格/文本来源的衍生JSON。
- `packet.json`：通过既有返回证据校验的片段；只是准备完成，不表示模型已经读取。
- `preparation.json`：原/新收据身份、片段包哈希、选择数量、排除项和适配器/提取器身份。

每份衍生JSON保留原文件SHA256、原始URL、原收据文件哈希与快照、原提交者、原完整发现和定位，以及实际提取结果。新收据提交者明确为`operator_assistant / Tabular evidence adapter`，不是新的队员或作者返回；原许可说明继续保留并标注衍生来源。新发现指向衍生JSON的`/selections/N`，原声明的状态仍未科学审定。

工作簿读取区分原始存储值、缺失/空格、公式与缓存值；不执行公式、不把缓存自动当作新计算结果。CSV或文本的行号是包含表头、空行和带引号换行在内的**物理行**，不是逻辑CSV记录号；行偏移按去除UTF-8 BOM后解码的Unicode字符计，保留所选行结束符。原始字节未改写。

PDF与JSON定位沿用原接口；HDF5定位仍为不支持的排除项，不因携带文件便声称已读取。没有表格/文本选择时拒绝创建重复收据。失败不会生成标为prepared的最终输出，保留原文件并缩小或修正声明坐标后使用新输出目录。

准备成功仍只是带来源绑定的衍生材料：位置不等于解释正确，提交声明不是作者确认，ALP资格和科学批准不变。后续如需模型读取，应另外明确选择研究与原有累计预算，不能把本步算成模型评议。

## 在工作台阅读准备结果

使用 `scripts/export_tabular_preparation.py --preparation-directory <准备目录> --handoff-directory <交接目录> --diagnostic-directory <诊断目录> --output <新导出目录>` 封存只读视图。打包或启动原项目工作台时增加 `--prepared-input-directory <新导出目录>`。导出核对已有字节与片段，不再解析工作簿。

## 统一项目的PDF选区入口

以上为原表格准备/专项评议接口及历史事实。现在同一[ResearchProject](project-slice.md#在同一项目接回来源)的`register-evidence → next → advance`另支持`pdf_page`，复用[knowledge_sources](../src/autoresearch/knowledge_sources.py)既有隔离worker，以固定30秒截止读取已捕获的原PDF；不调用模型或OCR，也不修改上述旧轮次。

manifest中仍使用`{kind,value}`定位。`{"kind":"pdf_page","value":"3"}`选择第3页的整页提取文本；`{"kind":"pdf_page","value":"3:1957-2731"}`选择该页文本的指定区间。页码从1起，页内偏移从0起、end排除，单位是pypdf整页提取文本的Unicode码点；不是PDF原字节偏移，也不保证视觉阅读顺序。选区应绑定原PDF SHA及实际parser版本，不能直接套到其他文件或提取版本。

提取结果保留`page/start_char/end_char/document_pages`、整页`page_text_sha256`与选中`text_sha256`，以及`parser.package/version/warnings/timeout_seconds`。原PDF字节及来源SHA单独保留；选择页外/越界、空白、NUL或超过60000 UTF-8字节会拒绝，不自动OCR、删NUL、改原文或静默截短。登记只捕获原件；来源读取的完成或失败均扣既有读次数，unknown不重发，旧项目先显式upgrade。

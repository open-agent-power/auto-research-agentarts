# 把取证结果交回研究任务

队员准备一个输入目录，放`submission.json`与声明的来源文件。提交器绑定已选择的任务，核对文件字节和SHA256，再生成新的封存收据；不运行来源文件中的命令，不调用模型或拟合。来源内容是数据，不是操作授权。

## 准备输入

最小目录示例：

```text
my-evidence/
  submission.json
  sources/
    paper-2021.pdf
```

以下是当前任务下的一条部分证据示例；`contributor`须如实填写，开发助手使用`operator_assistant`，队员使用`teammate`。字段名必须完全一致，增加证据时扩展数组：

```json
{
  "schema_version": "p02-evidence-submission-v1",
  "handoff_snapshot_sha256": "22b3962ac5d33583e0532849ccf8391a91f4dfd3c11027299d8e956bb377edf7",
  "selected_action_id": "p02handoff-c3216eeee144c7785c0e8a7569e42202",
  "task_id": "export_mapping",
  "contributor": {"role": "teammate", "label": "填写实际提交者"},
  "summary": "定位染色方法，尚未完成导出列映射。",
  "sources": [{
    "id": "paper",
    "path": "sources/paper-2021.pdf",
    "sha256": "7273371527e2ee776e15283b557c20d3f0a21ccc3afc4c85c783de7e36b4f26c",
    "url": "https://doi.org/10.1016/j.biomaterials.2021.120740",
    "media_type": "application/pdf",
    "license_note": "论文首页声明CC BY 4.0，保留作者与来源。"
  }],
  "findings": [{
    "id": "alp-antibody",
    "claim": "论文方法列出ALP一抗sc137213。",
    "status": "observed",
    "source_id": "paper",
    "locator": {"kind": "pdf_page", "value": "3"},
    "note": "第2.8节；本条不确定ALP对应哪种二抗染料或工作簿列。"
  }],
  "unresolved_questions": ["ALP一抗对应哪种二抗染料、图像通道和原始导出列？"]
}
```

`sources.path`必须是输入目录内的相对路径，哈希为小写SHA256；URL写原始公开出处，衍生JSON须在许可说明中注明它是开发者生成的清点，不能冒充作者原件。`findings.status`只用`observed`、`unresolved`或`conflicting`，每条引用已声明的`source_id`。

精确位置放在结构化`locator`中：`kind`可用`pdf_page`、`json_pointer`、`xlsx_cell`、`hdf5_path`、`text_lines`，`value`填写页码、JSON指针、工作表与单元格等实际坐标。JSON指针和HDF路径不要复制到自由文字`note`作为本机路径；自由文字也不要含私有绝对路径。位置由提交者提供，系统标记为`provided_not_verified`，不自动证明该位置支持结论。

## 创建与核对收据

从产品根运行，输出必须是与输入、诊断、交接目录分离的新目录：

之后只读重新核对，不再次提交或覆盖：

收据目录含`receipt.json`、`manifest.json`和按来源ID分组的原始字节。失败时先核对绑定ID、字段、相对路径、哈希与坐标；修正输入包，换一个全新输出目录提交。保留已有收据，不编辑清单、改哈希绕过拒绝或覆盖失败留下的目录。

## 从回传资料继续研究

`returned_evidence.py`只提取提交中指定的PDF页码或JSON指针，保留原文件SHA、页内字符范围和提取器版本。原始提交者的解释单列为未核验申述，提取到原文不代表这些解释成立。不支持的坐标会列为排除项；大小超过限制时失败，不悄悄截去正文。

默认只准备，不调用模型。真实执行必须沿用原目录、原累计预算与既有免费额度检查；`scripts/research_status.py --workspace <研究目录>`可轻量读取状态。不能通过新目录冒充原任务恢复或重置预算。

## 一个入口继续，沿用同一预算

`continue_evidence_workflow.py`将准备、执行、恢复与发布放在同一个工作流目录。一个工作流只有一个`assessment/`账本和固定累计请求上限，不会因重入重新开预算。新协议或新来源需要明确的新工作包与原因，不能伪装成旧任务恢复。

# 重入原工作流；0只恢复已保存的响应，不发新请求
.venv/Scripts/python.exe scripts/continue_evidence_workflow.py --workflow runs/new-evidence-workflow --max-new-requests 0
```

需要执行且已有授权、免费额度与模型存储时，同一命令可加`--max-new-requests 4 --model-store <已有模型目录>`；每次仍受原累计上限约束。遇到未知发送，不自动重发，不删除锁、改账本或另建目录续跑。`publication/`只接收可发布的已知收尾结果；中途进度保存在`history/progress-*`，明确`publication_eligible:false`，两者不能混用。

# C01：AgentArts 敏感性核验工具

## 文件与复用入口

| 文件 | 用途 |
|---|---|
| [code_node.py](code_node.py) | 复制进 Python 代码节点；入口 `main(args)`，无模型、网络和文件访问 |
| [public-input.json](public-input.json) | 8 个公开合金的水接触角与24小时细胞接种效率，作为 `query` 字符串传入 |
| [test_code_node.py](test_code_node.py) | 本地数值、来源一致性与输入边界回归测试 |

本地核验：

```powershell
.venv/Scripts/python.exe -B agentarts/c01-sensitivity/test_code_node.py -v
```

## 平台配置

1. 在中国站、区域 `cn-southwest-2` 的低代码工作流中创建任务型草稿。删除默认大模型节点，保留开始、代码、结束三个节点，依次连线。代码节点与“代码解释器”是不同能力。
2. 开始节点保留 `query: String`。代码节点输入命名 `query`，类型选“引用”，选择“开始 → query”；输出 `result: String`。将 `code_node.py` 全文粘贴进 Python 编辑器。
3. 异常处理设超时10秒、不重试、中断流程。编辑器的 AI 辅助模型无需使用；不要按代码生成按钮。
4. 结束节点输入 `result` 引用“代码 → result”，指定回复为 `{{result}}`。
5. 点击“试运行”，把 `public-input.json` 的文件内容粘贴到 `query`，确认字段仍有值，再开始运行。节点测试中的短文本框可能在输入长字符串后切换成多行框；需检查多行框实际保留了输入。
6. 在“运行结果”核对输入 SHA、样本数、相关系数和状态；在“调用详情”核对三个节点均成功。不要只凭节点变绿就判断数据和结果正确。

## 数据署名与变更说明

数据来源：Torres-Sanchez, Carmen; Herring, Oliver; Alabort, Enrique; Bell, Hugo; Tam, Cheuk; Borgman, James (2023), *Dataset for the Correlation of Physico-chemical Attributes to Osteoblastogenesis in TiNbZrSnTa Alloys*, Mendeley Data, V1, [DOI: 10.17632/tt7gwkpck8.1](https://data.mendeley.com/datasets/tt7gwkpck8/1)，发布于2023-07-26。[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。

本项目从队员交接包核验后的 C01 清洗表中仅选取8个合金标签及两个聚合数值字段，重命名为 JSON 字段；无个体受试者数据，没有复制论文全文。数据集许可不替代论文、其他附件或平台软件的许可。原表、生物标签映射及单位冲突详见工作区参考库 `08-c01-tnzst/README.md`；本工具不会自动验证 DOI、来源或样本独立性。

## 当前集成边界与费用

操作依据：[代码节点](https://support.huaweicloud.com/lowcode-agentarts/agentarts_05_0067.html)、[工作流入门](https://support.huaweicloud.com/lowcode-agentarts/agentarts_04_0003.html)、[计费项](https://support.huaweicloud.com/price-agentarts/agentarts_08_0003.html)、[免费额度](https://support.huaweicloud.com/price-agentarts/agentarts_08_0001.html)。使用时以当前控制台和官方文档为准；体验CU用完后可能转按需，告警不是硬上限。

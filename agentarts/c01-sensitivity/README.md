# C01：AgentArts 敏感性核验工具

2026-10-30 已在华为云中国站 AgentArts 低代码平台完成真实代码节点测试和两次完整工作流试运行。此目录提供可复用的源码与公开输入；平台原生导出包尚未取得，不能当作一键导入包。

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

独立数值对照使用当前开发环境已有的 SciPy；缺失时明确跳过。冻结 CSV 位于 ignored `runs/c01-tnzst-r10-final`，不随 Git 分发；另一 checkout 缺失时该来源一致性测试也会明确跳过。本机本轮 9 项测试全部实际通过，没有跳过。

## 平台配置

1. 在中国站、区域 `cn-southwest-2` 的低代码工作流中创建任务型草稿。删除默认大模型节点，保留开始、代码、结束三个节点，依次连线。代码节点与“代码解释器”是不同能力。
2. 开始节点保留 `query: String`。代码节点输入命名 `query`，类型选“引用”，选择“开始 → query”；输出 `result: String`。将 `code_node.py` 全文粘贴进 Python 编辑器。
3. 异常处理设超时10秒、不重试、中断流程。编辑器的 AI 辅助模型无需使用；不要按代码生成按钮。
4. 结束节点输入 `result` 引用“代码 → result”，指定回复为 `{{result}}`。
5. 点击“试运行”，把 `public-input.json` 的文件内容粘贴到 `query`，确认字段仍有值，再开始运行。节点测试中的短文本框可能在输入长字符串后切换成多行框；需检查多行框实际保留了输入。
6. 在“运行结果”核对输入 SHA、样本数、相关系数和状态；在“调用详情”核对三个节点均成功。不要只凭节点变绿就判断数据和结果正确。

本轮草稿名 `C01材料细胞敏感性核验`，ID `a4f9e1e9-a5cf-4c71-a2e9-593b08db1b34`。它在当前账户可继续编辑，没有提交版本、发布渠道或配置外部调用凭据。[打开工作流](https://console.huaweicloud.com/agentarts/?region=cn-southwest-2#/home/agent-center/app-flow/flow?id=a4f9e1e9-a5cf-4c71-a2e9-593b08db1b34&from=)。

## 实际结果与判读

| 平台操作（北京时间） | 平台显示耗时 | 实际结果 |
|---|---:|---|
| 01:00:44，代码节点测试 | 56 ms | 8个样本，`r=0.5234731822584694`，一次剔除反向，`needs_review` |
| 01:13:18，完整工作流试运行 | 57 ms | 与节点测试结果一致；调用链为开始1 ms、代码49 ms、结束3 ms |
| 01:16:03，删除输入中的 Alloy 4 后再次完整试运行 | 62 ms | 7个样本，`r=-0.7788568345407015`，输入 SHA 随之改变，`exploratory_only` |

8样本的 canonical JSON SHA-256：`da623d987f74cdc00610ff403225c8ecc0761bb46e58bf6530e77d744bf541ed`；7样本输入为 `4bea463963d5eb115fc328e2ceb2f27e0aac9f4e1380e5ca76b5de6369b7b021`。哈希保留样本顺序，输入空白不影响该值。云端与本地数值以绝对误差 `1e-12` 核对；浮点末位不必逐字相等。

`needs_review` 表示相关方向受单个合金影响或存在未定义相关系数。`exploratory_only` 只表示当前这项诊断没触发复核条件；不表示可直接开展实验、材料更优或研究已获得独立验证。删除 Alloy 4 是演示输入变化和事后敏感性，不能据此选择性排除不利样本。只有少量合金、样本身份映射和重复结构仍有未决问题；未做显著性检验、因果识别、新实验或模型训练。

## 数据署名与变更说明

数据来源：Torres-Sanchez, Carmen; Herring, Oliver; Alabort, Enrique; Bell, Hugo; Tam, Cheuk; Borgman, James (2023), *Dataset for the Correlation of Physico-chemical Attributes to Osteoblastogenesis in TiNbZrSnTa Alloys*, Mendeley Data, V1, [DOI: 10.17632/tt7gwkpck8.1](https://data.mendeley.com/datasets/tt7gwkpck8/1)，发布于2023-07-26。[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。

本项目从队员交接包核验后的 C01 清洗表中仅选取8个合金标签及两个聚合数值字段，重命名为 JSON 字段；无个体受试者数据，没有复制论文全文。数据集许可不替代论文、其他附件或平台软件的许可。原表、生物标签映射及单位冲突详见工作区参考库 `08-c01-tnzst/README.md`；本工具不会自动验证 DOI、来源或样本独立性。

## 当前集成边界与费用

- 已验证的是控制台沙箱中的独立工作流，尚未由本地 C01Loop/ResearchLoop 调用；本地工作台、原报告、原始账本及 `platform_connected` 标记没有据此改写。自主模型决策、持久记忆和连续研究仍待接入。
- 运行输出、截图和核对记录保存在 ignored `.agent/artifacts/r14-*`；不提交浏览器会话、Cookie、密钥或运行产物。UI未展示可关联的真实 Trace ID，此处不宣称平台 Trace 集成完成。
- 用量复查于北京时间01:19：体验版有效期至2026-11-20 23:59:59，仍显示已用0/20 CU、MaaS已用0/2百万Tokens、应用1/50。计量可能延迟或舍入，不能据此证明现金账单精确为0。本轮只发起3次上述纯代码执行，无模型调用，无新建 Runtime/代码解释器会话、部署实例或持久凭据；累计新增现金上限仍为5元，后续调用前继续复查，不能重置。
- 原生导出跳转到平台 OBS 文件地址后 `ERR_TIMED_OUT`，未得到原生工作流包；未重复创建应用。高代码 Runtime 镜像、认证、存储、API发布均不由本轮替代验收。

操作依据：[代码节点](https://support.huaweicloud.com/lowcode-agentarts/agentarts_05_0067.html)、[工作流入门](https://support.huaweicloud.com/lowcode-agentarts/agentarts_04_0003.html)、[计费项](https://support.huaweicloud.com/price-agentarts/agentarts_08_0003.html)、[免费额度](https://support.huaweicloud.com/price-agentarts/agentarts_08_0001.html)。使用时以当前控制台和官方文档为准；体验CU用完后可能转按需，告警不是硬上限。

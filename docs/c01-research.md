# C01：由Agent逐步推进的研究工具

本入口把资料检索、可配置的真实分析、反馈和停止决定放进同一份研究账本。当前由外部Agent读取观察后逐次提交JSON；不会在脚本里预置一串提案。它没有后端模型调用，不会自行连接平台或消费模型额度。

已复用的计算是 `c01._round / loo_predictions` 和 `c01_loop` 的两项敏感性分析。输入仍是已校验SHA的公开C01原包，标准化只在每折7个训练合金上拟合。Agent可以调整Ridge收缩和四项允许特征的子集，不能改数据、目标、评估、文件路径或执行任意代码。

## 启动与接手

先按[资料检索入口](knowledge.md)建立固定索引。以下命令在产品根执行，实际文件路径按本机环境设置。

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.venv/Scripts/python.exe scripts/c01_research.py create --workspace runs/my-c01-study --archive ../../references/auto-research/08-c01-tnzst/案例输入包-C01-TNZST-20261028.zip --index runs/my-knowledge/knowledge.sqlite --goal "检验材料属性对体外细胞响应的预测与敏感性" --max-actions 12 --max-fits 4
.venv/Scripts/python.exe scripts/c01_research.py observe --workspace runs/my-c01-study
```

Agent接手同一workspace，保留累计额度，先读取observe结果，再向apply的UTF-8标准输入发送一个对象。标识示例需要替换成刚读到的真实值；不能照抄旧观察。

```json
{
  "request_id": "one-unique-decision-id",
  "observation_sha256": "CURRENT_OBSERVATION_SHA256",
  "action": "fit",
  "reason": "依据实际反馈选择本次对照；说明为什么值得做及不能证明什么",
  "source_citation_ids": ["RETRIEVED_CITATION_ID"],
  "evidence_action_ids": ["LATEST_EXPERIMENT_ACTION_ID"],
  "parameters": {
    "alpha": 100,
    "features": ["ecm_gpa", "yield_mpa"],
    "hypothesis": "可被这次计算反驳的工作假设",
    "expected_effect": "预期观察与失败条件"
  }
}
```

调用：`.venv/Scripts/python.exe scripts/c01_research.py apply --workspace runs/my-c01-study`，从标准输入提供上面的JSON。

| 动作 | 参数 | 返回内容 |
|---|---|---|
| search | query、可选kinds/limit；可成对指定document_id/source_sha256，最多4段 | 在固定来源或全库检索；原文、文件哈希、行号或论文页码 |
| read_source | document_id、source_sha256、start_chunk、count（1或2） | 顺序读取原索引片段、实际窗口、下一偏移与目录导航；不读取任意路径 |
| review_evidence | field、question、finding、status、next_check | 绑定1至4条已检索原片段的资料判断；保存已知、未知与下一检查，不修改审计或科学资格 |
| fit | alpha 0.001–10000、固定特征子集、hypothesis、expected_effect | 四终点32次真实逐折拟合、预测、MAE/R²、越界警告 |
| residuals | fit_action_id | 已完成配方的误差集中情况；不会删除样本或重训 |
| correlation | 空对象 | 固定接触角—接种率变量对的逐一排除敏感性 |
| pause / stop | 空对象 | 保存控制决定；之后不再派工 |

search尚无引用时可用空引用列表。实验必须引用本研究检索过的来源，并引用最新实验；提供的来源与动作标识都必须存在。安全暂停／停止允许没有引用，但仍绑定当前观察并记录原因。未知、过期、重复配方和超额度请求不会推进账本。

`observe.source_catalogue`列出最多8份实际索引文档的ID、原来源SHA、索引文本SHA、类别和已有目录标签；更多文档数量明确显示，不能把目录当成完整覆盖。被普通检索命中的其他文档也可据原ID和SHA选择。`document_id`和`source_sha256`必须成对、来自当前目录或已见引用；不按文件名、标题或路径猜测替换。

读取先选来源，`start_chunk=0`可取得初始原片段和Markdown标题导航；后续采用目录中的`chunk_offset`或窗口的`next_chunk`。偏移为零基索引片段序号，不是行号或PDF页码。每次最多两段、每段最多1400字符，保留原citation ID、原文和原位置；长单行的顺序也按原构建时的确定性ID核对。目录标题仅作导航，只有实际返回的片段算进入本次阅读范围。来源可能只是已捕获正文前缀，读完索引也不代表读完原出版物或附件。

阅读和检索所得原片段都能供后续判断引用，不消耗fit额度。同一request ID恢复不会重复读取或记账；紧邻的完全相同窗口会拒绝。其他行动后可重读旧窗口以恢复有限上下文，引用身份不变，也不算新证据或科学进展。工作簿单位与样本映射未知、没有读到方法段、整篇论文没有方法，是三个不同判断，不能相互代替。

`review_evidence`让资料核验成为可继续的研究行动。`field`只能取固定特征、终点或`sample_mapping/cell_protocol`；问题与下一检查各不超过500原始字符，finding不超过1000。`status`仅为模型断言：`supported`表示具体问题已有所引文本回答，`unresolved`包含部分已知但仍有关键未知，`conflicting`表示来源存在不相容说法。它们均不表示科学批准。

执行器从已检索引用原样绑定来源、位置与完整chunk，不接受替换原文或任意路径；没有原文引用、重复解释或越界字段会拒绝。结果同时保存`source_linkage_verified=true`、`interpretation_verified=false`、`scientific_approval=false`。后续上下文能读到这些判断与下一检查，原始audit和数值仍保留；它不消耗fit额度，也不替代实验。公共附件只保留解释及引用位置，不复制原摘录；独立数值验证器不核准其科学含义。

相同request_id和原请求重放返回已提交结果，不重训；同ID更换内容被拒。SQLite写事务包含纯计算与落账，每个请求最多一份已提交记录。进程在提交前中断可能导致这项纯计算重做，不宣称物理执行恰好一次。读取／导出使用一致的只读事务，避免并发停止时把两个状态拼成报告。

默认最多12项动作、4项训练配方，保留最后一项给暂停／停止。重启进程可以在仍active的原账本继续；pause和stop当前均阻止派工，尚未提供恢复paused的CLI命令，不允许直接修改SQLite绕过。终态重放不会再次执行实验。输入、代码及索引身份冻结；更换代码不能把旧运行假装成新版本验收。

## 产出与尚未接通部分

```powershell
.venv/Scripts/python.exe scripts/c01_research.py export --workspace runs/my-c01-study --output runs/my-c01-delivery
```

在产品根使用已存在的原始复算目录、同一个公开输入包及校验过的交付目录启动：

打开 `http://127.0.0.1:8770/#/overview`。交付目录属于操作者ignored运行材料，克隆代码后须另取验证过的完整交付；上面的目录名不是自动创建步骤。

## 论文式PDF与可分发附件

```powershell
.venv/Scripts/python.exe scripts/export_c01_research.py --workspace runs/my-c01-study --output runs/my-c01-paper
```

输出目录必须新建，旧报告保留。报告包含问题与方法、实际结果、Agent推进过程、停止与适用条件、引用及复现步骤。图表只从经过独立数值校验的结果生成，不把失败结果或越界预测藏起来。

`reproduction.zip`只包含14项白名单文件及清单：公开数值输入、配方／预测／诊断／决策投影、引用位置、计算源码、环境版本、图表、报告及独立验证器。外部论文全文、检索摘录、参考仓库、浏览器状态和密钥不进入分发包。完整摘录仍保留在原研究账本，分发投影仅保留原观察哈希作为出处锚点，不能据此重建原观察。

解压到一个新目录，在已安装NumPy和scikit-learn的环境运行 `python verify_results.py`。验证器不导入附件source，不联网，独立重算每项配方的32次拟合、全部指标和两项敏感性诊断；还校验源码身份、文件哈希、普通文件及路径边界。不要直接以作者输出目录作附件根：它额外含ZIP与作者检查记录，纯附件验证会按设计拒绝多余成员。

清单不是数字签名；数值重算一致不是科学有效性、LLM身份或原始数据真实性认证，验证器也不自动证明PDF／CSV文字语义。报告图文另经实际渲染和数据对照检查。运行文件留在操作者ignored runs，单独克隆代码不会附带原研究材料。

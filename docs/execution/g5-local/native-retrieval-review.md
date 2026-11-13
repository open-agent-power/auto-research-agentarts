# G5-L 原生检索纯模块独立审查

结论：**本次被审纯模块可进入 root 的原生集成验证**。原专项17项小工程夹具、6项独立检查及完整真实输入的只读schema核对通过；最终严格echo补丁将夹具增至18项，另有下述独立source复核和[完整工程回归](integration-regression.md)。没有在此审查运行真实SciFact索引、排名或评分。这不是原生课题执行验收、完整G5 Gate、封闭评测或科研有效性结论。

审者 `repo_audit` 未修改被审模块或测试。首轮基于HEAD `03f90a31f187a156cfa156fee7c0d659fcc3d5c4`，最终补充基于`0c197e8c2cbd14a899b8097d476cdb93053380e3`的未提交工作树；以文件SHA及全树回执为准，不将新实现称为这些HEAD已有能力。合同为[native-integration-contract.md](native-integration-contract.md)，首轮核对版本SHA `eef102a431174608e083be1e9342017254d51ea387717583a02e51c0e12eff0b`。下表是最终被审版本；旧版文档原字节已归档。

| 被审文件 | SHA256 |
|---|---|
| `src/autoresearch/retrieval_adapter.py` | `16e111318074baa7b3d3b1648bdd690ec6e380db3e3115d6555ee9f3fab2ada7` |
| `src/autoresearch/retrieval_lexical.py` | `fc3a85ee18db8647e98eda8a3780d6f290039377f5e69783ed24fedecbd09f54` |
| `tests/test_retrieval_adapter.py` | `7c9a4621e6af9d719a10a26384fe88d3d93fcc7b25160453afc67e849e93d767` |

证据等级：`S` 为直接源码；`U` 为本次小工程夹具实测；`D` 为本次原始真实输入的机械 schema/身份读取。`U/D` 均不表示真实检索效果或科学评价。

| 核对项 | 源码证据及独立结果 |
|---|---|
| 原件捕获与身份 | `retrieval_adapter.py:117/:196/:232`：固定六个 basename，原始字节、严格 Base64、长度与 SHA、原 spec 与派生 scope、全包指纹逐项核对；捕获结束再按相同安全 reader 重读比对。`source_evidence_adapter.py:128/:153` 检查父目录、普通文件、链接、大小及读前/读中/读后身份。`U` 另验硬链接、父目录 symlink 拒绝，原件保持。没有路径、URL、archive member 或命令进入 runtime 参数。 |
| 严格 schema 与引用闭合 | `retrieval_adapter.py:71/:86/:131/:154/:173/:196`：重复 JSON key、非法 UTF-8、NUL、非有限值、未知字段、超限、重复 ID/成对标签、错 foreign key、交叉 split 拒绝。metadata 限对象、16KiB、512 节点、8 层、key128/string4096；原字节不删改。`U` 另外从 capture 入口验证 escaped surrogate/key、NUL、浮点溢出均分类为 `INVALID_SOURCE`。 |
| 有限执行能力 | `retrieval_adapter.py:2/:301/:408`、`retrieval_lexical.py:6`：固定 stdlib/native imports、固定两方法及 audit 参数 envelope；无候选代码解释、动态导入、shell、pickle、网络获取或外部模型路径。加载 schema 已检查行/字节/字段上限，结果完整大小上限4MiB (`:297`)。这是有界可信本地处理；未实现 OS 隔离、硬 CPU/RSS 上限或同用户防篡改。 |
| 词法定义等价 | `retrieval_lexical.py:14/:18/:36/:58` 对应冻结 `scripts/run_cpu_transfer_benchmarks.py:130/:134/:152/:174`：先 `text.lower()` 再 `[a-z0-9]+`；title+text、log-TF 平滑 IDF/cosine；BM25 `k1=1.2,b=.75`，查询词按唯一词累加；同分按 document ID 升序、top20；五个二元引用指标一致。`U` 独立5文档、12 query/method 组合、48个指标比较完全同值，另验 tie、未知词及零 token corpus。未以 SQLite FTS5 替代此算法。 |
| 排名先于指标 | `retrieval_adapter.py:303/:308/:317/:318`：先完整双方法/三 split 排名，再 canonical hash，之后调用 metrics。`U` 在每次评分时断言6次小夹具排名已全部完成。qrels/metadata 在 `_checked` 阶段已经读取并验证；排序只使用 corpus title/text、query text，评分使用引用 qrels。排名哈希在内存形成，随最终 ToolResult 保存，没有独立持久的 ranking checkpoint，更不是 sealed evaluation。 |
| 保存诊断不重做实验 | `retrieval_adapter.py:333/:408` 检查保存排名哈希、配对覆盖、合法指标与操作计数；audit 仅从保存指标重算差值和 adverse 集并核对旧摘要。`U` 将 build_index/retrieve/metrics 全部 patch 为失败后，audit 仍成功且不修改输入；不重排、不重新用 gold 评分、不 fit。 |
| 结果与出处可复核 | `retrieval_adapter.py:256/:263/:313/:320/:325/:420`：完整排名/逐 query 指标都保存；所有损失或任一 arm 未完整召回的 query 留入 adverse，tie 仍在完整原结果/差值；保存 query 物理行、命中文档物理行、资产 SHA、TSV query/document locator 及旧 action 引用。计时含在保存排名指纹中，重放应回读原件而不重新生成时间值。文档命中是未审阅引用，不代表 SUPPORT/CONTRADICT、答案正确或来源许可获批。 |

**修正与失败保留。** 首版 `8921df...` 的14项 unit 通过，但独立检查发现 `str.splitlines()` 将正文中合法 U+2028/U+0085 当记录分隔符，导致来源读取失败；首轮检查为4/5通过，保留在 `runs/g5-native-retrieval-review-20261113-01/`，未覆盖。owner 改用 LF/CRLF 物理记录，最终独立行号为2/3/4且正文字符完整。旧 standalone loader 也用 `splitlines()`；这里修正的是新 native 物理行合同，并未修改冻结旧研究或词法公式。

原拟 metadata 必须空对象的假设被 owner 的真实 parser-only 预检否定；root 批准改为有界 opaque JSON。[原预检](native-data-preflight.md)保留第一次失败和原件映射。独立 schema 读取再次确认1109条 query 中693条有非空 metadata。原句级标签被保留、声明且不被固定排名/评分使用，不能据此称为未知标签或保密评测。修改 metadata 不改变排名/指标的17项 unit 中有专门小夹具；本次未重新开展真实检索。

**独立真实输入核对（仅 D）。** 对捕获的同一份11,128,187原始字节计算 SHA 后解析；将 tokenizer/index/retrieve/metrics 四函数全部 patch 为拒绝，实际调用均0。源包 SHA `546a09773bc8e77aa7f034ca58753394f6a75c3ecf610e3c66c3f24eea2ab51b`，snapshot `2ff1e33fc9b780037338f9916b9430bd6502029058ccd5386334af1e2b430895`：5183文档、1109 query；train809 query/919对、test300/339对；80/80/300 split ID 与原 freeze 精确一致；FK、字段、行数及包上限通过。此核对读取已公开标签，不是来源内容提取 action、重新检索、独立上游许可审查或 scientific validation。

**最终严格echo补充。** root要求将`_checked:204/:216`中的spec echo与派生scope比较改为canonical相等，拒绝Python中`20.0==20`、`True==1`造成的类型混同。lexical未变，新增1项unit含2个负例，当前共18项。独立补充再确认spec `20.0`及scope `3.0`分别被`EVIDENCE_CHANGED`拒绝；同一真实11,128,187字节packet、snapshot与全部原件不变，四lexical入口patch为失败时load仍通过且调用全0。补充回执`runs/g5-native-retrieval-review-20261113-01/strict-echo-final/receipt.json`，SHA `edcdb8bc74442583b1cb0a67c3039baf0d7b2e7ab80e4b9e058499b249ad3598`。旧17项版文档原字节在同目录`review-before-strict-echo.md`，SHA `0ac1f520daee1c51d6d141cbabb7763d3c265263806607956214cc84931b5c66`，原专项回执不改写为新版本。

**尚须整层集成验证。** `SavedRetrievalAudit.execute_saved:409` 只验证 predecessor ID/SHA 的格式，并不证明该 SHA 对应当前项目原 action；合同明确由 controller 验证并供应保存 ToolResult。此模块通过不能替代同项目/同 source/精确 predecessor hash、registry 与 selector、2 actions/0 fit/API 预算、不可变保存、原 ID 重放/新路径恢复、报告与引用导出检查。真实 SciFact 完整范围也由新的 host freeze 绑定，generic 小夹具通过不能替代它。上述集成仍由 root 另行验证，本审查不提前验收。

本次两个命令均用 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python`，分别运行 `/workspace/work/g5-native-review/audit-final.py` 与 `schema-only.py`。前者17/17 unit、6/6独立检查，0 fail/error/skip；后者只做机械读取。Python3.12.14/Linux6.18.57，词法运行仅依赖 stdlib；adapter/reader 的递归 code identity 及所有被审文件 SHA 见回执。真实 SciFact index/rank/score0、fit0、model/API0、native actions0；工程小夹具确实运行了索引/排名/指标计算。

三旧 case 共292文件（Concrete101/RealEstate101/Slump90）及5份 G4 controls 在前后 SHA 完全一致；本次不改源码/测试、不写旧 case，真实研究累计50次 estimator 保持。独立证据在以下本地文件：

- `runs/g5-native-retrieval-review-20261113-01/final/receipt.json`，SHA `a5ddb1e3e287d890aeaa2ae5d189f1f350bde6f780257517d4117bfea131a71e`。
- `runs/g5-native-retrieval-review-20261113-01/final/schema-only-receipt.json`，SHA `a12070e1fc51bc9d25015b4f46cb2a9133de7f6a05402a20746a1f77b10175dd`。
- 首轮失败 `runs/g5-native-retrieval-review-20261113-01/receipt.json`，SHA `9c5a5816dee508bc3ada549c02182702b8da83391fb76ad704673ede39865191`；原检查和日志均保留。

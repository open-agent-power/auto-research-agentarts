# M1 预检门禁 · 2026-11-19

- 阶段：**M0 课题预注册，审批卡未签字**。本轮没有执行任何检索、排名或评分。
- 产出：`scripts/m1_preflight.py`（门禁）+ `scripts/m1_preflight_selftest.py`（故障注入自检）
- 判定：**NO_GO_UNSIGNED**（退出码 2）。除签字外九项检查全绿——也就是说，签字是唯一剩下的事。
- 证据：`runs/m1-preflight-20261119/result.json`、`runs/m1-preflight-20261119/crosscheck-result.json`（gitignored）

## 为什么要做这一步

上一轮（交叉核对 23/23）证明的是**输入**没被改。但它没回答一个更要紧的问题：**打分器本身算得对不对**。`freeze.json` 把打分链路钉成了 `staged_adapter_identity` 一个哈希——哈希对，只说明「跑的是同一份代码」，不说明这份代码的 nDCG 分母、MRR 窗口、top-20 截断是按合同实现的。若评价器有错，M1 跑出来的数字与冻结校验都会一致地错。

所以本轮把「能不能开跑」做成一条可重复执行的判定，而不是一句口头结论。

## 门禁九项（本轮实测）

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| P0 解释器是钉住的 `.venv` | PASS | 3.12.14 + numpy 2.5.4，`sys.executable` 解析后等于 `.venv/Scripts/python.exe` |
| P1 审批卡已签字 | **BLOCKED** | 4 个勾选框勾了 0 个，`签字人/日期` 均为空，状态行仍写「待签字」 |
| P2 预算余量 | PASS | 现金上限 5 CNY，`confirmed_cash_spent=null`（记 unknown，不推测）；研究工具行动 0/2、模型 0、fit 0（操作者声明，门禁不计量） |
| P3 `freeze.py --check`（.venv） | PASS | 退出 0，`FROZEN PACKET INTACT`，snapshot `ec7f3452…` |
| P4 独立内容交叉核对 | PASS | 复用 `scripts/crosscheck_m0_packet.py`，23/23，`snapshot` 重算 == 发布值 |
| P5 代码钉从字节独立重算 | PASS | 独立复现 `staged_adapter_identity` 链 == `0d659650…` |
| P6 指标合同 vs 手算夹具 | PASS | 7 个夹具全部命中手算字面量（1e-12 容差） |
| P7 排序合同（合成文档） | PASS | tie-break 升序、top-20 截断、排除先于截断、两处实现一致 |
| P8 比较常量四处一致 | PASS | `freeze.json` / `spec.json` / `adapter.COMPARISON` / `lexical.METRICS` |
| P9 同 ID 排除在本包内不起作用 | INFO | 查询 `q-dev-01…`、文档 `d-16-233.1…`，交集 0 |

退出码约定：`0` GO；`2` 仅因未签字被挡（其余全绿）；`1` 有真实检查失败，禁止开跑。

## 本轮新查出来的四件事

### 1. `freeze.py --check` 失败不等于内容被改

`staged_adapter_identity` 的链条末端是 `tabular_source.extraction_identity()`，而它把 **`sys.version` 字符串和 pypdf 的版本号一起喂进哈希**。所以同一套字节、换一个解释器或换一个 pypdf，`--check` 会报 `FROZEN PACKET CHANGED`，asset 哈希却一个都没动。

已实测：`.venv`（3.12.14）→ `INTACT`；托管 3.13.12 → 在 `import numpy` 处就 `ModuleNotFoundError`，根本走不到哈希。另做了敏感度探针：只改 `sys.version` 字符串、字节全同，钉值即变（`0d659650…` → 另一值）。

含义：签字后若 `--check` 报变化，**先看 P5 的分解**再决定是内容漂移还是环境漂移；不要一看到报错就先怀疑包。这也解释了为什么门禁把解释器放在 P0。

### 2. `ignore_identical_ids` 在本包里从未生效

32 个查询 ID 与 85 个文档 ID 命名空间不相交（交集 0）。合同里这条子句合法、但不被本课题行使。写报告时不能说「同 ID 排除已在本研究中验证」。

### 3. 排序逻辑有两份实现

- `retrieval_lexical.retrieve()`：`k1=1.2, b=0.75, top 20` 是**字面量**。
- `relevance_retrieval_adapter.retrieve()`：从 `COMPARISON` 读，多了 `exclude_doc_id`。

M1 走后者。两者今天在夹具上一致（P7），但常量若改一处不改另一处就会静默分叉。这是登记在案的结构风险，不是当前缺陷。

### 4. 指标合同的边界已经测过

7 个夹具里有三个是真正的边界，不是摆设：

- 正例排在**第 14 位**：`recall@10=0`、`recall@20=1`——抓「k 窗口写错」（把 20 当成 10，或反之）。
- **12 个正例**：`recall@10 = 10/12`、`ndcg@10 = 1.0`——抓「recall 分母用 min(k,|R|)」和「nDCG 理想值未按 10 截断」。
- 正例在**第 21 位**（top-20 之外）：三项全 0。

另记一条边缘事实：全停用词查询（如空串）返回**空排名**而不是抛错。本包 32 题不触发，但值得知道。

## 门禁本身能不能失败（故障注入 11/11）

只证明「现在全绿」是没有意义的，还得证明「出错时会红」。`scripts/m1_preflight_selftest.py` 逐项注入故障，每项都按预期翻红：

| 注入 | 期望 | 实测 |
| --- | --- | --- |
| 四框全勾 + 填签字（假卡，仅自检） | PASS | PASS |
| 只勾三框 | BLOCKED | BLOCKED |
| 勾满但签名为空 | BLOCKED | BLOCKED |
| 记录现金超上限 | FAIL | FAIL |
| 声明研究行动 3/2 | FAIL | FAIL |
| nDCG 偏 1% | FAIL | FAIL |
| 结果里缺 `mrr@10` | FAIL | FAIL |
| `recall@20` 塌成 `recall@5` | FAIL | FAIL |
| tie-break 反序 | FAIL | FAIL |
| 截断放宽到 25 | FAIL | FAIL |
| pypdf 版本挪一位 | 钉值必须变 | 已变 |

自检不改冻结包：审批卡与预算文件都复制到临时目录，打分器故障全部用桩。

## 一句诚实的话

这套门禁是**同模型、同一双手**写的，独立性来自「另写一份实现 + 手算字面量」，不来自人。对外只能写「冷上下文复核通过」，不能写「独立评审通过」；门禁 GO 也只意味着「可以开跑」，不是「结果可信」。

## 下一任务

1. **等签字**（`runs/m0-cfr-20261118/approval-card.md` 第 9 节四项 + 签名）。
2. 签字后：`.venv/Scripts/python.exe -B scripts/m1_preflight.py` 必须返回 `GO`（退出 0），再按审批卡第 7 节跑那一次 primary。
3. 若 `--check` 报变化：先读 P5 分解区分环境漂移与内容漂移，不要直接重生成冻结包。

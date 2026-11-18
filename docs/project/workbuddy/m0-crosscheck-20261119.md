# M0 冻结包独立交叉核对（2026-11-19）

**一句话结论：** 冻结包 `m0-cfr-20261118` 的 `snapshot_sha256` 用**另一套实现**（纯标准库、不导入 `src.autoresearch`）从磁盘字节重算，结果与发布值**逐字符相同**；23 项核对全过。新发现两件事实（行尾平台依赖、解释器依赖），都不改变冻结值，但要写进 M1 的执行前提。

本轮**没有**跑排名、没有新增研究工具行动、没有修改任何冻结输入。审批卡仍未签字，M1 仍未执行。

## 为什么值得单独做这一层

既有 7 项篡改测试已经证明了「适配器能拒结构缺陷、但**不校验内容字节**」——协议 §5.1 写得很清楚。也就是说，链路上留了一个洞：**没有任何既有检查证明语料正文真的来自那份冻结源**。本轮补的正是这一格，并顺手把「作者自己的脚本说自己没问题」换成「另一套实现复算同一结果」。

独立性说清楚：脚本作者是我，语料作者也是我（同一模型不同轮次），所以这**不是第三方评审**，只能叫「冷上下文 + 不同实现的复核」。它能排除实现层的手滑与自证，排除不了共同的先验误读。

## 23 项核对

| 组 | 核对 | 结果 |
| --- | --- | --- |
| A1 | 4 个资产 + `spec.json` 的字节数与 SHA-256 对 `freeze.json` | 全同 |
| A2 | `spec.json` 的 `comparison`/`limits` 等于协议常量复述 | 相同 |
| A3 | `spec.json` 3,303 B ≤ 65,536 B | 通过 |
| **B1** | **独立组装 payload 重算 fingerprint** | **`ec7f3452…cfa2593` == 发布值** |
| B2 | `freeze.json` counts 等于重算 scope | 85 / 32 / 8-24 / 32 / 0 |
| C1 | 语料 85 篇、题目 32 道 | 通过 |
| C2 | dev/validation 不交、声明集 == 题目集 == qrels 键集 | 交集 0 |
| C3 | qrels 表头精确、32 对全 `score=2` | 通过 |
| C4 | 每题恰好 1 个正例，且全部能在语料里找到 | 缺失 0 |
| C5 | 无重复 qrels 行 | 32 唯一 |
| C6 | 正文非空、`metadata` 全为空对象、id 唯一 | 通过 |
| C7 | `selection.json` 的 doc_ids 与语料一致 | 各 85 |
| C8 | 覆盖声明的 11 个 Part | 233/238/239/240/255/260/323/429/435/437/465 |
| D1 | 源档 4,422,809 B + `fbaf04e9…82b3a9` | 相同 |
| D2 | 收据 SHA `9d6b06a5…` | 相同 |
| D3 | `spec.source_provenance` 三个身份与 freeze 一致 | 相同 |
| **E1** | **85 篇正文逐篇归一化后落在其源 SECTION 内** | **85/85 命中，977 个 SECTION 索引** |
| F1 | 台账 86 行 = 85 kept + 1 excluded（`d-16-465.3`） | kept 集 == 语料集 |
| F2 | 台账 `chars` 列 == 正文原始长度 | 0 处不符 |
| F3 | 语料内 `incorporated by reference` 出现次数 | 0 |
| F4 | 没有 `[Reserved]` 段落被当成文档收录 | 0 |
| G1 | 资产总量 287,918 B / 上限 11,800,000 B；canonical payload 392,872 B / 16,000,000 B | 通过 |
| H1 | 每个资产内部无混行尾 | 通过（但跨文件不同，见下） |

E1 的做法：用自己的正则把 XML 切 `<SECTION>`、按 `<SECTNO>` 取 `§ x.y` 编号、剔 `<SU>` 与标签、反转义、折叠空白，然后判断每条语料正文是否是归一化后的**子串**。子串判定故意宽松（不追求与抽取器逐字节一致，那是复读不是复核），足够证明「正文不是凭空写的」。

## 两处新发现

**1. 冻结哈希绑定行尾（跨平台不可复现）。** 五个文件的行尾并不统一：

| 文件 | 行尾 |
| --- | --- |
| `corpus.jsonl` | LF |
| `license.md` | LF |
| `queries.jsonl` | CRLF |
| `qrels.tsv` | CRLF |
| `spec.json` | CRLF |

这是 Windows 文本模式写入（`open(...,"w")` 把 `\n` 转成 `\r\n`）与字节写入混用的结果。**对本机 M1 无影响**——冻结就是这堆字节，`freeze.py --check` 也正是比字节。但若哪天在 Linux 上重生成同内容，`queries`/`qrels`/`spec` 会变成 LF，三个哈希全变、`freeze.py --check` 必报 `FROZEN PACKET CHANGED`。**结论：这套冻结只在本机字节意义上可复现**，重生成必须显式 `newline=""`，或干脆把行尾写进协议。

**2. 官方校验脚本依赖解释器，managed Python 跑不起来。** 用托管解释器 Python 3.13.12 跑 `freeze.py --check` 会在 import 阶段挂掉：

```
src/autoresearch/c01.py:21: import numpy as np
ModuleNotFoundError: No module named 'numpy'
```

能跑的是仓库自带 `.venv`（Python 3.12.14，numpy 2.5.4）：

```
.venv/Scripts/python.exe -B runs/m0-cfr-20261118/freeze.py --check
→ FROZEN PACKET INTACT
→ snapshot_sha256 ec7f3452…cfa2593   (exit 0)
```

因为 `build()` 内部就是调 `capture_source`，这一条同时再次确认了「真实适配器接受 + `missing_positive_document_count=0`」。**M1 必须用 `.venv` 解释器**，否则第一步就卡住——这不是科学问题，是执行前提，写在这里免得签字后才发现。

## 本轮我自己的两次假失败（如实记录）

首次跑出 22/23，两条 FAIL 都是核对脚本的错，不是包的问题：

1. **C3 报表头 `'score\r'`** —— 我用 `split("\n")` 切 CRLF 文件，残留 `\r`。适配器用 `csv.reader(newline="")` 不会有这问题。改法：切行前统一 `replace("\r\n","\n")`。
2. **F1 报台账 86 行 ≠ 85** —— 我预设台账只记 kept，实际它对被排除的 §465.3 也留了一行 `excluded` 并写明理由。这是**更好的做法**，是我的断言写窄了。改法：断言 85 kept + 1 excluded 且 excluded 恰为 `d-16-465.3`。

修完 23/23。这两条留在报告里，因为「核对脚本也会错」本身是这层复核需要被复核的理由。

## 边界

- 未运行任何排名，`model_calls=0`、`native_fits=0`、现金 0、研究工具行动 **0**（本轮全部读盘与本地计算）。
- 未改 `freeze.json`、未改 `assets/`、未改协议常量、未重跑构建器。
- 未推 GitHub。
- 平台自身用量：`unknown`（不可见，不推测）。
- 对外只能写「冷上下文复核 + 不同实现复算通过」，不写「独立评审通过」。

## 复现

```
cd track2/auto-research
C:/Users/chenfeng/.workbuddy/binaries/python/versions/3.13.12/python.exe -B scripts/crosscheck_m0_packet.py
# → 23/23 checks passed; runs/m0-crosscheck-20261119/result.json
.venv/Scripts/python.exe -B runs/m0-cfr-20261118/freeze.py --check
# → FROZEN PACKET INTACT
```

脚本 `scripts/crosscheck_m0_packet.py` 进 Git；结果 JSON 与包本体一样留在 ignored `runs/`。

## 这轮之后仍卡在同一处

**签字。** 冻结值现在有两条独立路径互证（作者 `freeze.py` + 本轮 stdlib 复算），审批卡第 4 节与第 5 节已补上本轮结论与那两项执行前提。签字后第一件事不是跑排名，而是用 `.venv` 跑一次 `freeze.py --check` 确认包没在这段时间被动过。

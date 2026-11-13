# G5 原生集成工程回归

**有限验收：完整测试通过，源文件与测试不变；含派生缓存的整个src树不满足逐字节不变。** root已接受这项明确的缓存例外，无需仅为缓存变化再次运行拟合夹具。原严格回执保留 `passed=false`，另有独立分类验收，不覆盖原结果。

2026-11-13 在 `/workspace/auto-research-agentarts` 执行一次完整命令：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

| 结果 | 实测 |
|---|---:|
| 总数 / 通过 / 跳过 | 1225 / 1206 / 19 |
| failure / error / exit | 0 / 0 / 0 |
| unittest / wall秒 | 188.297 / 190.332 |
| 新分组覆盖 | retrieval18、scheduling20、CPU project9、CPU report9、lease guard5 |

19项跳过来自未分发外部原件、Windows专属进程/网络生命周期及未安装官方runtime extra，逐项原因在日志/回执。测试包含真实工程拟合夹具，**不是全程序fit0**；夹具精确fit数未单独计量。没有执行新原生SciFact/调度课题，新增外部模型/API请求0；模型测试采用既有mock/本地transport，运行时只捕获credential是否存在，不打印值。

HEAD前后同为`0c197e8c2cbd14a899b8097d476cdb93053380e3`，测试的是其未提交G5工作树。src/tests完整文件清单、tracked binary diff及所有untracked新代码都在前后manifest中，不能仅凭HEAD重建被测树。实际Python3.12.14/Linux6.18.57；实际导入/安装版本一致：NumPy2.5.4、SciPy1.17.0、sklearn1.8.0、h5py3.16.0、ReportLab4.4.9、pypdf6.21.4。完整installed列表和真实模块路径保存在`runtime.json/dependencies.txt`；这是既有venv工程回归，不宣称干净安装。

保护结果：

- src183个非bytecode文件、tests整树360文件前后内容/模式相同；source-only manifest SHA均为`372e85f03b1ea64e69ae2d70bd847085c1d7f1c1c6248249df62929669817166`。
- 包含缓存的src树为329→330文件，4个`.pyc`变化：`method_registry`、`research_methods`、`research_project`更新，`scheduling_adapter`新增。因此严格entire-src检查为false。全部路径、原/新SHA/size在`source-tree-differences.json`，未删除或恢复缓存来伪造通过。
- 原Concrete101/RealEstate101/Slump90共292文件、G4 VM case28/原生确认case10、5份G4冻结controls及旧G5 standalone11文件均逐字节/模式相同。SQLite用`mode=ro&immutable=1`独立读取；原fit分别20/20/10，合计50，预算、状态版本、model/source/tool计数与ledger SHA前后不变。
- source/tests tracked diff SHA前后同为`10973ee052dac9cb9a9dd96ebb052e05f4b5a4ffcde484ce94c0c4d65cf5f8a9`，tracked code diff亦相同。whole Git diff因本轮授权docs/索引编辑不同；新增host driver/validator准备文件在untracked列表另记，不是测试树变化或课题执行。

主证据目录`runs/g5-native-integration-regression-20261113-01/`：

| 文件 | SHA256 |
|---|---|
| `unittest.log`（226553字节） | `e962d80baa3b9aaf3bb2d039bb03c64f1c54bb14d17d17c5c3cc0e0183340e44` |
| `regression-receipt.json`（原严格false） | `f2f33b3ddf56aa67ed3f2dd5a845e8047dc78eeb22ebf6bdfc0829f5436092ef` |
| `limited-acceptance.json` | `90b6312bacf58429605bfec82abac4f66156f69951b394a4ad0cc580716bcdfd` |
| `before.json` / `after.json` | `dc508feea7b0d09e7e4dd4eeff68a9e7863c00bc98dda97c529246a74c9286d7` / `b11a3f7b9b78068935fd39661571d704a1be9c2713849f6079da830a4d805928` |

reviewer的host捕获脚本首次有generator括号语法错误，发生在启动任何unittest子进程前；修正后完整suite只运行一次，前置失败另存`host-preflight-failure.json`。本轮没有修改core或弱化测试。

[retrieval独审](native-retrieval-review.md)已补最终adapter `16e11131...`的严格spec/scope echo与18项fixture依据；[算法独审](native-algorithm-review.md)保留70个小样例独立穷举、保存audit和原输入schema检查。工程回归通过不替代真实新课题的freeze、累计预算、原ID重放/恢复、报告验收，也不解除原G0隔离/runtime阻塞。

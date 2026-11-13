# G5-L 原生加权区间调度纯模块独立审查

结论：**被审纯模块与只读输入可进入 root 的整层原生集成验证**。最终20项 unit、6项独立检查通过；独立70个小样例与穷举最优目标、原函数完整选中序列及操作计数一致。另只读核对准备好的16个 workload 原件与旧输入身份，未执行这些 workload。这里不验收完整 G5 Gate、原生课题生命周期、科研有效性或生产采用。

审者 `repo_audit` 未编写或修改被审 kernel/adapter/tests，没有另领租约。审查基于 HEAD `0c197e8c2cbd14a899b8097d476cdb93053380e3` 加下列新文件，以文件 SHA 为准。依据为 [实现合同](native-algorithm-contract.md)；[准备数据说明](native-algorithm-data.md)的源范围、失败和成本说明分别保留。

| 被审文件 | SHA256 |
|---|---|
| `src/autoresearch/scheduling_kernel.py` | `3a335e102279ce9e6a7a8861a3f203670fccfbfb3ea3d2941f8b9406ea92e401` |
| `src/autoresearch/scheduling_adapter.py` | `86f653b0bfbc9cb6c9b596c09a02ddb4252871ced1ed70a530091deaff04a098` |
| `tests/test_scheduling_adapter.py` | `2cd69bee932d4114ad3c1fb09ee620b1f46b6edbbf0eddbc5b2a0559ecb33892` |
| `docs/execution/g5-local/native-algorithm-contract.md` | `42d5faac4897299e243c50391403204de1451caadba002d227336f62a9fa7c72` |

证据等级：`S`直接源码；`U`本次小工程夹具执行；`D`本次完整准备输入的只读身份/schema核对。`D`不求解、不产生新的计时结果。审查中导入冻结旧脚本仅用于小样例函数差分，没有调用其 batch、prepare 或 run 入口。

| 核对项 | 证据与结论 |
|---|---|
| 原 DP 与 tie 定义 | `scheduling_kernel.py:34` 对应冻结 `scripts/run_cpu_transfer_benchmarks.py:253`：按 `(end,start,整数id)` 排序，baseline遍历全部前驱，candidate精确用 `bisect_right(ends,start,0,i)`；仅 `pick>dp[-1]` 才取当前任务，相等时跳过；按同一 parent 路径恢复完整顺序。`U`独立70例、140个arm对照目标与旧函数完整 schedule 全同，包含ID2/10及反序输入。 |
| 独立正确性与支持域 | `scheduling_adapter.py:126` 拒绝非整数/bool、重复或越界ID、非正时长、超界ticks/weight；权重可负/零，空实例允许。`scheduling_kernel.py:90` 的穷举仅n≤12。独立检查另用全部组合及任意两区间的对称不重叠条件求目标，不调用产品 brute-force 或 DP 算期望；70例最大n10，含空、相邻、重叠、负/零weight与多个最优解。非正时长没有被扩展成新 endpoint 约定。 |
| 原输入 packing/hash | `scheduling_kernel.py:16`、`scheduling_adapter.py:126`：每条完整 jobs dict还原 `(start,end,weight,id)`，按原输入顺序编码为JSON数组，SHA与旧 `value_hash` 一致。独立 literal bytes hash及反序差异通过；不把数字ID转字符串，不依seed重新生成或截断输入。 |
| 完整预检成本 | `scheduling_adapter.py:145/:170/:259`：先核所有case/job/byte/schema/hash，再累计 `repetitions*n*(n-1)//2`、总jobs、n≤12时的子集数，全部通过后才 solve。测试大数组仅用于预检拒绝，并把求解器patch为失败。4096/25000/32实例、110,000,000 scan比较、131072子集及4,000,000结果字节等上限不能由spec增加。逻辑比较数不含排序、验证或原生bisect内部指令，不能等同CPU/内存硬隔离。 |
| 文件与元数据能力 | `scheduling_adapter.py:63/:92/:106/:197`：只捕获固定 `spec.json/jobs.json/license.md`，闭合字段、严格UTF-8/重复key/非有限JSON/原资产长度SHA，scope从原字节导出；复用 `source_evidence_adapter.py:128/:153` 目录/普通单链接文件与单次读稳定性检查。`U`额外hardlink拒绝；schema读取时solve/brute/generator/clock全部禁用仍通过。URL、license、generator名称是有界声明文本，不触发获取/代码运行。多个文件逐一稳定捕获，并不提供跨文件同时快照或同UID防篡改保证。 |
| 运行记录与计时 | `scheduling_adapter.py:259` 每个test arm各3次，顺序AB/BA/AB，其余各1次；保留所有原jobs、run、完整schedule/SHA、目标、seconds和counter。仅 `kernel.schedule` 被单独计时，验证/序列化成本不冒充此延迟。baseline full-scan比较数恰为n(n−1)/2，binary为0只表示无全扫描；bisect调用与DP/backtracking步数另记、内部比较为null未知。`U`用独立朴素回溯计数再核saved路径步数。 |
| AUDIT不重新求解/计时 | `scheduling_adapter.py:315/:415` 验保存jobs/hash、运行覆盖/顺序、可行性、权重和、完整序列、counter及保存计时摘要，`scheduling_kernel.py:102`只数保存路径，不执行DP。独立patch schedule/brute_force/jobs_for/bisect_right/perf_counter/time全部拒绝时audit仍成功，原ToolResult内容不变；返回solver/brute/new-timing计数均0。它不重新证明保存最优值，依赖已验证的原primary及不可变前驱。 |
| 不利结果与引用 | `scheduling_adapter.py:225/:243/:249` 保存每个case median、绝对差、可测speedup及faster/slower/tie；全部较慢和tie ID仍在adverse，所有原始运行不丢弃。jobs资产SHA+JSON case locator定位原件，case内完整jobs/selected整数ID可复核；audit引用原action/result参数。观测明示synthetic engineering、known exact DP、scientific_validation=false；时延改善不自动成为新算法、RSI或科学收益。 |

**已修复并保留的两个实际反例。** 初版adapter `1364f0b8...` 接受重封包后echo spec中的`3.0`，尽管原spec字节为整数`3`；原因是Python数值相等被当作精确spec相等。另外合法JSON数`1e309`转为inf后，在host capture的canonical编码外逸为未分类ValueError。反例均未调用solver，保留 `initial-source-findings.json`。owner最小改为canonical精确echo比较及有限JSON-float检查（`:63/:170`），增加两项回归；最终20项unit与独立反例重验通过，源packet不变。本审查未改冻结旧脚本或原研究证据。

**独立准备输入核对（仅D）。** 同一份packet原始字节SHA `c801e08c980caa8f56be6865eef149c98e3cad1c486b0abd39c37695611dcc3e`，1,338,429字节；snapshot `08ebf6433efb414ff139197036f5fa419ffe9e0f11037954f537d5a80e8b678d`。只读load/_checked通过：16case/20544jobs，包含4个原dev/validation及所有12个test（128/512/2048/4096×303/404/505）。每条还原整数tuple hash与旧72条test method/repeat身份行、4条dev/validation身份行匹配；没有用旧objective/schedule/time作新计算的期望。spec绑定的旧script/protocol/manifest SHA也相同。

上述输入未来需80次solver调用、95,599,712次baseline逻辑前驱比较；这些**只是预检数，不是本轮执行数**。最小case32，所以本packet穷举子集预算0；旧28个小正确性workload不在此packet中。只读核对将 schedule/brute/verify/generator/perf_counter/execute 六入口patch为拒绝，调用计数全部0，未生成、求解或重计时真实输入。owner准备脚本最后console摘要的KeyError及两次只读finalization由数据文档另存，不能把前置失败抹除。

**整层尚待验证。** adapter只检查predecessor ID/SHA格式；同项目/source、真实原action/result/evaluator/code身份、2累计tool/0fit/API、unknown预留、精确ID重放、恢复与四报告导出仍须 root 的原生controller/registry/core/report通道验证。保存audit的算术检查不能替代这些绑定，也不能凭可行性断言完全伪造的保存值是原最优结果。generic fixture通过不能代替真实16case范围冻结。此审查不新建控制器、实际课题或预算账本。

本轮命令均为 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python` 加 `/workspace/work/g5-native-algorithm-review/audit.py` 或 `schema-only.py`。Python3.12.14/Linux6.18.57；kernel仅stdlib，递归adapter identity/源依赖SHA在回执。20/20 unit、6/6独立检查、0fail/error/skip；真实准备workload求解0、fit0、model/API0、native action0。小工程夹具确实执行了DP与独立穷举。

旧Concrete101/RealEstate101/Slump90共292文件、旧G5 standalone11文件及5份G4 controls前后SHA一致，原真实研究累计50estimator账本不动。最终本地证据：

- `runs/g5-native-algorithm-review-20261113-01/final/receipt.json`，SHA `8f3965077dbba49f07f6c9c1daba88ac4327d75d9795dc0fd4904c0651ab9bd6`。
- `runs/g5-native-algorithm-review-20261113-01/final/schema-only-receipt.json`，SHA `ff13b8d9da1f42f621024062e3ecbee4f8d762155a22af6c51b76d9b6fda4ab3`。
- 初次反例 `runs/g5-native-algorithm-review-20261113-01/initial-source-findings.json`，SHA `abc325b477311252ae2a00aa6da58e74e8876f7692322f030fb75483b8ced570`；70例输入/原始两arm结果、日志及前后保护manifest均保留。

# 原生 CPU 归档重开与资产来源

本指南对应既有 `runs/sprint-005-delivery/native-cpu-reproduction-evidence.zip`：77,407,847 字节，SHA-256 `e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58`。它包含 930 个 ZIP 成员；`delivery-inventory.json` 列出 926 个 payload 文件及 494 个受保护原路径的映射。归档本身保持原样，本指南是后续交接文档，不能声称它已在这个旧 ZIP 内。

允许的重开目标是：在全新 scratch 中读取归档提供的两个既有 native manager，核对原始结果、报告、预算，并按原 ID 取回已保存响应。它不授权新建课题、重新排名/求解/拟合、重跑完整 driver、重置额度、迁移 producer 或再次执行原 attempt batch。

## 三层源码身份

| 身份 | 完整 commit | 用途与限制 |
|---|---|---|
| 科研执行冻结 | `8e8a206ed0b71479a6e774e36ed91fdb06e21c22` | 两个真实 native CPU case 的原执行源码；不把后续展示字节回填到此 freeze |
| 展示和安装 | `e638b5f3782d12a7b54bb9ede5596e5c4d9726cf` | 无取证任务正常空态、4 个方法中文名和构建 UI；已验证科研 code identity 未改变 |
| 本次 bundle tip | `e97c0a697ce641081b0a276f5dfa5d1a29762879` | 交付文档与完整 public Git 历史入口；不是替代前两者的新研究版本 |

`source/native-cpu-public-history.bundle` 同时包含以上历史对象。它的 SHA-256 是 `be55d7bf08e96083e8b62c8596a3ba6a70539e5b9aa84188565a01a72447fd8a`。选择源码时必须使用固定 commit，不能把当前 main 或 bundle tip 自动当作原科研版本。包内 clean-release wheel 来自 e638b5f，位于 `evidence/g6-release/release-attempt-02/dist/agentarts_autoresearch-0.1.0-py3-none-any.whl`，SHA-256 `574a83edc7eadb7d338bb43facd5c84b423e8494598d2ac5aadd3633e9d65295`。

## 离线恢复的前提

ZIP 提供源码、wheel、已保存 case、输入、报告、原件来源和验证证据；没有打包 venv、pip cache 或所有第三方依赖 wheel。只有在匹配的 Python 与依赖已就绪时，读取保存结果的恢复过程才可做到离线。干净机器从网络安装依赖是另一个阶段，不能称为这个包自带的完整离线安装。

匹配运行环境的实测依据是归档内 `evidence/g6-release/release-attempt-02/installed-closure.json`、`pip-freeze.log` 和 `evidence/g6-release/requirements-reproduction.lock`。历史 lock 首行关于 closure 未验证的文字保持原件；后续 native release 已另记实际 23-distribution closure，不回写旧 lock。关键数值依赖为 NumPy 2.5.4、SciPy 1.17.0、scikit-learn 1.8.0；完整 18 pins 和额外闭包以这些原文件为准。

现有干净 1.8 环境可作为已安装的第三方依赖来源，但必须记录真实来源及版本；产品源码和 case 必须来自 ZIP，不能悄悄使用主仓库、旧 site-packages 中的产品模块或外部原始 case。不得把依赖复用写成新建完整 clean install。1.9.1 环境已真实改变 Concrete/Real Estate 的历史分折；保留其失败，不降级或伪装为同次通过。详见 [运行环境与复现边界](runtime-reproduction-boundary.md)。

## 保留原 ID 的恢复顺序

1. 先核 ZIP 的字节数与 SHA，读取根 `README.md`、`delivery-inventory.json` 和 `archive-manifest.json`。清单映射是定位原字节的依据，不是允许改写原声明的授权。
2. 使用新 scratch，核对归档 member 清单和文件哈希，再恢复固定源码。仅解压/复制所需原件；不覆盖已有输出、manager 或归档。
3. 确认两个归档 manager 的 `workbench.sqlite` 和 `projects/<import-slot>/project.sqlite` 都已存在，再构造读取/恢复入口。若 DB 缺失、哈希不符或原请求 ID 不存在，停止并保留错误；绝不能由“找不到”自动走 create。
4. 仅重放已经被 DB 接受、请求正文 digest 相符的 `native-primary`、`native-audit`、`native-wait`、`native-report` 原请求。原报告 replay 读取原文件，不重新导出报告。比较时只允许移除响应的 `replayed` 标记，不改科学字段。
5. 保存实际源码/模块来源、依赖版本、原请求 ID、结果/附件 SHA、预算和 manager 全文件前后清单。预期新增 fit、排名、求解、模型、来源提取和研究 action 均为 0；接口限本地只读。

两个 manager 在 ZIP 中的根路径分别为 `repo/runs/g5-native-cases-20261113-01/retrieval/manager/` 和 `repo/runs/g5-native-cases-20261113-01/scheduling/manager/`。恢复其完整目录关系，不只复制单个 SQLite 文件。原始 packet、freeze、完整结果和报告同时保留；项目 ID、snapshot_ref、action/result/source/report 身份和累计额度不变。

原件的绝对路径声明仍指向当时的 `/workspace/...`；`delivery-inventory.json` 的 `protected_original_archive_paths` 给出 494 个对应 member。不得批量字符串替换这些声明或改写冻结输入以让验证通过。重定位只在明确的只读副本访问层完成，并另记映射；遇到未覆盖路径要报告缺口。

当前实现入口是 `scripts/reopen_native_cpu_delivery.py`，分开执行 prepare 与经独审绑定的 recover。在仓库根运行，下例使用示意的新目录；实际须替换为 `/workspace/work/g6-archive-reopen-<unique>` 下尚不存在、未被其他尝试使用的目录。已有 01 目录不得重跑：

```sh
python scripts/reopen_native_cpu_delivery.py prepare \
  --archive /workspace/auto-research-agentarts/runs/sprint-005-delivery/native-cpu-reproduction-evidence.zip \
  --root /workspace/work/g6-archive-reopen-example-new
```

prepare 校验并恢复完整 930-member `payload/`，从内部 bundle 生成 `final-source/`、`science-source/`、`release-source/` 三个固定 checkout，并从归档 wheel 用 `--no-index --no-deps --no-compile --target` 安装全新 `target/`，核对 177 个包文件。其产物 `archive-validation.json` 与 `prepared.json` 只代表准备完成。第三方依赖仍由外部 `/workspace/work/g6-native-release-20261113-01/venv` 提供，不从 ZIP 安装依赖。

独审必须提供一份新的真实 JSON，`schema_version=g6-native-archive-reopen-review-v1`、`status=approved`，精确绑定这个 root、实际 `prepared_sha256` 与 `helper_sha256`，并写明 reviewer 和 limitations。不要自行填写 approved 来绕过审查，也不能套用旧 G5/G6 receipt。取得该文件后才执行下面命令，把占位路径换成实际独审文件：

```sh
python scripts/reopen_native_cpu_delivery.py recover \
  --root /workspace/work/g6-archive-reopen-example-new \
  --review /绝对路径/本轮真实独审.json
```

recover 由干净 Python 的 `-I -B` 子进程运行，产品模块只能从新 `target/` 加载，case 从 `payload/` 下已存在的两个 manager 打开；预定每域仅 4 个原 ID，共 8 次保存重放。3 版计划、source cap 和 import 仅从原 DB 读验，不重新执行 create/source-cap/import。成功必须有 `recovery.json` 及 `attempt-final.json` 的实际结果，不能从 prepare 推断。失败保留 `prepare-error.json`、`recovery-error.json` 或最终 unknown receipt 和日志，不自动重试或新建 ID。已有 [clean wheel 保存接续](native-release.md) 是先前独立 scope 的证据，不替代本轮 archive-only 演练。原件补充包不作为此 helper 的 native case、源码或依赖输入。

## 保留的 01 准备与恢复失败

`/workspace/work/g6-archive-reopen-20261113-01` 的实际 prepare 已通过：930 members 的 CRC/bytes/SHA、bundle 三个固定 pin 与干净 checkout、177 个 source/wheel/target 包文件一致；target 的全部 187 文件另行冻结。`prepared.json` 的 schema 是 `g6-native-archive-reopen-prepared-v1`，状态保持 `prepared_not_replayed`，SHA-256 `ab3d6fa2e6b5488a9acdbb49a7aa887a5a85dd94d6abfd344806104e17bee7f0`。

01 随后的真实 recover 失败，**没有完成任何原 ID 重放**。失败在归档 `target` 的产品导入链中：h5py 调用 stdlib `platform.processor()`，其固定 `uname -p` 探测被严格 Popen 守卫阻止。此时尚未绑定 manager 或提交原 ID 请求；守卫记录 1 次 Popen 尝试，真正启动的该探测进程为 0，fit/compute/create/export/model/原 case 存储守卫计数均为 0。不是“产品导入前失败”，也不是 8 次 replay 通过。`recovery-error.json` 的 `completed_saved_replays=0`；`attempt-final.json` 状态为 `unknown_preserve_no_retry`，`recovery.json` 不存在，01 整体和日志保持不变，不在该目录重试。

外层 observer 另核旧 ZIP、494 个受保护原文件及路径集合不变，01 的 930-member payload 和 187-file target 也不变；这些保护清单仅供外层前后核验，没有作为恢复输入。证据在 `/workspace/work/g6-archive-reopen-precheck/`：

| 回执 | SHA-256 |
|---|---|
| `prepare-protection-receipt.json` | `99e4a8f24552b373ded2635aefb6e4f5ec37eae23b5feb2e40981d145f5fac72` |
| `failed-recover-protection-receipt.json` | `4e85c923c232d555f06f42315cc4a041df6ac00f64af637d654aba7bc9ed7339` |

窄修 helper 已以 `82d44b4f9a9d48e1a223b07ca97872cb4ef35563` 提交，脚本 SHA-256 `da287780a3a694719d80c4e1d615fb9661e9facde45eb2b0b2f6be72c7c6b83f`。它在文件/import/网络守卫已经安装后，先完成真实 `platform.processor()` 元数据预热；临时 launcher 只允许系统 `uname -p` 精确调用一次，并记录 binary/argv/stdout/returncode/value，随后恢复严格 Popen 守卫再导入 h5py/产品。网络从 bootstrap 前就禁止。静态审查与小型 clean-env fixture 已通过，fixture 实际发生 1 次 uname，随后的 h5py 导入没有 Popen；这不是实际案例重放结果。

因此须分开报告外部依赖 bootstrap 的受控 subprocess 与 saved-recovery 阶段的严格 subprocess 计数，不能声称 whole child 的 subprocess 为 0。完整 replay 阶段的 fit/排名/求解/source/model/report 计算守卫没有放宽。02 使用新 scratch 和新 exact review；它只隔离恢复尝试，不是新研究或新额度，两域原 DB 的已用 2 次工具额度保持。

## 02 实际恢复通过：仅取回保存结果

`/workspace/work/g6-archive-reopen-20261113-02` 已实际完成 prepare 和一次经新独审绑定的 recover。`recovery.json` 的 schema 为 `g6-native-archive-recovery-v1`，状态 `saved_archive_recovery_verified`；`attempt-final.json` 为 `completed`。检索与调度各取回 4 个原 ID，共 8/8 次 `replayed=true`。primary/audit 保存响应为 `completed`，wait 为 `waiting`，report 为 `exported`；这些是原响应状态，不是本轮重新派发或导出。3 plans、source cap、import 只读核验，每案 2 个已用工具额度、0 预留及 fit/model/source 使用量不变。

实际 child bootstrap 启动 1 次系统 `/usr/bin/uname -p`，returncode=0，stdout 是 `unknown\n`，`platform.processor()` 的真实值是空字符串；没有伪造处理器值。bootstrap 网络为 0。随后严格保存恢复阶段的 subprocess、network、fit、新排名/求解/模型/来源提取/报告生成及原存储 fallback 守卫均为 0。整个 child 有这 1 次 bootstrap subprocess，不能描述为全流程零子进程或零失败。

97 个实际 loaded 产品模块全部来自归档 wheel 新装的 `target/`；177 个产品/资源文件与归档 wheel、e638b5f 源码字节相同。完整 187-file target、930-member payload、旧 ZIP、494 个受保护原文件和 10 个完整路径集合前后不变；01 的 6 个失败控制原 SHA 保持。依赖仍透明复用外部 clean1.8 环境，实际 Python 3.12.14、NumPy 2.5.4、SciPy 1.17.0、scikit-learn 1.8.0；没有从 ZIP 提供依赖或新建另一完整依赖环境。

[独立审查](archive-reopen-independent-review.md)接受这个有限 scope：prepared 核对 1838 项、保存结果核对 1510 项，另核 494 个原文件及 10 个 nameset；审查者没有重放原 ID。其 checker 的 3 个历史失败版本也保留，不改成无失败历史。完整机读摘要见 [archive-reopen-results.json](archive-reopen-results.json)，只收身份、计数和原始回执定位，不复制 97 条模块路径表。

| 02 原始回执 | SHA-256 |
|---|---|
| `prepared.json` | `f31c5adc6fc1e73ad7e5e308e9fc9843b76beaca6eb1e533e47cf83e96c57d21` |
| `independent-review.json` | `54f00e2e8c9d1627ca2b5a32e1dd6d812862a954f814538b2bad022b68199db0` |
| `recovery.json` | `458e1712ba9f662866d17466b1876451a7e41e53aee867e5b7f4b0569ce06a41` |
| `attempt-final.json` | `dc5b1ad20ff2a16a7dabc836e682e53a8248ac6398f42baf73a9839fa95d2a88` |
| `dependency-bootstrap.json` | `43a425a53e3cd06837069d856a0ca3b1a98e920ce4c498bb8cbf32a9f5fd09f6` |
| 外层 `recover-02-protection-receipt.json` | `3a771930419af4a62401bdbd65d7af75c72b188d1e770b3008d9b039423a6c25` |
| 独立 `runs/g6-archive-reopen-review/final-review.json` | `299f0139529dfc3d629ba92d7506a4d75e09241b3829049830530bf8767cad70` |

结论限于同机合作式守卫下的归档保存恢复；它不建立 OS 隔离、科学模型 refit 复现、完整离线依赖安装或原 G0/G6 全 Gate 通过。开发 token 和金额仍未知，不记为 0。

## 资产许可与原件定位

以下路径均相对于 ZIP 根。本轮只核对保存的原声明、来源及字节，不新增许可证或给出法律保证。官方页面是当时保存的页面快照；完整法律条款仍以其原链接为准。

| 资产 | 已保存声明与来源 | 原件位置及使用边界 |
|---|---|---|
| SciFact claims / BEIR queries 和 qrels | SciFact `LICENSE.md`：claims 与 evidence annotations 为 CC BY 4.0；作者 Wadden 等，EMNLP 2020。qrels 是从 `cited_doc_ids` 得到的引用文档标签 | `sources/g5-original-inputs/SCIFACT-LICENSE.md`，等字节副本 `sources/native-retrieval-inputs/license.md`；BEIR ZIP、原 SciFact tar、JSONL/TSV 同目录保留。归档 `repo/docs/execution/g5-local/source-provenance.md` 记录原 repo commit、来源 URL、归一化差异与分割身份。保留作者与来源归属；引用命中不等于 support/refute |
| SciFact abstracts / BEIR corpus | 原 SciFact 声明：来自 Semantic Scholar S2ORC，ODC-By 1.0；SciFact 代码的 Apache-2.0 不代替数据许可 | 同一原 LICENSE 的 Abstracts 段；`sources/g5-original-inputs/scifact/corpus.jsonl` 和 `sources/native-retrieval-inputs/corpus.jsonl`。保留数据库/来源归属，不把全部数据统称 CC BY |
| UCI Concrete Compressive Strength | 保存的 UCI 页面声明 CC BY 4.0，I-Cheng Yeh，DOI `10.24432/C5PK67`；原 README 另要求保留 Yeh 与 1998 年论文版权/出处 | `repo/runs/cloud-concrete-local-20261113-01/source-bundle/sources/uci-concrete-page.md` 与同目录 `Concrete_Readme.txt`。两份原声明同时保留，不用新许可证覆盖旧 notice |
| UCI Real Estate Valuation | 保存的 UCI 页面声明 CC BY 4.0，I-Cheng Yeh，DOI `10.24432/C5J30W` | `repo/runs/g3-local-transfer-20261113-01/real-estate/source-bundle/sources/source-1-official-page.md`；完整原作者和引用以页面及 source-bundle manifest 为准 |
| UCI Concrete Slump Test | 保存的 UCI 页面声明 CC BY 4.0，I-Cheng Yeh，DOI `10.24432/C5FG7D`；原 names 文件保留 | `repo/runs/g3-local-transfer-20261113-01/slump/source-bundle/sources/source-2-official-page.md` 与同目录 `source-1-slump_test.names`。原 names 本身没有独立许可段，不把它写成许可文本 |
| 合成 weighted interval jobs | 项目本地固定生成器产生的 synthetic 工程输入，没有引用外部调度数据集 | `sources/native-scheduling-inputs/jobs.json`、`spec.json`、`license.md`。note 仅记来源，明确未创设新许可，也没有声称 public domain；这不是新算法发现 |
| 产品/前端代码及第三方组件 | e638b5f 源树没有顶层 LICENSE；不能替项目作者补造 MIT/Apache 等许可。第三方 notices 与 bundle 字节单独保留 | bundle 中固定源码的 `THIRD_PARTY_NOTICES.md`、`src/autoresearch/web/vendor-licenses.txt` 及 wheel 内相应资源；第三方许可不自动授予整个产品的新许可 |

三份 UCI 研究输入的转换后 CSV、source snapshot 和来源原件在各自 manager/source-bundle 中保留；这个 ZIP 成员中没有独立的 UCI 原下载 XLS/XLSX 或 ZIP。它可用于保存案例核验，不应被描述成包含全部上游原下载文件的镜像。SciFact 的两个实际下载压缩包则确实在包中。

该 UCI 缺口随后由独立补充包闭合：`runs/sprint-006-originals/uci-original-downloads-supplement.zip`，209,918 字节，37 members，SHA-256 `1930516373006e6cb44b00d8d43fc512dcc82e44890680b066560f0b013a1cc7`。旧 77MB ZIP 的身份不变；补充包内 `supplement-manifest.json` 明确关联旧包 SHA，旧包并未被重写为包含这些文件。

正式小索引 [originals-supplement.json](originals-supplement.json)记录补充包、原包、manifest、创建回执和薄 packer 的 bytes/SHA，以及三条转换来源链；详细逐文件 allowlist 继续以原 `supplement-manifest.json` 为准，没有重打包或覆盖补充 ZIP。

补充包保存 34 个 payload：三份原下载 ZIP、Concrete XLS / Real Estate XLSX / Slump `.data` 和 `.names` 原 member、研究转换实际使用的官方 CSV、旧 source manifests、转换 receipts、字段映射、许可页及原 README。全部 36 条旧 source-manifest 声明已与现存文件匹配，3 条原输入→旧 conversion receipt→77MB 归档 case CSV 的 SHA 链全同。Concrete XLS 是从旧 ZIP 原 member 直接读取；其单独 member SHA 在本轮观察，不冒称旧 receipt 已单独登记该 SHA。Concrete 和 Real Estate 原转换使用的是官方 CSV，Slump 使用 `.data`；Excel 仅为下载原件核对，不是训练直接读取的格式。

`scripts/archive_original_data_supplement.py` 只读核对并打包，没有重新转换或执行其中代码。`supplement-manifest.json` SHA-256 为 `939403cff8e5a1187aa163e9f30a60d93a937f30ed4fcad8a22841b337cf0490`；`create-receipt.json` 另记 ZIP CRC、全部 payload SHA、原输入及旧 ZIP 不变，0 下载/转换/fit/model/预算变更。原准备 manifest 的 `prepared_not_created` 状态保持不变，创建成功由后一个 receipt 表达。包中未带 Firecrawl request/index IDs、浏览器/依赖缓存或凭据，也未新增产品许可证。

本轮已读并与 inventory 逐字节核对以上 8 个许可/来源文件；SciFact 原声明及 native 副本 SHA-256 同为 `56ee69bc639cbab8f0b2e4b67091ec5e9390aa99a1d65f0a35e4274686c9a806`，synthetic note 为 `123c4a15a5b070596c78b9245bc27afe4e9f9bd74b923eb15b5c7dd67a22bf96`。其余各原件的完整 bytes/SHA 均可按表中 member 从 `delivery-inventory.json` 查得，不另维护会漂移的副本。

演示文件位于 `evidence/readonly-demo/g5-native-demo-20261113-01/final-metrics-focus/`。本轮从 ZIP 读取、核对并实际查看两张 `*-frame-14s.png`：检索真实 test 指标与调度 adverse case/分组计数可读。它们展示已保存记录，不是本轮重跑研究的证据；原视频和看帧 receipt 保持原样。

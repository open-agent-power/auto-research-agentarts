# 软件原件捕获：稳定文件与真实追加的核对

现有S01记录中，稳定文件捕获成功，读取期间的一次真实追加被拒绝。A40进一步固定了官方CPython 3.12.14源码，完整核对公开`os.lstat`与`os.fstat`调用链，并把相关选区正式读入原软件项目。源码支持两种API可能返回不同含义的ctime，现有实现因此继续在同一API内检查ctime变化。

## 本机记录与比较规则

S01保存的Python字符串为`3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]`，环境为`os_name=nt`、`sys_platform=win32`。稳定文件的跨API差异只有`st_ctime_ns`：`lstat.ctime_ns`等于创建时间，`fstat.ctime_ns`等于该记录中的修改时间；两次lstat之间、两次fstat之间都保持稳定。原字段见[A40历史记录摘要](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/historical-s01-summary.json)，完整原件见[S01保存记录](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/source-evidence/S01-observations.json)。

当前读取器保留以下比较方式：

| 比较位置 | 实际检查 |
| --- | --- |
| `_file_identity`，142–146行；158行调用 | 跨fstat与lstat比较dev、ino、size、mtime_ns、birthtime_ns、mode、nlink |
| `_stable_identity`，149–150行 | 在以上字段中加入ctime_ns，供同一API前后检查 |
| `_read_file`，153–166行 | 比较同一fd的两次fstat、路径的两次lstat，并核对读取字节数与大小上限 |

见[当前实现](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/src/autoresearch/source_evidence_adapter.py:142)及[A34冻结副本](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/bundle-local/sources/source_evidence_adapter.py:142)。跨API的ctime不直接比较；同一API前后ctime改变仍须拒绝。

S01的`actual_midread_append`通过hook安排时机：真实读取后、下一次真实fstat前，向任务自有副本执行append/fsync。文件由14949增至14997字节，fstat的mtime/ctime随之变化，实际返回`EVIDENCE_CHANGED`。hook只控制时机，未伪造stat。原正常捕获与真实追加结果继续保留，见[操作者核对第2–5行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/source-evidence/operator-findings.txt:2)。

旧S01副本、项目冻结原件与当前代码的上述三个函数，逐函数文本和忽略位置的AST相同；全文件身份不同。比较范围见[核对第9–11行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/source-evidence/operator-findings.txt:9)。

## 精确版本源码支持的解释

A40通过官方标签`v3.12.14`固定到提交[`2abcf904b8dac8c999d2b3aac76681abb333798a`](https://github.com/python/cpython/tree/2abcf904b8dac8c999d2b3aac76681abb333798a)，身份回执见[version-identity.json](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/version-identity.json)。这补齐了A36使用3.12分支文档时缺少的精确源码版本。

| 公开调用链 | 固定源码中的结果 |
| --- | --- |
| `os.lstat` → `os_lstat_impl` → `posix_do_stat` → `win32_lstat` → `win32_xstat` | 入口把follow_symlinks设为0，Windows路径进入win32_lstat；win32_xstat在返回前把birthtime及其纳秒部分复制给ctime。见[公开入口3087–3093行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Modules/posixmodule.c#L3087-L3093)、[分派2660–2722行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Modules/posixmodule.c#L2660-L2722)、[复制2139–2171行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Modules/posixmodule.c#L2139-L2171)。 |
| `os.fstat` → `os_fstat_impl` → `FSTAT` → `_Py_fstat_noraise` → `_Py_attribute_data_to_stat` | Windows的FSTAT指向内部辅助函数。磁盘句柄取得FILE_BASIC_INFO后，CreationTime写入birthtime，ChangeTime写入ctime；公开os_fstat_impl成功后直接打包，没有再把birthtime复制回ctime。见[公开入口11174–11195行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Modules/posixmodule.c#L11174-L11195)、[宏495–503行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Modules/posixmodule.c#L495-L503)、[句柄取值1233–1289行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Python/fileutils.c#L1233-L1289)、[时间转换1107–1127行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Python/fileutils.c#L1107-L1127)。 |
| 两条链 → `_pystat_fromstructstat` | 完整打包函数分别输出ctime和birthtime，没有改写二者。见[2535–2654行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Modules/posixmodule.c#L2535-L2654)；Windows在[1833行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Modules/posixmodule.c#L1833)启用纳秒字段。 |

因此，在该版本磁盘文件的成功路径上，lstat的ctime表示创建时间，fstat的ctime保留ChangeTime。这与S01中跨API不同、同API稳定的记录一致；创建时间与变更时间恰好相等时，两者也可返回相等数值。完整说明和可读取范围见[源码分析](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/clock-findings.md)及[范围索引](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/clock-source-ranges.json)。

该精确版本的[官方文档3042–3088行](https://github.com/python/cpython/blob/2abcf904b8dac8c999d2b3aac76681abb333798a/Doc/library/os.rst#L3042-L3088)将Windows的ctime字段标为弃用，并推荐birthtime表达创建时间。上述公开调用链进一步区分了两个入口的实际取值。

S01的Python字符串包含`main`和构建日期，没有该官方提交身份。固定官方源码可以解释观测对应的实现路径，不能据版本号认定历史本机二进制就是该提交的未修改构建。

## 原软件项目的实际消费

A40继续使用`project-5fec60e579854cdbb6d3f71abd0d6090`。项目从v15推进到v21：显式升级为v16，登记资料后为v17，完成来源读取后为v21。原控制器的`operator_assistant`来源读取已完成，进程退出码为0，行动为`action-a4737c18cc2fad5bdc98983d1bc081c2`；来源额度从3/8变为4/8，本地方法仍为1/1，原生模型请求仍为0。见[读取回执](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/read-source.stdout.json)。

[资料清单](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/bundle/manifest.json)的12个选区已完成读取，每项提取文本均与冻结源对应行逐一相同。升级、登记、推进的三个原请求ID重放均以退出码0完成，项目状态和宿主模型记录保持不变，见[A40核对记录](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/validation.json)。[A40消费后的默认上下文](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/context-after.json)共5条证据，均来自该轮固定官方源码；当时候选与阻塞均为空。

宿主CLI仍为原2/2次、报告估值0.124035USD，超过0.10USD配置阈值；[A34第二次CLI失败](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/README.md)的记录保留。A40未增加模型调用，现金结算与历史费用仍为unknown。

## A47：当前环境与两次历史运行分开

2026-11-04补充了当前环境元数据及历史记录可获得性核对。S01与原软件项目A7的正常捕获是两次运行，不能把它们的目录或设备字段混为同一条记录。

S01原件的`/case_directory`明确指向D盘任务自有目录`runs/s01-source-identity-20261102/case-b0915f2a94`。脚本第14行将ROOT设为自身目录，第114–117行在ROOT下创建case目录和正常副本并读取stat。见[原evidence第18行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/s01-source-identity-20261102/evidence.json:18)、[脚本第14行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/s01-source-identity-20261102/run_software_task.py:14)及[第114行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/s01-source-identity-20261102/run_software_task.py:114)。

| 历史记录 | 保存的st_dev | 与本次现有目录的比较 |
| --- | --- | --- |
| S01正常样本 | `16340799956857048985` | 与当前D盘相同 |
| A7行动`action-03e4d5aa78628a590545ebbbae8db8f2`的正常捕获 | `11259831322542394960` | 与当前C盘相同 |

两条设备号的依据分别是S01原stat及[A7保存行动](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a7-domains-20261102/software-step.json)。当前TEMP位于C盘；它不能回填S01或A7的历史路径，设备号与当前卷相同也不证明历史卷映射或文件系统始终不变。

当前系统报告为Windows 11、`10.0.26200`，当前C、D两卷均为NTFS。当前Python完整字符串仍为`3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]`，与S01保存字符串相同；当前`sys._git`没有提交标识。

当前产品`.venv`指向`C:/Users/chenfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`作为base解释器。本地runtime manifest声明bundle为`26.1026.10807`、Python为`3.12.14`、平台为`win32/x64`；该base Python的PE版本资源也报告`3.12.14`。完整当前观测见[current-runtime.json](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a47-current-runtime-provenance-20261104/current-runtime.json)。

这些是当前观测及本地文件声明，不是历史二进制、构建源码提交或历史OS/文件系统的认证。已查历史材料仍没有解释器路径、base解释器、二进制身份及OS/文件系统记录；可获得性范围与缺字段见[修正后的历史核对](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a47-current-runtime-provenance-20261104/history-availability.corrected.json)。A40源码解释继续保留，不由这些当前字段进一步确认历史ctime差异的成因或跨环境兼容性。

### 来源读取与保留的失败

原软件项目从v21登记资料至v22，首次读取到v26时因`UNSUPPORTED_LOCATOR`失败：该提取器不支持所用JSON pointer选区。初次进程退出码为2，原失败及其资料包保留，见[首次读取输出](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a47-current-runtime-provenance-20261104/read-source.stdout.json)。

随后另建物理文本行选区的资料包，以新请求登记到v27，再读取到v31成功。9个选区的提取文本均与冻结原件相应行一致；未用新输出覆盖原失败，见[修正资料清单](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a47-current-runtime-provenance-20261104/bundle-corrected-lines/manifest.json)与[成功读取输出](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a47-current-runtime-provenance-20261104/read-source-corrected.stdout.json)。

新登记、新读取以及旧failed父请求均按原ID核对，状态与日志没有新增。旧failed原ID核对的进程退出码为0，业务状态仍是`failed`，只表示成功读回原失败，不能写成原读取成功。

本轮两次来源尝试为一次失败、一次成功，来源累计从4/8到6/8；本地方法仍1/1、原生模型0、拟合0。宿主原2/2次CLI及0.124035USD超阈值、第二次失败的记录不变；hiMSC仍v36，两个工作台管理目录也未变。见[消费与重放核对](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a47-current-runtime-provenance-20261104/consumption-validation.json)。

新的默认context共5条，包含两次历史运行的区分及历史缺字段记录，候选与阻塞均为空；不是全部当前OS段都已进入默认top5。A47没有重跑S01探针、真实追加或旧实验，没有调用模型、启动服务或建立新测试环境。

## A41历史报告与核对入口

A41当时从原软件项目v21导出资料，导出时核心快照与宿主快照均与原项目一致，状态和模型日志未改变；原A34报告当时的核心快照已过期，见[导出前状态](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a41-current-software-report-20261104/before.json)。A47后核心已到v31，A41的v21包不含本次来源、核心快照已过期，宿主模型记录保持原样。本轮未重导PDF，也未另交v31补件ZIP；下一步从v31导出完整报告，A41包继续作为历史证据。

历史阅读入口为[v21 PDF](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a41-current-software-report-20261104/report/report.pdf)；逐项核对使用[report.json](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a41-current-software-report-20261104/report/report.json)、[input.json](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a41-current-software-report-20261104/report/input.json)和[文件身份清单](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a41-current-software-report-20261104/report/manifest.json)。具体字段路径见[队友核对指南](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a41-current-software-report-20261104/review-guide.md)。

PDF共6页，提供有界节选；12个新增选区完整保存在report.json的source_selections中，连同历史选区共18条。input中的27个附件均与原项目原件逐字节对应，包含A40的6份来源及其中的官方LICENSE；原始字节可沿source_manifest核对。manifest所列四个导出文件的身份均已核对。

分享入口为[v21完整资料包](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a41-current-software-report-20261104/software-review-v21.zip)，包含上述导出文件、清单与核对指南。该资料用于核对软件v21已有证据、源码解释和宿主CLI记录，未增加研究行动或模型调用。

## Limitations

S01是当时环境的一次受控真实文件检查；A40完成固定源码分析，A47补充当前环境与历史材料核对及选区消费，没有重新进行文件实测，也不表示模型已经阅读这些内容。当前Windows版本和NTFS卷类型已观测，历史二进制与官方提交的对应关系、历史OS构建及文件系统仍缺；各种链接及全部竞态也未穷尽。源码与历史观测一致，尚不足以确认S01中差异的实际成因。三个函数的一致性不覆盖整个捕获系统；源码解释和来源读取也不能证明独立用户价值或科研资格。现金结算和历史费用继续为unknown。`runs/`证据位于本机忽略目录，普通源码克隆不包含。

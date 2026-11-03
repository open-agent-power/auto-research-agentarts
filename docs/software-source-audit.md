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

[资料清单](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/bundle/manifest.json)的12个选区已完成读取，每项提取文本均与冻结源对应行逐一相同。升级、登记、推进的三个原请求ID重放均以退出码0完成，项目状态和宿主模型记录保持不变，见[A40核对记录](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/validation.json)。[消费后的默认上下文](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a40-cpython-version-evidence-20261104/context-after.json)共5条证据，均来自本轮固定官方源码；当前候选与阻塞均为空。

宿主CLI仍为原2/2次、报告估值0.124035USD，超过0.10USD配置阈值；[A34第二次CLI失败](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/README.md)的记录保留。A40未增加模型调用，现金结算与历史费用仍为unknown。

## Limitations

S01是当时环境的一次受控真实文件检查；A40完成固定源码分析和选区消费，没有重新进行文件实测，也不表示模型已经阅读这些内容。历史二进制与官方提交的对应关系、OS构建、文件系统、各种链接及全部竞态仍未证实；源码与历史观测一致，尚不足以确认S01中差异的实际成因。三个函数的一致性不覆盖整个捕获系统；源码解释和来源读取也不能证明独立用户价值或科研资格。现金结算和历史费用继续为unknown。`runs/`证据位于本机忽略目录，普通源码克隆不包含。

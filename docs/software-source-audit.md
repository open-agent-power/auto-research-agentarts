# 软件原件捕获：稳定文件与真实追加的核对

问题是：在Windows上捕获资料文件时，能否接收没有变化的文件，同时拒绝读取期间真的发生的追加？现有S01记录支持在其当时环境保留当前比较方式：正常捕获成功，一次真实追加被拒绝。A36把相关原件正式读取进原软件项目，补齐可追溯的解释；没有重跑旧实验。

## 为什么要区分两种比较

S01保存的环境为Python3.12.14、`os_name=nt`、`sys_platform=win32`。同一稳定文件的路径查询`lstat`与已打开文件查询`fstat`之间，只有`st_ctime_ns`不同；各自读取前后的值保持稳定。因此，跨API数值不同不能直接当成文件发生变化，同一API前后变了仍须拒绝。原始字段与观察见[操作者核对第2–5行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/source-evidence/operator-findings.txt:2)及[保存的S01原记录](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/source-evidence/S01-observations.json)。

当前读取器这样处理，冻结副本保留相同片段：

| 比较位置 | 实际检查 |
|---|---|
| `_file_identity`，142–146行；158行调用 | 跨`fstat`与`lstat`比较dev、ino、size、mtime_ns、birthtime_ns、mode、nlink，不比较ctime |
| `_stable_identity`，149–150行 | 在以上字段中加回ctime_ns，供同一API前后检查 |
| `_read_file`，153–166行 | 比较同一fd的两次fstat、路径的两次lstat，并核对读取字节数与大小上限 |

见[当前实现第142行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/src/autoresearch/source_evidence_adapter.py:142)及[已捕获副本第142行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/bundle-local/sources/source_evidence_adapter.py:142)。这段实现仍检查ctime，只在相同API内比较它。

## 实际追加有没有被拦住

S01的`actual_midread_append`用hook安排时机：真实读取后、下一次真实fstat前，向任务自有副本执行append/fsync。文件由14949增至14997字节，fstat的mtime/ctime随之变化，实际返回`EVIDENCE_CHANGED`。hook只控制时机，未伪造stat；A34和A36都未重放这次变更。见[操作者核对第5行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/source-evidence/operator-findings.txt:5)。

旧S01副本、项目冻结原件与当前代码的三个函数，逐函数文本和忽略位置的AST相同；全文件身份并不相同，不能写成“历史代码始终未变”。比较范围与字节差异见[核对第9–11行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/source-evidence/operator-findings.txt:9)。

## 官方资料能支持什么

已捕获的[CPython 3.12分支官方文档](https://raw.githubusercontent.com/python/cpython/3.12/Doc/library/os.rst)说明：`fstat(fd)`返回文件描述符状态，与`os.stat(fd)`等价；Windows上的`st_ctime`及`st_ctime_ns`在3.12被标为弃用，创建时间建议使用birthtime字段。对应本地坐标为[1057–1067行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/bundle-docs/sources/python312-os.rst:1057)、[3042–3050行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/bundle-docs/sources/python312-os.rst:3042)、[3064–3074行](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/bundle-docs/sources/python312-os.rst:3064)。这些说明帮助解释字段与版本边界，具体跨API差异仍以保存的本机观测为依据。

## 本次推进到哪里

A36沿原项目`project-5fec60e579854cdbb6d3f71abd0d6090`，通过原控制器完成一次`operator_assistant`来源读取，行动为`action-884319a1cbfbf5c9dbd39c52496cb7cd`。项目由v11到v15，来源读取由2/8到3/8，本地方法仍1/1、原生模型仍0；读取选区为当前代码142–166行、操作者核对1–13行。原始捕获文件随资料包保留，见[本轮读取回执](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a36-software-source-followup-20261104/read-source.stdout.json)。

[新的选择上下文](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a36-software-source-followup-20261104/context-after.json:1)优先列出这两项，默认共5项证据；操作者记录在该默认节选中展示1–9行，完整1–13行可沿原件核对。当前没有可执行候选，提取文本进入上下文不表示模型已经阅读。CLI仍为原2/2次、报告估值0.124035USD，超过0.10USD配置阈值；[A34第二次CLI失败](D:/XiangMuLuoDi/Development/ICT/track2/auto-research/runs/a34-two-model-decisions-20261104/README.md)的事实保留，A36没有新增模型调用。

原请求ID重放后，项目状态与宿主模型日志保持一致，没有新增行动；原数值行动和前两次来源行动保留原记录。来源读取使原A34报告过期，本轮交付当前核对文档，未生成新PDF。

队友现在可用上述代码与原始观察检查解释是否对应实际字段。若要补新的兼容性证据，缺口是具体OS构建、文件系统及新环境中的稳定捕获/真实追加记录；现有结论无需通过重复调用模型来扩大。

## Limitations

S01是当时环境的一次受控真实文件检查，A36是原件选区提取，不能当作新一轮文件实测。官方材料来自3.12分支，不是精确3.12.14实现快照；OS构建、文件系统、各种链接与全部竞态仍未证实。三函数片段不覆盖整个捕获系统，来源提取与代码一致性也不能证明独立用户价值或科研资格。资料声明与解释仍待独立核对，现金结算和历史费用继续为unknown；`runs/`原件在本机忽略目录，普通源码克隆不包含。

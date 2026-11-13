# G5 原生课题原ID与移址恢复独立核对

**最终四项均通过。** 两个已完成课题各在原位置和复制manager后重放：每项102检查、18次原ID调用；合计408检查、72次调用，没有新增研究行动。独立算术核验另由保存工件验证器负责，本项不重新排名、计分、求解或计时。

| 课题 / 位置 | `replay.json` SHA256 |
|---|---|
| retrieval / 原位置 | `4d841b170250e9f0be0cb2b22740d5314941edc05baaa46e5115c2685f681b4d` |
| retrieval / 移址 | `235aae596aaf98eae38026e39248363000a635e135642c13a0da584ffa952c68` |
| scheduling / 原位置 | `5cb0ae1a6e25d0e4563de0458e09d03e7620ac3fd50b978ffe0920a89d69d843` |
| scheduling / 移址 | `337358022e17b82211932a3b49e73c951878377a4e0c48d4ddd6b3476a95cbc3` |

完整回执在`/workspace/work/g5-native-replay-20261113-01/{retrieval,scheduling}-{original,relocated}-pinned-02/`。总回执`summary.json` SHA `8ea065bce37fbc29b96b62f25225ee6e6a7266ea003fbac5c792d4b43b1f4c3c`，包含各artifact前后manifest、原件访问记录、调用响应、代码归档及保护清单。

执行使用干净pin `work/native-cpu-source-8e8a206`：HEAD精确`8e8a206ed0b71479a6e774e36ed91fdb06e21c22`、完整freeze.code_files逐字节/大小相同；导入前选择该src，97个已加载autoresearch模块的origin全部在pin内，core与runtime identity匹配。main后续获批UI变更单列，没有放宽科研manifest或用新UI源码代替冻结源。

重放范围为原steps中13个有ID命令（含source-cap/select/import/3plans/primary/audit/wait/已存report与其原replay），另核两个core child及三个core plan。无ID的create明确跳过、函数patch拒绝；不会在已经搬走的`unmanaged-project`新建项目。source-cap接收器定位已有managed project，import保留原workspace字符串和原ID，仅让现有manager查询已完成记录，调用前逐ID核原digest。没有新import意图、新project或新ID。

移址仅完整复制已有manager到`/workspace/work/g5-native-restored-20261113-01/{retrieval,scheduling}-pinned/manager`。接收器存储根在内存路由，保存正文、context、request ID、project/run ID、ancestry、预算及回复中的绝对workspace原值均不改。**只规范boolean replayed字段**；报告时间戳和四附件完整字节不规范、不重建。原/复制状态都保持三版plan、waiting、2 tools、0 fit/model/source且无预留。

primary/AUDIT新执行、token/index/rank/metrics、schedule/brute/generator、fit、report rendering、model/network/CLI和perf_counter均patch为拒绝，实际触发计数0。移址期间builtins/Path/os.open及SQLite URI访问拒绝原case和原packet；真正source.json读取记录位于复制manager内。路径canonicalization/stat仍可处理原workspace声明；这不是OS隔离或同UID防篡改承诺。

retrieval完整原case63文件、scheduling62文件及每个manager13文件前后SHA/size/mode全相同；两个复制manager也同。另复核369份原保护文件仍精确等两个freeze，清单`protected-originals-final.json`。未改旧课题或已有报告，没有重置研究预算。

早期使用main、在UI改动前通过完整freeze的四项各98检查/18调用原件也保留，另72次原ID重放；本审查实际合计144次只读同ID调用，新增研究action/fit/model API仍0。随后按root要求改用干净pin，形成上述最终四项。非pin main的dirty/HEAD负例均在任何autoresearch导入或重放前拒绝，原case前后同SHA；早期拒绝尚未建立单独manager基线，不能把该未取得基线的false解释为manager发生改写。

成功pinned运行的checker源归档`helper-pinned-successful-runs.py`，SHA `cfde35711561b1ca053216a6a63bc4003f575aa52f4277022251ba853c2130ea`。当前[scripts/verify_native_cpu_replay.py](../../../scripts/verify_native_cpu_replay.py)仅再修复早期拒绝时console计数从-1显示为0，SHA `4cec7c897179d16d116752a1091a20c52c2e0040c374727682a9859c9e2ddb13`；身份/请求/接收器/guard检查未变。原console失败及第二次预检拒绝都保留，不为显示元数据重做研究或覆盖成功回执。

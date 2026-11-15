# S090：未知父请求的 Project 门禁与只读恢复视图

沿 S089 的真实可达合成链（原 child 同 ID 恢复 completed，parent 仍 unknown）复现：旧 Project 新 ID 可扩本地工具2→3、收紧来源8→7、升级源码身份，以及接受直接工具步骤；第二个工具入口由哨兵拦截，未执行。Europe PMC 新 DOI 在同样状态可触及模拟 Popen；全程无真实网络。修复前四项 Project 证据 `runs/s090-unknown-parent-project/pre-fix.json` SHA `dd9a3201b4c014515e885e6b05636f7f9537fa6614fa33937abdda2ca2e8675d`，Europe PMC 修前日志与首次夹具缺参失败保留本地。

Project 在 writer 锁下对新 freshness 请求、直接新 step 和新 upgrade 阻断 unknown parent；已存在的原 child/source/revision 按原 ID 恢复路径保留，合法 prepared parent 的首次 child 不被误拦。共享门覆盖受其约束的 budget、来源、manager新批次等调用；不宣称所有不使用此门的入口都受保护。Europe PMC 复用共享门，不复制新的生产门。

合法原 parent 保存 unknown 后，child 同 ID 已完成时，旧纯 selection view 因快照不相等拒绝读取。新视图只允许同一原 child、合法版本先后及结构身份相符的 unknown→completed 分叉，仍展示 parent 及其冻结 child 的 unknown；不将后来的 child 当作已确认 parent。纯视图只核传入 state 的结构与身份，不声称核磁盘或 SQL；report 另按既有流程检查工件。伪造ID、非法状态/时序与工件内容篡改合成用例拒绝。

统一冻结版独审新增Project/selection/report/Europe PMC及旧selection 21/21、旧Controller/recipe/质量策略/Workbench 42/42；Europe PMC作者相关12/12。联合16模块112项 unittest日志末尾 OK（进程已退出，但工具截断未保留独立shell退出码），包含五次实际进程SIGKILL切点；日志 SHA `d390fa66aa4d5a9a909144a683f65f0b650699f26e1d55d565b94dcc8f71d461`。修前视图拒绝日志 SHA `f989450b63fc4da5adcc8606a7338a03d3ec0b999670e8a2203cc7403dc07b2c`；一次 report 测试误以为空白变化改变规范化内容摘要，改为实际内容篡改后通过，原失败保留。

所有验证为隔离合成，来源传输 mock，无新真实科研/模型/fit；不证明真实断电、所有中断路径或OS隔离。原 Bike Project/manager SQLite SHA 分别保持 `26aa23c73e6f50025c7cd0bf4d58196a8f12050c7b65496bc098903911204080`、`0413c121e3e63115fa4140b87c1c24061fadca70f4acd9e0dd73e5271db6d49c`，旧pin和预算保持。开发费用/token unknown。Workbench普通manager unknown记录的可见性仍需单独核查。

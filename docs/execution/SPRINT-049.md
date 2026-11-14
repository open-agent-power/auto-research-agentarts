# S049：完整报告丢回执后按原ID收敛

沿原SQLite manager与export，不新建journal。新export意图记录恢复capability、body/slot、Project/source/Host/报告生成源码身份；export_report在全部payload计算完、创建目标目录前调用内部before_publish，以原事务先封存manifest原canonical bytes SHA，再写报告。回调接收深拷贝，不得改真实payload。

若完整文件已发布而完成回执缺失，再次提交原body/ID只核预封SHA、精确五文件、四输出字节及报告/input/source/Project/Host/源码绑定，原事务补回收据和报告指针；不调用export_report重新生成，不换目录。staged父流程沿其同原ID观察收敛。旧无version/预封SHA、缺文件、额外文件、symlink、任一漂移继续原停点；另一新ID不能绕过同项目未完成export。

## 实际证据

实现相关回归51/51、独立6/6通过；190源文件均按writer交回SHA冻结并前后不变。独立真实server子进程在完整export返回后os._exit(86)，HTTP客户端得到RemoteDisconnected，原manager仅preparing且预封manifest SHA已落盘。新server进程禁止调用export_report，原body/ID HTTP返回200、原manager completed，五文件hash与完整Project状态/预算完全一致。合成项目研究行动0、model0、fit0。

[精确验证](g5-local/report-recovery-verification.json)保留实际命令/脚本/源码/文件SHA和原件路径。进程exit恢复不等于断电fsync/磁盘故障或OS隔离验收。此前三项legacy tests因mock不接受新增可选hook参数在原测试逻辑前失败；只改透传/真实export包装后通过，失败未删。旧source304c25a的保守停点行为仍保留在其pin，新代码不补造旧意图。

## 按用户要求更新工作流

远端Adaptive Agent Workflow已实际fetch并回读main 02e72e3e411bec53db2288651df01afb27d8904d/v0.3.1，完整7文件替换全局native skill并逐字节核验，旧包归档，镜像同步及上游11项本地测试通过。root及本轮实际执行/独审成员明确读取新版SKILL/runtime-playbook；当前宿主用显式owner loop，未把配置当live hook证明，Cloud Skill Library旧副本未冒称更新。

复用docs/project/current.md作为2415字符当前工作笔记；此前长原文逐字节保存在current-history-through-S048-20261115.md，全部历史研究原件/失败/预算未改。dev-system继续停用。

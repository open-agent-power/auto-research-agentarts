# S111：工作台双指标事前登记首片

显式 staged 入口允许操作者在现有项目/计划/候选上登记验证集两项整体均值差条件、各自阈值及 met/not_met 分支；unknown 走原策略 wait。该页只登记和观察，不执行 primary、audit 或模型，不登记 final；future Controller ID 仅被引用并不预留。条件是整体均值，达标不意味着 S108 逐题负向子集消失；策略不是全局禁止普通旧入口。计划变更不能静默迁移原登记。

新manager意图在Project writer下保存原body、source/plan/context、根与nonce；Project 登记和独立kind claim在同一SQLite事务提交。直接core先抢ID或原intent/claim缺失不认领；resume-only仅核原已完成登记/claim，必要时补原manager回执，不首次登记/派发；新pending参与项目切换/全量门，旧入口跨command碰撞拒绝。页面同会话保存原body/ID，未知或丢失停查；协作式锁非OS隔离。

该opt-in 入口须 `-B` 和新空 `PYTHONPYCACHEPREFIX` 启动，加载模块/源码清单/缓存检查发现异常时 CODE_CHANGED；旧入口不受此启动门影响。源码缓存门不是密码签名或恶意账本防护。独立审查首次未设空prefix出现2失败3错误及浏览器CODE_CHANGED，保留 `/tmp/s111-independent-tests.log`；符合条件后最终独立50/50、另24/24 exit0。预检延迟加载缓存的修前合成案会先留下manager意图，日志 `runs/s111-verification/late-cache-before-fix.log` SHA `0e69185115a7142c26bb23fad635eab0ab5a66e583ec6e5a75c5f4fa3343d25b`；修后在_accept前停查。

独立实际Chromium/HTTP两隔离案例：正常显式登记并核原claim、原计划/预算不变且unknown不等于0；首包未到跨刷新保留原body/ID，resume-only停查且不写。两个新进程 `os._exit(86)` 故障窗口：manager intent后/core前停查；core登记+claim后/manager回执前核原件补回执，原ID重放，预算与actions不增。非SIGKILL/断电/所有并发证明；所有测试为合成，未触真实研究或调用模型。

后续须另行接显式原future ID primary执行及反馈分支，并标明可能各消耗一次工具；不得当作本首片已完成。

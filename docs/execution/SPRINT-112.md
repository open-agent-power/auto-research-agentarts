# S112：staged primary 原 future ID 的后端首片

新增显式 Workbench/HTTP staged-primary 路径：以同源码版本事前登记的原 future Controller ID 接受 primary；预核原项目/source/计划/registration、候选与预算。manager 先保存原body/nonce，Project 的 parent 与独立claim同事务，派生child的action与child claim在另一Project事务；只有首次创建者一次dispatch。旧 Controller/Project step/resume/source入口对新marked未决请求锁内设门，已有child/replay不可收养或自动复用。parent/child/manager不是单一跨库事务。

已有 manager intent 但无 parent/claim、parent/child未终态（含child完成而parent未完）、failed/rejected/unknown均保守停查，不从缺失推未执行；仅 parent+child completed且原请求、登记、decision/snapshot、原source、canonical工件/SQL及两claim匹配时，可按原ID只读核对并补manager回执。旧版本项目和S111旧pin登记不可自动升级，新版本合成需从同源码先登记；低层直接修改非OS隔离。登记本身不预留future ID，其他入口若抢先占用不可认领。

作者合成/旧接口/真实loopback HTTP回归43/43，独审43/43及另一独审42/42，exit0；另独立注入parent claim或child claim插入失败，记录及claim同事务回滚、0适配器调用，零工具额度在manager accept前拒绝。跨新进程原ID重放已测；direct抢占和异常切点仅函数注入，未验证真实双进程竞争。工作树编辑时一次回归发生1失败1错误CODE_CHANGED，原日志 `runs/s112-verification/compat-tests.log` 保留，固定版重跑通过。代码首片尚无 UI；真实研究/模型未调用，新项目预算未扩。旧pin不得迁移。

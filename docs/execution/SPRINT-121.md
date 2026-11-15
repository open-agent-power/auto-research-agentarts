# S121：已知 staged 反馈到直接后继计划

新增 LocalWorkbench Python 显式入口，将已认证的原 S111 登记、S112 primary 和 S115 wait/audit 的已知反馈引用绑定至操作者填写的直接后继计划。manager→Project 锁顺序，Project revision 与专用 claim 同事务；manager 和 Project 不构成跨库原子事务。原意图存在而 Project claim 缺失时同ID停查，不重新创建；同ID仅核原资料并返回原 revision。禁止已有 private evaluation/freeze/final 的项目使用，unknown、未决来源/模型、漂移和非法顺序停查；旧普通计划入口拒绝跨入口重放新类型。无需也不会自动派发研究。

固定 HEAD `72ca7f19d20ecb7877a5d8f7a4dc78891d122ca6` 加本次候选，205 项清单 SHA `415e0293f622660f992542b57d789ef56dc94e42c1413ae9295bdeebbeef7595`；作者六模块83/83，独立专项14/14及旧反馈/经验/S120回归35/35。一次真实双进程竞争：一方 PROJECT_BUSY、一方仅建一个 revision，预算不变；wait/audit 后继又保存 plan3 后，plan2 原ID仍可历史核验，使用新ID借旧反馈另建后继被拒。日志 `runs/s121-independent-review/`。source unknown 使用合成状态注入，不是真实网络中断；claim 故障为注入，不是断电测试。

初稿的旧入口同ID绕过、source pending漏检、audit完成时序和材料末次核验问题已修；默认Python缺h5py、负例误期待错误码等失败保留 `runs/s121-verification/`。本功能仅 Python manager，未接 HTTP/UI，也没有策略自动消费后继计划；仅保存人工计划与原反馈绑定，不把已完成primary补造事前登记或追认原holdout final。隔离合成，不证明模型自主或真实科研收益；旧项目源码pin与预算未更改。

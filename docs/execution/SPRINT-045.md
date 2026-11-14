# Sprint045 · 开发集分离与一次最终评价

用户指出上一轮报告后停止不符合持续要求，本轮在北京时间2026-11-15 00:42重新核环境、origin/HEAD和released租约，领取 `root-evaluation-20261115T0042`；旧盘仍缺。基线 `5be416e0ce931d12ee631d07188c659fd3128337`，原6人池复用，未新开代理。三小时仍只是对齐，不等待触发才开发。

## 实际产品增量

独立dev/validation源→host事前登记private final包→真实validation→固定规则冻结策略→原预算/普通action一次final配对→同ID恢复与报告。没有通过隐藏query_splits来把旧test改称盲测。接口、数据流和限制见[使用合同](../staged-retrieval-evaluation.md)。

新source拒额外query/qrels/metadata；候选/冻结/模型上下文只读元数据和公开开发结果。final的原action持久claim和排他启动凭据先于私有读取/排名；重复调用和unknown不重派。BM25被选时真实复用一次排名/评分。完整元数据schema包含内层request及SHA绑定，不能用嵌套内容加重算SHA混入报告。

## 验收与失败

- 冻结188个产品Python源文件，core `6a5c9e47a19ceebe883930a51d9524788374245e9fd8d774a4e88af2db20c0ab`，Controller `ea63841f4fdd82228f464657247c93ea4dd679c8e6dfd368b158fd03b888b5f4`。
- root相关回归91/91通过；独立组合41/41及4/4自建不利probe通过；source执行前后无变化。真实loopback登记/冻结/final、原SQLite预算、四文件报告及同ID重放均有工程证据。
- 独审发现并修复BM25重复评分、无claim直接计算/重复同claim计算、允许字段嵌套注入；不把修复前代码或通过数量当真实科研收益。
- 并行作者在口头freeze后又修源，导致一轮工程E2E返回CODE_CHANGED。未换原ID掩盖，临时fixture随测试生命周期清理，失败记录保留；随后改为各writer明确交回SHA，再核完整snapshot，避免边改边验。新的已冻结合成项目通过，不是旧项目迁移。

精确源码/命令/日志SHA见[验证索引](g5-local/staged-retrieval-verification.json)。私有哨兵、source/plan/packet篡改、marker前后中断、正负零差及操作次数均为构造工程输入；没有新科研模型/付费API/拟合，旧50fit/pilot3/2保持。

## 继续下一项

并行核新公开数据：NFCorpus学术用途边界未确认，CQADupStack judgments/署名与体积边界未完成，不强行纳入；未下载或评测它们。官方SQuAD站点明确数据CC BY-SA4.0，v1.1 dev HEAD为4,854,279B。继续先固定SQuAD段落检索子任务的采样、许可、比较、预算和原ID恢复协议，再下载并经原生阶段执行；公开dev内拆分只称程序性heldout，不称未曝光或盲测。

# S128：S127 合成包单分支端到端预演

固定 HEAD `aafae0e5f3763811bb0e5ce24175b96fcd6e9e88`、384 项源码/输入清单 SHA `d32d1fb06b42f03b6f3312b2910a385b61e0d2874b7574b265c3537106ac4731` 和已发布 S127 人工包 `cc62d84e405fa61cd297128bc792deb8ca4311e02830e402c3ac85c43e9ec923`。同一隔离 Project `project-58451f890805469cb0f1945adaf469c9`、run `run-fc7dc8e83fc9402a9c8e99c5f64f9093`：显式用途、evidence 8→0、人工计划v1及在行动前登记 Recall@20/MRR@10 差均≥0，met→wait、not_met→audit；唯一原 future ID `s128-primary`。

primary 完成后观测器误监控 `lexical.retrieve` 而非 `relevance_retrieval_adapter.retrieve`，断言失败停查，日志和原项目保留；按同ID/body resume-only 恢复，不重新派发。工件保存300条唯一排名/300指标，自报 index1/rank300/score300；实时 rank 哨兵不覆盖正确入口，不能补称观测到300次调用。独审从保存的排名与合成 qrels 独立重算300指标，两种方法/dev/validation均为1，两个validation差值[0,0]，原登记 met→wait、无child。最终 1/2 合成工具、0模型/fit/evidence。

真实浏览器在同项目保存人工 plan v2：服务先成功后故意丢回执，刷新后同原body/ID经 resume-only 核验；S122 默认 wait，显式后验规则仅 suggest_audit、may_execute=false，不派发。独审只读核4条manager意图与5条Project claims、自哈希/工件封套、原登记时序、最终40文件与源输入384文件；最终清单 SHA `1ebae7cfddb0a135c4db2d3bd8ce77fe6e65ca4c0de06743da561dae69ac38ba`。独审起初误用 result 局部哈希触发内存断言，按源码封套更正通过；原文件未改。浏览器独审为脚本与冻结证据只读核对，非独立重跑。

此为单一人工数据、一个met分支，不验证另一audit分支，不是Wikinews真实研究、模型自主或科研收益。无SIGKILL/断电/OS隔离证明；旧真实项目和原盘未打开。

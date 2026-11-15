# S100：严格采纳已供应质量反馈的计划

此前普通质量采纳只要求回答引用原质量 action；不能证明该登记条件和结果在冻结的规划输入中。新增独立 Python opt-in `adopt_supplied_quality_plan`：核原 prepare selector、冻结材料、登记/条件、reader outcome、原 action/result、质量引用 SHA、完整 context/prompt 与原响应引用。仅已知 met/not_met 可采纳原文；unknown/缺失/漂移不通过。Host v3 intent 绑定原 prepare 与材料 SHA，Project计划和归属 claim 在原事务内绑定，写入前复核；原 ID 重放以已保存原 revision/claim 做历史只读认证，不能伪造旧当前计划。新旧入口互斥，旧 wire/Workbench 不自动改变。

验证：作者专项12/12、旧合同42/42，独立复验54/54（进程exit 0），均隔离合成；覆盖漂移/篡改、材料缺失、原响应引用、unknown、双切点恢复、旧入口互斥。测试 `tests/test_host_supplied_quality_adoption.py` SHA256 `262938f894a3b3792e4d25e7f056d031b90011dc59b8465204ba2d2517c55f01`，Host源码SHA256 `cebb61dfceda8692c139257d0f5b91ac3a45512b4134dcd366fc176166aac4c7`。这只证明封存材料及导入回答的引用关系，不证明模型实际收到/理解材料或科研收益；无真实模型/API/科研和新增预算。下一步若接Workbench，需manager意图绑定同一Host身份与Project claim，不能沿用未经绑定的归属。

另由工程成员最终源码相关回归 63/63、exit 0，含原有6个真实 SIGKILL 合成恢复切点；日志 `runs/s100-related-regression/unittest.log` SHA256 `74f61281439abe35d49f2c5f42671e8e5a8b63c15a69a6d465cfcdb8f0bb75d8`。非断电恢复，工程工具/IO非零。

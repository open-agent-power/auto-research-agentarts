# S060：保存validation的配对胜负与单题影响

Status: verified。实际原件事后描述审计和独立复算完成，不认领新科学实验或收益。

原S046/S054各100个validation、固定R20与MRR@10，保留所有题/平局/缺正例，不挑adverse；两个指标都按TF-IDF−BM25。核原保存wins/losses/ties和均值，计算每题移除后其余99题的完整精度均值与范围，以及非零原方向下LOO近零/反号数量；原均值近零时该两数量为null。EPS1e-12仅对齐原保存统计，绝不改变原冻结的严格R20>0。

[固定协议](g5-local/saved-validation-stability-protocol-v1.json)在逐题审计前保存，协议SHAb1c9b193807629053e73d5a98621689196daf25bc138a2217bc94382caec3d4b；这是已曝结果后的方法冻结，不冒称前瞻预注册确认。脚本scripts/audit_saved_validation_stability.py，源码SHA dd5c2a9aac654322ffe5e1c4473426f3b379647c9318825c9ccc8cae7fa26239。原reader commit030af51c4ff06813d08a5f75610dea9f6573ad26/corea05f668…保持。

复用原_checked_primary各一次，校验公共dev+validation/SQL/源/保存算术，分析输出仅validation；阻止private/Host/非primary工件/排名/评分/fit/派发/恢复/写入。完整性hash在guard外读取包含private的原字节，不称整体验证零privateI/O。仅受信developer脚本，非OS隔离；实际命令显式PYTHONOPTIMIZE=0（身份/哨兵使用assert），输出到新的ignored runs/s060-verification文件，不覆盖历史。

3项算术边界测试通过（单题正贡献移除归零、反号/原零不适用、异常/缺失/重复/原summary冲突）。engineering只给未看逐题值的方法意见，root实现与执行；capability_review静态独审无阻断，要求显式关闭优化后执行，再独核实际数值。最多400对差/400LOO，0新研究project/action/模型/fit/排名/评分；旧两个case3/3不改。无p值/CI/显著性/跨dataset因果或新收益声明，单题影响不代表多题稳健。

脚本/协议先以4e17a63af164cd8d0cb49a1e5a3feae458df459d推送main并回读，再实际执行；优化flags=0，原输出SHA9c4d2d8bc1297856b89317e4f279cca030f756e3e5e1635ab3d98bece06e7d38，原脚本/协议未修改。root两案各调用_checked_primary一次，完整400对/400 LOO通过，独立另按原工件/SQL/source集合与summary复算全部400+400，未使用root结论当数据。

| 原validation案例 | 指标TF-IDF−BM25均值 | 胜/负/平 | 移除单题后的均值范围 |
|---|---|---|---|
| S046 | R20 −.01 | 0/1/99 | −.0101010101至0 |
| S046 | MRR −.0355555556 | 1/12/87 | −.0426487093至−.0291806958 |
| S054 | R20 +.01 | 1/0/99 | 0至+.0101010101 |
| S054 | MRR −.0069047619 | 7/10/83 | −.0137085137至+.0016835017 |

两个R20差异各只有一题，移除该题差异归零；S054 MRR移除一题可反号，S046 MRR任意单题移除后仍负。这里的MRR是validation，不能混成此前final的−.0209167。这不是显著性/总体、跨任务或新算法收益结论。

原S04636/S05447文件各前后逐字节一致，S05017另核同，共100原件保护；原两个3/3科研预算无改。完整性hash在guard外读private字节，分析和独审本身拒绝private/final/非primary，只基于公共dev+validation核验、输出validation。独立脚本初次猜错测试文件名的只读错误保留；两次实际独立复算均exit0、stderr空，v2增加原source/summary直接核对，不伪造初版计算失败。

[精确aggregate/输入/代码/恢复边界](g5-local/saved-validation-stability-results.json)。全量原逐题结果留ignored runs/s060-verification/original-validation-audit.json，不提交原运行数据。原研究仍只按原pin/ID接续，本审计不登记新project/action或授权模型。

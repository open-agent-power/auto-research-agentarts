# S060：保存validation的配对胜负与单题影响

Status: prepared。真实事后描述审计尚未运行，不认领结果。

原S046/S054各100个validation、固定R20与MRR@10，保留所有题/平局/缺正例，不挑adverse；两个指标都按TF-IDF−BM25。核原保存wins/losses/ties和均值，计算每题移除后其余99题的完整精度均值与范围，以及非零原方向下LOO近零/反号数量；原均值近零时该两数量为null。EPS1e-12仅对齐原保存统计，绝不改变原冻结的严格R20>0。

[固定协议](g5-local/saved-validation-stability-protocol-v1.json)在逐题审计前保存，协议SHAb1c9b193807629053e73d5a98621689196daf25bc138a2217bc94382caec3d4b；这是已曝结果后的方法冻结，不冒称前瞻预注册确认。脚本scripts/audit_saved_validation_stability.py，源码SHA dd5c2a9aac654322ffe5e1c4473426f3b379647c9318825c9ccc8cae7fa26239。原reader commit030af51c4ff06813d08a5f75610dea9f6573ad26/corea05f668…保持。

复用原_checked_primary各一次，校验公共dev+validation/SQL/源/保存算术，分析输出仅validation；阻止private/Host/非primary工件/排名/评分/fit/派发/恢复/写入。完整性hash在guard外读取包含private的原字节，不称整体验证零privateI/O。仅受信developer脚本，非OS隔离；实际命令显式PYTHONOPTIMIZE=0（身份/哨兵使用assert），输出到新的ignored runs/s060-verification文件，不覆盖历史。

3项算术边界测试通过（单题正贡献移除归零、反号/原零不适用、异常/缺失/重复/原summary冲突）。engineering只给未看逐题值的方法意见，root实现与执行；capability_review静态独审无阻断，要求显式关闭优化后执行，再独核实际数值。最多400对差/400LOO，0新研究project/action/模型/fit/排名/评分；旧两个case3/3不改。无p值/CI/显著性/跨dataset因果或新收益声明，单题影响不代表多题稳健。

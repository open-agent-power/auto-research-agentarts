# Sprint043 · 未完成请求的源身份保护与可运行反馈演示

接续已推送的S042 `9858adffdcc8b579522832e7855715042524bda3`，没有等待下一个三小时触发。源码续作范围、原研究额度和旧盘缺失事实保持。

## 修复实际发现的缺口

后续独立探针确认保存检索阅读器未纳入core身份；原`step`同ID分支会先进入`_recover`，可能在reader源码变化后将running写成unknown或提交已落盘工件。原Controller只在child尚未存在时核源码，且CODE_CHANGED会把parent置为永久rejected。这些是实证工程缺陷，S042定点通过没有覆盖它们。

现将reader源哈希纳入core；非终态`_recover`在读工件/写unknown之前核原action、project和当前core身份。Controller的非终态parent无论是否已有child都在操作前核core/Controller身份，源码不符只抛CODE_CHANGED，不永久改写原parent。已完成/失败的终态仍沿原约定核验并重放。

根源身份测试在隔离拷贝中只改reader字节，再起全新解释器，确认副本修改前身份相同、修改后新请求被阻断且原项目不变。非实现者另固定4个中断窗口：parent-only、child无工件、child有工件、终态重放；跨pin不写，原pin可按原ID完成或保持unknown预留，adapter不再执行。

最后相关工程回归78/78通过，产品源码执行前后SHA完全相同；独立源身份/中断回归30/30通过，关键源码/测试SHA稳定。修复前实际running→unknown负例保留，修复后同探针CODE_CHANGED且原账本不变。

## 实际可运行交付

[演示与命令](../../examples/hypothesis-feedback/README.md)不依赖测试目录。首次生成真实本地合成ZIP/receipt/selection及哈希，登记固定预测并保存原请求；独立进程恢复后执行原检索，再按冻结分支执行原结果审计；再次重启新增行动0。默认不联网、不模型推理、不拟合，不覆写非空目标，不改未知原请求或自动创建替代ID。

已完成三进程实际运行：validation candidate-minus-baseline Recall20为0.0，按事前gt0判为condition_not_met；原primary+saved audit共2工具，原预算2/2、0模型请求/拟合，原生JSON/Markdown/PDF报告保存。该结果是构造工程负例，不是科研收益；既有adapter已计算test，非盲测。旧源码尝试和非空目标启动均拒绝，不重建原演示项目。

非实现者随后在同一目标独立执行resume：新增行动0；包含数据库、原请求、source/ZIP、两个工件及全部报告的完整目录SHA清单前后相同。另用真实9858 cleanpin、SQLite只读模式核首轮工程登记，原ID/源码身份/预算和全目录字节不变，未执行其尚未启动的行动。初次三进程输出在实现者tool transcript，未补造为原始落盘日志；独立重放raw与完整清单已保存。

## 原件与接续

S042持久登记fixture保留原core39b46e98…及真实clean源码pin `/workspace/development-continuation-20261114/source-pins/9858adf`；没有升级或新ID复制。新演示使用新core和自己的明确工程预算，不替代历史研究。精确代码身份、日志和文件SHA、独审与失败见[验证索引](g5-local/source-pin-demo-verification.json)。

下一优先仍是研究决策与原生执行：为新研究冻结尚未曝光的评价协议，并比较反馈策略的真实适用范围。长期研究收益、原生Linux模型transport和旧盘恢复尚缺，原有模型/API额度不扩。

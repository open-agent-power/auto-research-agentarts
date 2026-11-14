# Sprint039：产品自己生成并接续宿主委派批次

过去一次多阶段试跑靠root在产品外写脚本串联。现在已有HostModelBatch新增独立delegated v2库/CLI：产品持久保存下一Host ID、context/prompt SHA，返回等待原外部回答；调用方导入原字节后，同一批次恢复并只消费已收到的回答。行动真实完成才推进cursor和准备下一个候选，剩余原slot允许时可提出反馈后计划，停待显式采用。[操作合同](../host-model-selection.md#宿主委派的持久批次)。

源码 **7c1f399a557856d232e523416f6c8b49ebc8d399**，clean pin `/workspace/work/delegated-batch-source-7c1f399`；[精确验证与失败](g5-local/delegated-batch-verification.json)。独审核源码后先冻结本地candidate，再在独立pin验18项。真实Host/Controller/项目持久化配一个手造工程adapter：三处中断按原ID恢复，adapter恰1次、native工程工具账1/原Host slot2，计划保留proposed，经显式fixture adopt后结束。没有实际模型、真实排名/评分或研究拟合；这是工程恢复，不是科研收益。

实现最终15项定点测试，独验另7项有重叠，不相加称独有测试数；CLI真实工程入口返回awaiting/1slot/0actions，报告识别v2。旧v1四个方法AST与原一致，同输入_begin记录776字节相同；未重跑全部v1和真实多进程并发。导入前bootstrap未计，实际外部推理/token/费用unknown。原pilot没有被读取/重试或扩其3/2额度。

独审发现并修复缺/畸形回执误结束、Host身份遗漏、父结果/完整child绑定及plan adopted版本不符；各次日志保留。首轮4项环境错引旧安装只有terminal记录，原trace未持久，明确不补造；独验预轮缺源SHA不作冻结证明、CLI捕获器缺方法及旧v1夹具缺root错误也保留，最终才通过。

目前仅库/CLI；工作台继续按钮尚未接v2。当前sourceb2e的707b49 wheel不含本能力，源码入口需显式加载7c1 pin/src或后续匹配安装。新反馈计划仍默认汇总，S036逐query材料未自动选择；原生Linux模型transport、研究质量/效率及长期无人值守没有验证。

cached Host applied/outcome unknown仍停审；下一S040只观察已经完成的原Controller/普通child并补Host缓存，不调用dispatch或重开预算，旧7c1 pending继续原pin。后续优先反证/假设与有意义的独立比较，避免继续扩大展示包装。

# Sprint010：独立相关性任务与冻结策略迁移

北京时间2026-11-14 04:45:53从继承云盘接续，main起点 `618cad42323c53bfbbfebdbe7fe5c77e9edf604c`，origin正确、工作树干净、无其他活跃lease。独有owner `root-sprint010-20261114T0446`。已读dev-system/research-dev-router、current/AUTONOMY/执行入口及原包阶段要求；494原件与三根完整421路径集一致，8个上游checkout仍为manifest固定HEAD且clean。

## 来源和真实负证据

NFCorpus官方主页及原README仅授学术用途；其graded相关性也不能套旧SciFact citation合同。未执行该目标。许可证据、原件、403和失败均保留，转查ArguAna。

ArguAna由作者官方Webis站点源码与Zenodo版本`3973258`交叉确认CC BY 4.0；106,453,976B原ZIP SHA `814e3bcf0daf905495702f34781905a28d58a1220a4be5182d0e9e40438fcebb`，MD5与官方一致。完整24,908成员的路径/大小/CRC核验通过。BEIR ZIP SHA `cfdf79adce27a401b3cd3ea267903134dbfab2c6afeb95d7fe5724a00bf7557b`。

全8,674文档、1,406查询、1,406条grade1标注保留。1,298个query与corpus同ID、同正文，须在top20前排除自身；5条正标注目标缺文档，保留分母，不补造或删标签。去URL/换行/首尾空白的声明转换后，全部正文/查询与原作者数据精确匹配，1,401个存在目标的正例对应原true pair；独立审查另从原ZIP重算确认。ID缩写与标题转换未复现，不宣称完整canonical转换/榜单。

[来源/准入/输入完整身份](g5-local/retrieval-transfer-source-audit.json)。来源回执SHA `c40e97347774c5986f9b5a0f1d0e3d6a025bc26b5465051d46b7f2f8dff66b67`；schema-only准备输入15,686,699B、SHA `d20458472f460eec731e15c292b5b1229e3c30f35896e9e1ef1cac8d722f634c`。全资产11,732,412B低于新合同11,800,000B、packet仍低于原核心16,000,000B，没有扩大旧接入/预算。准备阶段0目标排名/评分/项目/fit/model。

## 实现与工程验证

新增独立`relevance_retrieval_adapter`及两个明确注册工具，保留旧citation/lexical字节。BM25基线、TF-IDF候选，保存原grade，二元正相关指标，同ID排除在top20前、缺正例留分母。沿原Project/Controller/Workbench保存预算、三版计划、行动和报告；新报告/前端摘要明确相关性，不把旧citation阅读器接入新合同。

新增来源准备和独立freeze/run host wrapper。新study lineage固定`g5-arguana-source-arm-transfer-v1`；唯一真实output `runs/g5-retrieval-transfer-20261114-01`。全局共享exclusive study claim和每output attempt/worker claim防合作执行者重复开预算，非OS权限边界；unknown只恢复该原请求/原manager，不复制换目录。

- 新adapter9项、新原生生命周期2项、新报告6项工程检查已通过；旧citation18、旧原生CPU9、旧报告9分别通过。重复检查不是新增研究样本。
- 生命周期小夹具核3版计划/2tool/0fit/model/source、四报告、primary/audit/wait原body重放无计算和额度增长，拒绝citation命令混入新lineage。
- 前端typecheck/lint/build通过，两个尺寸5张真实浏览器工程组件截图已检查；0组件网络/页面错误，不冒充真实目标五页验收。
- 实际旧SciFact source policy原工件核验通过；5种篡改拒绝。`pytest`缺失的首命令失败保留，改用已有unittest，没有安装依赖。

限定工程回执在`runs/sprint-010-design-audit-20261114/implementation-validation.json`、`runs/sprint-010-relevance-report-20261114/validation.json`和`runs/sprint-010-driver-engineering-20261114/host-only-verification.json`。

## 先冻结后评价

固定seed `arguana-transfer-v1`按query ID SHA取80/80/300，原官方只有test，此为程序划分；未评价的946query仍保留。选样不读成绩或标签可达性，460中2条缺正例仍评价。来源指导规则只读旧SciFact已知public的BM25−TF-IDF test Recall20 `-0.011055555555555556`，固定选TF-IDF；目标dev/validation仅描述，不用于重新选择。

Policy v2 SHA `f7c3b5172d44cca6c721f050a5524a360c6f4d88f7d81159593755dcb9bd9a96`。预声明test Recall20候选−基线大于`1e-12`仅支持该子集局部coverage transfer，绝对值≤该阈值无改善，小于负阈值为负迁移；保留全部其他指标亏损，不自动采用/宣称显著或通用。候选与固定TF-IDF无来源负对照同臂，结构差为0，不能证明记忆因果收益。

完整[执行协议](g5-local/retrieval-transfer-protocol.md)及[用户/开发说明](../relevance-retrieval.md)。实现先提交，然后准备exact source/code/output/policy/selection freeze，独审批准后才允许一次2tool/0fit/model/source真实对照；本节初始记录不认领未运行的目标结果。


## 后续一次真实运行与原生交接

实现提交 `250954e98024844e102352aac8666859e4f761be` 后，exactfreeze `15b06d4828caf86ec1bb7db5d53692ebafc9a97559e81a346032fbd0cd65e81d` 经独立703项事前准入批准，唯一attempt实际return0完成。不是再次运行旧case。新project `project-0940a2e0cbd841e58677d2ecd99a33e2`，producer `867075eb62d29a71bb71e99175c063c10fd3f9c8c9427ab8b4679a44b4969e30`；clean科研pin `/workspace/work/arguana-transfer-source-250954e`，原manager/relocation/请求body全部保存。

真实460query/920rank/920score、1个index，test300的Recall20 BM250.746667→TF-IDF0.896667，nDCG0.396192→0.503379。但test43个nDCG亏损、2个Recall20亏损，all460的186混合坏例（63有指标亏损/123无亏损但召回不全）均保留。2个selected缺正例query两臂全部指标0，不删标签。固定TF-IDF无来源对照与候选逐值同一，记忆增量按构造0；冻结test主目标只支持该程序子集局部coverage表现。完整[真实结果](g5-local/retrieval-transfer-results.md)及[机器索引](g5-local/retrieval-transfer-results.json)。

实际预算2tools/0reserved/0fits/models/source；3版计划依据真实反馈推进并waiting，4文件原生报告已导出。独立新解释器从科研pin加载99产品module，7个原ID（primary/audit/wait/report/3plan）守卫下全部replay，23类禁止计算/派发/创建/报告生成守卫0触发。实际7GET/0POST读取4报告和2行动原bytes/SHA一致，572科研文件（含494旧保护）及路径保持；没有以报告生成或重算伪装恢复。

## 继续修复真实界面缺口

先在科研pin18840只读服务实测5页/双尺寸、16张实际看图、20browserGET+10API GET，指标方向/186坏例/手机末列可读，但overview和experiments方法名回退“后续检查”。于是继续在独立worktree修2个methodName映射和bundle，commit `944b5aef970765f7993bbff758b5dc70728ac50f`，已fast-forward合main，未重跑研究。

新clean UI树 `/workspace/work/arguana-ui-labels-20261114`、18841指原manager，无写/模型开关。4受影响页面/双尺寸真实截图全部看图，20browserGET+10API GET，5类API前后同、13manager文件及174科研Python字节保持，producer仍8670身份；限定独审逐两映射与bundle、2代表看图通过。原250科研pin/18840保留。

失败仍保留：browser01 strict selector误匹配两个summary；UI依赖符号链接让构建漏vendor notice，未提交该产物，复制已有依赖后正确重建；label browser01误假设公共API含code_identity而停在首GET，02改以实际源/身份核验。另发现独立post-run协作任务为interrupted，恢复原任务/原数据，不重建研究或额度。

所有旧source pins、494原件/421路径、历史50研究estimator保持；开发成本unknown，未扩模型/API/fit预算。本轮未验收newcode的完整wheel/全Gate/隔离/封存/多代RSI；旧citation查询阅读器与通用方法经验/自动选臂尚未覆盖新合同。下一项是新relevance保存坏例按需阅读，沿原项目/工件/SHA校验，禁止再跑这批或借新ID重置额度。


事后必要独审18组通过，原receipt `runs/sprint-010-independent-20261114/post-run-review.json`，SHA `513598cce2945fd897d3ae27e43ffdfb5ea8afb1ee18726c8d46ce2a7acb02d1`。只核保存身份/配对算术，没有重新对gold评分；详细证据与边界见机器结果。每触发报告已保存latest-report.md/json，下一计划2026-11-14 07:47:27北京时间，平台run/result/投递仍unknown。

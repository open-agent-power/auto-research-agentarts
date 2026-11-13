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

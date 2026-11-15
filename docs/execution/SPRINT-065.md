# S065：新真实支持文档检索课题准备

状态：source/protocol/driver固定并经合成与独审通过，准备发布。真实Hotpot原JSON尚未解析、未选样、未建项目或执行；不能将准备记为科研收益。

HotpotQA作者README固定3635853403a8735609ee997664e1528f4480762a声明dataset CC BY-SA4；作者说明Wikipedia原dump 2017-10-01，原wiki衍生文件另称CC BY-SA3。第三方RAGLAB固定revision取得原JSON 46,320,117B / SHA4e9ecb5c8d3b719f624d66b60f8d56bf227f03914f5f0753d6fa1b359d7104ea，与历史dataset_infos记载的作者原始dev文件长度与SHA相同；本次不是从作者源直连。已有公开数据服务曾在进程内解析一条公开样例仅为schema；固定原JSON尚未解析。逐wiki revision和全部贡献者仍unknown；保留作者/许可/来源、每篇title及维基URL归因sidecar；不对版权义务作完全已满足断言。原文、query、qrels和原报告仅本地，公开仅独审白名单聚合。

[预定协议](g5-local/hotpot-support-protocol-v1.json) SHA3772acf2ba1a458a0bae834205b77b840deaeae70fb33d5a1e64b23aeb0f5fef：先以原问题规范组/qid hash固定300并分100/100/100，输出q-/d-隔离ID、原title/空metadata与完整支持文档正例；全局同title异内容、缺标签/坐标、原cap不满足即停，不换seed或筛难例。拟独立新study、3工具/0模型/0fit/单并发/1800秒，v2 holdout映射met→TFIDF、notmet→BM25、unknown→stop，两个已知branch均事前audit；原ID/独立claim/预算与S052-S064一致。notmet时final同BM25基线差0是构造，不是TFIDF最终结果。此公开数据准备会完整解析包含final候选字段，不可称盲、未曝光、QA或多跳推理验证。只有protocol/driver/source发布、合成含失败/恢复验证及独审通过后才可解析原JSON并prepare。

BoolQ备选：作者CC BY-SA3，原dev第三方镜像与TFDS历史源SHA逐字一致、3270非空title；SuperGLUE val不是缺标题，而是 `title + ' -- ' + passage`，3270逐题映射与标签来源核验一致。初次裸passage比较得0匹配曾误判标题丢失，已纠正并留失败；train/val 720 passage重合，test未解压。本轮未用标签判断相关性或排名评分。[来源审计](g5-local/new-retrieval-source-audit.json)。

固定driver `scripts/run_hotpot_support_study.py`/protocol/test与191源共195文件manifest SHA a66dc739740d3ebc1c053b3ae4b8e56c0038d254079c66fa5aaec2c89bc0557f，core ca09803b71c2bfd82a3356d428f4f05b8a311da433ea1109019e556b53d7c572；作者48相关含11本专项，独审7合成检查通过。测试原native两已知branch各3工具、final100题分别TFIDF双臂200次或BM25单臂100次rank/score；unknown仅primary1工具/final未测。作者真正新PID按原body终态只读重放，独审核其回执并另测同ID及未知/来源重封拒绝。0模型/fit，工程fixture调用与真实研究分开，费用/token unknown。

prepare及run/replay来源核验会把公开原JSON和私有selection/holdout再解析，包括final候选字段，不声称盲或执行前未读final字节；正常原报告内含source文本，只留本地，公开仅另审allowlist aggregate。独审final qid/文本/hash/base64排除是合成canary范围，非全部泄漏途径证明。初合成预期met实际notmet已修夹具并保留日志；WIP错误origin和source/query/sidecar绑定缺口固定前已修。root曾向已完成成员发消息却误以为独审在跑，已明确纠正并followup后实际独审；不把静态审查冒称最终验证。[证据](g5-local/hotpot-driver-verification.json)。

下一步：仅在本固定protocol/driver发布、验证准确source pin及原lease后，按唯一claim准备固定输入，检查global title/容量，失败即保留并停止；成功后以原3工具预算与同ID原生运行。该步骤尚未发生。

## 真实输入已按固定协议准备，尚未执行

驱动/协议先以源码 `5d431097f3b4846ac240745121e56070edd78e86` 推main并固定干净pin，之后唯一claim准备成功、无Project/行动。独立从完整原JSON重新选样/生成并比对：7405行/7405题组，100/100/100，2982篇文章，每题2个支持文档共600正例；开发资产2,122,881B低于11.8MB，原准备14文件前后不变，100 final qid不在5个开发资产/spec的精确字节中。source snapshot `c7bd3a7286072af61cd53b20465bc6f5dde3ecefae759cc5b0d08fb4c9da9dfb`；sidecar `b2b5b693a0da72140d58fa71f3e41dbf075713d1adc477b84e217c7726dd7604`；holdout `6c5d0cd4627e2379b99bae3b1f1dc837be85b5ea9964ec498f314d264895a053`；原claim `b31b5c582771dfc8e21b7ecfe5d891ecee799829c24665bd4991e4c11c5cf1c9`。

准备和独审实际各解析完整公开原JSON与private selection/holdout/sidecar，包括final候选，shared corpus/公开预曝均不构成盲测；qid精确不出现不保证无语义侧信道。未排名、评分、fit或调用模型，3工具只是上限、当前尚无研究账本，费用/token unknown。逐wiki revision与贡献者仍unknown；原文和原报告只在受控本地，公开仅单独检查的aggregate。[精确输入与预算](g5-local/hotpot-prepared-input.json)。

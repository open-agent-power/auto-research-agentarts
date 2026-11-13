# 保存不利查询阅读：输入审计

这是下一功能的真实输入核对，未实现HTTP endpoint或UI。科学源码仍`8e8a206ed0b71479a6e774e36ed91fdb06e21c22`，原codeidentity `3945ed0f5ec85b0ce42af0bb9ac0d0c27034bf932dac27fee9f7008ec2d3707e`；本轮读取时main=`2ea6c0a`，不修改producer或预算。

原项目 `project-b0ad79226f0a454b99b604e373e39bbb` 的primary `action-f2291951a00d194f4069b2b40a9c8a00`与audit `action-6f6cf23eaa4fb3922931cae1d95ef14f` 在`tool_result.result.adverse_queries`保存同133行；observation只有计数。60行任一指标下降，另73行无下降但任一臂Recall20不全（65两臂不全、8仅baseline不全），不能把133全称为candidate恶化。

已逐条核对920保存排名与920指标行、18400文档原行坐标、1109原query及5183原document身份。实际样例：762为指标损失，1397为两臂不全，495为仅baseline不全；两臂共6次原TSV qrel读取（3个不同原始引用行）与保存引用一致。引用相关性不代表事实支持/反驳或答案正确。

未保存逐文档retrieval score，只有ordinal rank与保存的per-query metrics。不能重建分数或把qrel TSV score当检索分数。保持原rank顺序、query ID/split、project/action/result/source SHA绑定，缺失显示未记录或错误，不重排或补算。

source.json为11,128,187B，绑定的corpus8,106,566B、queries209,731B及qrels/许可原件嵌入其中。后续宿主查找必须校验既存artifact/source身份及有界字节，再按需返回query/doc原文和定位；客户端不得提交任意文件路径，原文用textContent，不能把整个packet/base64或全corpus加载到DOM。首屏25不利行、单query两臂40排名行目前仅为方案，接口尚未执行这些限制。

本机完整字段路径和SHA在 `runs/sprint-008-adverse-reader-contract-20261114/contract.json`，SHA256：

`614e89aba0f56046c42c1b1b0ad9c19604bf2c4e80dcea15298647da6fa09ab8`

主回执 `receipt.json` SHA：`069043b48d082412057afe5c874882ba0bcca93e9ea15fb86c5cb547df382b75`，原件/输入前后同。样例与原qrel复核分别在`samples.json`／`qrel-readback.json`；`inspect_saved_adverse.py`保留实际读取方法。21,460项断言是字段/身份审计，不是新增研究效果。新fit、排名、评分、模型/API均0，开发成本unknown。

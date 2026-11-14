# S054 固定公开 TRAIN 段落检索与条件续作

本协议在任何检索/评分前冻结。来源已经下载并作结构选择，因此不宣称事前未接触材料。它是同一公开 SQuAD v1.1 数据集的另一个官方 split 和固定段落群体；S046 的 DEV 研究保持原件/预算，不重跑或迁移。当前可见历史未找到 TRAIN 实际研究，旧不可见账本保持 unknown。两批 corpus 抽样不同，不能把原始分数之差解释为跨批次的受控处理效应。

官方 TRAIN 原件30,288,272字节，SHA `3527663986b8295af4f7fcdff1ba1ff3f72d07d61a20f487cb238a6ef92fd955`，官方说明 CC BY-SA4.0。先按固定 train 段落 ID 的 SHA 取2,200，再仅在其中按原 S046 去重与 qid SHA 顺序取300，划100/100/100。无答案抽取或排名调参，正例仅原问题所属段落映射；不是问答答案质量或穷尽相关性。

复用原 BM25/TF-IDF、指标、Project/Controller、S052 条件 Workbench。先保存计划、0来源行动上限、独立 final 包和 `validation candidate-minus-baseline Recall20 > 0` 事前登记；再执行一次原 primary。条件满足只允许原 saved-audit，经核验后固定规则冻结策略、至多一次 final 和报告。未满足或 unknown 保存原等待结果，**final 未测/None，不填0**。只有验证成功才评价 final，故 final 有条件性选择，不能作为无选择偏差的独立复制或一般效益证据。

新唯一 study `s054-squad-train-conditional-v1`，工具最多3、模型/拟合/来源行动0、研究并发1、总执行窗口1800秒。完整请求派发前写一次，跨 source-pin 的合作式 claim 固定唯一目录；resume 只用原目录/ID/body/版本和累计预算，缺库或 unknown 不创建替代研究、不重发。源码、预算或输入漂移就停止。它不构成 OS 隔离、模型运行时或完整 Gate 验收。

[冻结 JSON](squad-train-conditional-protocol-v1.json)含原始输入/选择/资产哈希、明确语义、原请求 ID、预算及恢复合同。仅在 clean 已发布 source pin、独立审查和准备核验通过后执行；本协议页面不据准备状态认领实验完成。

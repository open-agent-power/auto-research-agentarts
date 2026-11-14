# S054：官方TRAIN固定检索与条件续作

S051/S052发布后继续实际研究准备：同一公开SQuAD v1.1、不同官方TRAIN split和固定段落群体，不是新数据集、盲测或跨dataset泛化。原S046 DEV/ArguAna/S050原件、source pin和额度保持。可见Git历史未找到TRAIN实际研究，缺失旧盘unknown，不宣称全球未用。

## 行动前固定与已验

原TRAIN30,288,272B / SHA3527663986b8295af4f7fcdff1ba1ff3f72d07d61a20f487cb238a6ef92fd955，官方dataset-level CC BY-SA4.0已留原网页。先按固定train段落ID SHA取2,200，再仅在其中10,240 QA/10,208去重群体按原seed取100/100/100。原始答案字段未被使用，正例是原问题所属段落，非穷尽相关性或答案质量。输入manifest SHA77f50e312c9d64910a9fb37108d49d82bf434647285c4b269f92d365f9b774a1，独立重建300映射/19源文件前后相同。临时容量packet2,469,760B使用dummy provenance，只计工程容量检查；正式prepare需真实凭据。

[协议JSON](g5-local/squad-train-conditional-protocol-v1.json) SHAeaea343cd2f9b653b546f6fb8b5b4b3b2ed38452ff6959a866feac2342f0d997，在排名前固定validation Recall20 TF-IDF−BM25>0；met才原audit→freeze→至多一次final/report，否则原等待且final=None。该final有validation条件选择偏差，不是无偏独立效益证明。最多3工具/0模型/fit/来源行动、单研究并发、原1800秒窗口。

复用原S046安全保存/哈希/公开源码身份/结果读取与原Project/Controller/Workbench，新增固定host driver，不新建产品runtime或预算账本。固定study/跨pin O_EXCL合作claim、完整原body先存、缺库/未知停原请求、原期限和终态只读重放。独审修正active resume写构造器前先只读核损坏SQLite、deadline元信息自洽、完整保存双臂dev/validation与adverse摘要；不声称OS强隔离或防协同篡改整账本。

最终driver SHA5b36b28b24d19ebd169d573804d501cf291db3268632ec401f332fc3288b5fe3，测试c382abdadd5c98e8648746d3fe8f5b32a7e6472381d3ef6b2c3cfed0183700b4；Project core仍300421cc466b459f3b86e74fd6ebecf800dc67f10fb9d7e160f9ad46a839f1e1，191产品源码未改。root专项10/独审5通过，涵盖实际合成正final全链、负/零等待、超期只读、不自洽deadline/空库不写恢复。它们是工程检查；正式TRAIN项目尚未创建、尚未排名评分，不据源码发布认领研究完成。

## 唯一执行与恢复

发布clean exact source pin后，仅root运行 `scripts/run_squad_train_conditional_study.py --source-commit <fullSHA> --prepare`，核prepared/原件身份与0项目，再唯一 `--run`。再次只 `--resume` 原pin/claim/body/ID/目录，不因失败换项目或重置预算。driver与完整[协议说明](g5-local/squad-train-conditional-protocol.md)以最终发布字节为准。

本轮root/engineering/capability_review复用AAW v0.3.1显式owner loop和原生评测方法，未加载dev-system/新模型服务。工程token/费用unknown。source/driver审查和命令日志在ignored `runs/s054-review/` 与 `runs/s054-verification/`；真实执行完成/停点将另存原始结果和共享索引，不把触发或prepare当完成。

# S127：Wikinews 协议纯合成准备器

新增内建人工 fixture 准备器，公开入口不接受外部内容路径、不联网、不创建 Project、不派发研究；仅生成 synthetic/unverified 的 XML、来源证据、staged 四资产/spec 和 capture/load packet。真实 Wikimedia 正文解析、许可/归因与研究授权仍未解决。

固定 HEAD `e17c27121c9e706a88041ab5ea51f81fb44bc316` 加候选，200项清单 SHA `7f6c773896b4edff7d04f157a0450cb697a5180f53e95ffa41bedd883627af98`。作者及独立专项各15/15；独立标准库从保存的人工 XML 复算1005页、1002连通分量、两盐固定选择1000 corpus/50 dev/100 validation与150一对一 qrels；独立目录与作者11文件逐字一致，packet SHA `cc62d84e405fa61cd297128bc792deb8ca4311e02830e402c3ac85c43e9ec923`。日志 `runs/s127-independent-review/`。

选定 network/subprocess、Project、索引、rank/score/model/fit 哨兵未触发；捕获前后资产/链接漂移、fsync故障、拒绝重用半成品为合成注入，不证明断电或OS隔离。`contracts.py` 已通过现有身份链间接包含，另显式记录哈希；有限文件身份不证明加载内存或完整环境。排序输入变化时内容资产相同，但绑定原XML SHA 的 spec/packet 按设计变化。无真实研究或模型新增。

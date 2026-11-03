# 查看来源评议的真实续接结果

这份只读记录承接[来源评议续接](evidence-continuation.md)：最后一次请求已收到回复，但四项回答都缺少必填的 `status`，零对象处理的 `evidence_ids` 为空，因此没有形成有效评议。模型文字和宿主格式核对分开显示，原始参数没有修补。

当前累计预留 **4/4**，其中原来的未知请求仍占1次；不自动重发，也没有新拟合。后来准备的Excel与文本片段仍未交给模型。旧PDF属于先前数值轮次，不包含这次回复。

## 从封存记录导出

在产品根目录执行，输出必须是新目录：

导出 `continuation.json`、`continuation.md` 和文件清单。它们绑定原进度、来源、任务及续接收据的哈希。只公开原工具参数、响应计数、来源别名和格式缺项，不分发模型隐藏推理、账号或本机路径。哈希用于核对版本，不证明解释正确。

把该目录作为 `build_chemotopo_handoff.py` 的 `--source-continuation-directory`，同时提供同一 `--source-progress-directory`，即可放进独立只读包。直接服务使用相同参数；页面下载地址为 `/api/p02/source-continuation.json` 和 `/api/p02/source-continuation.md`。

本记录用于判断下一步材料缺口与接口问题。原回答提到的抗体、导出列、批次和零对象规则仍须回到作者来源核对，不能因文字完整就标为任务完成。

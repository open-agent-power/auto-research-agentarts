# G6 本地原生案例只读演示

2026-11-13 录制了两段真实浏览器 WebM；这是查看已完成 G5 案例的交接材料，未触发新研究。

| 案例 | 最终视频（runs/g5-native-demo-20261113-01/final-metrics-focus/） | 时长 | 编码/尺寸 |
|---|---|---:|---|
| SciFact 引用检索 | retrieval-readonly.webm | 31.28s | VP8，25 fps，1440×900 |
| 合成区间调度 | scheduling-readonly.webm | 30.68s | VP8，25 fps，1440×900 |

服务使用干净源快照 `e638b5f3782d12a7b54bb9ede5596e5c4d9726cf`，只读端口 18832/18833；未启用动作或模型。画面经过总览、研究、实验实际观察披露与指标、成果披露、报告和复现输入入口；没有执行/保存/POST。两段 14s 实际视频帧已查看：检索包含 BM25/TFIDF 的 test 指标；调度包含各 split 计数及保留的 adverse case。成果页显示已保存结果、未核实问题和报告附件入口。视频未剪辑、配音或合成运行状态。

录屏路由只允许相应 origin 的 GET/HEAD，service worker 被阻止；实际 0 非允许请求、0 HTTP 错误、0 pageerror。完整 63 个检索案例文件、62 个调度案例文件及各 5 个 API 响应前后 SHA 完全一致（project、report JSON/Markdown/PDF、input JSON）；state_version=13、3 个计划版本、2 个已有工具调用和预算不变，新增 fit、model、source、research action 全为 0。

`runs/g5-native-demo-20261113-01/README.md` 是播放入口；`final-metrics-focus/recording-receipt.json` 保留原始请求/metadata/完整哈希验证，另存 `visual-inspection.json` 记录人工看帧；`export-allowlist.json` 给归档器逐文件绝对路径、bytes、SHA。初版 clip 仍保留，不覆盖，归档选择最终指标聚焦版。录屏脚本与 before/after 清单一并交付，不导出 Chromium profile、依赖缓存或无关路径。

演示仅表明既有科研记录在产品页面可读。检索不扩展为领域判断，Recall@5/20 负差保留；调度是合成工程 benchmark 的既有算法代码优化。此材料不声称重新计算、独立科研验证、跨依赖版本模型复现或完整 G6 全范围通过。唯一新增下载为官方 Playwright ffmpeg1011 视频依赖，无模型/付费 API。

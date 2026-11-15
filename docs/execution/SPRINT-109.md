# S109：S108 事后负向结果的原生经验适配

新增 `posthoc-validation-loss-experience-bundle-v1`，以已发布 S108 结果及协议的固定 bytes/SHA 为来源，每包只含所选 S065 或 S067 一案，真实 primary ID 仅为上游来源引用，独立 scope/observation 与 S066 不冲突。导入以 binding 校字节，不回读原项目/逐题/final，不宣称现场数值重算、签名、匿名、因果或整体收益；raw Memory 明确 `action_role=upstream_primary_reference_not_audit_producer` 并保留限制。当前只支持固定两条 available 结果，不是任意后验/suppressed 通用适配器。

复用 Native Memory 和目标 Project 显式 import、selection context、操作者计划 refs；没有自动让模型引用或采用，真实目标项目未创建。Project 与报告 code identity包含新 reader，旧项目须原pin。报告 JSON/Markdown/PDF 和页面已有案例卡片有专用类型，不误标Ridge；页面文件选择器尚不支持新类型导入。原S066与S065/S067各3/3预算未改。

修订版作者32/32、独立29/29及另27/27合成，exit0；独审还验证旧 staged case 已被计划引用后导入新case，原ID重放、两case报告与目标预算不变，夹具额外3次合成来源工具非真实研究。独立 Chromium/本地HTTP核卡片的来源角色和未重算限制。独审发现 raw Memory 原记录此前未注明 action ID 角色，已修复并重跑；旧版29/29不计修后验收。reader SHA `0de6a4f01ef6b9e341689aef77d97b623ee9075ff742e7ec91bdf50103d24e61`、测试SHA `c32e6b8c6d185defce8a5b01010f3178662c5614335496c177307ff78b2b663d`。截至此提交无真实Memory导入、新Project、模型或研究行动。

## 已发布聚合的实际 Memory 导入

以已推源码 `c1a8b3a3130f3b54eea292bc6df15e1a7aac4d0a` 的相同代码，在 `e5339b34238b989f3edfda33d6758cef2177cc4f`（差异仅两份交接文档）建立单独 Memory `runs/s109-real-published-memory/memory/memory.sqlite`：公开S108结果/协议原bytes对应 S065、S067 各首次 inserted 1、重复 inserted 0；SQLite immutable 核验 integrity ok、entries/events/source_versions 各2。Memory SHA `f14ee417c7fa56fe127dbfbb1529f3b1cfd932353f86d02c8c1b88eabbf07d62`，实际回执 `runs/s109-real-published-memory/receipt.json` SHA `fba4ffa05643091c1c6b0a4586047d0e2b1d83e7db8d59f1d751b5b2bcfd4563`。

两包独立：[S065](g5-local/s109-s065-posthoc-bundle.json) SHA `aa7b3be6cb250fbf51827765087c966840e27bf72e708484aa254915e992aad3`；[S067](g5-local/s109-s067-posthoc-bundle.json) SHA `d92f6b7b6c76842fe8d9b95d92fdebed0ca362f5d6305865b065f277b14a00d0`。独审只读核历史链/原记录与公开bytes重新 derive 对照、bundle隔离和限制；未重写 Memory。首次尝试因负责人两份交接文档未提交而在建Memory之前安全停止，失败脚本/日志保留，提交交接并验证源码相同后才重试。

本轮没有打开旧Project或pin，无法称本轮独立核验其预算未变；S108时点各3/3是此前证据。没有新Project、研究工具、排名、评分、拟合、模型或付费API；开发和I/O成本unknown。导入已发布bytes不等于重新计算、真实模型采纳或科研迁移收益；这两包尚未导入任何真实目标项目。

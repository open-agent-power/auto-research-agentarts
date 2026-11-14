# S055：把真实覆盖收益与排序亏损保存为经验

S054完成后继续使用既有 `StagedExperienceMemory.import_project → recall → export_case`，未改产品代码、创建新研究项目或追加原3/3工具。源项目由 `LocalWorkbench.open_readonly` 定位，完整47文件及Project状态/预算前后均相同。

真实案例632,278B / SHA `6aa0ca75d05630df69eabec5abaec3ba0530cd488041833b02163cde1b988d45`，源producer与捕获core均 `300421cc466b459f3b86e74fd6ebecf800dc67f10fb9d7e160f9ad46a839f1e1`。保存validation .98→.99和final .97→.98，同时保留final MRR −.020917、nDCG −.011180及31个开发/验证不利查询。没有自动采用或声称跨任务收益。

新工程Memory可recall并导出合法case，幂等重放新增entry为0。case最终部分仅聚合/原SHA引用，100条原final逐query标识哈希均未进入bundle；离线final绑定仍需回原件核验。捕获/重放阶段有private、index/rank/score/model/fit/step/recover哨兵，补充重放修正初次host目录guard命名不完整；完整性hash在哨兵外读取过全部private字节，未解析，故不声称整体验证无private I/O或OS隔离。

[精确代码、案例、预算保护与验证](g5-local/train-tradeoff-experience-verification.json)，本地实际case/Memory/原命令位于ignored `runs/s055-verification/`。新研究行动/模型/fit均0，开发token/费用unknown。

继续S056已实查的下一缺口：新staged检索原query与两臂保存排名虽然在source/工件中，旧阅读API与saved_materials仍拒此family。先补独立dev/validation只读reader/既有GET，保持原train/test响应；Host/plan材料另列后续，不靠新排名或扩大原预算解释失败。

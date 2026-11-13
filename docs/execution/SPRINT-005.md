# Sprint 005：原生跨领域闭环与干净安装接续

本轮把原独立CPU对照接入同一研究工作台，并完成真实两领域执行、独立结果核对、原ID／移址恢复、页面验收及当前产品的干净安装。用户新增的定时推进要求也已实现：每3小时的平台任务已enabled并回读核同一cloud环境；首次实际定时执行仍待验，不把配置成功当运行成功。

## 实际交付

| 增量 | 实测及入口 |
|---|---|
| 引用文档检索 | 5183文档、固定460queries，920排名/评分；BM25 test nDCG+.027553，但Recall5−.017278、Recall20−.011056，不自动采用。[原生结果](g5-local/native-results.md) |
| 合成区间调度 | 16任务/20544jobs/80保存run，16独立Fenwick最优；4096规模倍率中位118.176×仅对朴素扫描DP，一条dev小任务实际更慢保留 |
| 原生研究状态 | 两案各3plans、2/2tools、0研究fit/model/API/source-extraction、state13 waiting，实际观察/action/result SHA导致第二版计划和保存审计 |
| 独立验算 | 固定验证器首轮9910项；920排名/指标逐项同原对照，60条有指标损失、73条无损失但至少一臂召回不足，16任务全schedule/目标/ops保存。[独立核验](g5-local/native-results-independent.md) |
| 恢复与重开 | 清洁8e8源码、97模块origin核对；原/移址两域408项检查、72次原ID重放；另早期72次读取全部保留，无新计算，预算/原件/4报告不变。[恢复](g5-local/native-replay-review.md) |
| 页面 | 每域5桌面＋2手机视图，0页面/HTTP错误、56GET/0写操作，8下载SHA同；新无任务空态与4方法中文名。PDF7/8页仅首末实际视觉检查，字体/留白限制保留。[UI](g5-local/native-ui-verification.md) |
| 当前产品干净安装 | e638源轮子1212193字节；177包文件源/wheel/site-packages同SHA，无systemsite、18精确观察pins/23实际closure；两case仅副本保存接续/HTTP/PDF通过。[G6范围](g6-local/native-release.md) |
| 真实操作演示 | 两段31.28/30.68秒、1440×900只读浏览录屏，实际指标帧已看；案例与5类API字节不变，0新研究/写操作。[演示范围](g6-local/native-demo.md) |
| 定时与参考 | 每3h检查成果、对齐原计划、实际继续开发/验证/推送；cooperative lease避免配合者并发写。8参考仓库真实checkout、固定HEAD、源码/许可复用矩阵已核；不是8个完整runtime全部合并。[规程](AUTONOMY.md) |

## 固定身份和工程证据

科研实现提交`7f33dcc`，保护空文件窄修后真实冻结`8e8a206ed0b71479a6e774e36ed91fdb06e21c22`。后置UI提交`e638b5f3782d12a7b54bb9ede5596e5c4d9726cf`只改展示/API投影，不改科研producer身份；当前产品clean wheel也由e638对象快照构建。两实际课题的共同code identity为`3945ed0f5ec85b0ce42af0bb9ac0d0c27034bf932dac27fee9f7008ec2d3707e`。两阶段源码分别保留在干净pin checkout，不改原freeze以掩盖展示增量。

完整工程回归1225项：1206通过、19跳过、0失败/错误；后置UI17相关检查及typecheck/build另过，不把重叠测试相加为unique总数。4个派生pyc变化使原严格全src树回执false，有限源码/测试/研究原件验收另存；183非bytecode源码、tests、292旧研究文件与累计50estimator未改。原369保护文件及路径集合始终保持。见[回归](g5-local/integration-regression.md)、[整层审查](g5-local/native-core-review.md)、[最终限定总审](g5-local/native-final-review.md)、[机器验收](g5-local/native-acceptance.json)。

报告和原始案件在`runs/g5-native-cases-20261113-01/{retrieval,scheduling}`；各累计两工具已用满，不得再run整个driver、新建同课题或复制额度。仅按原请求ID与现有DB恢复。旧Concrete/RE/Slump继续原20/20/10fit账本与固定0ceb源码服务18830；新CPU只读服务18832/18833固定e638源码，actions/model关闭。

## 真实失败、成本和边界

保留metadata原件空对象假设、数值类型echo、JSONL Unicode行、运行前14合法空日志读取、缺少可选time命令、UI检查器字段/选择器、旧预览预期409、后置UI误对旧源码清单、replay HEAD/dirty负例、G6保护对象schema helper失败及所有修后独立证据。没有通过重写评价器、删坏例、降级旧1.9环境、重发unknown或换研究ID来获得通过。

两个实际driver总wall分别17.417/11.234秒，包含校验、保存与报告；不与旧独立脚本时延冒充同条件效益对照。产品模型/API及两新课题研究fit为0；工程回归fixture确有fit，精确数未计量。依赖安装有网络、clean运行18loopback；开发token、基础设施和金额未知。

qrels是引用文档，不是事实真伪；调度是已知精确DP的合成工程任务；公开结果已知。未启用生成模型/LLM judge、未证明记忆因果增益、多Agent研究收益、真实用户满意、OS/sealed隔离或多代RSI。干净安装与保存重放不等于主课题模型重新训练复现。原G0及完整阶段门保持，用户接受同一Worker限制无需重复决策。

后续按已授权范围核验本轮复现归档、补独立离线重开演练并核首个定时执行。所有后续研究先另行固定明确范围/评价/预算，不重置以上旧案件。

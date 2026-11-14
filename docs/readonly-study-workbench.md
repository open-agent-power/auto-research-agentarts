# 保存研究与项目原记录的只读工作台

现有manager可用正式只读入口打开，不运行原构造器的mkdir、建表或writer锁。已安装含该功能的wheel时：

```bash
python -m autoresearch.readonly_workbench --root /workspace/auto-research-agentarts/runs/g5-native-cases-20261113-01/scheduling/manager --port 18791
```

打开打印出的本机URL `/#/saved-study`。模块只接受root和port，不提供动作、模型、修复或恢复参数。帮助可在缺h5py的base环境显示；实际服务需要`sources`额外依赖，完整验收使用`[reports,sources]`及固定依赖。原源码脚本也可用`python scripts/serve_local_workbench.py --root <existing-manager> --read-only`，不能与actions/model开关组合。缺manager/DB或有SQLite副文件时报错，不创建或修复旧目录。

页面分开显示独立study的原计划和已记消耗、当前项目原预算字段及原行动。当前原调度项目state13、两completed action、原producer3945；独立study是source62/runtimee731，当前产品core4b。它们不共享预算或执行身份。历史费用null、现金结算unknown仍为未知；原字段不是新算的used/reserved/现金余额，不因查看分配额度。

独立研究保留原负结果：12个小n样本均慢，保存主耗时比1.261183787；27性能case可横向滚动并展开三臂原中位数和invalid预热，16原文件路径/SHA只读引用。研究源数据、旧case、50历史fits及唯一primary/audit不重跑。当前项目只投影已有记录，不实例化/升级或选择项目，不把外部study伪造成当前action。来源绑定不认证科学结论。

新host不加载旧项目完整五页，导航明确其范围；当前报告下载/经验导入等不适用入口隐藏。缺失、unknown、failed、integrity_error和项目no_active/partial保留各自状态。它不是三臂执行runtime或项目经验import。默认旧写模式未被改为只读；未启用新模式不等于无初始化写入。

SQLite使用只读immutable连接、固定路径/slot校验和前后stat/副文件检查，要求没有并发writer，不构成OS隔离。服务仅绑定loopback，所有写方法拒绝。退出Ctrl-C关闭自己的socket；源码变化要求重启，不热换已启动代码。

[逐阶段真实HTTP/截图及失败范围](execution/g5-local/readonly-study-view-verification.json) · [b1e安装包及准确依赖范围](execution/g6-local/readonly-workbench-release.json)。84cc完整界面验收与b1e安装CLI/手机定点补验分开；旧b1e包不包含其后新增的证据ZIP下载和假设来源视图。

最新source79218/最终wheel3770包含固定原证据ZIP下载与假设来源。页面只自动读取描述；点击后才请求ZIP，服务/浏览器分别核大小和SHA。包内是原研究source62及docs93，不能当当前完整运行环境或复制重开账本。缺失/篡改不会生成新包。

“假设来源与反证”原样引用冻结协议；项目ID匹配不是自动关联/因果/共享预算，不解释原串的额外数值含义。原结果不重新运行。[下载原件检查](execution/g5-local/study-capsule-download-verification.json) · [假设来源检查](execution/g5-local/hypothesis-source-verification.json) · [最新安装物](execution/g6-local/readonly-evidence-final-release.json)。

source3b01另增加“保存的计划与控制器记录”和“保存的报告记录”。三版计划原文及完整选择上下文、两条匹配行动、第三条等待/null、工作台preparing/null分别保留，读取不会恢复执行。保存报告显示原快照/导出器身份及四文件manifest声明；服务仅读取manifest/report.json，不下载或生成报告，当前性unknown。缺失组独立显示，不丢弃已读预算。[S026真实验收](execution/SPRINT-026.md)明确源码截图与安装物范围；旧792/3770包不含这些字段。

最新[S027安装物](execution/g6-local/stored-plan-report-release.json)对应source3b01，wheel1289743B/SHA3b12703b…，新venv `/workspace/work/g6-stored-plan-report-20261114/venv`。真实CLI与桌面/手机代表性smoke已验；完整源码矩阵、第三方依赖核查和原Gate范围分别记载。

S030在原控制器记录下增加“核对原请求与身份”：仅全部原摘要相符时显示规范JSON语义body及两个用途摘要，不代表原HTTP字节或执行授权；页面不提交原请求。缺失/不一致分别显示状态。[真实原案与异常验收](execution/g5-local/saved-request-handoff-verification.json)。最新[S031安装物](execution/g6-local/saved-request-handoff-release.json)为source de20/wheel33287dd1…，含S028收据修复及本只读视图，旧包原样保留。

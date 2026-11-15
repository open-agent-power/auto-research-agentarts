# S102：严格材料采纳的真实进程中断验证

基于固定 HEAD `99e241d2e80930e23d90ae698e57360f5633cd88`、隔离合成项目，对 S101 三层 manager→Host v4→Project 四个预定提交窗口，通过父进程确认状态、真实 SIGKILL -9、不同 PID 原请求重启。作者和独立审查各4/4 exit 0。独审PID：manager intent 后 67950→67965、Host v4 intent 后 67930→67940、Project revision/claim 后 67975→67985 均停查；Host applied 后 67907→67920 验证原凭据后只补 manager 回执。

测试核原 body/selector、v4 intent/ref/material、Project claim/action SQL、来源/工件/Host文件与预算；每案例合成工具1、model/fit/evidence 0，禁止新增dispatch。前三原件不变，末点仅manager回执可变。专项测试 SHA `70785f14dbd1495f8791fb9dc0628366a2b6b4a21cd3f6d0d85f5c2b8fd0e81b`；作者日志 `runs/s102-strict-sigkill/author-run.log` SHA `699b50bb86208b392ca4bac111b708836c6bf6161a5aa649dbbfc1978f1d753f`，独审日志 `/tmp/s102-independent-review.log` SHA `c45c08ebf19ead87b4885760205713fed3b914c9feb9da506f0c6dfd9e2cd259`。原日志未记录临时合成 project_id/selector SHA，无法事后补造。

该结果不证明断电、全部时序或真实模型理解与研究收益；无新增真实研究/API或额度。下一项优先核对原回答具体片段与封存质量事实，区分人工指定语义映射及unknown。

# S114：工作台显式执行已登记 primary

在S111登记面板显式选择同Project、当前计划/source/候选/预算匹配的 staged v2 原登记，以其原 future Controller ID 提交S112 strict primary；不是通用按钮生成新ID。页面在用户点击前展示原条件/分支、登记、计划/source/context摘要、候选及预算，说明至多消耗1本地工具并对注册语料 dev/validation做固定BM25/TF-IDF ranking/score，不执行final、模型或fit；不会自动执行。

首发前将原body/ID写入session，写入失败不发；异常/回执未知保留，只许原ID resume-only核对，完整成功还须后端核原parent/child claim和原action后才清。Project只读新增 `staged_primary_choices` 投影仅表登记元数据/快照，不认证manager归属或实际加载代码；旧direct v2可显示但缺S111 claim时后端拒绝不派发。已有staged v2登记项目响应新增可选字段，没该登记项目旧形状不变；旧pin不升级。完整 pending summary 大于0锁首次执行并提示截断，未决状态停查。

作者及独审相关后端29/29，另一独审43/43 exit0；独立Chromium/真实本地HTTP用隔离合成项目覆盖session存储失败无POST、首包未到原resume停查、成功回执丢失原ID收敛、伪理由/伪resume child SHA保留原body、双击一次primary+resume、返回中外部切项目、旧direct无claim拒绝0 action；pending total=9 使用mock GET，跨项目草稿清理经程序操作隐藏控件，未声称用户可见点击。作者首轮隐藏控件定位超时/夹具失败记录于 `runs/s114-verification`。本轮无真实项目/模型调用。源码identity沿S112，旧S111 pin原登记不迁移。

页面尚无S111反馈策略执行/等待按钮，见下一工作；此前S113七个真实进程窗口是S112后端合成验证，非本次真实科研或断电证明。

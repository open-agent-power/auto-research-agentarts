# S106：页面严格采纳与仅恢复入口

工作台对 Host 已供应的登记新增显式严格质量采纳，用户选择原登记；已知 met/not_met 可选，unknown、来源/项目/状态漂移、原行动未被回复引用等不启用。旧普通采纳保留，不能被称为质量认证。原五字段请求体与manager ID存于会话；不自动发起模型或扩额。

新 resume-only HTTP 入口在 manager writer 锁内要求原ID、command和完整body digest已存在，old=None停查，禁止当作首次提交；经原 Host v4/Project claim路径复验。首包未知/超时后用户显式按原body恢复；首次成功后页面以同原body调用resume-only核对原凭据，必要时可补原manager回执，并非始终只读。再核原计划投影ID/version/SHA才清会话body；错误回执或核对失败保留。投影GET只做身份/快照对照，并非独立三层认证。会话body丢失时停查，不猜测重造。

作者最终定向15/15、同后端旧相关48/48；独审旧版本40/40、修正测试后5/5，进程exit0。独立四个合成服务和Chromium/真实本地HTTP覆盖回执丢失后跨刷新原ID/body恢复、首包未到resume-only 409不写、伪造成功SHA保留原body再显式恢复；unknown/漂移/缺引用/未通过及旧普通入口部分用浏览器模拟。模型/研究派发哨兵未触发，预算不变。独立浏览器结果 `/tmp/s106-independent-review/browser-result-final.json` SHA `75c42aec4a464de5e4fd2a5b103e64dcd5b29a61524b91f20645327fc4bcd7c9`；测试修正后SHA `252c7cc16be91ef5b3364be1889b7d143c9f269220530f3418591f25e3334633`。测试首次SQL INSERT列顺序错误使同摘要异命令分支未覆盖；独立正确列序已证明生产守卫有效，现已修正测试。夹具字段/预期与服务关闭Ctrl-C 130按原日志保留。

无真实模型/API或新增真实研究；不证明模型理解、科学收益、断电或OS隔离。

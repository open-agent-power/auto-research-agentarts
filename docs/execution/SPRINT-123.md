# S123：工作台后继计划决策预览

将 S122 显式只读预览接入本地工作台 HTTP 和页面。页面绑定当前 project、run、snapshot、plan 和原反馈；默认等待，可显示由操作者在反馈后选择的事后审计建议，明确仍需另行授权，不提供执行按钮。返回候选和预算必须与当前 context 对照；项目切换、迟到/伪造响应及未决请求停查。认证仍在服务端，计划摘要投影只用于身份对照。preview 不写研究账本或派发，但协作锁可写；旧只读宿主不开放 POST。S121 保存仍仅 Python。

固定 HEAD `86221bfb8cdb1c3899cbf4e1feecb31265bc1421` 加候选，257 项清单 SHA `fca12be5421be4c973a00eb51d4ba240727c20af72c8bcd0845676102032bd6f`。作者 Python 21/21，lint/build及浏览器通过；独立实际 Chromium 正向3/3、伪候选/额度/原因3/3、项目A→B→A迟到1/1、真实SQLite sidecar停查1/1，HTTP4/4。unknown、9 pending 和恶意文本为浏览器模拟，各1/1且0 POST。独立日志见 `runs/s123-independent-review/`。

以已发布 S122 commit `a0118d56c78141df4c6d1bbc69cc2627c68803c6` 建新合成项目，再经新 HTTP 预览成功；manager 源码 SHA `cd10c8240d16922dbd9906f2dfa7e490ec4c30ea5f2a4e19f5325af252f70027` 不变，Project/manager ledger 字节不变。此为合成兼容验证，不代表所有旧项目；无新真实研究或模型。保留夹具目录冲突和错误分支设置引起的失败日志；旧盘未恢复。

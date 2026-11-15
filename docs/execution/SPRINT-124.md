# S124：后继计划原请求恢复门

新增 Python resume-only 入口，在 manager writer 内核对完整原 body、ID、command、digest、意图及 Project 原 revision/claim；原意图不存在或不完整时停查，本次不创建请求。Project 已提交且原凭据齐全时仅补原 manager 回执；completed 仅认证原链。不能从当前草稿重造请求，旧 save 入口合同不变。新 manager 源码身份不同，旧项目继续原 pin，不自动迁移；尚无 HTTP/UI。

固定 HEAD `0f6a86f39a87f40976d09b7640003c111ed1a5c7` 加候选，207项清单 SHA `366d107f362e0b1fc5188ff0bcd27b5f1ed149dfe3f9b8e7b686c4e4aca165c8`。作者四模块40/40；独立新进程专项10/10（日志 SHA `084eee9a2b97c89c88d3a2c8e898601fcc7b7733a42b20e24fe171d2dad0e7cc`）、原 intent.body 篡改停查及旧pin跨进程验收通过。两个提交窗口为函数故障注入后另起进程，不是 SIGKILL/断电；旧pin合成项目由新manager拒绝、旧manager原ID重放成功，双账本不变。

缺原行不能证明历史从未接受，只能证明本次没有创建；保留初版文案问题及测试记录。全部隔离合成，无新真实研究、模型或预算；旧真实项目未打开。

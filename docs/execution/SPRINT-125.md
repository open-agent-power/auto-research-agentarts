# S125：工作台后继计划保存及原ID恢复

页面显式选择原反馈并保存人工后继计划，S121 首次保存与 S124 resume-only 分离为受保护 HTTP 入口；管理器源码身份保持不变。发送前，在 Web Lock 下写读仅含项目/请求身份的 localStorage 哨兵和本标签 sessionStorage 完整原 body；失败不发。成功或不确定回执均需用相同原 ID/body 经 resume-only 认证原 manager/Project claim；仅当原 revision 仍为最新且服务器状态投影 SHA 相符才清，已有更新计划或原件丢失停查。计划正文保留在本标签页会话，localStorage 不含正文。锁与哨兵仅约束配合的同源标签；双存储同时清除、跨设备或不合作进程不受保证。

完整管理器 pending 扫描仅是状态投影，不认证研究 claim；无法归属/损坏 unknown、截断停查，禁用只读宿主不获取写锁。无 active 时完整 manager 概览为空才允许创建，有已归属 pending 仅允许回原项目核对。GET/HTTP 安全门及原ID核验不允许新ID绕过原请求；旧 manager pin 不迁移，S124 pin 合成项目通过新HTTP原ID重放且双账本字节不变。协作锁可能写文件；保存/补回执会写账本。

固定 HEAD `da56ef2a2b5934939418bf2e1bbba4355b6e2a50` 加候选；最终256项清单 SHA `628f91860e91486f184ce3f8981e62fe52e6ef027b1ecebccc35b1f3c144d3bc`。作者相关32/32、修订测试等待后 HTTP13/13；独立 HTTP13/13，真实 Chromium 正常/丢回执2、存储/伪回执/首包未达/双tab5、无active4、跨项目迟到1通过。故障和损坏记录为隔离合成/注入，非SIGKILL或真实研究。独审两轮原5秒 HTTP 测试分别2项、1项超时，日志保留；单次同界计时2.209秒不可证明5秒稳定。仅测试 helper 改 GET15秒、其他请求60秒，与页面上限对应，无重试或生产变更；通过不证明5秒性能改善。浏览器目录/断言夹具失败亦保留 `runs/s125-verification/` 和 `runs/s125-independent-review/`。

未新增模型、工具研究、fit或真实科研收益；原旧盘与真实项目未打开，未知成本不填0。

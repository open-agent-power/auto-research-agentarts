# Sprint023：固定原证据包显式下载

source `e0db52ff3cfa206cb78f95c7a1ad2a0449fabab6`增加固定DTO GET study-capsule和固定ZIP GET study-capsule.zip，无query/path/study参数、不POST、不读取任意rawref。只读原4671421B/SHA3c12ef…包，先完整验证再回同一内存buffer；浏览器用户显式点击后二次SHA/大小核对，页面未自动发文件GET。descriptor完整磁盘校验读取仍有实际I/O，不能说无磁盘读。

桌面/手机真实2份下载逐byte等原ZIP；五服务共75wire（73GET/POST1/PUT1）。缺档/tamper/drift独立fixture分别404/409/409，真实原件从未改；query/穿越/后缀/写请求拒绝且无ZIPbody。10图验证者全看，独审亲看4代表图并独立比下载bytes。每服务原ZIP/17study/13manager/574/421保持、namedguards0/已知uname-p1、均关闭；第五服务补预算DOM连续性只GET。

17相关fake测试有raw日志，不是科研收益。原包绑定source62/docs93，不含当前UI完整环境；复制claim换ID/目录不能重开预算。旧91afwheel不含本路由，最终3770已含。[精确回执](g5-local/study-capsule-download-verification.json)。原唯一audit保持，不因导出增次，开发费用unknown。

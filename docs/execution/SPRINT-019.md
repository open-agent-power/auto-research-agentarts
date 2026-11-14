# Sprint019：同一Workbench的只读外部研究引用API

源码 `e88c3f5c8b69a32cc2418e81abaddd78619e27d9`，clean pin `/workspace/work/saved-study-reference-api-source-e88c3f5`。ProjectController/LocalWorkbench增加静态getter，既有ProjectWorkbench增加唯一 `GET /api/local-workbench/saved-study-reference`。不读取/升级当前项目，不接收路径或study参数，不在POST表中；仅附`scope=saved_external_reference_not_current_project_result`，保留reader非完成态与实际spent，不能当当前项目执行结果。

22 fake及原CPU协议HTTP回归过，独立代码审查过。原manager上的窄真实HTTP8请求：1真实GET200/12198B/27cases/16refs，实际reader1；裸?及两个参数请求均400，POST/PUT405，邻路404；另1手造unknown200单列，非真实study变unknown。wire路径证实裸?没有被客户端吞掉，非法请求不reader/manager。

原study17文件/锁、原manager13文件、state13/两个completed actions/原预算限额2及574文件/421路径集合保持；本次脚本未新算computed reserved，旧reserved0只能沿用此前证据及DB同字节。临时loopback服务已关闭，项目动作/模型未启用。

首次尝试被h5py导入时uname-p的严格守卫阻断：已为保护哈希读取原件，未完成product导入、未启动服务/发送HTTP/调用reader，原件不变。失败保留，成功轮仅放行精确1次/usr/bin/uname -p/shell=false元数据探测，其他列举process/非loopback/DNS/model/native/账本/项目/SQLite写/formal-verifier加载守卫0。不是全进程子进程0。

原LocalWorkbench构造器会mkdir/建schema/取锁，真实验收以__new__仅设置原root/db跳过构造器，真实走新静态handler链。结论不证明正常构造启动无写；不扩大改造历史构造器。独立最终审查仅读已有回执，不重跑HTTP/研究/全574保护。

[使用与边界](../saved-study-reference.md) · [精确验收/身份](g5-local/saved-study-reference-http-verification.json)。仅只读后端/API完成，UI、项目显式关联和三臂执行runtime未完成；当前404wheel不含该后续source。原62/e731、404/4b93、controller/workbench自身新指纹分开保存，旧producer/pins/预算不升级不扩额。0新增研究/fit/产品模型/API/正式审计，开发成本unknown。下一项：沿现有DESIGN增加独立只读引用视图和预算分栏，先核真正无写的host启动路径，再做原案桌面/手机验证。

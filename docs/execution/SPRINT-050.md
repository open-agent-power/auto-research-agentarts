# S050：一次Linux Codex选择探测的可审准备

前置S049已推052b763并固定pin，按最新版AAW v0.3.1以代表性探测调查native Linux模型链路，先交付可审代码/输入/预算，不直接重写Host或启动真实模型。代码复用现有ProjectController context、Host prompt/严格解析和delegated账本。

固定三文档synthetic项目；prepare只记录source/真实远端/CLI版本及bin SHA/context/输入/原预算，不创建Host正grant或模型请求。execute需另行用户批准该prepare SHA的一次新范围后，才留唯一O_EXCL启动标记、分配1逻辑Host额度、启动最多1个CLI进程。只import/validate proposal，不consume、不dispatch研究工具、不fit。未知及工具事件保留原ID/原目录/原marker不重发。

原有0模型边界仍有效。当前只有脚本/合成验证完成，尚未创建真实固定pilot或批准记录，也未运行真实模型。发布固定source后root将只运行prepare，产出可审scope，再就新1次模型范围请用户决定。三文档不是科研评测；无生产Codex provider、真实自主收益或硬费用cap声明。

## 已验与失败

作者12项/root最终12项和独立16项合成测试通过，包括真实fake CLI子进程、无批准/改scope前置阻断、marker不重发、工具事件unknown、source实际远端及shadow检查。190产品源码保持S049原字节。

独审实际复现-B仍读取伪造有效pyc；入口现在于project import前设置私有新bytecode缓存namespace并禁写，真实子进程验证伪pyc不执行且原cache不改。marker文件及父目录同步失败阻止Host/CLI，未声称全面断电/OS隔离。此前本地remote ref、英文长hash批准、reasoning/尾newline三项均具体修复，原失败/probe保留。

完整[方案](g5-local/codex-selection-pilot-proposal.md)与[验证](g5-local/codex-selection-pilot-verification.json)。CLI控制只是请求；工具/MCP/web/文件系统隔离未经证明，底层请求/token/费用unknown；CLI 0.1字段为旧Host API估计字段，不能冒称该CLI实际收费硬cap。没有新付费API配置。

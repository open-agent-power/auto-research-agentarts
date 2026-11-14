# 工作台推进收据与原ID接续

从sourcec5bb4f8开始，LocalWorkbench.advance/advance_recipe仍用同一原请求ID和参数调用ProjectController，再保存core原响应至该manager请求。waiting和unknown分别保存，不把“返回了响应”当作行动completed。重复调用继续经core，不能通过外层缓存绕过其既有规则。

原请求在core保存后、manager结果写入前中断，明确提交相同ID及相同body可沿既有core重放后收尾；不另建ID/项目/预算。没有core parent/child时仍由原core处理，可能在既有门禁下执行原授权行动。未知执行继续占用原预留，不能清零或自动重算。核心拒绝时不制造完成收据，原请求与异常保留。

历史case不会被后台遍历或自动改写；只读host始终拒写。原冻结source/runtime/预算条件仍需遵守，不应以新代码升级或复制旧目录尝试恢复。原core终态重放是保存响应阅读，不证明重新核过所有工件。完整[S028工程验证](execution/g5-local/manager-advance-receipt-verification.json)和[S029安装范围](execution/g6-local/manager-receipt-release.json)区分真实wait/unknown、模拟完成与原研究。

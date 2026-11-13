# 原生 CPU 保存结果阅读验收

## 入口与范围

最终展示源码：`7633792a6e817efe32ec0750e0846be43fdb55f6`。实现为 `frontend/src/cpu-results.ts`，由 `project-view.ts` 的 `comparison` 复用。既有五页、原行动身份、原观察 JSON 和下载沿用；不添加排名、求解、研究命令、付费服务或模型调用。

检索主观察读取 `summary.paired_summary.splits` 的原宏指标、成对均差和 wins/ties/losses；诊断观察没有宏指标时明确指向前序结果，不补造。调度读取 `summary.by_split/per_case` 的原计时、目标与完整排程比较。缺失与非有限值显示未记录，真实零值保留。

本次展示复用已知公开结果。负的 Recall 变化和唯一慢例始终可见；133 adverse 不等于 133 条候选恶化。完整字段与行为见 [Sprint007](../SPRINT-007.md)，旧科学范围仍以 [原生总审](native-final-review.md)为准。

## 最终实际检查

云盘原件 `runs/sprint-007-ui-20261113-04/receipt.json`：

`cb49d1f0ac837d9b232d02022ceb79f20fac91d60147b599ec373c23dac98aab`

最终 04 整组通过，两真实已有项目、桌面与手机共 4 浏览器上下文、20 个项目／尺寸／页面组合及 38 张截图。80 浏览器 GET、0 POST／非同源拦截／页面错误／HTTP 错误；4 原行动下载与磁盘逐字节相同，8 报告 HTTP 读取及前后五类 API 摘要一致。真实 GET 不计作新的研究 tool dispatch。

表格容器保持在 CPU 内容宽度内；手机可横向及纵向滚动。对每个可见表格滚至末端，检查最后正文单元格文字范围不被固定首列遮住且不越过右边界。实际看图核对 `retrieval-mobile-table-right-0.png` 的完整胜／平／负和 `scheduling-mobile-table-right-1.png` 的倍率／目标；键盘展开、完整任务数量、深链接刷新及浏览器后退也通过。Agent 看图不等于用户体验已获用户认可。

根看图原件 `visual-review.json` SHA256：

`83d0f4e38a5fbdc068f132129b6ff827ba5c392a3a4e964e19b3bfadf4296d7c`

494 保护文件前后清单 SHA 均为：

`3a379a7a7aca359d3b6c7f538cef176bd1fe7e0a25a0c24a7f0f24c33a5d6407`

三案例根完整文件路径集 421 条相同；额外原始数据及协议也在 494 清单中。保护范围是列明的研究原件，不声称整个工作盘未写入浏览器或开发证据。

## 独立审查与工程检查

`runs/sprint-007-semantic-review-20261113/acceptance.json`：36 项保存来源／schema／计数核对，SHA `fce8fdd82da59b81f28aa20dfc4ee2215f09929288daa24720e9367933041eb5`。

`render-review.json`：63 项编译展示检查，SHA `f84b1b31bcc2264b016eddd80de9a805604715876d4e96d10ee0eec8a7402b91`。它针对初版相同数据逻辑，不能冒充 CSS 浏览器检查；后续变化及最终浏览器证据由独立最终回执另外绑定。

`final-source-binding.json`：20 项初次布局修复源码绑定，SHA `d292b41f69835adf9aaaa2e96b156b1a0249ec00aa445c808d18233b24f912ad`。后续只改手机样式及其生成 CSS，原回执保持原范围。最终独审的精确 SHA 见[机器索引](cpu-results-ui.json)。

`npm run format:check`、`npm run lint`、`npm run build` 已实际通过，build 内执行 `tsc --noEmit`；最终 CSS 改动再次 format/build。没有新增 Python 产品代码，因此不重复历史全套工程回归或拟合。

## 失败与恢复

- 01：基础检查 passed，但看图拒绝其手机布局，保留 receipt、全部图片和实际展开前后几何诊断。
- 02：检索部分完整；调度服务返回 `LOCAL_WORKBENCH_FAILED`，后续 GET connection-refused，整组 failed 保留。CLI 没有公开细因，不推断已查明。
- 03：原调度服务恢复后原项目只读检查 passed；进一步横向截图发现末列被固定首列遮住，独立审查记录为未完成手机可读验收。
- 04：从最终 pin 用新展示端口 18836/18837 启动；两个服务先健康核对原 state/budget，再完整检查。没有创建或复制研究项目，没有重发任何科学行动。

当前预览从 `/workspace/work/native-cpu-ui-7633792` 的 `scripts/serve_local_workbench.py` 启动，使用原 `.venv/bin/python -B`、`PYTHONDONTWRITEBYTECODE=1`。`--root` 分别仍是 `runs/g5-native-cases-20261113-01/{retrieval,scheduling}/manager`，不带 `--enable-local-actions` 或模型参数。中间 2f 展示进程已停止，旧科研 pin 不覆盖。服务冷启动时可用相同入口只读重开；任何研究 unknown 仍只能按其原 ID 处理，不能用新目录重新执行。


最终独立回执 `runs/sprint-007-semantic-review-20261113/final-review.json`：807项限定验收通过，SHA256 `32ab952808fcd685e36968c11af1f0fc47763d6061c813552bbad3f53c812ee2`。实际查看4张最终图片；接受结果展示增量，不扩大科学或隔离结论。

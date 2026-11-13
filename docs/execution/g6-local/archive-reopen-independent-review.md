# Archive-only 保存恢复独立审查

结论：接受本次 **G6-L archive-only 保存恢复**。02 从原 77,407,847 字节 ZIP 提供 case、原请求、报告、源码 bundle 和 wheel，在全新 scratch 中实际取回 8 个已完成请求。没有重新排名、求解、拟合、调用产品模型、提取来源或生成报告；这不等于模型重训复现、完整离线依赖安装、OS 隔离或原 G0/G6 全部通过。

## 准入与物料身份

- 原 ZIP SHA-256 为 `e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58`，根 manifest 为 `6c35932e8a9170c868b89e198479b4c7b52670b366720bda39ee6e9ebf40f1e1`。路径、重复项、特殊文件、大小、完整成员集合、CRC 与 SHA 在首次写入 scratch 前核验。
- 02 root 为 `/workspace/work/g6-archive-reopen-20261113-02`，prepared SHA 为 `f31c5adc6fc1e73ad7e5e308e9fc9843b76beaca6eb1e533e47cf83e96c57d21`，helper 为 `da287780a3a694719d80c4e1d615fb9661e9facde45eb2b0b2f6be72c7c6b83f`，由提交 `82d44b4` 固定。新审批 `recovery-02-review.json` SHA 为 `54f00e2e8c9d1627ca2b5a32e1dd6d812862a954f814538b2bad022b68199db0`；没有复用 01 审批。
- 内部 bundle 的 tip、科研、展示版本分别为 `e97c0a6`、`8e8a206`、`e638b5f`。三个 checkout 的完整提交与 clean 状态匹配；两份科学 freeze 的源码清单吻合。
- 独立核对全部 930 个 payload 文件、187 个完整 target 文件、177 个 Git/wheel/target 产品文件。导入前和收尾均比对完整 target 树，覆盖 metadata、bin 与新增 `.pyc`、`.so`、`.pth`；只核 177 个产品文件的原始缺口已修复。
- 第三方依赖透明复用 `/workspace/work/g6-native-release-20261113-01/venv`。Python 3.12.14，实际 loaded 与安装 metadata 的 NumPy 2.5.4、SciPy 1.17.0、scikit-learn 1.8.0 相符；产品只从本次新 target 加载。该 ZIP 没有提供完整依赖 wheel 集合。

## 真实失败与修复边界

01 在归档 target 的产品导入链中，由 h5py 请求 stdlib `platform.processor()`，其 `uname -p` 被严格 Popen 守卫拒绝。尚未绑定 manager 或重放请求：完成请求 0，实际探测进程启动 0，fit/来源/模型/新计算均为 0。01 的 host attempt 仍为 `unknown_preserve_no_retry`；六个失败控制文件原 SHA 全部保持，没有改写为成功。

02 使用单独审查的新 helper 与 scratch。child 在已有文件、导入和网络守卫内先预热真实平台缓存：仅允许一次精确 `['uname', '-p']`、4 个 stdlib 参数，拒绝调用者 shell、executable、env、cwd、位置参数和第二次调用；强制解析系统 binary，并保存 binary SHA、stdout、returncode、processor 值与计数。随后恢复严格 Popen 禁令，才导入数值依赖和产品。

实际 bootstrap 执行一次 `/usr/bin/uname -p`，stdout 为 `unknown\n`、returncode 0、processor 为真实空字符串；bootstrap 网络为 0。不能把整个 child 描述为零子进程。保存恢复阶段的子进程、网络、fit、新计算/模型/来源/报告与原存储 fallback 守卫均为 0。

## 实际保存恢复结果

两域分别取回原 `native-primary`、`native-audit`、`native-wait`、`native-report`，共 8 次，全部 `replayed=true`。未调用 create/import 或重新派发工具。每个原 manager 保持 2 个 spent tools、0 预留、3 个 plan、2 个 completed action 和 waiting 状态，fit/model/source-extraction 为 0。项目、run、source scope、parent/child/result 身份与四个原报告文件均匹配；绝对路径声明未被改写。

97 个实际产品模块的来源全部位于 02 新 target，且字节与归档产品清单匹配。原仓库、旧 case/packet 和旧 venv 产品的读取 fallback 被拒；外部 observer 只用于保护证明，不向恢复供应 case 输入。

独立只读结果检查 1510 项通过，核对 8 个保存响应及接受正文 digest、SQLite 项目记录和动作、预算、8 个原报告附件、97 个模块来源、完整 payload/target 与 bootstrap/attempt 回执。审查者没有重放任何 ID。另一个独立子审核对 494/494 原文件身份及 10/10 完整树 nameset，symlink 为 0；01 六个失败控制与旧 ZIP 身份保持。prepared 阶段另有 1838 项检查通过。

结果 SHA：`recovery.json` 为 `458e1712ba9f662866d17466b1876451a7e41e53aee867e5b7f4b0569ce06a41`；`dependency-bootstrap.json` 为 `43a425a53e3cd06837069d856a0ca3b1a98e920ce4c498bb8cbf32a9f5fd09f6`；`attempt-final.json` 为 `dc5b1ad20ff2a16a7dabc836e682e53a8248ac6398f42baf73a9839fa95d2a88`。

## 审查记录与限制

本审新增的只读 checker 最初误把派生 budget 当持久化 budget 全量、把 manager advance intent 当 controller 完成响应、把 project ID 当报告 slot；三次断言失败、v1/v2/v3 代码和诊断均保留在 `runs/g6-archive-reopen-review/`。按产品真实层级比较后 1510 项通过，期间未改 case、控制、预算或发出请求。这些是审查工具的假设错误，与上面的真实 01 恢复失败分开记录。

证据入口：`runs/g6-archive-reopen-review/{prepared-02-review,recovery-02-independent-results,final-review}.json`；外层保护证明 `/workspace/work/g6-archive-reopen-precheck/recover-02-protection-receipt.json`。完整结果检查脚本为同目录 `verify_saved_recovery.py`，仅用标准库读取保存数据。

没有当前阻断级问题。结论限于同机合作式守卫下的归档保存接续；依赖仍来自已有环境，未重新训练或重算科研结果，未提供完整 OS 隔离、不可见评价或原完整 Gate 的证据。开发 token、金额未知，不写为 0。

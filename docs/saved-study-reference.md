# 读取已完成的独立研究引用

固定研究`g5-scheduling-threshold-transfer-v1`的只读入口：

```bash
python /workspace/work/saved-study-reference-source-a1152b4/scripts/read_saved_study_reference.py summary
```

`status`使用同一完整绑定检查。入口只支持这一原study和固定原件路径，不接受任意目录、study ID或执行代码；源码 `a1152b4f5d952888d583086e01d023badb95a955`。系统Python/stdlib即可读取，不依赖完整科研venv；它没有重新执行研究，原producer仍为source62/e731，不用当前产品4b93替代。

成功返回`completed`、原study/claim/请求ID、冻结协议/计划预算与实际消耗、27案例保存摘要、唯一保存审计结论及16个原文件的路径/长度/SHA引用。输出JSON12136B（CLI换行后12137B），上限64KiB；不内嵌完整raw、不作为现有4MiB经验包，也不伪造native project/action/run ID。原2.16MB结果中的2400主事件、另存primary完成回执及live SQLite末2条审计事件须共同绑定，不能仅凭旧结果文件的phase字段断言完成。

缺档返回`unavailable`，未决/操作性SQLite错误返回`unknown`，已知失败返回`failed`，篡改/其他损坏返回`integrity_error`，均不填0预算或补造成功。非completed的CLI退出1；不新建账本、换ID/目录、重跑生成/求解/正式审计。没有原云盘时如实报告缺失，不能用导出包重造历史。

字段`binding_only=true`、`numerical_recomputation=false`、`raw_data_included=false`和`may_execute=false`明确这是保存引用，不是重新数值证明、来源认证或执行授权。它不访问/写当前项目预算；`current_project_budget_unchanged`只指该reader不改预算，未检查其他并发项目。历史源timestamp/boot被保留，不因当前boot不同重执行。

最终源码由独立成员用系统Python只调用一次实际CLI；product导入前进程/网络守卫、导入后生成/求解/账本写入及formal verifier加载守卫均0，17原文件和锁字节保持。此前旧源码成功读取记录与最终验收分开。10项假工件异常/绑定测试及独审通过，完整证据见[验证索引](execution/g5-local/saved-study-reference-verification.json)。

此版本仅host-only reader/CLI。后续Controller/Workbench只读API、项目显式关联、前端和三臂执行runtime各自需要独立实现；404成品不含该reader，不将这些待建项写成完成。

S019 source `e88c3f5c8b69a32cc2418e81abaddd78619e27d9`另已接入既有ProjectController→LocalWorkbench→ProjectWorkbench固定GET `/api/local-workbench/saved-study-reference`，只附外部引用scope，不取当前项目binding，不关联项目。任何query（包括空`?`）、POST/PUT和邻近路径均拒绝；无配置workbench时404。API成功仅表示已读到原保存引用，不代表新的原生primary完成。

[HTTP验收](execution/g5-local/saved-study-reference-http-verification.json)为绕过会写构造器的窄场景，使用原root/db与静态真实链；不能据此承诺普通LocalWorkbench构造启动只读。首次h5py的uname-p守卫失败保留，成功轮精确允许一次该元数据探测。UI、项目关联和三臂执行仍待建；404wheel不含后续reader/API。

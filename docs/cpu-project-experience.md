# 固定CPU保存结果的方法经验

三项固定primary（citation检索、relevance检索、加权区间调度）使用独立的 `cpu-project-experience-bundle-v1` 和 `project-saved-cpu-byte-binding-v1`。只接受原项目唯一、已完成的primary行动；audit、pending、unknown、失败或未完成行动明确拒绝，不通过新ID或复制项目重新执行。

## 捕获与身份

`derive_cpu_observation(workspace, action_id)` 读取原ResearchProject，核对project/run、注册方法、原方法实例/参数/评价、请求SHA、原source文件字节SHA和原生协议、result封套及producer。前后项目state、捕获runtime与实现文件身份必须相同。原项目登记身份、原producer、当前capture runtime与模块SHA分别保留；这不是升级原项目。

保存条目为 `diagnostic_observation`、`numerical_recomputation=false`。scope包括来源snapshot、输入承诺、捕获实现身份与独立协议；输入承诺为 `fingerprint({result_sha256, retained_source_sha256: fingerprint(source)})`，绑定全部保留的spec、原spec字节和资产引用。原spec与其base64/hash一起改写也不能沿用旧记录身份。

封套保留完整原action、envelope/tool_result、原scope、完整spec（含有序分区数组）、spec_source原字节、资产SHA/size引用与限制。所有排名、逐query指标、负例/缺失正例，或完整jobs、runs和schedules保留，不能截取较好结果。**不包含原source packet和语料等资产原字节**；scope或snapshot SHA是引用，离线无法据此独立重算缺席的原包。自带哈希不是签名或独立来源证明。

捕获时校验真实原source；离线验证重做保留字段、结构、绑定与已存值一致性。对已存指标汇总、保存schedule可行性和算术的复核，不是重新排名、金标评分、拟合、求解或新研究，也不证明科学正确性、许可批准或封存评价。

## 记忆、导出与检索资格

`CPUExperienceMemory` 复用现有ResearchMemory的有界知识存储、exact-scope检索、事件链和撤回。新增binding存储模式返回 `binding_validation`，事件明确数值正确性未审；旧数值模式返回及原因保持。相同ID不允许改变不可变内容或跨验证模式重入；合法provenance版本可追记。重新导入不恢复已撤回记录，恢复使用原entry与明确的状态请求ID。

CPU与Ridge使用显式schema分派。旧 `project_experience.parse_bundle` 仍严格Ridge-only；CPU不会假装Ridge/OOF或放宽其检验。当前项目沿原experience-import/status/resume和同ID账本保存原包，方法案例仍最多4个active，恢复与撤回规则不变。完整原包继续进入报告input资产，报告与界面按CPU语义显示保存对照，不显示Ridge/MAE/目标列占位。

summary最多64KiB，只投影原方法/评价、来源身份、保存分区/负例计数与汇总、限制。完整数组在原包。只有显式导入的active案例进入现有条件context，按domain/contract和method/evaluation关联，始终标 `analogy_not_current_evidence`、`scientific_validation=false`；不添加候选、改变参数/排序、自动选臂、消耗研究额度或晋级。

## 本机CLI

```bash
.venv/bin/python scripts/cpu_project_experience.py import-project --memory <知识目录> --workspace <原项目目录> --action-id <原primary行动ID>
.venv/bin/python scripts/cpu_project_experience.py recall --memory <同知识目录> --scope <原scope.json>
.venv/bin/python scripts/cpu_project_experience.py export --memory <同知识目录> --scope <原scope.json> --entry-id <原entryID> --case-id <案例ID> --version 1 --method-card <方法卡.json> --limitations <限制.json> --output <新案例.json>
.venv/bin/python scripts/cpu_project_experience.py validate --bundle <案例.json>
.venv/bin/python scripts/cpu_project_experience.py summary --bundle <案例.json>
```

导出必须有精确匹配的原方法卡和1–8条限制；实际UTF-8原包最多4MiB，紧凑输出，不因缩进超过读取上限。已存在相同字节返回原文件，不同字节拒绝覆盖。retire/restore须带原entry-id、明确reason和request-id；include-retired只改变读取范围，不恢复资格。

本能力闭合保存证据与咨询资格，不认领策略迁移收益。尤其ArguAna的固定TF-IDF候选与对照同臂，仍没有可识别的因果记忆增益；旧亏损和未标注/缺正例保留。产品模型/API默认0，开发协作模型成本unknown，SDK/runtime、OS/sealed和多代RSI边界不变。

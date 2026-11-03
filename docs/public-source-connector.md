# 公开来源接入：Europe PMC DOI 元数据

目标是在同一 P02 项目里，把一次官方公开 HTTPS DOI 查询的原响应及来源身份交给既有来源读取链。它补充文献身份/可用性元数据；作者对象、通道、导出列、批次及 ALP 映射仍须另行取证。接入不创建新项目、不重跑 primary、不增加模型或拟合；平台接入与现金边界沿原约定。

## 三种工件必须分清

| 工件 | 身份与内容 |
|---|---|
| `provider-response.json` | `response.bin` 原 HTTP 响应实体字节的逐字节副本，不美化或重排JSON。保留整个响应，未选区也进入来源资产 |
| `host-projection.txt` | 宿主从严格JSON解析结果生成的确定性投影。每行标记宿主派生身份及原响应 JSON pointer，仅投影精确匹配 DOI 的有限书目字段与 URL 元数据 |
| `host-provenance.json` | 宿主取得/转换记录：请求和最终URL、取得UTC、HTTP状态、安全响应头、原字节SHA/大小、任务身份及代码身份。不是提供方原响应或作者确认 |

原响应的来源URL是实际 API 请求URL；两个宿主工件使用各自内容SHA的 `urn:`，并在 provenance 连接回原响应。原文与宿主主张、HTTP成功与科研资格分别保存。`isOpenAccess`、链接列表、公开可访问都不自动成为复用许可；许可或访问条款未核实时明确保留 unknown。不投影摘要长文，不跟随 URL，不声称取得全文。

## 复用同一项目的流程

以下为模板，替换尖括号参数；输出目录都须是新的，并与原项目、原HTTP响应分离。

```powershell
.venv/Scripts/python.exe scripts/run_research_project.py evidence-task --workspace <同一P02项目目录>
.venv/Scripts/python.exe scripts/fetch_project_source.py fetch --workspace <同一P02项目目录> --request-id <取得ID> --doi <目标DOI> --output <新HTTP目录>
.venv/Scripts/python.exe scripts/fetch_project_source.py status --workspace <同一P02项目目录> --request-id <取得ID>
.venv/Scripts/python.exe scripts/fetch_project_source.py build-bundle --workspace <同一P02项目目录> --request-id <取得ID> --output <新bundle目录>
.venv/Scripts/python.exe scripts/run_research_project.py register-evidence --workspace <同一P02项目目录> --request-id <登记ID> --bundle <新bundle目录>
.venv/Scripts/python.exe scripts/run_research_project.py next --workspace <同一P02项目目录>
.venv/Scripts/python.exe scripts/run_research_project.py advance --workspace <同一P02项目目录> --request-id <推进ID>
```

使用前核对各 CLI 的 `--help`。`fetch` 的实际请求、超时、累计来源请求上限及未知恢复以 [europe_pmc.py](../src/autoresearch/europe_pmc.py) 为准。`status` 仅离线核对/恢复取得记录，不发送新请求。`build-bundle` 也只读保存响应、构造本地新包，不注册或提取研究选区。

同一项目在首个 `fetch` 时冻结 **8次公开GET额度**，独立记录实际派发、已取得/失败及未知预留；换输出目录或请求ID不重置累计额度。已有 unknown 时阻止新 fetch，**0次自动 retry**，不能把超时当失败后静默重发。这允许同一项目后续继续取得其他论文，不代表本页已实际发送8次。模型请求保持0，原5元现金上限及未知结算、平台暂停不变。

已 received 的同一 DOI 使用原请求ID离线复用；本次原取得ID为 `a12-doi-metadata`。已知失败可由操作者显式使用新ID重试并占剩余额度，不能覆盖失败记录；unknown 仍阻断其他新 fetch，不能借换ID或目录绕过。取得与选区提取是两套独立计数，不能把 GET 1/8 与提取2/8合成一次总预算。

task_ref 精确复用 `evidence-task` 返回的 project_id、旧 completed P02 primary 的 based_on_action_id 和 method_id，不用换项目、重新 primary 或修改来源收据来适配任务。若原项目需要代码升级，主控须沿显式 upgrade 流程保存版本记录；不因目录或连接器变化重置预算。过期状态、unknown 或费用约束不由构包器绕过。

## 数据边界和失败

- JSON 重复键、非有限数值、非法结构以及 hitCount 与结果页不一致都拒绝构包，不解释为零命中。
- 真正 `hitCount=0` 时投影明确记录“提供方返回零”，不证明论文或测量映射不存在。有结果但没有精确 DOI 匹配时单独说明，不把其他记录塞进目标论文。
- 只投影当前返回页；最多8个精确匹配记录、每记录最多4条URL元数据，字段过长会明确标注宿主截断。全部原响应仍完整归档，不自动翻页或扩搜。
- 投影和 provenance 使用实际物理行定位，分别受256行、60000 UTF-8字节限制。超过范围明确拒绝，不能静默截短整个响应或伪造页内完整性。
- 只有完整 received、HTTP 200、未截断的 JSON 原响应能构包；错误或未知记录保留，不自动重发。已存在输出不覆盖。
- `register-evidence` 仅登记冻结收据和资产；控制器选择后才执行实际来源读取和FTS。提取仍输出 mapping unresolved、资格 unknown；原作者映射待办保留。

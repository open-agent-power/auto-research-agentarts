# S122：后继计划的只读决策预览

新增 LocalWorkbench Python 预览：认证 completed S121 原请求、原反馈、计划与 claim，读取真实最新 context、唯一绑定原 primary 的 audit 候选和预算。默认 wait；明确的反馈后规则可建议事后 audit，但不授权或派发，原登记 wait 不变；原 audit 已完成或预算不足等待，unknown、未决、证据漂移停查。不支持 holdout 或非空 knowledge_refs；不运行模型、fit、重排、评分或 final。旧项目不升级 manager pin。

固定 HEAD `39030cfc85c6dbc1fb13c21c9965fd48df2100b2` 加本次候选，205 项清单 SHA `28d7cbc5a930a9bf66a69d0a70364f003efc5f5ab03c7623fc00b56c2010a55f`。作者三模块47/47，独立专项12/12，日志 SHA `dd5f6032e8c10df03dae9679fc2342b6383d0bfea9f74d0adfaea1dcad733c9f`。独立新合成夹具核完整文件树：仅创建两个各1字节 writer.lock，其余文件字节不变、无 SQLite sidecar，dispatch/step/save/accept 哨兵未触发；锁副作用不等于全文件零写，非 OS 隔离保证。实际 direct 相同 primary 新ID复用原 action，预算不变；悬空WAL拒绝。

两个不同反馈的示例使用同一后验映射，但事前条件算子不同，不是同一预注册规则的受控科研比较。规则为操作者提供，非模型从计划推导；仅合成，无新真实研究或模型。新增功能仅Python、无HTTP/UI或执行权限。初报HEAD误用旧值，已核正；旧真实项目/原盘未打开。

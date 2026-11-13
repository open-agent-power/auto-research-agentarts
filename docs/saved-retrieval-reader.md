# 保存不利查询阅读器

已经完成的原生引用检索项目，可在实验中心的原行动卡点击“查看不利查询原记录”。页面不会自动读取，也不提交研究。每页最多25条，保留原顺序和原分类；选择查询后才读取原查询、两臂各最多20篇保存文档及原指标。主检索行动和保存审计行动均沿同一已登记项目读取。

133条原记录包括60条指标损失，以及73条无指标损失但召回不全（65两臂不足、8仅基线不足）。这些数字来自完整保存结果，不能由只有总数的observation投影补造。指标改善不自动采用候选；未列入原引用标签不等于文献与查询无关，引用标签也不是支持／反驳或答案真伪判定。

## 读取与边界

选择查询后展示原queries.jsonl行号、输入SHA、保存指标及两臂文档序位。展开文档可阅读标题和文本、原corpus.jsonl行号、文档ID、SHA及原引用标签；原行动和前驱身份可展开核对。返回列表恢复触发按钮焦点和列表位置。

没有保存逐文档检索分数，因此不提供或补算分数。文档正文最多展示4096个Unicode字符、标题512字符、查询4096字符，超过时明确提示展示截断；原输入字节和原定位保持。它读取保存的top20，不重建未保存的全语料排名。手机指标表可局部横向滑动，正文和来源身份换行，文档列表有界滚动。

切页、刷新或加载失败不新建项目、不重发科研请求、不扩预算。刷新后需重新显式读取。项目/快照不符时显示错误；失败分页保留上次已核对分页并标明，失效或已移除的异步视图不会接收新结果。

## 只读HTTP接口

两个接口均为GET，始终要求来自当前`GET /api/project`的三个字段：`project_id`、`snapshot_ref`、`action_id`。action须为当前项目中已完成的原检索或保存审计行动。客户端不提交文件路径、研究request_id、模型请求或运行参数。

| 路径 | 附加字段 | 返回 |
|---|---|---|
| `/api/project/retrieval-adverse.json` | 可选`offset`（默认0）、`limit`（默认25，1至25） | `saved-retrieval-adverse-page-v1`，binding、pagination、全体分类counts和本页items |
| `/api/project/retrieval-query.json` | 必须`query_id`、`split`（dev/validation/test） | `saved-retrieval-query-v1`，binding、原query、分类和两臂metrics/qrel/documents |

只接受单次非空字段和精确字段集合，选择器最多2048字节，页offset不得超过原不利行数（允许空终页）。不存在的原行动或不利查询返回404；非法、重复、未知或超限选择器返回400；旧快照或活动项目变化返回409。工件损坏或超限返回固定错误，不泄露宿主文件路径。现有写门禁与同源规则不变。

每次读取均验证项目、完整结果封套指纹、action/result/source身份及audit→primary关系。source.json先按既有16,000,000字节上限读取，再按原资产上限和SHA校验；单行动最多5MiB，响应最多1MiB。保存query/文档行号、qrel来源及两臂完整记录资格均核对；模块只验证并复制原值，不调用执行器、索引、rank、评分、拟合或控制器行动。

服务在读取前后重新核对当前活动项目和snapshot，前端再次核对project/snapshot/action/result/source与原primary绑定。接口不接受客户端任意路径。文本通过textContent展示，不把原metadata里的支持/反驳注释当作检索真值。

## 实现与实际证据

后端为`src/autoresearch/saved_retrieval_reader.py`，路由在`project_workbench.py`；前端为`frontend/src/retrieval-reader.ts`，从原`cpu-results.ts`／`project-view.ts`复用。源码固定提交 `0acb05e253f543ea2483e383c7e2358c81c422bd`，旧科研codeidentity仍为 `3945ed0f5ec85b0ce42af0bb9ac0d0c27034bf932dac27fee9f7008ec2d3707e`，不升级旧producer。

针对性测试17项、原HTTP门禁5项、前端format/lint/typecheck/build通过。真实原项目HTTP59次GET检查覆盖12页、两行动共6次查询详情及26次错误返回；两个已有项目的桌面/手机五页与按需阅读在实际浏览器验收。完整证据和限定审查见[Sprint009](execution/SPRINT-009.md)。这是保存结果阅读增量，不是新增科研收益、隐藏评价、完整隔离或多代RSI。

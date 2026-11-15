# S131：两条合成反馈后的人工计划与原ID恢复

续用 S130 两个原合成项目，在 HEAD `d6270082c5f51ebbe4cdb4df7745192999a6c8ad`（与原执行 HEAD `435578e5507c499d1a48995c3c17872d10b52d22` 仅文档不同）按原反馈分别保存人工 plan v2，未再派研究。原树87文件先完整备份并独审逐字匹配、无 SQLite sidecar，备份清单 SHA `6c65ae930178bff23305b9d74143aaa83e03ff07b8a2e6d61ce38a8b825625c7`；备份仅证据，不能替代原manager路径。

每案真实浏览器首个保存请求在服务返回200后人为丢回执，刷新后以完全相同原body/ID resume-only；原body逐字保存并校SHA。S127 plan `local-successor-plan-733da262-7a02-411d-860e-bd0a120991b8` SHA `8c7b45594c9bd6b6120c95df2e3a0080e0035142c4ab74b0b0f7a450b7adaf4e`；S129 plan `local-successor-plan-448d224c-abdc-43ab-aff0-67a3029f20a6` SHA `a310a03c2dabc89f09ddb3885303c6ead124bbb8031d420f9f841b5cd9d3bd91`。默认预览均 wait；显式后验规则S127仅建议 audit 且需新授权，S129 wait/audit_already_completed，均 may_execute=false。

独立只读核199文件清单 SHA `35aa10fa0326d48cb05c3397c0f0127287e43ce14071e49ec07ea0490a9bac2f`，与备份逐表对照：仅4个SQLite合法变化，每案新增plan v2/claim及manager completed intent/receipt；原actions、claims、source、三行动工件及预算1/2和2/2不变。作者预览前后双库 SHA 不变，dispatch/step/index/rank/score/audit线程函数profile为0；锁文件可能写，此非OS隔离/无网络证明。独审核脚本及回执，未重跑浏览器；人为丢回执非SIGKILL。原脚本曾将body多写换行已修正，初稿保留。仅人工白盒合成，不构成真实科研或模型自主。

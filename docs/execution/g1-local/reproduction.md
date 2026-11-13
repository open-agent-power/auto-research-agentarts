# 复现、只读验算与恢复

这是经批准的可信本地切片交付，不是原G0/G6干净环境验收或无人值守模型runtime。固定研究源码提交为`5d36424`；原始冻结记录保存runner、独立评价器、controller、授权、协议和两设计的8项SHA。研究期间原生核心代码未改，环境未升级。

## 当前云电脑入口

- 原案例：`/workspace/auto-research-agentarts/runs/cloud-concrete-local-20261113-01/`。
- 原生manager：上述目录的`manager/`。单个project SQLite及工件、原始上传、来源捕获、manager映射和报告均在其中。
- 原官方数据与字段/许可原件：`/workspace/work/g0-data-research/`。
- 独立算术：`runs/g1-local-verification/final/`；重放与流程：`runs/g1-local-review/`；浏览器/PDF：`runs/g1-local-ui/`。
- 本地只读工作台：云电脑中的`http://127.0.0.1:18830/`；没有外网发布，写操作和模型CLI关闭。

使用已验证的项目虚拟环境`.venv/bin/python`，普通宿主Python缺少来源依赖h5py。精确包版本见[运行环境](requirements-reproduction.lock)；当前venv继承预装系统包，不把它称作全新干净安装验证。

## 只读独立验算（不重新训练）

选择尚不存在的输出目录：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/verify_concrete_reproduction.py \
  --manager runs/cloud-concrete-local-20261113-01/manager \
  --original-csv /workspace/work/g0-data-research/data.csv \
  --output runs/my-new-concrete-verification
```

该工具只读SQLite和文件，用原输入及保存的Scaler/Ridge参数重建预测，禁止`.fit`。输出保存全部检查、失败及逐行/组/折对应；只有所有要求通过才退出0。输出目录不得覆盖输入或旧证据。

研究启动时先用baseline阶段冻结计划v1并执行第一轮；读取真实结果后保存plan-v2，再运行candidate，最后plan-v3/finish。`scripts/run_concrete_reproduction.py`只是固定案例宿主胶水，所有研究动作仍经原manager/controller。它不是通用研究控制器或模型Agent，也不能通过新ID/目录重置本例额度。

**不要为验证本次结果重新执行研究阶段或创建新项目。** 已完成请求的安全重放使用保存的原ID/原参数；独立审阅脚本将任何新拟合、工具、网络或模型派发变成异常。当前20次fit上限已用满，更多研究需要新的明确范围和授权，不能复制本例预算当新额度。

## 恢复包的内容与边界

交付准备保存在`runs/g1-local-delivery/`：包含代码Git bundle、完整case（manager映射/SQLite/工件/来源/冻结请求/计划/原生报告/图）、原始公开数据与许可、独立验算/重放/界面证据、监督脚本、文件哈希清单及恢复说明。第三方上游整仓、凭据和浏览器profile不打包。

原生`report.json`不是可自动恢复的数据库；恢复必须保留完整manager和原项目工件。文件移到新路径时，旧宿主来源注册请求含原bundle绝对路径；应核对源bundle所有字节一致并记录存储路径映射，仅在内存中指向恢复位置，不改原请求、科学参数或SQLite。原生请求指纹绑定相同来源receipt，不把改变存储位置当新研究。

恢复路径检查另留`runs/g1-local-restored/`，不以新建替代项目伪装重开。同环境新路径验算3252项及29原ID重放/18项检查均已通过；重放期间禁止访问原case，原请求/账本与恢复副本101个文件字节保持。原源bundle位置仅作内存映射，不代表冻结whole runner可任意位置原样运行。G6新机器安装、完整上游运行和安全隔离另行验收。

## 图表与报告

原生导出为report JSON/Markdown/PDF、input JSON及manifest；完整source、OOF与系数保留在项目工件。图表是只读保存结果的派生视图，脚本`plot_concrete_reproduction.py`输出PNG/SVG及来源/输出SHA，包含负预测及年龄覆盖稀疏性。它不修改研究状态、不执行fit，也不构成外部科学验证。

已生成归档`runs/g1-local-delivery/concrete-reproduction.zip`，280条目、ZIP CRC及逐文件SHA全核验；包含的代码main为`ab1e9da`，研究冻结仍为`5d36424`。其后归档清单/Worker接入说明等元数据提交不改变归档内研究身份。[归档清单](delivery-manifest.json)保存SHA与大小。

# S077 — 新表格 Project 的显式用途声明

`ResearchProject.create` 新增仅供新建 `data.tabular-quality-audit` Project 使用的可选 `evidence_purpose="operator_declared_descriptive_research"`。该值是**操作者声明的拟议用途**，不证明研究已获授权、来源许可或领域资格成立，也不改变候选、预算、模型权限或 `scientific_validation`。省略参数时，原顶层 `isolated_adapter_regression_not_new_research` 值及 registration 形状保持不变；显式 null、布尔、其他值及非表格主方法在创建目录之前拒绝。当前只有 Python `ResearchProject.create` 支持该选项；Workbench/CLI 的**直接创建**接口和 UI 未扩展，已创建的 Project 可沿现有 manager import 路径导入。

显式值同时保存到 Project 顶层和 registration，读取时检查两处一致；原配置重开返回原状态，漏传或改变配置会冲突，不给旧 Project 补贴标签。显式用途的重开另核 Project 内保存 `source.json` 的原 SHA 和 snapshot；改变原文件时拒绝而不重建。Project 原状态及 `report.project` JSON 可见声明；它不是签名，也不防能够协调重写完整账本的攻击。旧 Project 的状态不迁移，默认读取不补新字段。

冻结 `runs/s077-verification/source-freeze.json` 的 SHA-256 为 `60e9c7928183b654e9c69bd5cfe31f068df89c368e8fe335a2153dd5f4d30ad4`，含 192 个产品 Python 源及专项测试，共 193 项。修改前 Project core 为 `e4424e6e8b1d0927f1d6dd71d412767b1210a29e4dc84f91`，候选新 core 为 `3bcccb20f6b428795fe7563ba9892af99fa83ed06704923fefe9e3f70c846f0e`；旧 pin 保持原 core，不自动升级。`research_project.py` SHA `caa47c451f70a30eb48a30f98274190cad6e66e45e58f6ae32d49908261d50e6`，`tests/test_project_purpose.py` SHA `986ebeaddfb6315eb0403729a012f1ca5fbab160d7653b329a8464584cdb0b9a`。

作者相关合成回归 27/27 通过，日志 `runs/s077-verification/related-regression.log` SHA `ecc1d9b96fbb7dc3a668cb2166c983339a13c30d2a271634c4bd1b6890466ee3`。默认状态的新旧合成比较在移除不同实例必然不同的 Project/run ID、core 和 snapshot 后字节一致。作者首次基线因将 source 放入 Project 父目录触发原 `SOURCE_OVERLAP`，换隔离合成目录后通过；第一次专项将两个不同 Project 的 snapshot 直接比较导致测试断言失败，修正比较范围后通过，失败记录均保留。

独审 [本机记录](../../runs/s077-review/independent-assessment.md) 对冻结前后 193 项逐一核对，独立合成检查 4/4：旧版实际源码创建后由当前代码只读，完整 canonical 状态和 snapshot 相同；显式用途/非法输入、内部 source 漂移、原 manager import ID 重放、report JSON 及两处单字段 SQLite 篡改按预期处理。独审另单独重跑作者专项 6/6；这与独立四项及作者 27 项分别计数，不重复包装为独立新测试。模拟创建中断后保留部分 source 且拒绝重建，不声称断电恢复或 OS 隔离已验证。

独审还只读比较原 S065 producer pin `5d431097f3b4846ac240745121e56070edd78e86` 与当前代码的完整 Project status；原 producer core `ca09803b71c2bfd82a3356d428f4f05b8a311da433ea1109019e556b53d7c572`、公开 dev/validation source packet SHA 及 3/3 工具预算未变。该检查读取项目账本状态和含共享 corpus 的公开 source packet，没有读取 private/final 文件或行动工件，没有恢复或派发；它不证明旧 Project 可由新 core 执行。

独审最初运行的 `independent-probe.log` 因 unittest 自动收集作者的另外两项合成测试而包含额外工程计算：其中一个合成 Project 使用 **2/2 工具**（质量与数值关联，账面 model/fit/evidence 0），另有 4 次成功的直接数值关联 adapter 计算及 1 次预期拒绝的直接调用。过滤测试类后的 `independent-core-only.log` 才是独立 4/4。作者相关回归亦包含合成工具/adapter 路径，未单独统计全进程所有调用；上述合成执行未安装覆盖所有 fit 和网络访问的独立哨兵，不能把整个过程写成普遍零工具、零私有读取或零外部行为。独审旧 pin 的原版子进程也没有单独安装网络哨兵。受信本地守卫不是 OS 隔离，开发费用/token 未测，保持 unknown。

本增量没有下载 Bike 数据、创建真实 Bike Project 或启动该研究；Bike 预案仍待用户决定，其许可、具体预算、原始文件 SHA 和后续研究行动均不由用途标签自动授权。

源码提交 `3ba33b62a0d8456fb0d04765285e11d0b7e1195c` 已推送；pin `/workspace/development-continuation-20261114/source-pins/3ba33b6` 与193项冻结文件逐项匹配。

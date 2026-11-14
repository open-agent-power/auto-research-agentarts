# 相关性阅读器安装交接

当前阅读器实现提交 `140d6ec44e293cb6e3c92f3be9f3c3bee4dccf0c`，后续依赖声明窄修 `2de2b854bf90404ce6288f8d3fed93e16ccf8581`。后者仅把reports的两个精确版本改为已验证closure的matplotlib3.10.8、pypdf6.21.4；180产品文件、174个Python文件与140逐字节一致。没有修改科研评价器、数据、producer或旧source pin。

## 两份独立成品

| 阶段 | 实际wheel | 安装及范围 |
|---|---|---|
| 140初版 | 1,237,373B，SHA `0a41bc29762ed3a7a93ec337532d2a5bc6f856746efb170e57ae9f9a0ae4a371` | fresh标准venv，base产品+22历史精确pins通过；当时未宣称reports extra解析通过 |
| 2de修复版 | 1,237,371B，SHA `f36cdf8f41ebe2d3f188e3573d9060ecb79aba47821179b3f12b8a867ced3d58` | 另一fresh标准venv，明确请求`[reports,sources]`，离线resolver/安装/pipcheck通过 |

原140 wheel在同一22约束下请求extras的dryrun实际exit1，反馈matplotlib原声明3.11.2与已验证3.10.8冲突；这不是公共版本不存在的证明。其全部7,153个venv文件/路径前后保持，没有重装或删除失败来迎合结果。2de resolver报告记录实际requested_extras、newwheel URL/hash及所选版本，不用base安装或help替代extra解析。

修复版路径：`/workspace/work/g6-relevance-extras-fixed-20261114/wheelhouse/agentarts_autoresearch-0.1.0-py3-none-any.whl`，标准安装在同根`venv`，Gitarchive的构建源在`source`。独立clean源码checkout `/workspace/work/relevance-reader-release-source-2de2b85`保留；没有在其内写build产物。初140成品另留于`/workspace/work/g6-relevance-reader-release-20261114`。

## 精确验证

- Git blob→archive→source→wheel→venv的180产品文件一致；23总分发项为产品+22固定非产品分发项，版本和所有实际加载origin绑定新venv，无systemsite或仓库editable借用。
- 每份新安装实际7,145条RECORD：6,711条声明SHA/size逐项核验；23条RECORD自身空hash；411条ensurepip保留的pip缓存无声明hash，只核来源.py存在并记录实际SHA，不把actual观察冒称wheel声明校验。初验证错误假定只有23条无hash而失败，原脚本/错误与缓存保留。
- 已加载site-packages module entries共999：99产品+900非产品；唯一物理文件992=99+893。初140误将总数标为thirdparty，原记录保留并补实际路径集合证明；2de从一开始分开记录。
- 两CLI帮助均exit0，实际runtime启动在缺可选SDK时友好exit2；没有安装SDK，不宣称cloud runtime集成。
- 每份新安装仅在原两case读取4page+4detail，涵盖primary/audit和missing正例；两manager共26文件/完整路径/DB/预算状态保持，2de八个body与140成功输出相同。原relevance producer8670和旧citation3945不升级，不新建或重跑任何课题。
- 29类禁止计算/执行守卫在导入后阶段0触发；导入前bootstrap进程精确次数/argv未计量，仍unknown。没有重跑HTTP、浏览器、拟合、排名或gold评分来扩充该阶段证明。

使用[22精确约束](relevance-reader-exact22.lock)和既有本地wheelhouse复现该安装闭包；它不是对任意默认网络解析或未来数值版本的承诺。数值runtime仍按项目登记校验，sklearn等变化不能静默继续旧研究。

原件、命令、初次失败和成品：`runs/sprint-011-install-20261114`及`runs/sprint-011-extras-install-20261114`。两份独立审查在`runs/sprint-011-install-independent-20261114/{review,extras-fixed-review}.json`，后者SHA `1925e7ef7e03aa766f2a195945ac3555b6deac35bd43ef5aac33dd46b1bfb147`。

这是当前产品安装/保存阅读增量。没有重新训练、独立gold重评分、通用方法经验收益、OS/sealed、多代RSI、完整G6或正式release/tag验收声明；主研究原预算和完整原件继续保护。

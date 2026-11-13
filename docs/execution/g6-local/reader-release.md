# 保存查询阅读器：安装交接验证

固定源码 `0acb05e253f543ea2483e383c7e2358c81c422bd`。所有构建/安装均在新scratch目录，不覆盖旧源码pin、旧venv、旧研究归档或旧pip target。

## 固定wheel与复用依赖的安装后读取

从Git archive解出独立源码，再离线构建同版本产品wheel，1,223,545字节，SHA256：

`dadf9baec9f8acf79e7ed8bd9758af14b4812aa64f1573cba67c5a668ddbea76`

文件位于 `/workspace/work/g6-reader-wheel-20261114/wheels/agentarts_autoresearch-0.1.0-py3-none-any.whl`。原wheel183成员及RECORD自身校验通过；178个产品文件在Git源码、wheel、新target之间逐字节相同。

此阶段透明复用旧clean1.8 Python的依赖，仅将新target放入新隔离子进程的产品导入路径。98个实际产品module全部来自新target，科研codeidentity仍3945ed0f…。实际12次回环GET读取原项目、两行动分页、query762两次／80条保存文档，以及四份原报告；state13/tools2不变。494原件、421路径集、旧clean产品356文件和新target188文件保持。

实际CPU依赖bootstrap启动一次uname，之后计算/fit/create/export/进程等守卫触发0。socket包装只允许回环，观测12次回环连接；没有独立的外联拒绝计数器，不填造全流程外联尝试0。构建、宿主命令及依赖加载与受守卫的保存读取阶段分别计。

主回执 `runs/sprint-009-reader-wheel-20261114/receipt.json` SHA：`babe30b81082aa26eb31da620c6e589e487efd22a617f34543e47c41aa3f5901`。
独立2385项文件/证据检查见 `runs/sprint-009-independent-20261114/wheel-review.json`，SHA `d4d269b400bf68633a781476f41420479233d5469da5304dba03cffa59cc887f`；未重复安装、导入或HTTP请求。

## pip target的实际边界

原 `--target` 安装的RECORD中，两条CLI路径为`../../bin/autoresearch`和`../../bin/autoresearch-runtime`，按target根解析会落到目标目录外；实际脚本在target/bin。脚本字节本身可核对，但该RECORD相对路径不自洽，且shebang使用旧依赖Python。本阶段不接受独立运行target/bin CLI的主张。

原target/RECORD与失败边界完整保留，没有手工改RECORD来制造通过。模块导入及HTTP读取的限定通过不等于完整标准安装通过。

## 标准venv的独立安装记录

另建 `/workspace/work/g6-reader-standard-record-20261114`，无systemsite、不安装运行依赖，将相同wheel离线安装。188条RECORD路径全部落在新venv内，187项SHA/大小准确，1项RECORD自身按规范不带自哈希；178产品文件与wheel一致，两CLI脚本权限/shebang/导入目标正确。该阶段不导入产品或执行CLI，不能写成有依赖的运行通过。

回执 `runs/sprint-009-standard-record-20261114/receipt.json` SHA `fc9254cf91ce6edc7c0a6e65bb273c5aeec7dc4ae9c79fe9c0ca49f10f801019`；独立759项检查原件 `standard-record-review.json` SHA `980059b48098307bfb80db158e93dec84b96ed5818f92067f13bd1996bf5817b`。旧target两条不自洽路径仍保留，不反写成原安装也通过。

## 范围

这些阶段接受安装物身份、标准安装记录和已存结果读取，不证明模型重训等价、完整研究复现、OS/sealed隔离、多代RSI或正式发布。旧研究、协议、负结果与预算保持。完整历史依赖清单的独立安装另行记录，不能把上述复用依赖步骤冒充已从零安装。


## 完整历史依赖的独立安装（0ac）

另建 `/workspace/work/g6-reader-clean-install-20261114/venv`，无systemsite，只使用自身site-packages。历史清单为23个分发项，包含产品及22个其余分发项（含pip等打包工具），不是23个额外运行依赖。按原官方URL和哈希获取21个依赖wheel，另复制同版本Python自带pip及原产品wheel；本地23归档共96,352,983字节。获取阶段使用公共网络，之后安装为`--no-index --no-deps --no-compile`，阶段分别计，不能说整轮零网络。

23项实际版本逐项匹配，pip check通过；6732条RECORD中6709项SHA/大小准确，23项自身RECORD按规范无自哈希，全部路径在新venv内，178产品文件与原0ac wheel相同。实际998个site-packages模块来源全部位于新venv，其中98个产品模块、900个第三方模块，科研identity仍3945ed0f…。12回环GET读取原两行动及报告，state13/tools2、原件和预算保持。

直接执行本venv的`autoresearch --help`退出0；旧入口的`autoresearch-runtime --help`退出1，原因是未安装可选agentarts SDK，原stderr和该负结果保留。没有因此安装额外SDK或声称云runtime集成完成。两次宿主CLI是真实进程，其内部子进程未单独计量；HTTP smoke里的uname1次与随后守卫0不能替代整个准备/CLI阶段计数。

该阶段原件为`runs/sprint-009-clean-install-20261114/receipt.json`，SHA `e617a415e18df839b2773f7875ecd27b31cbaf00eb673bb8447030ce2208c4fd`。两次license metadata解析错误也保留，修正只涉及审计器兼容旧/内嵌metadata，没有替换依赖版本、wheel或原证据。

## 可选runtime帮助入口窄修

源码 `8a394e316009a035cd5ac2de5fd2f00a3ca0fe79` 新增stdlib延迟加载shim `runtime_cli.py`，console entrypoint改指它；原`runtime.py`字节不变。帮助和未知参数先由argparse处理，之后才导入旧adapter；已知可选依赖缺失时以exit2明确提示，其他导入或委派后的错误继续抛出，不伪报“服务未启动”。

8项针对性测试通过，其中独立子进程禁止SDK导入、socket和工作目录创建，验证帮助不启动服务。SDK可用时仅以工程stub验证原main单次委派，不能作为云runtime验收。原0ac wheel/venv/负结果保持；新wheel与独立安装的实际CLI结果另按最终回执核对。


独立复核另发现原安装审计将998个site-packages模块总数误标为第三方数量；按原模块路径集合区分为98产品＋900第三方。原receipt和检查器失败保留，公开计数据原路径集合纠正，没有重新导入或伪增模块。


## 最终CLI修复版的独立安装（8a）

保持旧0ac wheel、第四venv及其帮助失败原件，另从`8a394e316009a035cd5ac2de5fd2f00a3ca0fe79`构建新wheel，1,224,468字节，SHA256 `e2941f74f2e93ba15a6f4eda7e8e53c9d539f99f39ac6e030f146b32fc8aa563`。位置 `/workspace/work/g6-reader-cli-fixed-20261114`；新标准venv从既有22个非产品wheel与新产品wheel离线安装，没有新下载或版本升级。

179个产品文件与Git/wheel/安装逐字节相同；此前178个reader、前端、旧adapter文件也与0ac逐字节相同，所以复用原UI/HTTP证据并明示原验收source0ac，不冒称浏览器重跑于8a。23个分发项、pip check、全部6733 RECORD（6710哈希项＋23自身记录）通过。

实际运行本venv三个命令：`autoresearch --help`退出0，`autoresearch-runtime --help`退出0，未装SDK时`autoresearch-runtime`退出2并给明确提示、无traceback。另在安装入口的缺SDK无参数分支上加socket/进程/建目录守卫，均未触发；帮助则由8项源测试及实际--help退出0分别举证；不把它当成SDK已安装或云服务执行通过。

新环境只使用自身site-packages，998个实际模块来源为98产品＋900第三方。12次回环GET读取原两行动、query762和报告，旧3945科研identity、state13/tools2保持。CPU依赖预热uname1次后，读取阶段计算/进程守卫0，模型/fit/rank/score/研究报告生成0。三次宿主CLI执行及其内部未单独计量活动，与该守卫阶段分开，未声明全流程零网络/子进程。

最终回执 `runs/sprint-009-cli-fixed-install-20261114/receipt.json` SHA `703d554323851f34ccef2cee4d8b039975528c8e05a6eead79b75310a239cb93`。其中某原验证器描述继承“178bytes”字样，实际数据/断言和文件证明为179，另有`validation-field-clarifications.json`澄清；原描述、原第四模块总数误标签和失败原件不覆盖。


最终新安装物独立复核15471项文件/保存值断言通过，无安装/CLI/HTTP重复执行。回执 `runs/sprint-009-independent-20261114/cli-fixed-install-review.json` SHA `60b557a108f91c9b5d81bb86d800ea2c1a48091d7ce527beec7a32f46f3a2930`；第四原生安装独审14772项（含已保留的可选CLI失败），SHA `0cd23a05230f5cdbfcda62dbc2cd72776bcadcb0dc850b1fce171b0ad2b022d5`。这些计数是工程核对，不是新增科研样本。

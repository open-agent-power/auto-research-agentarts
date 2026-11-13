# 原生 wheel 干净安装与保存恢复独立限定总审

结论：**精确源码／历史依赖环境中的 wheel 安装及保存结果恢复增量可交付。未通过完整 G6 或科学模型重现。**

本审只读核对真实文件和回执，不重复下载、build、install、replay、HTTP、排名、求解或 fit。
正式原件 `runs/g6-native-final-review/review.json` SHA：
`18d14c0402b8292156725a76240d3da1fd94a9755a77f55de22359418566586d`。
1,019 项校验主要是逐文件 SHA，不是额外科研实验次数。

## 实际包与环境

source commit `e638b5f3782d12a7b54bb9ede5596e5c4d9726cf` 是 G5 科研 batch 后的独立只读 UI 改进。
独立从 Git object 重新读取完整 tar，核其 archive SHA、783 个 snapshot 文件，以及 build 后各 tracked 源文件。
wheel／已安装 Python、数据与 web 资源全部177文件与该 source 精确匹配，ZIP CRC 全过。

wheel 为 `agentarts_autoresearch-0.1.0-py3-none-any.whl`，1,212,193 bytes，SHA：
`574a83edc7eadb7d338bb43facd5c84b423e8494598d2ac5aadd3633e9d65295`。
实际 installed origin 在
`/workspace/work/g6-native-release-20261113-01/venv/lib/python3.12/site-packages/autoresearch`；
真实 `pyvenv.cfg` 为 `include-system-site-packages = false`，smoke 使用该 Python 的 `-I`，
未从 repo 或原开发环境导入产品包。本审直接核对 installed 177 文件字节，不只相信路径声明。

环境精确安装18个 observed 历史 pin，并保留完整23 distribution closure（含 product、pip、tzdata、setuptools、wheel）。
数值运行版本为 NumPy2.5.4／SciPy1.17.0／sklearn1.8.0，实际 code identity 与已注册项目一致。
这是 **base product 加历史观察到的依赖闭包**；没有请求带不同 matplotlib／pypdf 约束的 reports extra，
不能说默认 extras 的任意新解析已验收。PyPI 依赖准备确实使用网络，product wheel 安装使用 no-index／no-deps；
不是整轮零网络工作。6个 build／install／pip／smoke命令 exit0，pip check通过。

## 保存课题恢复与 HTTP

两个 manager 各先复制，再要求原 request body 已对应 accepted digest；
每域 primary／audit／wait／report 四个原 ID 只返回保存结果。13个 manager 文件、完整 state／预算前后保持，
没有新 project、原生 action、科学 source 提取、fit、模型 API 或 report 导出。
归一化只去除 boolean `replayed`；原请求、路径、时间戳、来源和结果字节不改。

实际 HTTP 为每域 **8 GET＋1 POST405**，总 **16 GET＋2 POST405＝18 loopback connections**，
没有非本地 product 连接。4附件／域的 HTTP SHA／大小逐一与原 manifest／磁盘匹配，
console／module CLI help通过，PDF保留7／8页并有文本。这里未运行浏览器或重做整份PDF视觉验收。

已读 smoke guard 代码：拒绝 primary／saved audit、index／rank／metrics、生成／DP／brute、fit、
source execute、model transport、subprocess及 report collect／render／export；原 case／原 packet 的普通 open、
Path.open、os.open、SQLite fallback 禁止，复制 source.json 实际被读。禁止调用计数空，
369 个历史保护原件与两完整原 native case 前／完成／后保持。它是可信主机 smoke guard，不是 OS sandbox。

## 保留的失败与范围

attempt01 的 verifier 误把 `{bytes,sha256}` protection object 当 SHA 字符串，构建前失败且 commands为空；
原失败和 before／after 原件保留。attempt02 只修 manifest schema 映射，没有改数据、标准或重跑科学任务。
成功 `result.json` SHA：
`8f80b7174c96534a676d2041b3b8b5b468016b8c3fb3bdbca41fe24c6ee10d8b`；
本审另核全部23份 manifest artifact 的 SHA／长度。

旧 G6 sklearn1.9 分区不兼容失败继续保留；本次精确1.8安装／保存结果恢复没有反驳它，
也没有重新拟合原 OOF、重算模型系数或证明跨版本科学结果一致。
原 G0 cgroup／sealed 自主执行／完整 G6 仍未通过；开发 token／货币成本未知。

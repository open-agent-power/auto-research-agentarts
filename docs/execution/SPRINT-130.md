# S130：同 pin 双合成数据的事前规则分支

在 HEAD `435578e5507c499d1a48995c3c17872d10b52d22`，源码及两份本地人工输入403项清单 SHA `d390475d3d5648dea62bf5d84379e140c89f3af2677a62044e009bd6c6b31088`、事前协议 SHA `3aa71390043b644b01bec6982ead9cc8589ebbc92a2b32486118de235758c2f4` 固定后，先在两个全新独立合成 Project 分别登记完全相同的 validation 双指标差≥0、met→wait/not_met→saved audit；独审先核双方各0行动及0/2预算，再按各自原 future ID 首派。两原合成包仅保存在本地，SHA分别 `cc62d84e405fa61cd297128bc792deb8ca4311e02830e402c3ac85c43e9ec923`、`cbcf90e7b50d58dad3233a0a03fcb9f02fc07394250ee6a784557e59a7023e8e`。

S127合成 Project `project-801def1ed16c4badac8e184b5ae31bf4` 差 `[0,0]`→met/wait，无child，1/2工具；S129白盒 Project `project-eab44812e8e44a57a2c3c8de3dfe6feb` 差 `[0,-0.5]`→not_met/saved audit，2/2工具。各模型/fit/evidence 0，费用 unknown。两primary实时 Python线程profile各 index1/retrieve300/metrics300；audit为audit1且其他0；两primary和两feedback原ID resume所挂四函数均0。profile非OS/网络/跨进程保证。

独审未重派：重算两packet qrels与每案300保存排名的指标，验证差值、原audit前驱与排名SHA、两本SQL共9条登记/parent/child claims及三行动工件封套SHA；403项源码输入和86项结果匹配，结果清单 SHA `ef7e7e76b609bc0eadfd67a4504ab00b734a6c0993d501c50485e7e85cb95774`。登记时独审原先口头误报manager intent数量为4，已更正为2，原记录保留。

S129干扰按已知合成查询刻意构造，是白盒工程fixture拟合，不能称未见、真实Wikinews、经验迁移、模型自主或科研收益；无final/真实数据。旧Project不迁移或重派。

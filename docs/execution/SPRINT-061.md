# S061：把验证集单题影响供给研究计划

已实现显式plan-only材料 `staged_validation_stability`，selector精确包含kind、原primary action_id与result_sha256。复用原staged reader核source/SQL/原primary；返回全部validation的Recall@20/MRR配对均值、胜负平及留一影响范围和符号计数，不含query ID/hash或正文。少于两题时留一结果为null及原因，不编造0。原4 selector/64KiB上限不扩；recipe两入口拒绝，Host/report摘要仅身份。旧默认上下文及wire不变，不修改原freeze或自动决策。

作者42相关回归、独立5项探针通过；独立对原S046/S054保存数据与S060结果逐项比较，一次新材料reader读取，整份计划S046总1次/S054因原假设反馈另读总2次。实际只读上下文分别18974/20125字节，原状态及核验公开文件保持，CODE_CHANGED门保留；未读取final或调用模型。初次工程夹具路径不分离被拒绝、独审初次误判整份计划只能读取一次的失败均保留，修正后重新验证。

这将已有脆弱性信息传给下一份研究计划，不证明模型已经依据它改进研究或取得科研收益。原预算、源pin与历史case不重开。精确源及范围见 [验证记录](g5-local/staged-stability-material-verification.json)。

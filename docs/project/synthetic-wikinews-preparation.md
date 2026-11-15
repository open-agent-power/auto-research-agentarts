# Wikinews 结构的纯合成数据准备

`scripts/prepare_synthetic_wikinews.py` 是仅供工程测试的固定生成器：唯一公开参数是 `--output`，不能接收外部 XML、压缩包、文章、许可记录或 URL。它自行生成 1,005 条人工 XML 页面和虚构的逐页证据，不下载数据、不调用网络、不创建 Project，也不派发研究、模型或工具。内部以下划线标识的解析与选择函数可由合成测试调用；这种接口约束不是操作系统隔离或对不合作代码的防护。本准备器不是 Wikimedia dump 正文解析器、真实许可审查或真实研究授权。

生成器固定 Python Unicode 数据版本 15.0.0，仅接受有界的严格 UTF-8、指定 namespace 和极窄合成 XML 结构；DTD/自定义实体、redirect、多 revision、非预期结构、控制字符、模板/链接等不受支持内容直接拒绝。显示文本做 NFC，去重键做 NFC/casefold 和 ASCII 空白折叠；只有正文首行与 NFC 标题精确相等时才移除该行。不因此声称文本其他位置不含标题。每页必须有固定 synthetic-only 许可、归因、page/revision 身份及原文本摘要；缺失、冲突或不一致即停，不能把这些合成声明当成真实版权证据。

标题或正文的规范化键相同即连边，按传递闭包形成连通分量并保留最小数值 page ID；按协议两个固定盐分别取 1,000 条 corpus、50 条 dev 与 100 条 validation。查询 `q-` 与文档 `d-` 前缀不同，150 个弱正例恰一对一且文档实际存在；原生 adapter 本身容许缺失正例，故此处额外检查。正文与标题的语义及近似重复只针对合成夹具，不表示事件独立或真实检索质量。

脚本只调用现有 staged `capture_source`/`load_source` 验证四资产、spec 和 packet，不生成排名、指标或 final。输出保留 `fixture.xml`、synthetic claim、逐页 synthetic source receipt、selection、四资产/spec、`source.json` 与完成 receipt；逐项 SHA、Unicode/运行时、contracts.py 原 bytes 和 adapter 身份可对照。adapter identity 按当前源码链覆盖 staged adapter、relevance adapter、retrieval lexical、source evidence adapter、tabular source、chemotopo_data、c01、archive_inventory、contracts 和 knowledge_sources，并包含 Python 版本及 pypdf 版本声明；contracts 同时单独记录并首尾核查。这些只是该有限源码与版本身份，不证明已加载内存字节或整个运行环境，也不构成签名。spec 中受原生格式约束的 `archive_sha256` 实际指本合成未压缩 XML bytes，不能当作真实 Wikimedia 压缩包身份。相同代码、运行时和输入 bytes 应得到相同内容 bytes；仅将原 XML 页面顺序重排会保持选择和内容资产，但原 XML SHA 改变，因此绑定它的 spec/packet 也应改变。

输出只能是 `runs/` 下全新、无符号链接的 `s127-synthetic-wikinews-*` 直接子目录，独占建立；文件使用独占创建并 flush/fsync。capture 前后对生成原件、claim、selection、receipt、资产和 packet 做有界 no-follow 重读，并比对 packet 内的原资产与 spec；漂移停止，目录和原 claim 保留，同路径不可重试。最终 receipt 可能已写入而随后目录 fsync 失败，此时落盘状态 unknown，应保留目录核对，不能断言没有 receipt 或覆盖重来。这些是可信协作本地检查，不是原子多文件提交或防对抗并发的 OS 保证。

本片不支持读取真实 dump、bzip 解压、Wikitext 模板/链接转换或真实逐篇许可/修订历史。真实来源的固定 SHA-256、版权与归因、超既有限额获取、完整解析/筛选、资源和研究预算仍待独立审查及必要授权；不能由合成包、source receipt 或 S126 用途标签推导已经批准。结果体 4 MiB 限制只有真实执行时才可能最终知道，本准备器不排名、不预言其是否足够。后续合成反馈双分支预演也是独立阶段，尚未由此准备步骤完成。

# S107：质量材料到人工回复、采纳和报告的页面链

工作台新增明确的人工质量计划准备/原文件导入入口，复用现有 direct Host journal、原selector/预算与原ID，不启CLI/模型；准备消耗原Host grant的一次决策名额，不能因此视为外部调用授权。导入的回答由操作者提供，模型身份、推理次数和费用unknown。原生Project模型额度不增加。

Host writer同次保存版本化manual意图，绑定原准备规格、context、项目/run/snapshot与nonce；严格导入/消费在锁内核原件与孤儿状态，带标记未收口记录阻断其他Host新ID或旧入口绕过；严格采用绑定manual意图SHA和Project claim，终态历史复验。旧无标记Host流程保留。Host与Project不构成跨库事务，检查后的并发漂移可能留下原已准备记录/占用原名额，保留原ID停查，后续严格采用重认证。Host journal中prepare规格版本与manual marker双字段互校，单独丢失/不一致停查；同处于单账本，两字段协同删除或整本改写不在防护范围，不是独立签名。

页面同会话保存准备原ID/selector/body；人工回复发送前只保存原Host/project与文件SHA，未知后重选同文件，错误SHA拒绝。prepare 200需只读对照原Host记录后才清哨兵；会话清除/丢失不证明原请求不存在。原文件缺失或状态不明停查，不能靠新ID或重造原件恢复。

独立隔离合成Project `project-f0dba0ca0a324d0599a0b1c3e93329e0`，原Host `local-manual-plan-b38a33a4-9644-46fe-8445-b2d786d31602`、质量action `action-05faa5d6487c52b223420798e80e6641`、结果SHA `f34058b881151a7527ed9016c6adfa90862d400c40e8cca41cd1d1ff40912bd8`。真实Chromium/本地HTTP同项目完成选择预览→准备→人工原文件导入→选句事实核对→严格采纳→报告及原ID回放；已有1次合成质量工具，后续预算不增，Host名额1，CLI启动0。另四个新合成Project覆盖prepare首包未达、已接受回执丢失、import首包未达错文件SHA拒绝、伪造prepare 200；模型/dispatch/step哨兵。独审新旧44/44和另一次23/23 exit0，frontend lint通过；证据 `/tmp/s107-fixed-independent-review/full-browser-final.json` SHA `6cd0592a222422b2949e9891e7249a1177ee95bd42a9a6f8546f04f17ddaa596`。作者另将其原合成项目19文件字节核对保存在 `runs/s107-engineering/preserved-browser-project`，副本保留绝对路径，仅只读证据不声明迁移恢复。

负例：修前首次严格采纳后单删manual marker可重放、以及prepared单删marker可走旧import；原失败日志留 `runs/s107-engineering/`，已补claim绑定和双字段一致性并独审。浏览器早期定位/折叠详情失败沿原ID继续，未计最终验收。此结果仅证明合成人工链和所测会话恢复，不证明真实模型收到/理解/自主决策、科研收益、断电或OS隔离。

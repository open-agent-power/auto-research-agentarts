# 小n条件调度：两阶段冻结协议

本研究基于原n32慢例提出唯一“n≤32扫描，否则二分”假设；另一个原n32样本二分快2.339×的反证同时保留。阈值不是已测交叉点；不看新目标结果挑阈值。三个arm都走同一受限wrapper，真实计时含派发，比较固定二分、固定扫描与唯一阈值策略。原kernel、Fenwick源函数、旧16case与producer/pins/预算一律不改，不冒称原双臂adapter已支持三臂。

精确case/order/arm序列/预算/endpoint见[机器协议](scheduling-threshold-transfer-protocol.json)。27性能case为9尺寸×3新seed，另2小case做正确性，29次host RNG生成2642jobs；模型生成/API/fit/source extraction均0。kernel预算1140（暖机162、计时972、正确性6），独立Fenwick29、穷举2共4352子集，扫描比较上限6080234，单primary、最多一次保存审计、单研究worker和120秒本地窗口。预算属于新独立standalone研究，不复用/扩充原项目tool账本。

先审查固定代码/协议/runtime/预算和唯一study/request，再持久化全局claim，之后每一次生成均先预约后回执。29完整输入及SHA封存后第二次独审，才允许primary。每个kernel（包括暖机）、Fenwick、穷举均相同预约/回执规则；prepared无回执即unknown整体停止，不能补跑、换ID/目录或清库。完成回放只返原件，失败也耗预算并保留；原协议、输入、代码或runtime变化一律拒绝。

主终点为小n12case等权的case中位耗时比（策略/固定二分）的中位数。保留全部原计时/运行/排程/不利case；偶然零或非有限使对应终点不可解释，不删/补测。结果小于1只表明本次有限同机样本较快，不等于因果记忆、统计显著、通用性、新算法发现或默认晋级。全部schedule须可行且目标/原完整schedule一致；Fenwick仅独立验证最优目标，不声称独立证所有tie排程。

当前为正式协议定义与工程实现阶段：尚未签setup/input review，没有生成新jobs或执行新求解/计时。只有相应独审回执绑定固定版本后，才按阶段继续。OS/sealed、原完整Gate和多代RSI未通过，不再索要同一已接受缺失Worker。

120秒为prepare与primary累计活动窗口。prepare的单调时钟/boot起点及封存耗时持久化，独审等待不计；primary第一次接受按剩余时间固定deadline，同boot恢复不刷新，开始primary后的暂停计入。过期只准读/重放原已完成记录，不启动新调用；boot变化/未知或时钟回退拒绝。此本地合作限制及外围timeout不等于OS隔离。

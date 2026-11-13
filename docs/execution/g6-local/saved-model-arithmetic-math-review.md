# 保存模型算术验证器：独立数学与字段审查

**READY：允许root按最终冻结源码、原ZIP及固定容差开展一次真实算术验证。** 本审只做源码审查和小手算fixture，没有重建2991条实际预测、重算其指标或运行原CV。准入不预判真实算术通过。

| 审查对象 | SHA256 |
|---|---|
| `scripts/verify_saved_model_arithmetic.py` | `e112e126eca85c1d61dda38c08b9b70c3d73b37fee854b56ac076c9065c6f2fb` |
| `docs/execution/g6-local/saved-model-arithmetic-protocol.md` | `1e154433c58827cdada1e262bead66393ef66c0e44428e56ca93a23ce6df123d` |
| 独立fixture回执`runs/sprint006-saved-model-arithmetic-review-20261113-01/final/receipt.json` | `7fbb4ee75a1997cffd25f3860bab27717595de66863c0252b543749f262aa342` |

审者`repo_audit`未改作者源码、协议、原工件或ZIP。测试前后script/protocol SHA相同；运行时HEAD为`9f6058590a0024c5ef85aaeb49244d2f5f17f7e9`。保存字段的实物可行性先由[参数审计](prediction-reconstruction-audit.md)核定：3课题/5CV/25折，维度8/8/6/6/7，已存OOF2991条，所有必要参数齐全。

| 核对项 | 源码证据与结论 |
|---|---|
| 原token与列序 | `captured_source:132`独立UTF-8/BOM、CSV、header与logical/physical行解析；`training_rows:162`按保存的feature_columns原顺序取float，missing/nonfinite/group排除理由与冻结0ceb逻辑相符。不调用原mapper，不把target/group列当模型输入。 |
| raw/log1p映射与保存标准化 | `reconstruct:192`只对声明列做math.log1p、检查x>−1，再逐列用保存mean/正scale标准化。参数维度和有限性检查在算术前；不估计新的mean、scale或coef，不构造scaler/Ridge对象，不调用predict/transform/fit。 |
| 真正系数公式 | `:203`为`math.fsum(z[j]*saved_coef[j]) + saved_intercept`。输入仅来自原feature、training声明及保存折参数；`verify_analysis:244-246`先完成该公式，再读取stored predicted作比较。独立Fraction与cancelation手算确认没有从storedpred反算或复制输出，也没有把列按名字重排。 |
| 原reference与误差 | `verify_analysis:237`仅用保存train IDs定位原target并fsum求均值；随后独立比较fold/reference与每条OOF，按重建预测计算candidate/reference MAE及relative improvement。此处重算reference，不重新学习任何模型参数。 |
| 精确覆盖与身份 | `verify_analysis:207`核完整唯一有序OOF、原target/locator/group/fold、train/test互补与组隔离、每行测试一次；协议与Ridge八个参数用canonical精确比较。`verify:340`核注册source、action/run/code/request、envelope、冻结design、method-instance输入、quality predecessor、完整来源locator和原10条fit events，要求5份CV/25折/2991行及两组父子原partition hash一致。旧CV的quality predecessor与resource.parent_version不混用。 |
| 容差、负值与全部结果 | 常量`ABS_TOL=1e-10, REL_TOL=1e-12`，`comparison:114`逐项使用`absdiff <= max(abs_tol,rel_tol*max(abs(actual),abs(saved)))`。每行保留实际/保存值、差与实际limit；负预测符号另精确比较，不clip。输出全部行、per-fold最大差、指标和负值ID，不以抽样替代2991覆盖，不在看到结果后放宽容差。 |
| 计算能力与数据来源 | 只用stdlib；`Guards:274`拒绝新增非stdlib/product/数值或模型包导入并拒socket。SQLite从已manifest绑定的DB字节反序列化到`:memory:`，query_only SELECT。没有原adapter/mapper调用、线性方程求解或参数重估；作者脚本不执行source文本/表达式。独立archive-only准入另由总审负责，本项不替代其ZIP/manifest边界审查。 |
| 输出保护 | `Archive:311`先核原ZIP/manifest，`checked_absolute:78/output_boundaries:86/checked_output:98`在mkdir前拒绝原ZIP、保护文件/整树、新旧case外层root、main源码区及`REPO/work`冻结worktree区的双向重叠、`..`和父链symlink。合法`/workspace/work` scratch保留。原case outer和冻结0ceb/native8e source下输出的纯预检均拒绝、目录0创建。 |

早期输出保护有两项实质问题：只查父链DB漏过旧case外层；补主源码区后仍漏`REPO/work`中的冻结source。root/作者分别窄修，未改数学、数据或容差；旧f3a/cb0脚本与先前fixtures保留。当前e112才是本审准入版本，不把旧版未闭合边界当作通过。

**小fixture实测。** 作者37项hand fixtures全部通过，其中完整4行/2折例子明确为手造、未训练，含OOF覆盖、训练target reference、MAE和坏值拒绝。本审另14组独立检查通过：Fraction oracle、非字母列序与反序结果、非单位scale、截距与负输出、fsum大数抵消、选列log1p零值/已知指数、stored输出无关、bool/形状/非正或非有限scale/log域拒绝、固定abs/rel边界、6个原case/source/ZIP输出拒绝，以及9个product/third-party import和DNS的主动否定探针。后者是被拒的手算测试探针，不是实际模型或网络调用。

测试调用作者`self_test`时，真实`Archive`构造器及`verify`被patch为失败，确保没有偷跑实际输入。37是作者fixture断言计数，14是额外独立检查组，不把二者冒充51个真实数据测试。完整明细在`final/independent-small-checks.json`；手算输入都是本审字面常量，没有使用旧预测/报告数字作期望。

原494文件及ZIP在本审前后SHA/size完全相同，script/protocol也未变。所有原CV每份10条完成事件（5Scaler+5Ridge）属于既有历史50次fit，旧ToolResult的new_fits=5亦是历史Ridge数；**新验证fit0**不能覆盖或重置它们。新真实预测重建0、estimator predict/transform0、solver/index/model API0；本轮只有小手算及文件I/O。该结果只允许保存参数应用核验，不证明系数最优、重训等价、未知任务泛化、完整G6或OS隔离。

# G6 主研究保存系数预测重建：独立可行性审计

**可行，必要参数已经保存，无需补训练。** 只读实物核对找到3个旧课题的5份真实CV工件、25折参数及2991条保存OOF；每折的scaler均值/尺度、Ridge系数/截距、输入顺序、声明变换和原train/test记录均齐全。本轮没有计算任何实际预测或目标误差，没有调用fit、predict、transform、原mapper/执行adapter、solver/index或模型API。

本轮root为`477aae3f89e130f06d497d12d83d8d459def6955`。生产者冻结源码是清洁的`work/study-source-0ceb274`，HEAD `0ceb2742825a9e95b373260fb39950fcbb48af1b`；不是后来优化了group helper的main。其`ridge_validation_adapter.py` SHA `5c689576add16d5bd28cdf5c43a5c4599afb257a12f6b239018dcabcb0501090`。全部工件定位、原文件SHA、canonical envelope SHA及字段维度保存在`runs/sprint006-prediction-reconstruction-audit-20261113-01/saved-artifact-schema.json`。

| 原课题 / 实际CV action | OOF行 / 输入维度 / 折 | 输入与设计 |
|---|---|---|
| Concrete `action-3a4d3c93d9dae8a943a22e7757e03b8b` | 1030 / 8 / 5 | `concrete-cloud-mixture-transfer` v1，raw |
| Concrete `action-d093cfe1b49ae1365c9126ade64dd0b5` | 1030 / 8 / 5 | 同resource v2、parent1，`age:log1p`，龄期为天 |
| Real Estate `action-a1dcc3434446df440b04fab0841cf31d` | 414 / 6 / 5 | `real-estate-cloud-method-transfer` v1，raw |
| Real Estate `action-39075c63ac3c28e308488388c3751688` | 414 / 6 / 5 | 同resource v2、parent1，`house_age:log1p`，房龄为年 |
| Slump `action-fc4904b98d90bf787886cf26e68a7e9e` | 103 / 7 / 5 | `slump-cloud-method-transfer` v1，raw；没有age候选 |

合计是**2991条已存OOF，不是2991条新预测**；三个数据集分别1030/414/103原行，共1547行。五份工件全为`group_cv`，保存的exclusions均0。维度、参数有限性和正尺度通过结构检查；没有依据保存MAE反推、补造或修改系数。

**保存合同与源码证据。** 下述行号均指冻结0ceb源码。

| 字段 / JSON定位 | 实物及源码依据 |
|---|---|
| `tool_result.result.analysis` | `ridge_validation_adapter.py:167-171`输出`ridge-validation-v1`，含check/protocol/design_binding/source snapshot/oof/folds/exclusions/target/unit。 |
| `analysis.folds[f]` | `:136-140`保存`fold,train_records,test_records,reference_prediction,model_params,scaler_mean,scaler_scale,ridge_coefficients,ridge_intercept`。25折全部向量长度分别8/8/6/6/7，均为有限数，scale>0。`model_params`实际包含alpha1.0、fit_intercept=true、solver=auto、tol0.0001等八项；每份CV的五折声明一致。 |
| `analysis.design_binding.training` | `:18-58`使用完整CSV的声明feature顺序和split_group_columns；变换在`input_transforms`字典，raw版该项缺省。`resource.id/version/parent_version`标识CV父子；`analysis.predecessor`是质量行动引用，不可当成CV父版。 |
| `analysis.protocol.input_basis/model_input_terms` | `input_basis.py:8-23`记录log1p选列、完整列顺序及`raw_log1p_then_fold_standardization`；`:34-53`定义固定变换。两个candidate只变换上述age列，未做target变换。raw版没有basis扩展，不应虚构新列或用字符串表达式eval。 |
| `analysis.oof[i]` | `ridge_validation_adapter.py:153-155`保存`logical_record,physical_line_end,observed,predicted,groups,fold,reference_prediction`。输入feature本身在捕获CSV中，不在OOF行内。 |
| 原行 / target / reference | `tabular_quality_adapter.py:129-143/:302`：logical_record为除header后1-based数据记录，physical_line_end是含header的csv.reader.line_num；`ridge_validation_adapter.py:113/:135/:138`直接使用原target float，reference是训练折target均值，亦逐折/逐OOF保存。组分别为`mixture_signature/location_group/mixture_group`，不代表已经证明独立实验批次。 |
| CSV / spec / envelope绑定 | source packet为`tabular-quality-source-v1`，**顶层`source`而非`assets`**是`{file_name,bytes,sha256,bytes_base64}` CSV原字节，`spec_source`同形保存spec原字节。3份CSV资产及spec原字节/hash/echo有效，原始CSV也仍存在且匹配provenance中的origin SHA。`registration.source_sha256`绑定整packet原文件；snapshot为去掉snapshot字段后的canonical SHA；artifact envelope的`sha256`同样是canonical内容SHA，不能与artifact原文件SHA混用。5份action/envelope/source/design/target绑定相符。 |

**保存误差与系数算术是两种证据。** 从`oof.predicted/observed`重算MAE只验证已保存误差的算术，不能发现输入列顺序、scaler或模型表达不一致。从原CSV token和保存参数独立计算才检查预测映射：先按feature顺序取值，按显式声明应用`log1p`，再对该行原test fold做

`ŷ = saved_intercept + Σ_j (((φ(x_j) − saved_mean_j) / saved_scale_j) × saved_coefficient_j)`。

比较对象应为每条原OOF及其原locator/fold，不能拿报告MAE作为期望直接生成输出。现有`verify_concrete_reproduction.py:219-221`和`verify_tabular_transfer.py:212-214`源码已有这种保存参数公式；本轮未运行它们。此前G6的group/fold兼容检查也没有执行该公式，见[frozen-reproduction.md](frozen-reproduction.md)，不能把兼容通过写成新的预测复现。

**缺项与下一最小目标。** 对这5份工件的保存系数算术，必须字段没有缺项。没有单独保存每行变换后feature矩阵，但捕获原token、完整feature顺序及固定变换足以重建它；不需训练补存。也没有完整序列化scaler对象、var_/n_samples_seen_、实际解析后的auto solver/BLAS执行路径；这些不妨碍上述算术，却不能据此声称重做了原fit、重新学习了系数或获得跨环境bitwise一致。

最小完整零拟合目标可先选**Slump单baseline的103行/5折/7列**：冻结新checker、原source/artifact SHA、参数与提前固定的abs/rel容差；只读副本，纯标准库float/求和，不构造训练模型、不调用predict/transform/fit，不重建GroupKFold，直接使用保存train/test IDs核对每行。先用手算小夹具验证非单位scale/截距/列顺序和拒绝边界，再在root冻结后计算实际103行。随后可扩展两组raw/log1p父子，共2991行；天与年保持各自语义，Slump不造age。不一致必须保留失败，不调数据、容差或旧预算以取得通过。本审计只确认这些下一步有实物支持，未执行实际算术。

**一次性参考仓库与远端核对。** 8个既有refs的HEAD均匹配两份manifest，均Git clean；仅hash核对manifest已列出的61个文件，没有重读所有上游源码、安装其runtime或fetch。两份manifest JSON相同，完整路径/预期及实测SHA在`reference-heads.json`。

| ref | HEAD前12位 | 本次列名文件数 |
|---|---|---:|
| autoresearch | `228791fb499a` | 6 |
| AI-Scientist | `1de1dbc1f4ee` | 11 |
| AgentLaboratory | `d9017d90e329` | 10 |
| prime | `565415d1cfa3` | 7 |
| OpenHands | `d58ca3dcdf95` | 4 |
| software-agent-sdk | `7543710639b6` | 10 |
| beir | `ef83d2930706` | 7 |
| ragas | `298b68274234` | 6 |

唯一远端读取`git ls-remote origin refs/heads/main`成功，GitHub main精确为`477aae3f89e130f06d497d12d83d8d459def6955`，与root本轮target相同；未fetch或操作上游远端。没有查看/打印token值或原venv秘密。

全部读取通过标准库JSON、CSV header、SHA与SQLite`mode=ro&immutable=1`完成，没有导入产品执行模块。原Concrete101/RealEstate101/Slump90共292文件前后SHA/size完全相同，且全部SHA仍匹配G4 prefreeze原清单，5份G4控制文件也匹配冻结SHA。已有fit events20/20/10合计50保持；新fit/predict/transform/adapter/model API调用0。独立回执及完整清单在`runs/sprint006-prediction-reconstruction-audit-20261113-01/`，额外source/spec/action绑定与权威清单核对在`supplemental-bindings.json`；本项不完成G6科学复现，也不解除原资源/runtime边界。

# P02：让模型读取项目与预测诊断

## 新增能力与边界

| 行动 | 实际工作 | 不能据此声称 |
|---|---|---|
| inspect_project | 读取固定作者HDF5结构、白名单存储值与按索引绑定的OME元数据 | 执行作者管线、取得像素或对象输出、确认ALP蛋白身份 |
| remember_evidence | 保存工具核验的条件来源／预测数值观察，保留来源及协议身份 | 把模型理由、评议或下一步建议升级为已验证事实 |

两种新检查均先要求`inspect_source`，并引用最新证据；`inspect_prediction`还要求创建时已挂载预测目录。来源检查＋预测检查可准备`source_qualification`和`prediction_diagnostic`两项条件观察；仅来源检查＋四规则比较则沿用原两类数值观察。项目OME检查结果单独可见，不自动写成记忆。

## 创建与恢复

新HDF5工具通过模块导入成为研究API的依赖，启动CLI或使用相关API前需安装可选`sources`依赖，不能假定只有选择inspect_project时才需要h5py：

```powershell
.venv/Scripts/python.exe -m pip install -e '.[sources]'
```

预测目录由操作者在创建新研究时通过`--prediction-directory`显式挂载；模型不能提供路径。冻结配置与清单绑定三份来源文件、预测协议及工件身份。记忆scope沿用四字段，其中`inputs_sha256`复合绑定附件manifest、协议和reader身份，不把新观察混入旧条件。恢复不能更换附件或改旧配置，参数可省略沿用冻结值，或传同一路径核对。

恢复时使用同一workspace与新的output，省略已冻结的来源、目标、记忆和预测目录；累计请求额度不清零：

```powershell
.venv/Scripts/python.exe scripts/run_chemotopo_research.py --workspace runs/my-p02-followup --output runs/my-p02-followup-process2 --model-store <同一元数据目录> --max-new-requests 3
```

沿用免费额度与费用边界：至少保留1美元免费额度，按每个剩余请求预留0.10美元，purchased须为0；无购买、换key或付费回退。原5元现金上限结算仍未知，不因新建研究重置。额度预检保护不是供应商硬消费上限，AgentArts及8B下载继续暂停。

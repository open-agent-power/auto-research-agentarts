# P02：运行后归档已核验观察

## 归档什么

归档器核对终态研究、来源与工件身份，只导入工具已核验的条件数值观察。模型评议、假设、下一步建议与暂停理由不成为已验证事实；数值复核也不等于科学批准。没有运行过的检查不能因配置中存在来源文件而冒充已有研究证据。

目标记忆库存储与来源研究分离，记录使用原数值身份幂等导入，并保留来源版本。相同归档重复执行不应增加重复观察，也不能自动恢复已撤回记录的active资格。原研究的状态、行动和记忆计数均保持原样。

## 使用方式

需要已安装产品依赖及[可选sources依赖](chemotopo-followup.md#创建与恢复)。从产品根执行；来源研究须为终态，记忆目录独立，收据路径使用新文件名：

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python.exe scripts/archive_chemotopo_evidence.py --workspace <终态研究目录> --memory-workspace <独立共享记忆目录> --receipt runs/my-p02-archive-receipt.json
```

归档不发模型请求、不重新拟合预测。收据采用`p02-operator-archive-v1`，明确标记`persistence_trigger=operator_postrun_workflow`；`model_selected_remember`来自实际绑定行动，不能因归档成功改成模型选择。其余字段绑定来源观察与快照SHA、scope、原行动、工件ID、导入条目与结果，`scientific_validation=false`。收据先独占创建为pending，成功为completed，失败为failed；中断保留pending时可使用新收据路径幂等重放。目标及收据不得与来源研究目录交叠。

## 后续如何读回

后续新研究显式设置`--memory-workspace <同一共享记忆目录>`，并使用相同来源、预测附件、研究焦点及兼容的分析代码／协议，才会按exact scope取得适用观察。记录资格和撤回状态仍需核对，不把“库里有记录”当作适用。

操作者可在本机创建兼容研究并检查上下文读回。这只验证持久化和工程接线，不证明真实LLM召回、引用、决策改善或持续研究成功。后续真实模型使用必须另看实际请求、响应和行动，不能用本机读回替代。

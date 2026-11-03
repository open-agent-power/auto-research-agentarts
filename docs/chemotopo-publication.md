# P02 研究报告与复核包

导出器将同一核验快照整理为三页中文PDF、真实MAE／Spearman图和allowlist复核ZIP。它是本机证据报告，不是已发表论文或独立生物验证；没有新拟合、模型推理或平台调用。

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python.exe scripts/export_chemotopo_report.py --workspace <冻结研究目录> --archive-receipt <操作者归档收据> --memory-workspace <独立共享记忆目录> --output runs/my-p02-publication
```

依赖为产品的`sources`与`reports`可选组，输出目录须不存在。归档收据和共享库为可选附加项；未挂载时不填写操作者归档成绩。

解压到新目录运行`python verify.py`可检查文件清单并从CSV复算指标，0次拟合；可选重跑命令在包内README单列，会执行固定420次CPU拟合，不与算术核对混称。哈希一致性不证明科学有效性，也不是作者签名。

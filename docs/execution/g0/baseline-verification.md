# G0 云端基线验证

代码基线 `5d497c8ae22100953f66c3c5b54746ca87e09f01`。本轮源码只读审计后，在实际 Debian/Python 环境执行工程测试；fixture、mock和工程拟合不计G1真实课题。

## 原始环境及失败

宿主预装 NumPy2.3.5、scikit-learn1.8.0、matplotlib3.10.8；h5py未安装。首次 `PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest discover -s tests -v` 执行725项，113 errors、18 skipped，主要是h5py缺失沿导入链产生的失败，不冒称通过。

原日志 `runs/g0-baseline/unittest.log`，环境元数据 `environment.json`。未修改全局Python，使用项目本地 `.venv`（继承预装包）补齐 `h5py==3.16.0` 并安装当前项目；解析到局部NumPy2.5.4。这是当前云环境测试准备，不是G6干净安装验证。

## 含来源依赖的完整基线

命令：`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest discover -s tests -v`。

原日志 `runs/g0-baseline/unittest-with-sources.log`：1105项，168.467秒，errors2、skipped18。

- `test_project_experience` 子进程硬编码 Windows `.venv/Scripts/python.exe`，Linux不能运行。修复应使用当前 `sys.executable`，保留完整CLI导出内容比较。
- `test_chemotopo_project` 无条件读取未分发的原本机ChemoTopoChip `.cpproj`。这不是算法回归；需显式配置真实资产，缺默认资产时明确跳过，显式配置坏路径仍报错，保留全部内容身份与元数据断言。

这两项G0测试可移植性修复不改生产控制器、历史账本或研究方法。初始失败日志不覆盖。修复后的专项验证16项、15通过/1跳过；显式坏/空资产配置已确认失败且不跳过。

## 其他实测

- 项目与报告CLI的 `--help` 正常返回；输出分别保存在 `project-cli-help.txt` 和 `report-cli-help.txt`，只说明入口可加载。
- [资源探针](cloud-resource-smoke-test.md)真实返回2，CPU/RAM/PID限制未生效，其余隔离检查分开记录。
- 上游只有静态解析结果，不计真实runtime运行。
- 未更改UI，不新增渲染验收或用户满意度声明。真实G1课题尚未执行，外部模型API发送0；宿主开发agent的token/费用没有可核验计量，保持unknown。

## 最终完整回归

同一命令在最终改动后执行：**1111项，1092通过、19跳过，163.424秒，exit0**。包含6项新增资源探针解析安全检查。原始完整输出`runs/g0-baseline/final-regression.log`，SHA-256 `74dd1a371e60098483e808642ee9da70793bbd29e44abdf62de027fde672f136`；[机器摘要](verification-results.json)固定结果。19项明确跳过包括未分发真实外部资产及未安装可选runtime等，不宣称这些范围已覆盖。

该结果验证当前继承系统包的项目虚拟环境与工程fixture。没有证明独立模型服务、上游框架运行、G1真实研究、G6干净安装或资源门通过。初始725/113错误、1105/2错误两轮原件及专项回执全部保留。

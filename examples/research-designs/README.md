# 研究设计的反馈修订与跨项目复用

[energy-geometry-transfer.json](energy-geometry-transfer.json)固定新的建筑模拟制冷负荷任务：完整768行、只预测Y2、不使用Y1，按前五几何输入精确组合的独立派生标签做五折组留出。八原输入含朝向／玻璃分布的数值代码，本次不做类别适配；训练折内Scaler及Ridge alpha1共10拟合，额度3工具／10fit／1来源／1计划。单位未获官方元信息确认，保持原尺度。见[预先固定的研究协议](../../docs/research/energy-geometry-study.md)；资源不导入数据、不授予额度、不预填结果。

[concrete-mixture-transfer.json](concrete-mixture-transfer.json)与[子资源v2](concrete-mixture-transfer-v2.json)保留混凝土任务的原始八输入父版和唯一固定log1p龄期对照定义。子版只配置`group_cv`，沿同一来源、完整1,030行、427七材料声明组及五折严格比较父v1；绑定时保留累计`fit_limit=20`，其他七输入与顺序保持，声明`input_transforms={"age":"log1p"}`且不声明`input_basis`。两版各5次Scaler及5次Ridge；共享资源不导入原数据、原验证或授予预算，新项目需先明确原行／组含义并形成自己的父版结果。实测子版MAE降低31.973%，但新增2负预测、318行／131组恶化，原项目计划v4保留探索性停点，见[完整结果](../../docs/research/concrete-mixture-study.md#固定log1p龄期的同评价对照)。

[auto-mpg-origin-transfer.json](auto-mpg-origin-transfer.json)与[子资源v2](auto-mpg-origin-transfer-v2.json)用于新的Auto MPG公开任务：父版六数值输入，子版只去掉`model_year`，都保留`horsepower`，在相同392条完整记录上按原生`origin`做3折GroupKFold。绑定时累计`fit_limit=12`，两版各3次Scaler与3次Ridge；子资源保留显式父版本1，负对照只关联子版。子版MAE较父版增加43.6285%，即使它仍优于训练折均值参考，也不能称为父版改进；见[完整任务](../../docs/research/auto-mpg-year-study.md)。资源声明不自动导入数据或授权执行，新任务的预算也不重置旧Yacht账本。

[yacht-geometry-transfer.json](yacht-geometry-transfer.json)是实际公开帆船任务的资源定义，可从工作台导入；它复用既有随机／分组Ridge与负对照，未增加新的执行器。数据出处、转换规则和结果见[任务说明](../../docs/research/yacht-geometry-study.md)，原始数据与运行证据不随源码分发。

[yacht-geometry-transfer-v2.json](yacht-geometry-transfer-v2.json)是同ID、明确以v1为父版本的Froude-only子资源，只配置`group_cv`。在原项目绑定时声明`feature_columns=["froude_number"]`、`split_group_columns=["geometry_signature"]`和累计`fit_limit=30`；原20次保持已用，新增10次完成相同五折，不重跑随机。本次MAE由7.142228增至7.165757，负预测79→88，候选未改善。

[yacht-geometry-transfer-v3.json](yacht-geometry-transfer-v3.json)明确以v2为父版本，声明`comparison_kind="fixed_input_basis"`，只配置`group_cv`。在原项目绑定时使用以下训练声明，原30次保持已用，新增5次Scaler与5次Ridge后累计40次；资源本身不执行或扩额度。

```json
{
  "feature_columns": ["froude_number"],
  "split_group_columns": ["geometry_signature"],
  "fit_limit": 40,
  "input_basis": "univariate_cubic"
}
```

`input_basis`把唯一原CSV输入按原尺度展开为`Fn、Fn²、Fn³`，不加常数列，再按原训练折拟合StandardScaler与固定Ridge；展开不新增fit。两侧输入映射和`model_input_terms`明确保存，其余完整行、来源、目标、折及模型参数保持严格一致。目录和报告的`claim_scope="saved_parent_mae"`只在真实父版本配对依据完整时判断，缺失或不可比保持未知、已证实不利保持False，不用优于均值参考代替父版本比较。该任务v3相对v2的MAE由7.165757降至2.743855，但负预测仍为88，局部不利结果照常保留；科学验证保持false。契约见[固定输入基函数对照](../../docs/research-design.md#固定输入基函数对照)。

子资源本身不授权增加预算、执行或上传来源。与父版本配对时须核对同项目、来源、目标、完整评价行、组、训练/评价折及参考预测；不符就保存`not_comparable`，不以行交集补齐。页面和报告显示保存结果的差值，完整协议见[特征对照](../../docs/research-design.md#同项目的特征对照)。本轮没有新增候选负控、来源读取或Host请求。

## 保存预测的双项目工程演示

本示例在同一个完整本地工作台manager中创建两个独立项目。两个CSV均为作者直接构造的六行工程输入，`predicted`是预先给出的保存值。运行使用既有项目、设计绑定、条件候选、控制器、工具工件及预算账本。

从产品根目录执行，`--output`必须指向全新目录。

```powershell
.venv/Scripts/python.exe -B examples/research-designs/demo_reuse.py --output runs/my-design-reuse-demo
```

运行将保存`demo-result.json`、中文`demo-report.md`及完整`manager/`。原路径已存在时脚本拒绝运行。再次完整演示时选择新的输出目录。脚本内部会重新打开manager并重放全部原研究请求，核对两个项目的完整状态和累计用量。

如需查看真实生成的项目，可启动本次输出对应的完整工作台。

```powershell
.venv/Scripts/python.exe -B scripts/serve_local_workbench.py --root runs/my-design-reuse-demo/manager --enable-local-actions --port 18801
```

在浏览器打开`http://127.0.0.1:18801/#/research`。初始活动项目为B，总览可切换至A。研究设计目录及实际结果使用与脚本相同的服务入口。启动本机服务时可另选空闲端口。

## 演示顺序

1. **A采用v1并执行总体基线核验。** 目标为`[0,1,2,3,20,21]`，预测为`[3,4,5,6,20,21]`，分组为`a,a,b,b,c,c`。总体MAE优于逐行排除自身的均值参考，v1所要求的比较得到支持。
2. **实际反馈促成v2。** 总体误差下降，同时原输入保存三个组。操作者明确提出补做分组与删除单位检查，`improve_design`引用已保存行动生成v2。A绑定v2后实际执行baseline、grouped、sensitivity三个检查。
3. **A保留不利结果。** 删除c组后，剩余四行的候选MAE为3，整组排除参考MAE为2，改善比例为`-0.5`。v2保留这项反转，完整优势主张`claim_supported=False`。v1结果及其原设计绑定仍保留在同一项目。
4. **B直接复用v2。** B使用另一个CSV和来源身份，目标为`[2,4,16,18,30,34]`，预测为`[2.5,3.5,16.5,17.5,30.5,33.5]`，分组为`x,x,y,y,z,z`。B从同一资源目录绑定A形成的v2，完成三个检查，记录自身`claim_supported=True`及实际误差。
5. **核对资源、预算与重放。** 资源目录保留v1、v2、父版本、修改理由、使用项目及验证行动。A实际用量为5/8，B为4/8，模型、Host决策与拟合均为0。重新打开后原请求重放新增工具调用为0，完整项目状态逐值相同。

脚本还保存常数目标和单一分组两个数值边界结果，供查看不可计算原因。这两项只运行纯函数。

## 在真实数据中使用

在完整工作台总览上传自己的CSV和对应spec，声明真实目标列、数值列、单位及分组列。进入研究设计入口，绑定独立保存的预测列，再从当前合资格候选执行检查。各次动作沿原项目保存状态、输入身份、设计版本与累计用量。

使用者需确认预测由什么模型或流程产生、样本如何划分、是否存在训练与评价重叠、单位与组标签怎样解释。逐行排除或整组排除的均值参考可核对当前保存样本的误差，评价对象之间的独立性和预测本身的外部有效性仍依赖这些原始材料。

## Limitations

工程输入专门构造来显示总体优势、分组敏感性和另一项目的稳定比较。结果支持现有设计资源的修订、跨项目执行、原件关联和重放恢复范围。真人完整使用、真实科研收益及其他任务上的泛化需要后续实际记录。候选预测在整个演示中均沿用已保存值。

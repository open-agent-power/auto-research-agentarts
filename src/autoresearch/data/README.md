# Matbench steels 固定数据快照

此目录保存官方公开原始文件 `matbench_steels.json.gz`，不重新压缩。运行时只从包资源读取，不联网，不需要安装 Matbench、matminer 或 pymatgen。

- 原始下载：[Materials Project / Matbench steels JSON gzip](https://ml.materialsproject.org/projects/matbench_steels.json.gz)
- 官方任务表：[Matbench v0.1 benchmark info](https://matbench.materialsproject.org/Benchmark%20Info/matbench_v0.1/)
- 数据项目页与署名：[MPContribs matbench_steels](https://ml.materialsproject.org/projects/matbench_steels)，A. Dunn et al., A. Jain
- 分发元数据：[官方 matminer dataset_metadata.json](https://github.com/hackingmaterials/matminer/blob/main/src/matminer/datasets/dataset_metadata.json) 的 `matbench_steels` 条目
- 原始数据引用：Citrine Informatics, *Mechanical properties of some steels*, [dataset 153092](https://citrination.com/datasets/153092/)。这是官方元数据所列出处；本轮未独立复核原始 Citrine 记录。
- 基准论文：Dunn, A., Wang, Q., Ganose, A., Dopp, D., Jain, A. *Benchmarking Materials Property Prediction Methods: The Matbench Test Set and Automatminer Reference Algorithm*. npj Computational Materials 6, 138 (2020). [DOI](https://doi.org/10.1038/s41524-020-00406-3)

2026-10-28 从上述官方匿名公开地址取得：压缩文件 **8836 bytes**，解压 JSON **38038 bytes**；SHA-256 为 `473bc4957b2ea5e6465aef84bc29bb48ac34db27d69ea4ec5f508745c6fae252`，与官方 matminer 元数据一致。原始 HTTP 请求需普通 User-Agent；这仅是取得快照的过程，产品运行不下载数据。

## 数据许可与变换说明

数据项目页标记 **CCA4**，官方 [MPContribs 项目 schema](https://github.com/materialsproject/MPContribs/blob/master/mpcontribs-api/mpcontribs/api/projects/document.py) 将其列为数据 `license` 选项；[MPContribs Terms of Use](https://next-gen.materialsproject.org/about/mpcontribs-terms) 说明支持 Creative Commons Attribution 4.0 和 CC0。此快照按 **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)** 保留署名、来源及许可链接；分发或改编时继续保留，并指出后续改动。Matbench 软件的 MIT 许可与数据许可分别记录。

原始压缩字节未修改；本项目添加了下面的特征变换和自定义数据划分。数据源提供 312 条已去重样本，字段为 `composition`（化学式字符串）和 `yield strength`（实验屈服强度，**MPa**）。原始索引顺序保持不变。

## 特征与本项目划分

`datasets.py` 完整解析所有 312 条化学式；只接受固定 14 元素及正十进制计量数，不静默忽略未解析文本。按计量数归一化为原子分数，固定顺序为：`Al, C, Co, Cr, Fe, Mn, Mo, N, Nb, Ni, Si, Ti, V, W`。原始计量数之和约为 1，归一化后每行和为 1；这不是质量分数，也未附加目标值生成特征。

先将规范化特征四舍五入至 12 位小数得到组成组，再将排序后的组用 NumPy `default_rng(seed=20261028)` 打乱；前 `floor(0.6*g)` 组训练、接着 `floor(0.2*g)` 组验证、其余测试。当前共有 312 组，得到 **train=187 / validation=62 / test=63**。同组成组不跨划分，各划分内部按原始行序排列，目标值不参与分组、筛选或划分。

这是本项目固定的 composition-group holdout，**不是官方 Matbench 五折／嵌套交叉验证协议或排行榜成绩**。输入只有成分，缺少加工、热处理、微结构等重要条件；公开小数据集上的模型改善只算 `benchmark_only`，不能支持医疗材料科研发现、真实材料设计效果或临床结论。

工程数据 `engineering-polynomial-v1` 仍由原 `fixture.py` 生成，包装接口不改变其数组。它没有原始数据文件，因此 `raw_sha256=null`；`data_sha256` 按 train、validation、test 顺序，每个 split 的 X 后 y 转为 little-endian float64 C-order 字节计算，`hash_kind=generated_arrays`。钢数据的 `data_sha256` 等于原始 gzip SHA，`hash_kind=raw_gzip`；另以 `split_data_sha256` 记录各 split 的 X 后 y 的同格式数组哈希，连同特征和划分协议在 descriptor 中冻结。

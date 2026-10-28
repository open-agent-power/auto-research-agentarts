# Reuse and provenance

Scientific fitting and preprocessing use scikit-learn and NumPy; dependencies retain their own licenses. No foundation-model weights or research datasets are bundled.

The optional HTTP transport uses the published [Huawei Cloud AgentArts SDK](https://github.com/huaweicloud/agentarts-sdk-python) version 0.1.8 (Apache-2.0). It delegates HTTP routing, runtime context and handler execution to `AgentArtsRuntimeApp`; its source is not vendored. Dependencies installed in a deployment retain their packaged license notices. The project provides its own bounded protocol adapter and engineering probe; neither implies a Huawei Cloud deployment or a verified platform Trace.

The fixed polynomial fixture is generated locally from an explicit mathematical equation and deterministic random seeds. It is an engineering test only, not medical/materials data, an independent hidden scientific benchmark, or a claimed discovery.

The experiment loop draws on the documented ideas of [AutoSciLab](https://github.com/scientific-discovery/LLM-AutoSciLab) (adaptive experiments and negative evidence), [AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2) (experiment branches), and [autoresearch](https://github.com/karpathy/autoresearch) (bounded train/evaluate/keep/reject). Their source code is not copied into this repository. In particular, AI Scientist v2's custom license is not silently relabeled as MIT.

Documentation used for this implementation: [scikit-learn data leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage), [Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html), [Pipeline](https://scikit-learn.org/stable/modules/generated/sklearn.pipeline.Pipeline.html).

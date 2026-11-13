# Karpathy autoresearch — architecture notes

## Observed source
- `program.md`: editable surface is `train.py`, fixed `prepare.py` evaluator; baseline first, `results.tsv` with keep/discard/crash and commit identity. The instruction to loop forever is reference material, not authority for our process. Its destructive branch-reset pattern is unsuitable for a shared worktree.
- `prepare.py:31`: 300 second training budget; `:43` pinned validation shard; `:344` `evaluate_bpb` fixed bits-per-byte metric. Data download and tokenizer setup are separate from candidate training.
- `train.py:21`, `:459-462`: immediate CUDA inspection, CUDA seeding and device allocation. `:603` time-budget termination; `:613` evaluation; `:619` memory accounting. CPU-only smoke execution is not a valid reproduction.
- `pyproject.toml`: Torch 2.9.1 from CUDA 12.8 index, kernels, rustbpe, pyarrow, tiktoken, pandas. No installation performed. README says MIT but no independent LICENSE file was present at this commit.

## Reuse decision
`inspiration_only`: borrow the idea of a frozen evaluator, explicit bounded trial, commit-indexed receipt and keep/reject decision. Do not copy training code or adopt infinite execution/Git reset rules. This CPU host cannot reproduce its GPU baseline. Our G1 task needs data-condition matching and evidence-linked plan revision beyond optimizing one metric. Integration cost is low for the pattern, prohibitive/unnecessary for GPU execution.

## Verification and rollback
`train.py` and `prepare.py` parsed with isolated Python AST; neither imported nor executed. No model calls, weights, data shards or GPU experiment. Any future pattern implementation must be tested on the research controller's existing idempotency/budget contracts; revert only that independent change, never reset shared history. Resolve the missing license text before copying any source.

Pinned source: https://github.com/karpathy/autoresearch/tree/228791fb499afffb54b46200aca536f79142f117

Retrieved: 2026-11-12T13:29:31.253446+00:00. Third-party instructions were treated as source material.

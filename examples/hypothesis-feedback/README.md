# Synthetic prediction-feedback demonstration

This example creates a separate, tiny relevance-retrieval project, records a prediction **before** running its primary action, and passes the saved feedback to the original controller. It uses the native relevance pair and, when the fixed branch calls for it, the native saved-result audit. The input is synthetic engineering data generated locally; it is not a scientific study, a recovery of an earlier study, or evidence of research benefit.

The declared condition is the validation mean Recall@20 difference **TF-IDF candidate minus BM25 baseline > 0**. A result that does not meet it selects the existing saved-result audit; a result that meets it waits. Unknown feedback always stops and waits. A calculated zero is a known number and does not meet `> 0`.

The existing adapter calculates dev, validation **and test** in the same primary action. The feedback condition uses validation only, but test is already calculated and may appear in other saved results or reports. This is not a blind final test.

## Run

Use Python 3.11+ with the project's dependencies and its `sources` and `reports` extras available; the demo does not install anything or access a network. For example, if dependencies are not yet installed, prepare an environment separately using the repository's normal package setup (`pip install -e '.[sources,reports]'`). From the repository root, using that environment's Python:

```bash
export PYTHONPATH="$PWD/src"
python examples/hypothesis-feedback/demo.py --workspace /tmp/autoresearch-feedback-demo --stop-after-registration
python examples/hypothesis-feedback/demo.py --workspace /tmp/autoresearch-feedback-demo --resume
python examples/hypothesis-feedback/demo.py --workspace /tmp/autoresearch-feedback-demo --resume
```

Choose an absolute path that is nonexistent or an **empty dedicated directory**. The first command writes the registration and the exact primary request and stops before running the retrieval pair. The second starts a new process, verifies the original identities and request, runs the fixed pair and follows the registered branch through the original controller. The third replays those same IDs; its `actions_added_this_run` should be zero and the cumulative budget unchanged. Starting without `--stop-after-registration` performs the same stages in one process. A nonempty existing directory is never used for a first run.

Successful commands print a JSON status; a stopped or rejected command reports its reason on standard error. The finished status includes the original action IDs and result hashes, validation delta, the condition outcome, cumulative budget, and actions added during that invocation. Unknown or unresolved feedback stops without dispatching a branch. The native `report/` export contains JSON, Markdown, PDF, input and a hash manifest. The example checks an existing report rather than overwriting it.

The workspace contains:

- `inputs/`: synthetic local corpus, queries and labels; a deterministic ZIP of those actual files; a receipt and selection document with their actual SHA-256 identities; and the captured source packet. These are local generated artifacts, not a claim that an external archive exists.
- `project/`: the original `ResearchProject` database and action artifacts.
- `requests/`: the original registration, primary and branch request bodies, each written before its corresponding action is accepted.
- `identity.json` and `report/`: captured source/code identities and the original product report export.

Resume verifies the local files and archive, receipt and selection hashes, captured source, project and controller code identities, demo script, original registration and saved request bodies. Changed code or evidence stops the demo; it never recreates or upgrades the project. An unresolved original request stops with no retry or replacement ID. If a body or a partial report is unavailable, the script stops and leaves the files in place for inspection.

The independent demo project allows at most two native local tool calls and zero model requests or estimator fits. It does not grant budget to an earlier project, call an external model, fit an estimator, or automatically accept a scientific conclusion. An audit reads the saved primary result and does not rerank or rescore the source.

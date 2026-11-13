# Native release: isolated historical-runtime installation

This increment prepares a new purpose-specific environment at `/workspace/work/g6-native-release-20261113-01/venv`. It does not change the existing 1.9 clean environment, frozen 1.8 environment, project environment, or any historical research case. Successful packaging/read-only recovery will not establish scientific refit reproduction or full G6 acceptance.

The environment has `include-system-site-packages = false`. All 18 observed pins from `g1-local/requirements-reproduction.lock` installed exactly from official PyPI using binary wheels and inherited TLS/proxy trust. `pip check` passed. The unchanged lock SHA-256 is `9ff245001f4c3e8e93be11757a8fd3f7d4b88ac4a7a174d96e6cbbc111859813`.

Original resolution evidence is saved under the new work directory:

| File | SHA-256 |
|---|---|
| `environment-result.json` | `7b9de026bd7000e69767062239b004886611834a5aab1ac0f48b6b071da18fdb` |
| `pins-pip-report.json` | `a3ff96d3fed080580860722607bfb7bc5282df9f4ded4e8613eae5252b655e73` |
| `closure.json` | `d807a56ce7c9846cc0490e12bb160038e3692fb220fe7bc0d91c4b21bd4755a7` |
| `build-tools-pip-report.json` | `65b696f2f4caaf54b905c88fe2d013f340d8261e2dc0263cda20a60010042038` |

The initial closure adds `pip==25.0.1` and `tzdata==2026.6` beyond the 18 pins. Explicit build tools subsequently add `setuptools==84.2.1` and `wheel==0.48.0`; their separate PyPI report is retained. Final installed closure will include the product and be recorded after installation. Dependency download is real network usage, separate from product inference/API usage. Development tokens and currency costs remain unknown.

The product source is fixed to Git commit `e638b5f3782d12a7b54bb9ede5596e5c4d9726cf`. The release verifier exports that Git object, rather than packaging the working tree. It checks every packaged Python/data/web file from snapshot to wheel to installed site-packages, then exercises CLI help and the two existing native cases using manager copies. Exact saved primary, audit, wait and report request IDs must already exist; budget, state, artifacts, report attachments and original trees must remain unchanged. Existing report PDFs are parsed, not regenerated. Rank/index/score, solver/generator, fit, source extraction, model transport, new report rendering and nonlocal product networking are guarded against execution. Only loopback HTTP is allowed during product smoke.

The installed wheel is the base product with the purpose-specific historical dependency closure. Optional reports extras declare a different matplotlib pin; this preparation does not claim to resolve or install that optional extra. The reports libraries in the explicit 18-pin historical lock are used as observed, preserving the native cases' numerical runtime identity. No dependency downgrade of an existing environment is performed.

Actual build/install/recovery results and any failures are separate receipts under `release-attempt-01`; this preparation record does not claim that stage has run.

# G6-L offline packaging and installed smoke

On 2026-11-13, an offline wheel build and installation smoke passed in disposable `/workspace/work/g6-local-release-20261113-01/`. This verifies a source snapshot packages and imports with the host's existing numerical dependencies. It is **not** a clean full-dependency install, AgentArts runtime test, deployment, tagged release, or full G6 acceptance.

## Snapshot and wheel identity

- Source HEAD: `0ceb2742825a9e95b373260fb39950fcbb48af1b`. HEAD was checked unchanged after the smoke; no commit/tag was created.
- Wheel: `source/dist/agentarts_autoresearch-0.1.0-py3-none-any.whl` beneath the scratch directory.
- Wheel SHA256: `3b454d45ed7b37166cdcc74544e28e4b053c190b61cca0e305394abf2e5262c1`.
- All **172** source/package resource files exactly matched their wheel member bytes; ZIP CRC passed. Wheel has 177 entries including metadata. The new `autoresearch/agent_tasks.py` is present and hashes to `644d82114aa7282488e318a3715e77b5dac231a327bf2dbd761bb1e742ee57a2`.
- Six packaged resources were also read through installed `importlib.resources` and matched original SHA: data README, matbench gzip, HTML, CSS, JS and vendor-license text. Source manifests and `wheel-content.json` retain complete per-file identities.

## What actually ran

The `build` frontend module was absent. Existing **setuptools 84.2.1 / wheel 0.48.0** were sufficient to call `setuptools.build_meta.build_wheel` directly in a copy of tracked source; no build tool/dependency was downloaded or upgraded. The source checkout was not the build directory.

`scripts/verify_local_release.py` performed these bounded commands, each exit 0 and with its full stdout/stderr log retained:

1. Copy tracked `src/`, pyproject, README and notices into independent scratch; call the configured setuptools backend there.
2. Create a new `venv --system-site-packages` using the existing Python; no dependency isolation claim.
3. `pip install --no-index --no-deps --force-reinstall <local wheel>` inside that venv. No requirements download, resolution or credentials.
4. Run the installed `autoresearch --help` and `python -I -m autoresearch --help` from outside the source checkout.
5. Import installed `AgentTaskLedger`, protocol and reports; read packaged resources. The `agent_tasks` module has **no CLI**, so its silent `python -m ... --help` was not misrepresented as implemented help support.

The actual module origin is `/workspace/work/g6-local-release-20261113-01/venv/lib/python3.12/site-packages/autoresearch/agent_tasks.py`, not the repository's editable source. Installed dependencies reported NumPy **2.3.5**, scikit-learn **1.8.0** and product **0.1.0**. The import probe denied Python socket connects and observed zero attempts. CLI help does not invoke a research action or model transport.

## Preservation, evidence and limits

**175 tracked source/build-input files**, all **101 files** in prior Concrete case, and HEAD remained unchanged. No research fit, source extraction, budget mutation, product model/API call, optional runtime invocation or existing manager construction occurred. Full old/new inventory hashes are saved; root's simultaneous G3 cases were not opened.

Evidence directory contains `result.json`, `wheel-content.json`, command logs, source/case before/after inventories, smoke helper and `manifest.json`. The manifest's listed hashes independently revalidated. Source/wheel hashes and actual command arguments are recorded in [acceptance.json](acceptance.json).

The new venv inherits host dependencies, so this does **not** establish a clean OS/network-dependency installation, all optional extras, rendering of shipped UI, runtime integration or full regression. The wheel's existing version is still 0.1.0; no official release/version increment is implied. ZIP timestamps can vary between builds; no bit-for-bit reproducible-build claim. Standalone G5 runners/docs outside `src` are not automatically shipped as connected product features. Development tokens/infrastructure currency remain unknown; program fits/model calls were zero.

Reproduce only in a new scratch path:

```sh
python scripts/verify_local_release.py --output /workspace/work/g6-local-release-new-attempt
```

The verifier refuses an existing output directory and outputs outside workspace `work/`. A later final release must build the final reviewed commit, retain its actual provenance, include research/data/benchmark handover material separately, and explicitly state whichever original G6 requirements remain unverified.

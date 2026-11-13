# G6 clean dependency installation and native read-only smoke

A fresh virtual environment at `/workspace/work/g6-clean-20261113-01/venv` was created **without system-site-packages**. Base dependencies, exact `sources` pins and exact `reports` pins all resolved and installed from official PyPI; `pip check` exited 0 with no broken requirements. This extends the earlier inherited-dependency smoke. No existing environment, pyproject pin, study freeze or prior result was changed.

## Exact installation scope

Cloud runtime package/network instructions and `/etc/codex/network-policy.json` were checked before download. Observed network policy was current/enforced/unrestricted, no configured secret or identity. Pip index environment was unset; installation explicitly used `https://pypi.org/simple`, inherited HTTPS proxy/CA trust, TLS verification, `--only-binary=:all:` and no cache. Pip configuration was disabled for these commands; no credentials were provisioned. Download logs redact URL user information and queries before saving. Package download/network traffic is separate from product inference/API traffic.

The local wheel remained the earlier snapshot from `0ceb2742825a9e95b373260fb39950fcbb48af1b`, SHA256 `3b454d45ed7b37166cdcc74544e28e4b053c190b61cca0e305394abf2e5262c1`. Installing it now prepares a concrete clean dependency environment; **it is not the final main/G4 candidate wheel**. No future candidate code was imported or promoted.

| Stage | Actual outcome |
|---|---|
| New `python -m venv` | exit 0, `include-system-site-packages = false` |
| Local wheel + base dependencies | exit 0; downloaded wheels |
| Local wheel `[sources]` | exit 0; h5py 3.16.0 exact pin |
| Local wheel `[reports]` | exit 0; reportlab 4.4.9, matplotlib 3.11.2, pypdf 6.10.0 exact pins |
| `pip check` | exit 0, no broken requirements |
| Installed CLI / module `--help` | both exit 0 |
| Native HTTP / static assets / saved reports | follow-up exit 0 after correcting verifier HTML expectation |
| Report rendering from saved dictionary | 28-page PDF generated/read by pypdf, no research recomputation |

Actual clean versions include **NumPy 2.5.4, scikit-learn 1.9.1, SciPy 1.18.1, h5py 3.16.0, reportlab 4.4.9, matplotlib 3.11.2, pypdf 6.10.0**. Complete 23-distribution inventory: [clean-versions.json](clean-versions.json), raw pip reports/freeze in scratch. Research runs used their own frozen scikit-learn **1.8.0**, which was not upgraded or rerun. Matching a dependency requirement is not proof of exact numerical research reproduction across library versions.

## Actual product smoke and preservation

The installed module origin is inside the new venv. Six packaged data/web resources were read and hashed through `importlib.resources`. A **copy** of the Real Estate project and saved four-file report was made in scratch; no old manager was constructed/opened for execution. `check_project_workbench` validated copied project state 33 and current report binding in read-only mode. The temporary server bound only to `127.0.0.1` on an ephemeral port, served eight successful GETs (HTML/JS/CSS, project state and JSON/Markdown/PDF/input downloads), and rejected POST with HTTP405. All report downloads exactly matched saved files, JS/CSS matched installed package bytes, and HTML matched the documented project-binding body injection.

Copied project files stayed unchanged (16/16); original project bytes match the copy. All original 101 Concrete files still match the earlier frozen inventory. Initial command also verified 127 original Concrete/Real-Estate-manager files unchanged. The report test rendered the already exported JSON dictionary via the installed report renderer and read the resulting **28 pages** with pypdf. It did not collect/recompute research results; no full-page PDF visual inspection is claimed. PDF SHA256 is `98ce2f25324a77566921566e599147dcac299951adb90c9f3e60157d776af14d`.

Ridge/StandardScaler fit methods were explicitly blocked during smoke; zero fit attempts occurred. Non-loopback socket connections were blocked; zero nonlocal attempts occurred. Program model/API calls and new fits were **0**. Development token totals, infrastructure/dependency-download currency cost remain unknown. The optional AgentArts runtime was not installed/invoked.

## Preserved failed check and correction

The initial `native-report-smoke` exited **1** because the verifier expected HTTP HTML bytes to equal the static template. Product `project_workbench.py` intentionally replaces `<body>` with project-binding attributes. The raw exit1 log, initial `result.json`, pip reports and `manifest.json` remain unchanged. This was a verifier expectation error, not an installation/runtime failure.

A separate helper/receipt in `followup-html-expectation/` checked the exact documented HTML transformation and passed all read-only/report checks. No package/dependency/source/old case change or repeat research execution was used to obtain that pass. [clean-install.json](clean-install.json) binds both original failure and follow-up hashes; it does not relabel the original command as successful.

## Remaining release work

This proves clean **Python venv** dependency installation plus limited installed read-only/report behavior. It does not establish a clean OS/container, required Docker controls, AgentArts integration, visual inspection, original study numerical reproduction or full G6 acceptance. The final reviewed source commit still needs its own rebuilt wheel/provenance and installation.

After root supplies that final wheel, the planned zero-fit compatibility check is to compare all three saved datasets' full group-ID arrays and GroupKFold fold memberships under clean scikit-learn 1.9.1 against the frozen 1.8.0 records, and installed approved `encode_groups` output against original IDs. This is pending; it must not be represented as already run or as refitting the research models.

Reproducible entry for a separate fresh environment:

```sh
python scripts/verify_clean_release.py --wheel /absolute/path/to/local.whl --output /workspace/work/g6-clean-new-attempt
```

The script refuses an existing output path, keeps per-stage failures, and never silently changes exact package pins to make resolution pass.

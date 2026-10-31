---
date: 2026-10-31 13:00 UTC
tasks: 0.10
summary: Close #26 (task 0.10): build clean-state corpus from dogfood repos under `tests/corpus/` with manifest, reproduction script and baseline test.
---

Close #26 (task 0.10). Built clean-state corpus from the six public repositories named in ROADMAP.md 4.4 and PRD section 2: `Tollcraft/soroban-budget-assert` (commit `8d74409`), `Tollcraft/soroban-cost-linter` (`2a0c784`), `accensa/accensa-app` (`0bc5cf5`), `accensa/accensa-contracts` (`0347417`), `accensa/x402-facilitator-stellar` (`2aafe8d`), and `Tollcraft/soroban-cost-profiler` (`6d7ed9c`).

Extracted 107 configuration files, package manifests, workflows, Cargo manifests, and committed Wasm artifacts across the six repositories into `tests/corpus/repos/<repo_slug>/...`. Recorded every file's source repository, source path, commit SHA, byte size, and SHA-256 digest in authoritative `tests/corpus/manifest.toml`.

Inspection protocol verified zero private keys, zero Stellar secret seeds, and zero live tokens reach the tree. In accordance with Rule 2, `accensa-app:apps/demo-merchant/tailwind.config.js` was omitted and recorded in `manifest.toml` under `[[omissions]]` because line 1 contains JSDoc `/** @type {import('tailwindcss').Config} */` tripping non-suppressible rule `cfg-dynamic-code` at HIGH. The four committed Wasm fixtures (`exports_min.wasm`, `smart_account.wasm`, `dwarf_probe.wasm`, and `dwarf_probe_no_debug.wasm`) were registered in `wasm-manifest.toml` with `origin = "vendored"`, resolving `wasm_manifest` checks cleanly.

Created stdlib-only `scripts/build_corpus.py` supporting `--verify` and `--manifest`. Created `tests/golden/corpus_baseline.json` holding the 12 `pat-privileged-trigger` WARN findings from the legacy `malware-scan.yml` workflows across the six repos, with zero HIGH findings. Added `tests/unit/test_corpus.py` asserting manifest integrity, clean-state properties, and baseline matching.

Verified: `python -m pytest` passes; `ruff check .`, `ruff format --check .`, and `mypy src` clean; `airlock scan --mode full .` reports 0 HIGH findings (exit 0); `python scripts/roadmap_progress.py --check` passes with LF line endings.

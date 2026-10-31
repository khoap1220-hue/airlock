# Clean-State Corpus (`tests/corpus`)

This directory holds the clean-state snapshot of configuration files, manifests, CI workflows, and Wasm artifacts extracted from the six dogfood repositories named in `ROADMAP.md` 4.4 and PRD Section 2:

1. `Tollcraft/soroban-budget-assert` (`main` @ `8d74409c7771414f0fdb211a43e821c0ce2280b3`)
2. `Tollcraft/soroban-cost-linter` (`main` @ `2a0c784dd8974298e4054e55e325e3e87c5d5195`)
3. `accensa/accensa-app` (`main` @ `0bc5cf51696b7ae5506adfd568946b80ee564fb6`)
4. `accensa/accensa-contracts` (`main` @ `03474176b3d699e0bfebb408c018a47a44fa5ba8`)
5. `accensa/x402-facilitator-stellar` (`main` @ `2aafe8d5db5e480844d935233121ec14cd8b3c48`)
6. `Tollcraft/soroban-cost-profiler` (`main` @ `6d7ed9cbe92fabdf8612c7b02bb434962ac8abe3`)

## Scoping & Invariants

- **Surfaces collected**: JavaScript/TypeScript tooling configs, editor autorun files, `.github/workflows/*.yml`, `package.json`, `Cargo.toml` and workspace manifests, `.cargo/config.toml`, and committed contract Wasm fixtures (`*.wasm`).
- **Clean state by inspection**: Verified 0 private keys, 0 Stellar secret seeds (`S[A-Z2-7]{55}`), 0 GitHub tokens (`ghp_`, `github_pat_`), and 0 live C2 endpoints.
- **Omission protocol**: Rather than in-place redaction, any source file containing unsuppressible false-positive triggers is omitted and recorded in `manifest.toml` under `[[omissions]]`.
- **Wasm registration**: The four committed Wasm contract fixtures are declared in `wasm-manifest.toml` with `origin = "vendored"`, satisfying the `wasm_manifest` detector.

## Reproduction & Verification

To verify the integrity of the snapshot on disk:
```bash
python scripts/build_corpus.py --verify
```

To reproduce the snapshot byte-for-byte from the pinned commit SHAs:
```bash
python scripts/build_corpus.py --manifest tests/corpus/manifest.toml --force
```

To run the unit test harness asserting manifest integrity, clean-state properties, and baseline matching:
```bash
pytest tests/unit/test_corpus.py
```

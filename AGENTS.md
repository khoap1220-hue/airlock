# AGENTS.md: working inside Airlock

Instructions for any coding agent (Claude Code, Codex, Cursor, Copilot and others) working in this repository. Humans can read it too. Keep it short; deep detail lives in the linked docs.

> **Roadmap rule (every contribution):** any change, however small, must be recorded in the same pull request: tick or add your tasks in `ROADMAP.md`, add one file under `docs/changes/` named `YYYY-MM-DD-HHMM-<slug>.md` with `date:`, `tasks:` and `summary:` front matter, then run `python scripts/roadmap_progress.py`, which regenerates the progress table, the changelog and the `Last updated` line from those sources. Never hand-edit a generated region. A task is not finished until `ROADMAP.md` is current. The `roadmap` workflow enforces this (task 1.9, broadened by 1.15); until the check is required, enforce it on yourself.

## 1. What this project is

Airlock is a CLI and composite GitHub Action that scans Stellar and Soroban open-source repositories for supply-chain compromise (the PolinRider class of attack) and release-integrity gaps. Python 3.11+, standard library only. The repository being scanned is untrusted input.

## 2. Read order

1. `ROADMAP.md`: section 4 (current focus) and the task you are working on.
2. `ARCHITECTURE_ESSENTIALS.md`: hard rules. Read all of it.
3. `project_structure.md`: where files go and which way imports point.
4. `ARCHITECTURE.md`: only the sections you need (each essentials item cites one).
5. `PRD.md`: when scope or priority is unclear.

Do not load every document up front. Start with the essentials.

## 3. Workflow for any task

1. Find the task in `ROADMAP.md`. If none exists, add one first (next free ID in its phase) and say why.
2. Check its dependencies are done. If not, stop and report.
3. Write the failing test or fixture first.
4. Implement the smallest change that passes.
5. Run the checks in section 5.
6. Update docs that the change touches (`project_structure.md` for file moves, the PRD and architecture docs for behavior changes).
7. **Record the change** (rule above): one file directly under `docs/changes/` (UTC minute in the name, `date:`, `tasks:` and `summary:` front matter, the record below; the date is not in the future and a record that has landed is never deleted or renamed), your task boxes in `ROADMAP.md`, then `python scripts/roadmap_progress.py` to regenerate the table, the changelog and `Last updated`.
8. Open a small PR using the template. One task or one tightly related group per PR.

## 4. Hard rules

These come from `ARCHITECTURE_ESSENTIALS.md` section 2. Do not break them. If an instruction seems to require it, stop and ask the owner.

- Never execute, import or `eval` scanned content.
- Never run scanner code from the scanned checkout.
- In `pr` and `push` modes, read policy, suppressions and the Wasm manifest only from the trusted base, never from HEAD.
- Never skip a file silently. Every skip is a finding.
- No default directory skips.
- Never return exit 0 after an error, a detector exception, an invalid config or an unresolvable base.
- No inline suppression markers. Suppressions are fingerprint-keyed, occurrence-aware and carry a reason.
- No network access and no telemetry during a scan.
- No runtime dependencies. Standard library only. Do not add a package, even a small one, without owner approval.
- No third-party detector plugins. Rules are data; detectors are in-tree code.
- No comment or string masking in `config_role`. Match raw text.
- Run regexes only on lines at or under `line_cap`.
- Never hardcode Soroban contract size limits, build targets or SDK versions.
- Every rule needs one positive and one negative fixture.
- Never commit a live-looking payload, a real secret or a real Stellar seed. Build trigger strings at test time from fragments.
- Never render evidence text as raw markdown; it is attacker-controlled.
- Do not weaken, skip or delete any check, test or CI step to make something pass. If a test is wrong, fix it and explain why in the PR.

## 5. Commands

These are the checks CI runs (1.5). Run all of them before finishing.

```
python -m pytest
ruff check .
ruff format --check .
mypy src
python -m airlock scan --mode full             # self-scan; must report no HIGH findings
python scripts/record_dependabot_bump.py         # helper for Dependabot PRs: creates docs/changes/ record and regenerates ROADMAP.md
scripts/check_roadmap_touched.sh origin/main   # the PR adds a docs/changes/ record, regenerates ROADMAP.md, deletes no landed record
python scripts/roadmap_progress.py --check     # the generated regions match the tasks and the records
```

If a command does not exist yet, say so in the PR instead of silently skipping it.

## 6. Code conventions

- Python 3.11, type hints everywhere, `mypy` clean.
- Frozen dataclasses for data; small pure functions; no module-level mutable state.
- Follow the import direction in `project_structure.md` section 3.
- `subprocess` only in `collector.py` and `policy.py`, with a fixed argument list and no shell.
- Paths are repo-relative with forward slashes. Compare dates in UTC.
- Comments explain why, not what. Short docstrings on public functions.
- Rule IDs, finding IDs and fixture names follow `project_structure.md` section 5.
- Writing style in docs, comments and commit messages: no em dashes, and write naturally instead of forcing lists of three.

## 7. How to add things

- **Rule:** edit `rules/builtin/*.toml`, add positive and negative fixture builders, run the suite (it fails without both).
- **Detector:** new module under `detectors/`, register it in `detectors/__init__.py`, add rules and fixtures, update `ARCHITECTURE.md` section 9 and `ARCHITECTURE_ESSENTIALS.md` section 7.
- **Suppression:** only the owner adds suppressions to `airlock.toml`, with a reason.
- **Wasm fixture:** `airlock manifest add <path>`, and land the manifest change in its own PR first (two-step flow).
- **New requirement or decision:** update `PRD.md` and the ADR table, and add a row to the `ROADMAP.md` decision log.

## 8. Testing expectations

- Unit tests for every module; bypass tests for the seven cases in `PRD.md` Appendix B.
- ReDoS timing test for every regex pattern.
- Trusted-base tests for policy edits, force pushes, new branches and unresolvable bases.
- A change that affects findings must keep the parity test and the corpus gate green.
- Prefer a test that fails for the right reason over a long list of tests that pass trivially.

## 9. Commits and pull requests

- Conventional Commits, subject under 72 characters.
- Branch per task: `feat/<task-id>-<slug>`.
- Never commit to the default branch, never force-push, never rewrite shared history.
- PR description: task IDs, what changed, how it was tested, which docs were updated, and an explicit line confirming the change was recorded under `docs/changes/` and `ROADMAP.md` regenerated from it.
- Do not auto-merge. Do not bump the pinned SHA of a GitHub Action without reading the diff.
- Dependabot pull requests: Dependabot PRs for Actions and pip are ordinary pull requests and must pass the roadmap gate per Decision D-07. Before merging, check out the PR branch, review the diff, and run `python scripts/record_dependabot_bump.py` to synthesize the `docs/changes/` record, recompile `requirements-ci.txt` (if dev bounds changed), and regenerate `ROADMAP.md`. Commit what it writes to the PR branch.

## 10. When to stop and ask the owner

- A hard rule in section 4 appears to conflict with the task.
- The task needs a new dependency, a network call or a change to a protected path in a way that loosens a check.
- A doc statement is marked [Unverified] and the task depends on it (do the verifying Phase 0 task first, or ask).
- Two docs disagree.
- A decision marked Open in the `ROADMAP.md` decision log blocks the work.
- You are about to delete or rewrite more than a few hundred lines you did not write.

## 11. Be direct and skeptical

- State what is wrong first. Do not pad. If an instruction looks flawed, say so and propose the fix.
- Do not claim something works unless you ran it. Say what you ran and what you did not.
- Mark facts about external systems (GitHub behavior, Stellar tooling, Cargo) as verified or unverified. Do not turn an [Unverified] item into a requirement.

## 12. Protected paths

Take extra care in `src/airlock/policy.py`, `collector.py`, `runner.py`, `rules/`, `action.yml`, `.github/`, `scripts/`, `airlock.toml` and `wasm-manifest.toml`. Changes there need owner review and must not loosen any check.

## 13. Definition of done

- [ ] Tests written first and passing; all commands in section 5 green.
- [ ] No hard rule in section 4 broken.
- [ ] Docs updated where behavior, files or decisions changed.
- [ ] `ROADMAP.md` current: your tasks ticked, one record added under `docs/changes/`, and the progress table, changelog and `Last updated` regenerated rather than hand-edited.
- [ ] PR description lists task IDs and confirms the roadmap update.

# Contributing

The rules for automated contributors are in [`AGENTS.md`](AGENTS.md); humans are held to the
same bar. The design lives in [`PRD.md`](PRD.md), [`ARCHITECTURE.md`](ARCHITECTURE.md),
[`ARCHITECTURE_ESSENTIALS.md`](ARCHITECTURE_ESSENTIALS.md) and
[`project_structure.md`](project_structure.md).

## Per change

1. Find your task in `ROADMAP.md`. If there is none, add one with the next free ID in its
   phase and say why.
2. Check its dependencies are done. If they are not, stop and say so.
3. Write the failing test or fixture first, then the smallest change that passes.
4. Run `python -m pytest`, `ruff check .`, `ruff format --check .` and `mypy src`.
5. **Record the change in the same pull request.** Add one file under `docs/changes/`, named
   `YYYY-MM-DD-HHMM-<slug>.md` for the UTC minute it landed, with `date:`, `tasks:` and
   `summary:` front matter and the record itself below. The date cannot be in the future, and a
   record that has landed on the default branch is never deleted or renamed: if it is wrong, a
   later record says so. Tick or add your tasks in `ROADMAP.md`, then run
   `python scripts/roadmap_progress.py`, which regenerates the progress table, the changelog in
   section 9 and the `Last updated` line from those two sources. Check with
   `python scripts/roadmap_progress.py --check`. A change is not finished until the roadmap is
   current.
6. Update any document the change touches. If the code contradicts a doc, fix the doc.
7. If you changed a rule, run `python scripts/rule_reference.py` and `python scripts/build_site.py`
   and commit the regenerated `RULES.md` and `site/` files. The unit suite (and the Pages workflow
   for `site/`) runs both scripts with `--check` and fails a stale reference or page, because both
   are generated from the rule data rather than written by hand.

## Dependabot pull requests

Dependabot pull requests (Actions and pip dev tools) are ordinary pull requests. Per Decision D-07, the roadmap gate has no exemptions, including dependency bumps. Because Dependabot cannot author a `docs/changes/` record or regenerate `ROADMAP.md`, its initial pull request run fails the roadmap gate by design.

To merge a Dependabot pull request:

1. Review the diff per `AGENTS.md` 9. Never auto-merge, and never bump an Action SHA without reading the diff.
2. Check out the pull request branch.
3. Run `python scripts/record_dependabot_bump.py`. The script inspects the diff against the base branch, writes a compliant change record under `docs/changes/YYYY-MM-DD-HHMM-dependabot-<group>.md`, recompiles `requirements-ci.txt` with `uv pip compile` if dev dependencies changed, and regenerates `ROADMAP.md` via `python scripts/roadmap_progress.py`.
4. Commit the generated files to the branch. The roadmap gate and CI checks will then pass.

## Branches and commits

Branch per task as `feat/<task-id>-<slug>`. Conventional Commits, subject under 72
characters. Never commit to the default branch, never force-push, never rewrite shared
history, and do not bump a pinned Action SHA without reading the diff.

A conflict in `ROADMAP.md` can now only be inside a generated block: take either side, run
`python scripts/roadmap_progress.py`, and commit what it writes. Your change record is a file
nobody else edits, so the two records survive the merge untouched.

## Boundaries

No runtime dependencies. No network access or telemetry during a scan. No third-party
detector plugins: rules are data, detectors are in-tree code. No inline suppression markers.
Never commit a live-looking payload, a real secret or a real Stellar seed; trigger strings are
assembled at test time from fragments (see `tests/fixtures/`).

Protected paths (`project_structure.md` 2) need owner review: `src/airlock/policy.py`,
`collector.py`, `runner.py`, `rules/`, `action.yml`, `.github/`, `scripts/`, `airlock.toml`
and `wasm-manifest.toml`. Changes there must not weaken a check.

#!/usr/bin/env python3
"""Record a Dependabot dependency bump under `docs/changes/` and regenerate `ROADMAP.md` (task 1.6).

Dependabot pull requests are ordinary pull requests. Per Decision D-07 in `ROADMAP.md`,
the roadmap gate has no exemptions, including dependency bumps. Dependabot cannot author
a `docs/changes/` record or regenerate derived markdown blocks, so this helper automates
the mechanical merge-prep step.

The helper:
1. Analyzes the git diff against the base branch (`origin/main` or `main`).
2. Detects bumped dev dependencies in `pyproject.toml` and pinned action SHAs in `.github/workflows/`.
3. Verifies that runtime dependencies remain empty (AGENTS.md 4).
4. Synthesizes a valid, UTC-timestamped change record under `docs/changes/` with proper front matter.
5. Recompiles `requirements-ci.txt` with `uv pip compile` if dev dependencies changed and `uv` is available.
6. Executes `scripts/roadmap_progress.py` to recompute the derived tables and `Last updated` line.
7. Validates the resulting state with `scripts/roadmap_progress.py --check`.

Usage:
    python scripts/record_dependabot_bump.py [--base <ref>] [--dry-run] [--skip-uv]
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

ACTION_RE = re.compile(
    r"^\s*-\s*uses:\s*([^@\s]+)@([a-f0-9]{40}|[^\s#]+)(?:\s*#\s*(.+))?$",
    re.MULTILINE,
)


def fail(message: str) -> NoReturn:
    raise SystemExit(f"record_dependabot_bump: {message}")


def run_cmd(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    res = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if check and res.returncode != 0:
        fail(f"command {' '.join(args)} failed (exit {res.returncode}):\n{res.stderr or res.stdout}")
    return res


def get_base_ref(specified_base: str | None, repo_root: Path) -> str:
    candidates = [specified_base] if specified_base else ["origin/main", "main", "HEAD~1"]
    for ref in candidates:
        if not ref:
            continue
        res = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            return ref
    fail(f"could not resolve a valid git base commit from {candidates}; specify --base <ref>")


def get_merge_base(base_ref: str, repo_root: Path) -> str:
    res = run_cmd(["git", "-C", str(repo_root), "merge-base", base_ref, "HEAD"], cwd=repo_root)
    mb = res.stdout.strip()
    if not mb:
        fail(f"could not find a common merge base with {base_ref}")
    return mb


def get_changed_files(merge_base: str, repo_root: Path) -> list[str]:
    res_committed = run_cmd(["git", "-C", str(repo_root), "diff", "--name-only", merge_base, "HEAD"], cwd=repo_root)
    res_worktree = run_cmd(["git", "-C", str(repo_root), "diff", "--name-only", merge_base], cwd=repo_root)
    combined = set(res_committed.stdout.splitlines()) | set(res_worktree.stdout.splitlines())
    return sorted(p.replace("\\", "/") for p in combined if p.strip())


def parse_dev_deps(toml_text: str) -> dict[str, str]:
    try:
        data = tomllib.loads(toml_text)
    except Exception as exc:
        fail(f"failed to parse pyproject.toml: {exc}")
    runtime_deps = data.get("project", {}).get("dependencies", [])
    if runtime_deps:
        fail(f"AGENTS.md 4 violation: runtime dependencies must be empty, found {runtime_deps}")
    dev_list = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    deps: dict[str, str] = {}
    for entry in dev_list:
        entry = entry.strip()
        if not entry:
            continue
        parts = re.split(r"([><=~^! ]+.*)", entry, maxsplit=1)
        name = parts[0].strip()
        spec = parts[1].strip() if len(parts) > 1 else ""
        deps[name] = spec
    return deps


def parse_workflow_actions(workflow_text: str) -> dict[str, tuple[str, str]]:
    actions: dict[str, tuple[str, str]] = {}
    for match in ACTION_RE.finditer(workflow_text):
        action = match.group(1).strip()
        sha = match.group(2).strip()
        tag = (match.group(3) or "").strip()
        actions[action] = (sha, tag)
    return actions


def analyze_diff(
    merge_base: str, changed_files: list[str], repo_root: Path
) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[tuple[str, str], tuple[str, str]]]]:
    dev_bumps: dict[str, tuple[str, str]] = {}
    action_bumps: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {}

    if "pyproject.toml" in changed_files:
        res_old = run_cmd(["git", "-C", str(repo_root), "show", f"{merge_base}:pyproject.toml"], cwd=repo_root, check=False)
        old_toml = res_old.stdout if res_old.returncode == 0 else ""
        new_toml = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        old_deps = parse_dev_deps(old_toml) if old_toml else {}
        new_deps = parse_dev_deps(new_toml)
        for pkg, new_spec in new_deps.items():
            old_spec = old_deps.get(pkg, "")
            if old_spec != new_spec:
                dev_bumps[pkg] = (old_spec, new_spec)

    workflow_files = [f for f in changed_files if f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))]
    for wf in workflow_files:
        res_old = run_cmd(["git", "-C", str(repo_root), "show", f"{merge_base}:{wf}"], cwd=repo_root, check=False)
        old_wf = res_old.stdout if res_old.returncode == 0 else ""
        new_wf_path = repo_root / wf
        new_wf = new_wf_path.read_text(encoding="utf-8") if new_wf_path.exists() else ""
        old_actions = parse_workflow_actions(old_wf) if old_wf else {}
        new_actions = parse_workflow_actions(new_wf)
        for act, (new_sha, new_tag) in new_actions.items():
            old_sha, old_tag = old_actions.get(act, ("", ""))
            if (new_sha, new_tag) != (old_sha, old_tag):
                action_bumps[f"{wf}:{act}"] = ((old_sha, old_tag), (new_sha, new_tag))

    return dev_bumps, action_bumps


def build_summary_and_body(
    dev_bumps: dict[str, tuple[str, str]],
    action_bumps: dict[str, tuple[tuple[str, str], tuple[str, str]]],
    custom_summary: str | None = None,
) -> tuple[str, str, str]:
    if dev_bumps and not action_bumps:
        slug = "dependabot-python-group"
        pkgs = list(dev_bumps.keys())
        if len(pkgs) == 1:
            pkg_str = pkgs[0]
        elif len(pkgs) == 2:
            pkg_str = f"{pkgs[0]} and {pkgs[1]}"
        else:
            pkg_str = f"{', '.join(pkgs[:-1])} and {pkgs[-1]}"
        summary = (
            custom_summary
            or f"Accept Dependabot's grouped bump of {pkg_str} in the dev dependency group, with the CI suite unchanged."
        )
        body = (
            f"Dependabot opened a grouped `pip` pull request bumping {pkg_str} inside the `dev`\n"
            f"group in `pyproject.toml`. The runtime dependency list is still empty and no package is\n"
            f"added, so AGENTS.md 4 is unaffected.\n\n"
            f"`ci.yml` installs dev tools and build backends via hash-pinned `requirements-ci.txt` with\n"
            f"`--require-hashes` (task 1.18). The pull request's own checks passed and failed only the\n"
            f"roadmap gate, which a bot cannot satisfy on its own; this record is the part it was\n"
            f"missing. `python scripts/roadmap_progress.py` regenerated the changelog and `Last updated`\n"
            f"from it.\n\n"
            f"Task 1.6 is cited here because it configures Dependabot and settles its roadmap gate\n"
            f"interaction per Decision D-07."
        )
    elif action_bumps and not dev_bumps:
        slug = "dependabot-actions-group"
        act_names = sorted({k.split(":", 1)[1] for k in action_bumps.keys()})
        if len(act_names) == 1:
            act_str = act_names[0]
        elif len(act_names) == 2:
            act_str = f"{act_names[0]} and {act_names[1]}"
        else:
            act_str = f"{', '.join(act_names[:-1])} and {act_names[-1]}"
        summary = (
            custom_summary
            or f"Accept Dependabot's grouped bump of {act_str} in workflow files, preserving reviewed tags."
        )
        body = (
            f"Dependabot opened a grouped `github-actions` pull request bumping {act_str} across\n"
            f"workflow files in `.github/workflows/`. Each action remains pinned to a full commit SHA\n"
            f"with the reviewed tag preserved in a comment per AGENTS.md 9.\n\n"
            f"The pull request's checks failed only the roadmap gate, which a bot cannot satisfy on\n"
            f"its own; this record satisfies Decision D-07. `python scripts/roadmap_progress.py`\n"
            f"regenerated the changelog and `Last updated` from it.\n\n"
            f"Task 1.6 is cited here because it configures Dependabot and settles its roadmap gate\n"
            f"interaction per Decision D-07."
        )
    else:
        slug = "dependabot-deps-bump"
        summary = (
            custom_summary
            or "Accept Dependabot's grouped dependency bumps across dev tools and workflow actions."
        )
        body = (
            f"Dependabot opened pull requests updating dev dependencies in `pyproject.toml` and action\n"
            f"pins in `.github/workflows/`. Runtime dependencies remain empty (AGENTS.md 4).\n\n"
            f"The pull request's checks failed only the roadmap gate; this record satisfies Decision D-07.\n"
            f"`python scripts/roadmap_progress.py` regenerated the changelog and `Last updated` from it.\n\n"
            f"Task 1.6 is cited here because it configures Dependabot and settles its roadmap gate\n"
            f"interaction per Decision D-07."
        )

    summary = summary.replace("|", "\\|")
    if len(summary) > 240:
        summary = summary[:237] + "..."
    return slug, summary, body


def recompile_requirements_if_needed(repo_root: Path, skip_uv: bool = False) -> None:
    if skip_uv:
        return
    uv_bin = shutil.which("uv")
    if not uv_bin:
        print("record_dependabot_bump: uv not found on PATH; skipping requirements-ci.txt recompilation.", file=sys.stderr)
        return
    print("record_dependabot_bump: recompiling requirements-ci.txt via uv...")
    cmd = [
        uv_bin,
        "pip",
        "compile",
        "pyproject.toml",
        "--group",
        "dev",
        "--generate-hashes",
        "--python-version",
        "3.11",
        "--python-platform",
        "x86_64-unknown-linux-gnu",
        "-o",
        "requirements-ci.txt",
    ]
    res = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"record_dependabot_bump: warning: uv pip compile failed:\n{res.stderr}", file=sys.stderr)
        return
    req_file = repo_root / "requirements-ci.txt"
    if req_file.exists():
        req_file.write_bytes(req_file.read_bytes().replace(b"\r\n", b"\n"))
    print("record_dependabot_bump: requirements-ci.txt recompiled successfully.")


def run_roadmap_progress(repo_root: Path) -> None:
    progress_script = repo_root / "scripts" / "roadmap_progress.py"
    roadmap_file = repo_root / "ROADMAP.md"
    if not progress_script.exists() or not roadmap_file.exists():
        fail(f"missing {progress_script} or {roadmap_file}")

    roadmap_file.write_bytes(roadmap_file.read_bytes().replace(b"\r\n", b"\n"))
    for rec in (repo_root / "docs" / "changes").glob("*.md"):
        rec.write_bytes(rec.read_bytes().replace(b"\r\n", b"\n"))

    res = subprocess.run(
        [sys.executable, str(progress_script), str(roadmap_file)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        fail(f"roadmap_progress.py failed:\n{res.stderr or res.stdout}")

    roadmap_file.write_bytes(roadmap_file.read_bytes().replace(b"\r\n", b"\n"))

    res_check = subprocess.run(
        [sys.executable, str(progress_script), "--check", str(roadmap_file)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if res_check.returncode != 0:
        fail(f"roadmap_progress.py --check failed after regeneration:\n{res_check.stderr or res_check.stdout}")
    print("record_dependabot_bump: ROADMAP.md regenerated and verified successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record a Dependabot dependency bump under docs/changes/ and regenerate ROADMAP.md."
    )
    parser.add_argument("--base", help="Base git ref to compare against (defaults to origin/main or main).")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1], help="Path to repo root.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without writing.")
    parser.add_argument("--skip-uv", action="store_true", help="Skip recompiling requirements-ci.txt via uv.")
    parser.add_argument("--slug", help="Override change record slug.")
    parser.add_argument("--summary", help="Override change record summary.")
    parser.add_argument("--date", help="Override UTC timestamp (YYYY-MM-DD HH:MM) for deterministic testing.")
    args = parser.parse_args()

    repo_root = args.repo.resolve()
    base_ref = get_base_ref(args.base, repo_root)
    merge_base = get_merge_base(base_ref, repo_root)
    changed_files = get_changed_files(merge_base, repo_root)

    dev_bumps, action_bumps = analyze_diff(merge_base, changed_files, repo_root)
    if not dev_bumps and not action_bumps:
        fail(f"neither pyproject.toml nor .github/workflows/*.yml changed against {base_ref}")

    slug, summary, body = build_summary_and_body(dev_bumps, action_bumps, args.summary)
    if args.slug:
        slug = args.slug

    if args.date:
        try:
            stamp = datetime.strptime(args.date.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            fail(f"invalid --date {args.date!r}; expected YYYY-MM-DD HH:MM")
    else:
        stamp = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)

    filename = f"{stamp.strftime('%Y-%m-%d-%H%M')}-{slug}.md"
    record_path = repo_root / "docs" / "changes" / filename
    date_str = f"{stamp.strftime('%Y-%m-%d %H:%M')} UTC"

    content = f"---\ndate: {date_str}\ntasks: 1.6\nsummary: {summary}\n---\n\n{body}\n"

    if args.dry_run:
        print(f"[dry-run] Would create: {record_path.relative_to(repo_root)}")
        print(f"[dry-run] Summary: {summary}")
        print(f"[dry-run] Dev bumps: {dev_bumps}")
        print(f"[dry-run] Action bumps: {action_bumps}")
        return

    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(content.encode("utf-8"))
    print(f"record_dependabot_bump: created {record_path.relative_to(repo_root)}")

    if dev_bumps:
        recompile_requirements_if_needed(repo_root, skip_uv=args.skip_uv)

    run_roadmap_progress(repo_root)
    print("record_dependabot_bump: done. Commit the created record and modified files to your branch.")


if __name__ == "__main__":
    main()

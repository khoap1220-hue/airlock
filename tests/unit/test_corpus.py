"""Unit tests for the clean-state corpus (task 0.10, `ROADMAP.md`).

Verifies manifest integrity, byte-for-byte SHA-256 reproducibility, absence of secrets or live
tokens, and asserts that the baseline findings match `tests/golden/corpus_baseline.json`.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "tests" / "corpus" / "manifest.toml"
CORPUS_REPOS_DIR = REPO_ROOT / "tests" / "corpus" / "repos"
GOLDEN_BASELINE_PATH = REPO_ROOT / "tests" / "golden" / "corpus_baseline.json"

HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

# Secret inspection regexes (AGENTS.md 4, Issue #26 clean inspection protocol)
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----")
STELLAR_SEED_PATTERN = re.compile(r"\bS[A-Z2-7]{55}\b")
GITHUB_PAT_PATTERN = re.compile(r"\b(?:ghp_[A-Za-z0-9_]{36}|github_pat_[A-Za-z0-9_]{82})\b")


def load_manifest() -> dict[str, object]:
    assert MANIFEST_PATH.is_file(), f"Manifest file missing: {MANIFEST_PATH}"
    raw = MANIFEST_PATH.read_bytes()
    assert b"\r" not in raw, "manifest.toml must use LF line endings"
    return tomllib.loads(raw.decode("utf-8"))


class TestCorpusManifestIntegrity:
    def test_manifest_schema_and_repositories(self) -> None:
        data = load_manifest()
        assert data.get("version") == 1
        repos = data.get("repositories")
        assert isinstance(repos, dict)
        assert len(repos) == 6
        expected_slugs = {
            "soroban-budget-assert",
            "soroban-cost-linter",
            "accensa-app",
            "accensa-contracts",
            "x402-facilitator-stellar",
            "soroban-cost-profiler",
        }
        assert set(repos.keys()) == expected_slugs
        for slug, info in repos.items():
            assert isinstance(info, dict)
            assert "repo" in info
            assert HEX_40.match(info.get("commit", "")), f"Invalid commit SHA for {slug}: {info.get('commit')}"
            assert info.get("default_branch") == "main"

    def test_all_manifest_files_exist_and_match_hash(self) -> None:
        data = load_manifest()
        files = data.get("files")
        assert isinstance(files, list)
        assert len(files) >= 100, f"Expected at least 100 corpus files, got {len(files)}"

        seen_corpus_paths: set[Path] = set()
        for item in files:
            assert isinstance(item, dict)
            corpus_path_str = str(item["corpus_path"])
            file_path = REPO_ROOT / corpus_path_str
            assert file_path.is_file(), f"Declared corpus file missing on disk: {corpus_path_str}"
            seen_corpus_paths.add(file_path.resolve())

            raw = file_path.read_bytes()
            assert len(raw) == item["size_bytes"], (
                f"Size mismatch on {corpus_path_str}: actual {len(raw)} != expected {item['size_bytes']}"
            )
            actual_sha = hashlib.sha256(raw).hexdigest()
            assert actual_sha == item["sha256"], (
                f"Hash mismatch on {corpus_path_str}: actual {actual_sha} != expected {item['sha256']}"
            )

        # Assert no unmanifested files exist inside tests/corpus/repos
        if CORPUS_REPOS_DIR.is_dir():
            for disk_file in CORPUS_REPOS_DIR.rglob("*"):
                if disk_file.is_file():
                    assert disk_file.resolve() in seen_corpus_paths, (
                        f"Unmanifested file found in corpus directory: {disk_file.relative_to(REPO_ROOT)}"
                    )

    def test_manifest_omissions_are_documented(self) -> None:
        data = load_manifest()
        omissions = data.get("omissions")
        assert isinstance(omissions, list)
        assert len(omissions) >= 1
        for om in omissions:
            assert "repo" in om
            assert "source_path" in om
            assert "reason" in om
            assert len(om["reason"]) > 10


class TestCorpusCleanState:
    def test_corpus_contains_zero_secrets_or_live_tokens(self) -> None:
        """Scan all text files in the corpus to prove zero secrets reach the tree."""
        data = load_manifest()
        files = data.get("files", [])
        violations: list[str] = []

        for item in files:
            corpus_path_str = str(item["corpus_path"])
            file_path = REPO_ROOT / corpus_path_str
            raw = file_path.read_bytes()

            # Skip binary Wasm artifacts
            if corpus_path_str.endswith(".wasm") or raw.startswith(b"\x00asm"):
                continue

            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            if PRIVATE_KEY_PATTERN.search(text):
                violations.append(f"Private key pattern in {corpus_path_str}")
            if STELLAR_SEED_PATTERN.search(text):
                violations.append(f"Stellar seed pattern in {corpus_path_str}")
            if GITHUB_PAT_PATTERN.search(text):
                violations.append(f"GitHub token pattern in {corpus_path_str}")

        assert violations == [], f"Clean-state violation(s) detected:\n" + "\n".join(violations)


class TestCorpusBaselineReproducibility:
    def test_corpus_findings_match_golden_baseline(self) -> None:
        """Run scanner over corpus and assert byte-for-byte match with golden baseline."""
        assert GOLDEN_BASELINE_PATH.is_file(), f"Golden baseline missing: {GOLDEN_BASELINE_PATH}"
        raw_golden = GOLDEN_BASELINE_PATH.read_bytes()
        assert b"\r" not in raw_golden, "corpus_baseline.json must use LF line endings"
        golden_data = json.loads(raw_golden.decode("utf-8"))

        from airlock.cli import run_scan
        from airlock.model import Mode

        # Run scan over the repository and collect findings in tests/corpus/
        report = run_scan(REPO_ROOT, Mode.FULL)
        corpus_findings = [
            f for f in report.findings if f.path.startswith("tests/corpus/repos/")
        ]

        # Verify zero HIGH findings in corpus
        high_findings = [f for f in corpus_findings if f.severity.label == "high"]
        assert high_findings == [], f"Unexpected HIGH findings in corpus: {high_findings}"

        # Verify count and rule IDs match golden record
        assert len(corpus_findings) == golden_data.get("total_findings", len(golden_data.get("findings", [])))
        golden_findings = golden_data.get("findings", [])
        for actual, expected in zip(corpus_findings, golden_findings):
            assert actual.rule_id == expected["rule_id"]
            assert actual.path == expected["path"]
            assert actual.line == expected["line"]
            assert actual.severity.label == expected["severity"]

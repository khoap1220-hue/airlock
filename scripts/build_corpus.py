#!/usr/bin/env python3
"""Build and verify the clean-state corpus from dogfood repositories (task 0.10).

Reads `tests/corpus/manifest.toml`, verifies existing files against their pinned commit SHA
and SHA-256 digest, and optionally fetches missing files from GitHub without third-party dependencies.

Standard library only: Python 3.11 `tomllib`, `urllib.request`, `hashlib`, `pathlib`, `argparse`.
Never imports third-party packages.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_MANIFEST = Path("tests/corpus/manifest.toml")
DEFAULT_BASE_DIR = Path(".")


def compute_sha256(data: bytes) -> str:
    """Compute hex SHA-256 digest."""
    return hashlib.sha256(data).hexdigest()


def load_manifest(manifest_path: Path) -> dict[str, object]:
    """Parse and validate manifest.toml."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    raw = manifest_path.read_bytes()
    if b"\r" in raw:
        raise ValueError(f"Manifest {manifest_path} contains CRLF line endings; LF required.")
    data = tomllib.loads(raw.decode("utf-8"))
    if data.get("version") != 1:
        raise ValueError(f"Unsupported manifest version: {data.get('version')}")
    if "files" not in data or not isinstance(data["files"], list):
        raise ValueError("Manifest must contain a [[files]] list")
    return data


def verify_corpus(manifest_data: dict[str, object], base_dir: Path) -> tuple[int, list[str]]:
    """Verify all files declared in manifest exist and match their SHA-256 and size."""
    errors: list[str] = []
    files: list[dict[str, object]] = manifest_data["files"]  # type: ignore[assignment]
    seen_paths: set[Path] = set()

    for entry in files:
        rel_str = str(entry["corpus_path"])
        full_path = (base_dir / rel_str).resolve()
        seen_paths.add(full_path)

        if not full_path.is_file():
            errors.append(f"MISSING: {rel_str} (expected {entry['size_bytes']} bytes, sha256 {entry['sha256'][:12]})")
            continue

        raw = full_path.read_bytes()
        actual_size = len(raw)
        expected_size = entry["size_bytes"]
        if actual_size != expected_size:
            errors.append(f"SIZE_MISMATCH: {rel_str} (actual {actual_size} != expected {expected_size})")

        actual_hash = compute_sha256(raw)
        expected_hash = entry["sha256"]
        if actual_hash != expected_hash:
            errors.append(f"HASH_MISMATCH: {rel_str} (actual {actual_hash[:12]} != expected {expected_hash[:12]})")

    # Check for unmanifested stray files inside tests/corpus/repos
    repos_dir = (base_dir / "tests/corpus/repos").resolve()
    if repos_dir.is_dir():
        for path in repos_dir.rglob("*"):
            if path.is_file():
                if path.resolve() not in seen_paths:
                    errors.append(f"UNMANIFESTED_FILE: {path.relative_to(base_dir)}")

    return len(errors), errors


def fetch_file(repo: str, commit: str, source_path: str) -> bytes:
    """Download single blob from raw.githubusercontent.com using Python stdlib."""
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{source_path}"
    req = urllib.request.Request(url, headers={"User-Agent": "airlock-build-corpus/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                raise urllib.error.HTTPError(url, resp.status, f"HTTP {resp.status}", resp.headers, None)
            return resp.read()
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Failed to fetch {url}: {exc}") from exc


def build_corpus(manifest_data: dict[str, object], base_dir: Path, force: bool = False) -> tuple[int, int]:
    """Fetch missing or mismatched files declared in the manifest."""
    fetched = 0
    skipped = 0
    files: list[dict[str, object]] = manifest_data["files"]  # type: ignore[assignment]
    repos: dict[str, dict[str, str]] = manifest_data.get("repositories", {})  # type: ignore[assignment]

    for entry in files:
        rel_str = str(entry["corpus_path"])
        dest_path = base_dir / rel_str
        expected_hash = str(entry["sha256"])

        if dest_path.is_file() and not force:
            raw = dest_path.read_bytes()
            if compute_sha256(raw) == expected_hash:
                skipped += 1
                continue

        repo_slug = str(entry["repo"])
        repo_info = repos.get(repo_slug, {})
        full_repo = repo_info.get("repo", repo_slug)
        commit = str(entry["commit"])
        source_path = str(entry["source_path"])

        sys.stdout.write(f"Fetching {repo_slug}:{source_path} ... ")
        sys.stdout.flush()
        data = fetch_file(full_repo, commit, source_path)
        actual_hash = compute_sha256(data)
        if actual_hash != expected_hash:
            raise ValueError(f"Downloaded content hash mismatch for {rel_str}: {actual_hash} != {expected_hash}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(data)
        sys.stdout.write("OK\n")
        sys.stdout.flush()
        fetched += 1

    return fetched, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify the Airlock clean-state corpus.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to manifest.toml")
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR, help="Base directory of repository")
    parser.add_argument("--verify", action="store_true", help="Verify integrity of existing snapshot")
    parser.add_argument("--force", action="store_true", help="Force re-downloading even if file exists")
    args = parser.parse_args(argv)

    try:
        manifest_data = load_manifest(args.manifest)
    except Exception as exc:
        sys.stderr.write(f"Error loading manifest: {exc}\n")
        return 2

    if args.verify:
        err_count, errors = verify_corpus(manifest_data, args.base_dir)
        if err_count == 0:
            total = len(manifest_data.get("files", []))
            print(f"VERIFIED: All {total} corpus files match manifest byte-for-byte.")
            return 0
        else:
            sys.stderr.write(f"FAILED: {err_count} integrity violation(s) found:\n")
            for err in errors:
                sys.stderr.write(f"  - {err}\n")
            return 1

    try:
        fetched, skipped = build_corpus(manifest_data, args.base_dir, force=args.force)
        print(f"Build complete: {fetched} fetched, {skipped} up to date.")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Build error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

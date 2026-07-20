#!/usr/bin/env python3
"""Validate an incoming Retro release and maintain its public version index."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


VERSION_RE = re.compile(r"^[1-9][0-9]*(?:\.[0-9]+){1,2}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_summary(manifest: dict) -> dict:
    return {
        "version": manifest["version"],
        "tag": manifest["tag"],
        "publishedAt": manifest["publishedAt"],
        "title": manifest["title"],
        "summary": manifest["summary"],
        "notes": manifest["notes"],
        "source": manifest["source"],
        "assets": manifest["assets"],
        "releaseUrl": manifest["releaseUrl"],
    }


def validate(payload: Path) -> dict:
    manifest_path = payload / "release.json"
    notes_path = payload / "release-notes.md"
    artifacts = payload / "artifacts"
    manifest = read_json(manifest_path)

    version = str(manifest.get("version", ""))
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"invalid release version: {version!r}")
    if manifest.get("tag") != f"v{version}":
        raise ValueError("release tag must be v<version>")
    if manifest.get("releaseUrl") != (
        "https://github.com/iconidentify/chonkblocker-retro-downloads/releases/tag/"
        f"v{version}"
    ):
        raise ValueError("releaseUrl does not match the public release tag")

    notes = manifest.get("notes")
    if not isinstance(notes, list) or not notes or not all(
        isinstance(note, str) and note.strip() for note in notes
    ):
        raise ValueError("notes must be a non-empty string array")
    if not notes_path.is_file() or not notes_path.read_text(encoding="utf-8").strip():
        raise ValueError("release-notes.md is missing or empty")

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    for key in ("gameCommit", "appCommit"):
        if not COMMIT_RE.fullmatch(str(source.get(key, ""))):
            raise ValueError(f"source.{key} must be a full Git commit")
    if not SHA_RE.fullmatch(str(source.get("romSha256", ""))):
        raise ValueError("source.romSha256 must be SHA-256")

    asset_rows = manifest.get("assets")
    if not isinstance(asset_rows, list) or len(asset_rows) != 4:
        raise ValueError("exactly four downloadable assets are required")
    kinds = set()
    filenames = set()
    for row in asset_rows:
        if not isinstance(row, dict):
            raise ValueError("every asset must be an object")
        kind = str(row.get("kind", ""))
        filename = str(row.get("filename", ""))
        checksum_filename = str(row.get("checksumFilename", ""))
        expected = str(row.get("sha256", ""))
        if kind in kinds or filename in filenames:
            raise ValueError(f"duplicate asset: {kind or filename}")
        kinds.add(kind)
        filenames.add(filename)
        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise ValueError(f"unsafe asset filename: {filename!r}")
        if not SHA_RE.fullmatch(expected):
            raise ValueError(f"invalid SHA-256 for {filename}")
        asset_path = artifacts / filename
        checksum_path = artifacts / checksum_filename
        if not asset_path.is_file() or not checksum_path.is_file():
            raise ValueError(f"missing asset or checksum for {filename}")
        actual = sha256(asset_path)
        if actual != expected:
            raise ValueError(f"SHA-256 mismatch for {filename}: {actual}")
        checksum_text = checksum_path.read_text(encoding="utf-8").replace("\r", "").strip()
        checksum_parts = checksum_text.split()
        if len(checksum_parts) < 2 or checksum_parts[0] != expected or checksum_parts[-1] != filename:
            raise ValueError(f"invalid checksum manifest for {filename}")

    if kinds != {"rom", "macos", "windows", "linux"}:
        raise ValueError(f"unexpected asset kinds: {sorted(kinds)}")
    rom = next(row for row in asset_rows if row["kind"] == "rom")
    if rom["sha256"] != source["romSha256"]:
        raise ValueError("ROM asset does not match source.romSha256")
    if (artifacts / rom["filename"]).stat().st_size != 262_144:
        raise ValueError("standalone SNES ROM must be exactly 256 KiB")

    print(f"validated Chonk Blocker Retro {version} ({len(asset_rows)} assets)")
    return manifest


def write_index(payload: Path, repository: Path) -> None:
    manifest = validate(payload)
    version = manifest["version"]
    rom = next(row for row in manifest["assets"] if row["kind"] == "rom")
    release_dir = repository / "releases"
    release_dir.mkdir(parents=True, exist_ok=True)
    summary = release_summary(manifest)
    encoded = json.dumps(summary, indent=2, sort_keys=False) + "\n"
    (release_dir / f"v{version}.json").write_text(encoded, encoding="utf-8")
    (repository / "latest.json").write_text(encoded, encoding="utf-8")

    index_path = repository / "releases.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {"current": version, "releases": []}
    releases = [row for row in index.get("releases", []) if row.get("version") != version]
    releases.append(summary)
    releases.sort(
        key=lambda row: tuple(int(part) for part in row["version"].split(".")),
        reverse=True,
    )
    index = {"current": version, "releases": releases}
    index_path.write_text(
        json.dumps(index, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    public_notes = release_dir / f"v{version}.md"
    shutil.copyfile(payload / "release-notes.md", public_notes)
    browser_dir = repository / "browser"
    browser_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        payload / "artifacts" / rom["filename"],
        browser_dir / "Chonk-Blocker-Retro.sfc",
    )
    print(f"updated public index for Chonk Blocker Retro {version}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("payload", type=Path)
    index_parser = subparsers.add_parser("update-index")
    index_parser.add_argument("payload", type=Path)
    index_parser.add_argument("repository", type=Path)
    args = parser.parse_args()

    if args.command == "validate":
        validate(args.payload)
    else:
        write_index(args.payload, args.repository)


if __name__ == "__main__":
    main()

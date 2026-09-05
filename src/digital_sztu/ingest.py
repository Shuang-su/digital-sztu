from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import guess_mime, iter_regular_files, load_json, sha256_file, write_json


RISKY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".msi",
    ".apk",
    ".dmg",
    ".docm",
    ".xlsm",
    ".pptm",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".pfx",
    ".env",
}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz"}


def _risk_flags(path: Path, mime: str) -> list[str]:
    flags: list[str] = []
    suffix = path.suffix.lower()
    if suffix in RISKY_EXTENSIONS:
        flags.append("do-not-execute-or-publish")
    if suffix in ARCHIVE_EXTENSIONS:
        flags.append("nested-archive-review")
    if mime == "application/vnd.sqlite3":
        flags.append("database-private-review")
    lowered = path.name.lower()
    if any(word in lowered for word in ("password", "token", "cookie", "secret", "身份证", "学号")):
        flags.append("sensitive-filename")
    return sorted(set(flags))


def create_manifest(source: Path, output_dir: Path) -> tuple[Path, dict[str, Any]]:
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    entries: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    warnings: list[str] = [
        "This manifest contains a private local source path and must not be committed.",
        "Inventory does not execute, decrypt, normalize, publish, or copy source files.",
    ]
    base = source.parent if source.is_file() else source

    for path in iter_regular_files(source):
        relative = path.name if source.is_file() else path.relative_to(base).as_posix()
        digest = sha256_file(path)
        size = path.stat().st_size
        mime = guess_mime(path)
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(bytes.fromhex(digest))
        aggregate.update(str(size).encode("ascii"))
        entries.append(
            {
                "path": relative,
                "size_bytes": size,
                "sha256": digest,
                "mime_guess": mime,
                "risk_flags": _risk_flags(path, mime),
            }
        )

    if source.is_dir() and any(path.is_symlink() for path in source.rglob("*")):
        warnings.append("Symbolic links were skipped and not followed.")

    aggregate_hex = aggregate.hexdigest()
    submission_id = f"submission-{aggregate_hex[:16]}"
    destination = output_dir / submission_id / "manifest.json"
    if destination.is_file():
        existing = load_json(destination)
        if existing.get("aggregate_sha256") == aggregate_hex:
            return destination, existing

    created = datetime.now(timezone.utc).replace(microsecond=0)
    manifest = {
        "schema_version": "0.1.0",
        "submission_id": submission_id,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "source_path_private": str(source),
        "mode": "dry-run",
        "aggregate_sha256": aggregate_hex,
        "files": entries,
        "warnings": warnings,
    }
    write_json(destination, manifest)
    return destination, manifest

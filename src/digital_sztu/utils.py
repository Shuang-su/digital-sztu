from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable


WIKILINK_RE = re.compile(r"\[\[([a-z][a-z0-9-]*)(?:\|[^\]\n]+)?\]\]")


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "connect.config.json").is_file():
            return candidate
    raise FileNotFoundError("connect.config.json not found; run inside the Digital SZTU repository")


def load_json(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate JSON key {key!r}: {path}")
            value[key] = item
        return value

    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=reject_duplicate_keys)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, value: str) -> None:
    atomic_write_bytes(path, value.encode("utf-8"))


def write_json(path: Path, value: Any, *, sort_keys: bool = False) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n"
    atomic_write_text(path, text)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def iter_regular_files(path: Path) -> Iterable[Path]:
    if path.is_file() and not path.is_symlink():
        yield path
        return
    for child in sorted(path.rglob("*")):
        if child.is_file() and not child.is_symlink():
            yield child


def guess_mime(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            prefix = handle.read(32)
    except OSError:
        prefix = b""
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith(b"PK\x03\x04"):
        return "application/zip"
    if prefix.startswith(b"SQLite format 3\x00"):
        return "application/vnd.sqlite3"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def ensure_within(path: Path, parent: Path) -> Path:
    resolved = path.expanduser().resolve()
    boundary = parent.expanduser().resolve()
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise ValueError(f"Path must stay inside {boundary}") from exc
    return resolved


def extract_wikilinks(text: str) -> list[str]:
    return sorted(set(WIKILINK_RE.findall(unicodedata.normalize("NFC", text))))

"""A single, conservative public projection for every generated reading surface."""
from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit
import ipaddress

from .privacy import CREDENTIAL_PATTERNS
from .utils import canonical_json, sha256_bytes

SECRET_QUERY = re.compile(
    r"^(?:access[_-]?token|refresh[_-]?token|token|password|passwd|pwd|secret|api[_-]?key|"
    r"cookie|signature|credential|authorization|auth|session(?:id)?|jsessionid|ticket|sso[_-]?ticket)$", re.I
)


def public_url(value: str | None) -> bool:
    if not value:
        return True
    try:
        p = urlsplit(value)
        if p.hostname and (p.hostname.lower() == 'localhost' or p.hostname.lower().endswith(('.localhost', '.local'))):
            return False
        try:
            if p.hostname and not ipaddress.ip_address(p.hostname).is_global:
                return False
        except ValueError:
            pass
        return bool(p.scheme in {"http", "https"} and p.hostname and not p.username and not p.password
                    and not any(SECRET_QUERY.match(k) for k, _ in parse_qsl(p.query)))
    except ValueError:
        return False


def sensitive_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in CREDENTIAL_PATTERNS.values()) or any(
        not public_url(value.rstrip(".,;"))
        for value in re.findall(r'https?://[^\s<>"\)\]]+', text)
    )


def public_file(root: Path, path: Path, directory: Path | None = None) -> bool:
    return (path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to((directory or root).resolve())
            and not any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(root)))


def public_projection(root: Path, records: dict) -> dict:
    """Exclude whole evidence-bearing records if evidence cannot be made public.

    Never silently remove a contradicting citation to make a claim publishable.
    Navigation references can be pruned, but record prose mentioning an excluded
    stable identifier is also excluded rather than leaking the hidden label.
    """
    copied = copy.deepcopy(records)
    accepted: dict[str, tuple[str, Path, dict]] = {}
    rejected: set[str] = set()
    prose: dict[str, str] = {}
    for kind, items in copied.items():
        for path, record in items:
            rid = record["id"]
            privacy = record.get("privacy", {})
            text = json.dumps(record, ensure_ascii=False)
            safe_files = public_file(root, path)
            if record.get("narrative"):
                narrative = path.parent / record["narrative"]
                safe_files = safe_files and public_file(root, narrative, path.parent)
                if safe_files:
                    text += narrative.read_text(encoding="utf-8")
            prose[rid] = text
            if (not safe_files
                    or privacy.get("indexing") == "exclude" or privacy.get("risk") == "prohibited"
                    or privacy.get("handling") == "restricted" or record.get("status") == "draft"
                    or sensitive_text(text)):
                rejected.add(rid)
            else:
                accepted[rid] = (kind, path, record)

    changed = True
    while changed:
        changed = False
        for rid, (kind, _, record) in list(accepted.items()):
            dependencies = set(record.get("source_ids", []))
            if record.get("superseded_by"):
                dependencies.add(record["superseded_by"])
            for claim in record.get("claims", []):
                dependencies.update(c["source_id"] for c in claim["citations"])
            for link in record.get("links", []):
                dependencies.add(link["target_id"])
                dependencies.update(link["source_ids"])
            # Collection membership is navigation; keep public members only.
            text = prose[rid] if kind != "collection" else record.get("summary", "")
            hidden_reference = any(f"[[{item}" in text for item in rejected)
            if dependencies & rejected or hidden_reference:
                rejected.add(rid)
                accepted.pop(rid)
                changed = True
    public_ids = set(accepted)
    result = defaultdict(list)
    for rid in sorted(accepted):
        kind, path, record = accepted[rid]
        if kind == "collection":
            for key in ("event_ids", "knowledge_ids", "focus_ids", "related_collection_ids"):
                if key in record:
                    record[key] = [item for item in record[key] if item in public_ids]
            # Narrative links must not expose excluded targets, including labels.
            if record.get("narrative") and any(f"[[{item}" in prose[rid] for item in rejected):
                record["narrative"] = None
        result[kind].append((path, record))
    return result


def dataset_revision(root: Path, records: dict) -> str:
    rows = []
    for kind in sorted(records):
        for path, record in records[kind]:
            item: dict[str, Any] = {"kind": kind, "record": record}
            if record.get("narrative"):
                item["markdown"] = (path.parent / record["narrative"]).read_text(encoding="utf-8")
            rows.append(item)
    return "sha256:" + sha256_bytes(canonical_json(rows))


def check_public_records(root: Path) -> dict:
    """A release check for canonical files in a public repository.

    Local validation and a filtered view alone cannot protect a Git publication
    that also contains the canonical files. Report paths and reasons only.
    """
    from .validation import collect_repository
    errors = []
    for entries in collect_repository(root).values():
        for path, record in entries:
            privacy = record.get('privacy', {})
            text = json.dumps(record, ensure_ascii=False)
            safe_files = public_file(root, path)
            if record.get('narrative'):
                narrative = path.parent / record['narrative']
                safe_files = safe_files and public_file(root, narrative, path.parent)
                if safe_files:
                    text += narrative.read_text(encoding='utf-8')
            if not safe_files or sensitive_text(text) or privacy.get('risk') == 'prohibited' or privacy.get('handling') == 'restricted':
                errors.append({'path': path.relative_to(root).as_posix(), 'reason': 'canonical record is not eligible for public Git publication'})
    return {'ok': not errors, 'errors': errors}

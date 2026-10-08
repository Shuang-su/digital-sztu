from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .public import dataset_revision
from .utils import canonical_json, load_json, sha256_bytes, sha256_file, write_json, atomic_write_bytes


def _privacy(value: dict[str, Any]) -> dict[str, str]:
    return {
        "risk": value["risk"],
        "handling": value["handling"],
        "indexing": value["indexing"],
    }


def _links_for(
    owner_id: str,
    backlinks: dict[str, dict[str, list[dict[str, Any]]]],
    *,
    claim_id: str | None = None,
) -> list[dict[str, Any]]:
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    item = backlinks.get(owner_id, {"outgoing": [], "incoming": []})
    for direction in ("outgoing", "incoming"):
        for edge in item[direction]:
            if claim_id is not None and (
                direction != "outgoing" or claim_id not in edge.get("claim_ids", [])
            ):
                continue
            other_id = edge["to"] if direction == "outgoing" else edge["from"]
            claim_ids = sorted(set(edge.get("claim_ids", [])))
            source_ids = sorted(set(edge.get("source_ids", [])))
            locator = edge.get("locator")
            key = (
                direction,
                edge["relation"],
                other_id,
                tuple(claim_ids),
                tuple(source_ids),
                locator is None,
                locator or "",
            )
            result[key] = {
                "direction": direction,
                "relation": edge["relation"],
                "other_id": other_id,
                "claim_ids": claim_ids,
                "source_ids": source_ids,
                "locator": locator,
            }
    return [result[key] for key in sorted(result)]


def _event_citations(event: dict[str, Any]) -> list[dict[str, Any]]:
    citations: dict[tuple[Any, ...], dict[str, Any]] = {}
    for claim in event["claims"]:
        for citation in claim["citations"]:
            key = (
                citation["source_id"],
                citation["role"],
                citation.get("locator") is None,
                citation.get("locator") or "",
                citation.get("note") is None,
                citation.get("note") or "",
            )
            citations[key] = citation
    return [citations[key] for key in sorted(citations)]


def _finish_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    revision_payload = {
        key: value
        for key, value in chunk.items()
        if key not in {"revision_id", "provenance"}
    }
    revision_payload["record_sha256"] = chunk["provenance"]["record_sha256"]
    chunk["revision_id"] = f"sha256:{sha256_bytes(canonical_json(revision_payload))}"
    return chunk


def _base_chunk(
    *,
    root: Path,
    path: Path,
    owner_id: str,
    owner_type: str,
    chunk_kind: str,
    locator: str,
    title: str,
    text: str,
    time: dict[str, Any] | None,
    history_forms: list[str],
    claim_ids: list[str],
    citations: list[dict[str, Any]],
    links: list[dict[str, Any]],
    privacy: dict[str, Any],
    record_status: str | None,
    claim_verification: dict[str, str] | None,
    source_metadata: dict[str, Any] | None,
    evidence_role: str,
) -> dict[str, Any]:
    logical = locator.replace("/", ":")
    namespace = "digital-sztu" if owner_type == "knowledge" else "sztu-connect"
    chunk = {
        "schema_version": "0.2.0",
        "chunk_id": f"urn:{namespace}:chunk:{owner_id}:{logical}",
        "revision_id": "sha256:" + ("0" * 64),
        "owner_id": owner_id,
        "owner_type": owner_type,
        "chunk_kind": chunk_kind,
        "evidence_role": evidence_role,
        "locator": locator,
        "title": title,
        "text": text,
        "language": "zh-CN",
        "time": time,
        "history_forms": sorted(set(history_forms)),
        "claim_ids": sorted(set(claim_ids)),
        "citations": citations,
        "links": links,
        "verification": {
            "record_status": record_status,
            "claim": claim_verification,
        },
        "source_metadata": source_metadata,
        "privacy": _privacy(privacy),
        "provenance": {
            "record_path": path.relative_to(root).as_posix(),
            "record_sha256": f"sha256:{sha256_file(path)}",
            "exporter": "digital-sztu",
            "exporter_version": "0.2.0",
            "chunking_profile": "structured-fields-v1",
        },
    }
    return _finish_chunk(chunk)


def build_knowledge_chunks(
    root: Path,
    records: dict[str, list[tuple[Path, dict[str, Any]]]],
    backlinks: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    forms_by_event: dict[str, set[str]] = {}
    for _, collection in records["collection"]:
        for event_id in collection.get("event_ids", []) + collection.get("knowledge_ids", []):
            forms_by_event.setdefault(event_id, set()).add(collection["form"])

    chunks: list[dict[str, Any]] = []

    for path, event in records["event"] + records["knowledge"]:
        privacy = event["privacy"]
        common = {
            "root": root,
            "path": path,
            "owner_id": event["id"],
            "owner_type": event["type"],
            "title": event["title"],
            "time": event.get("time", event.get("validity")),
            "history_forms": sorted(forms_by_event.get(event["id"], set())),
            "privacy": privacy,
            "record_status": event["status"],
            "source_metadata": None,
        }
        chunks.append(
            _base_chunk(
                **common,
                chunk_kind="summary",
                locator="summary",
                text=event["summary"],
                claim_ids=[claim["id"] for claim in event["claims"]],
                citations=_event_citations(event),
                links=_links_for(event["id"], backlinks),
                claim_verification=None,
                evidence_role="navigation",
            )
        )
        for claim in event["claims"]:
            chunks.append(
                _base_chunk(
                    **common,
                    chunk_kind="claim",
                    locator=f"claim:{claim['id']}",
                    text=claim["text"],
                    claim_ids=[claim["id"]],
                    citations=claim["citations"],
                    links=_links_for(event["id"], backlinks, claim_id=claim["id"]),
                    claim_verification={
                        "kind": claim["kind"],
                        "certainty": claim["certainty"],
                    },
                    evidence_role="claim-evidence",
                )
            )

    for path, node in records["node"]:
        privacy = node["privacy"]
        text = node["name"]
        if node.get("aliases"):
            text += "\n别名：" + "、".join(node["aliases"])
        if node.get("summary"):
            text += "\n" + node["summary"]
        chunks.append(
            _base_chunk(
                root=root,
                path=path,
                owner_id=node["id"],
                owner_type="node",
                chunk_kind="node-metadata",
                locator="metadata",
                title=node["name"],
                text=text,
                time=None,
                history_forms=[],
                claim_ids=[],
                citations=[
                    {"source_id": source_id, "role": "context", "locator": None, "note": None}
                    for source_id in node["source_ids"]
                ],
                links=_links_for(node["id"], backlinks),
                privacy=privacy,
                record_status=node["status"],
                claim_verification=None,
                source_metadata=None,
                evidence_role="directory-metadata",
            )
        )

    for path, collection in records["collection"]:
        privacy = collection["privacy"]
        chunks.append(
            _base_chunk(
                root=root,
                path=path,
                owner_id=collection["id"],
                owner_type="collection",
                chunk_kind="summary",
                locator="summary",
                title=collection["title"],
                text=collection["summary"],
                time=None,
                history_forms=[collection["form"]],
                claim_ids=[],
                citations=[],
                links=_links_for(collection["id"], backlinks),
                privacy=privacy,
                record_status=None,
                claim_verification=None,
                source_metadata=None,
                evidence_role="navigation",
            )
        )

    for path, source in records["source"]:
        privacy = source["privacy"]
        parts = [source["title"]]
        if source.get("creator"):
            parts.append(f"创作者：{source['creator']}")
        if source.get("publisher"):
            parts.append(f"发布者：{source['publisher']}")
        if source.get("notes"):
            parts.append(source["notes"])
        chunks.append(
            _base_chunk(
                root=root,
                path=path,
                owner_id=source["id"],
                owner_type="source",
                chunk_kind="source-metadata",
                locator="metadata",
                title=source["title"],
                text="\n".join(parts),
                time=None,
                history_forms=[],
                claim_ids=[],
                citations=[],
                links=_links_for(source["id"], backlinks),
                privacy=privacy,
                record_status=None,
                claim_verification=None,
                source_metadata={
                    "source_kind": source["source_kind"],
                    "creator": source.get("creator"),
                    "publisher": source.get("publisher"),
                    "locator": source["locator"],
                    "dates": source["dates"],
                    "hashes": source["hashes"],
                    "access": source["access"],
                    "rights": source["rights"],
                    "reliability": source["reliability"],
                },
                evidence_role="source-metadata",
            )
        )

    return sorted(chunks, key=lambda item: item["chunk_id"])


def write_knowledge_export(
    root: Path,
    output: Path,
    records: dict[str, list[tuple[Path, dict[str, Any]]]],
    backlinks: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    chunks = build_knowledge_chunks(root, records, backlinks)
    errors: list[str] = []

    lines = [json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in chunks]
    payload = (("\n".join(lines) + "\n") if lines else "").encode("utf-8")
    digest = sha256_bytes(payload)
    manifest = {
        "schema_version": "0.2.0",
        "format": "digital-sztu-knowledge-jsonl@0.2",
        "chunking_profile": "structured-fields-v1",
        "chunks_path": "chunks.jsonl",
        "chunk_count": len(chunks),
        "chunks_sha256": f"sha256:{digest}",
        "dataset_revision": dataset_revision(root, records),
        "embedding": None,
    }
    manifest_validator = Draft202012Validator(
        load_json(root / "schemas" / "knowledge-manifest.schema.json")
    )
    for failure in manifest_validator.iter_errors(manifest):
        errors.append(f"manifest:{'.'.join(str(part) for part in failure.path) or '$'}: {failure.message}")
    if errors:
        return {"ok": False, "errors": errors, "chunks": len(chunks)}

    atomic_write_bytes(output / "chunks.jsonl", payload)
    write_json(output / "manifest.json", manifest, sort_keys=True)
    return {
        "ok": True,
        "chunks": len(chunks),
        "chunks_sha256": manifest["chunks_sha256"],
        "dataset_revision": manifest["dataset_revision"],
        "output": output.relative_to(root).as_posix(),
    }

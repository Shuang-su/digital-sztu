from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from calendar import monthrange
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .utils import extract_wikilinks, load_json, sha256_file


SCHEMA_FILES = {
    "knowledge": "knowledge.schema.json",
    "event": "event.schema.json",
    "node": "node.schema.json",
    "collection": "collection.schema.json",
    "source": "source.schema.json",
}

RECORD_PATTERNS = {
    "knowledge": "content/knowledge/**/record.json",
    "event": "content/events/**/event.json",
    "node": "content/nodes/**/*.json",
    "collection": "content/collections/**/collection.json",
    "source": "sources/records/*.json",
}

NODE_DIRECTORIES = {
    "person": "people",
    "organization": "organizations",
    "place": "places",
    "institution": "institutions",
    "topic": "topics",
}

PRECISION_LENGTH = {"year": 4, "month": 7, "day": 10}


def collect_repository(root: Path) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    result: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for kind, pattern in RECORD_PATTERNS.items():
        for path in sorted(root.glob(pattern)):
            result[kind].append((path, load_json(path)))
    return result


def _partial_date(value: str) -> date:
    if len(value) == 4:
        return date(int(value), 1, 1)
    if len(value) == 7:
        return datetime.strptime(value, "%Y-%m").date()
    if len(value) == 10:
        return datetime.strptime(value, "%Y-%m-%d").date()
    raise ValueError("expected YYYY, YYYY-MM, or YYYY-MM-DD")


def _validate_time(rel: Path, value: dict[str, Any], errors: list[str]) -> None:
    precision = value.get("precision")
    endpoints = [item for item in (value.get("start"), value.get("end")) if isinstance(item, str)]
    for endpoint in endpoints:
        try:
            _partial_date(endpoint)
        except ValueError as exc:
            errors.append(f"{rel}: invalid calendar date {endpoint!r}: {exc}")
        if precision in PRECISION_LENGTH and len(endpoint) != PRECISION_LENGTH[precision]:
            errors.append(f"{rel}: time precision {precision} does not match {endpoint!r}")
    start = value.get("start")
    end = value.get("end")
    if isinstance(start, str) and isinstance(end, str):
        try:
            if _partial_date(start) > _partial_date(end):
                errors.append(f"{rel}: time start is after end")
        except ValueError:
            pass


def _narrative_links(
    root: Path,
    path: Path,
    record: dict[str, Any],
    all_ids: set[str],
    errors: list[str],
) -> None:
    narrative = record.get("narrative")
    if not isinstance(narrative, str):
        return
    root_resolved = root.resolve()
    candidate = (path.parent / narrative).resolve()
    try:
        candidate.relative_to(path.parent.resolve())
    except ValueError:
        errors.append(f"{path.relative_to(root)}: narrative escapes its record directory")
        return
    if not candidate.is_file():
        errors.append(f"{path.relative_to(root)}: narrative file missing: {narrative}")
        return
    try:
        text = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"{candidate.relative_to(root)}: narrative is not UTF-8")
        return
    missing = sorted(set(extract_wikilinks(text)) - all_ids)
    if missing:
        errors.append(
            f"{candidate.relative_to(root_resolved)}: missing wikilink targets: {', '.join(missing)}"
        )


def validate_repository(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    validators: dict[str, Draft202012Validator] = {}
    schemas = {}
    for schema_path in sorted((root / "schemas").glob("*.schema.json")):
        try:
            schema = load_json(schema_path)
            Draft202012Validator.check_schema(schema)
            schemas[schema_path.name] = schema
        except Exception as exc:
            errors.append(f"{schema_path.relative_to(root)}: invalid schema: {exc}")
    missing = set(SCHEMA_FILES.values()) - schemas.keys()
    if missing or errors:
        return {"ok": False, "errors": errors + [f"missing or invalid schema: {name}" for name in sorted(missing)], "warnings": warnings, "counts": {}}
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema))
        for schema in schemas.values()
        if "$id" in schema
    )

    for kind, filename in SCHEMA_FILES.items():
        validators[kind] = Draft202012Validator(
            load_json(root / "schemas" / filename), format_checker=FormatChecker(), registry=registry
        )

    records: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    all_records: dict[str, tuple[str, Path, dict[str, Any]]] = {}
    invalid_paths: set[Path] = set()

    for kind, pattern in RECORD_PATTERNS.items():
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root)
            try:
                record = load_json(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel}: invalid JSON: {exc}")
                continue
            records[kind].append((path, record))
            failures = sorted(validators[kind].iter_errors(record), key=lambda item: list(item.path))
            if failures:
                invalid_paths.add(path)
            for failure in failures:
                location = ".".join(str(part) for part in failure.path) or "$"
                errors.append(f"{rel}:{location}: {failure.message}")
            record_id = record.get("id")
            if isinstance(record_id, str):
                if record_id in all_records:
                    previous = all_records[record_id][1]
                    errors.append(f"duplicate id {record_id}: {previous.relative_to(root)} and {rel}")
                else:
                    all_records[record_id] = (kind, path, record)

    all_records = {
        record_id: item
        for record_id, item in all_records.items()
        if item[1] not in invalid_paths
    }
    all_ids = set(all_records)
    source_ids = {record_id for record_id, (kind, _, _) in all_records.items() if kind == "source"}
    event_ids = {record_id for record_id, (kind, _, _) in all_records.items() if kind == "event"}
    knowledge_ids = {record_id for record_id, (kind, _, _) in all_records.items() if kind == "knowledge"}
    node_ids = {record_id for record_id, (kind, _, _) in all_records.items() if kind == "node"}
    collection_ids = {record_id for record_id, (kind, _, _) in all_records.items() if kind == "collection"}

    node_labels: dict[tuple[str, str], list[str]] = defaultdict(list)

    external_ids: dict[str, str] = {}
    for path, event in records["event"] + records["knowledge"]:
        if path in invalid_paths:
            continue
        rel = path.relative_to(root)
        event_id = event.get("id")
        parts = rel.parts
        if event["type"] == "knowledge":
            if parts != ("content", "knowledge", event_id, "record.json"):
                errors.append(f"{rel}: knowledge path must be content/knowledge/<id>/record.json")
            validity = event["validity"]
            for key in ("start", "end"):
                if validity[key] is not None:
                    try:
                        _partial_date(validity[key])
                    except ValueError:
                        errors.append(f"{rel}: invalid validity {key}")
            if validity["start"] and validity["end"]:
                try:
                    end = _partial_date(validity["end"])
                    if len(validity["end"]) == 4:
                        end = date(end.year, 12, 31)
                    elif len(validity["end"]) == 7:
                        end = date(end.year, end.month, monthrange(end.year, end.month)[1])
                    if _partial_date(validity["start"]) > end:
                        errors.append(f"{rel}: validity start is after end")
                except ValueError:
                    pass
            if event.get("superseded_by") and (event["superseded_by"] not in knowledge_ids or event["superseded_by"] == event_id):
                errors.append(f"{rel}: invalid superseded_by target")
            for identifier in event["external_ids"]:
                if identifier in external_ids:
                    errors.append(f"{rel}: duplicate external identity {identifier}")
                external_ids[identifier] = event_id
        elif len(parts) != 5 or parts[:2] != ("content", "events") or parts[-1] != "event.json":
            errors.append(f"{rel}: event path must be content/events/<year|undated>/<id>/event.json")
        elif event_id:
            if parts[3] != event_id:
                errors.append(f"{rel}: directory name must match id {event_id}")
            start = event.get("time", {}).get("start")
            expected_bucket = start[:4] if isinstance(start, str) else "undated"
            if parts[2] != expected_bucket:
                errors.append(f"{rel}: event belongs in {expected_bucket!r} time bucket")

        time_value = event.get("time")
        if isinstance(time_value, dict):
            _validate_time(rel, time_value, errors)

        claim_ids: set[str] = set()
        citation_sources_by_claim: dict[str, set[str]] = defaultdict(set)
        supports_by_claim: dict[str, set[str]] = defaultdict(set)
        has_contradiction = False
        for claim in event.get("claims", []):
            claim_id = claim.get("id")
            if isinstance(claim_id, str):
                if claim_id in claim_ids:
                    errors.append(f"{rel}: duplicate claim id {claim_id}")
                claim_ids.add(claim_id)
            for citation in claim.get("citations", []):
                source_id = citation.get("source_id")
                if source_id not in source_ids:
                    errors.append(f"{rel}: missing citation source {source_id}")
                    continue
                if isinstance(claim_id, str):
                    citation_sources_by_claim[claim_id].add(source_id)
                if citation.get("role") == "contradicts":
                    has_contradiction = True
                if citation.get("role") == "supports" and isinstance(claim_id, str):
                    source = all_records[source_id][2]
                    group = source.get("reliability", {}).get("independence_group")
                    if group:
                        supports_by_claim[claim_id].add(group)

        if event.get("status") == "corroborated":
            for claim in event.get("claims", []):
                if claim.get("kind") not in {"fact", "allegation"}:
                    continue
                if len(supports_by_claim.get(claim.get("id"), set())) < 2:
                    errors.append(
                        f"{rel}: corroborated claim {claim.get('id')} requires two support independence groups"
                    )
        if event.get("status") == "contested" and not has_contradiction:
            errors.append(f"{rel}: contested event requires a contradicts citation")

        seen_links: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()
        for link in event.get("links", []):
            target_id = link.get("target_id")
            if target_id not in event_ids | knowledge_ids | node_ids:
                errors.append(f"{rel}: missing link target {target_id}")
            if target_id == event_id:
                errors.append(f"{rel}: event cannot link to itself")
            missing_claims = sorted(set(link.get("claim_ids", [])) - claim_ids)
            missing_sources = sorted(set(link.get("source_ids", [])) - source_ids)
            if missing_claims:
                errors.append(f"{rel}: link has missing claim IDs: {', '.join(missing_claims)}")
            if missing_sources:
                errors.append(f"{rel}: link has missing source IDs: {', '.join(missing_sources)}")
            cited_sources = set().union(
                *(citation_sources_by_claim.get(item, set()) for item in link.get("claim_ids", []))
            )
            uncited_sources = sorted(set(link.get("source_ids", [])) - cited_sources)
            if uncited_sources:
                errors.append(
                    f"{rel}: link source IDs are not cited by its claims: {', '.join(uncited_sources)}"
                )
            key = (
                str(link.get("relation")),
                str(target_id),
                tuple(sorted(link.get("claim_ids", []))),
                tuple(sorted(link.get("source_ids", []))),
            )
            if key in seen_links:
                errors.append(f"{rel}: duplicate link {link.get('relation')} -> {target_id}")
            seen_links.add(key)
        _narrative_links(root, path, event, all_ids, errors)

    for path, node in records["node"]:
        if path in invalid_paths:
            continue
        rel = path.relative_to(root)
        node_id = node.get("id")
        kind = node.get("kind")
        expected_directory = NODE_DIRECTORIES.get(kind)
        if rel.parts[:2] != ("content", "nodes") or len(rel.parts) != 4:
            errors.append(f"{rel}: node path must be content/nodes/<kind-directory>/<id>.json")
        elif expected_directory and rel.parts[2] != expected_directory:
            errors.append(f"{rel}: {kind} node belongs in {expected_directory}/")
        if node_id and path.stem != node_id:
            errors.append(f"{rel}: filename must match id {node_id}")
        if node.get("status") == "described" and not node.get("source_ids"):
            errors.append(f"{rel}: described node requires at least one source")
        if node.get("summary") and not node.get("source_ids"):
            errors.append(f"{rel}: node summary requires at least one source")
        for source_id in node.get("source_ids", []):
            if source_id not in source_ids:
                errors.append(f"{rel}: missing source {source_id}")
        for label in [node.get("name"), *node.get("aliases", [])]:
            if isinstance(label, str):
                node_labels[(str(kind), label.casefold().strip())].append(str(node_id))

    for (kind, label), ids in sorted(node_labels.items()):
        unique_ids = sorted(set(ids))
        if label and len(unique_ids) > 1:
            warnings.append(f"ambiguous {kind} node label {label!r}: {', '.join(unique_ids)}")

    node_by_id = {
        record_id: record
        for record_id, (kind, _, record) in all_records.items()
        if kind == "node"
    }
    for path, collection in records["collection"]:
        if path in invalid_paths:
            continue
        rel = path.relative_to(root)
        collection_id = collection.get("id")
        if len(rel.parts) != 4 or rel.parts[:2] != ("content", "collections") or rel.parts[-1] != "collection.json":
            errors.append(f"{rel}: collection path must be content/collections/<id>/collection.json")
        elif rel.parts[2] != collection_id:
            errors.append(f"{rel}: directory name must match id {collection_id}")
        missing_events = sorted(set(collection.get("event_ids", [])) - event_ids)
        missing_knowledge = sorted(set(collection.get("knowledge_ids", [])) - knowledge_ids)
        if missing_knowledge:
            errors.append(f"{rel}: missing knowledge IDs: {', '.join(missing_knowledge)}")
        missing_focus = sorted(set(collection.get("focus_ids", [])) - node_ids)
        missing_related = sorted(set(collection.get("related_collection_ids", [])) - collection_ids)
        if missing_events:
            errors.append(f"{rel}: missing event IDs: {', '.join(missing_events)}")
        if missing_focus:
            errors.append(f"{rel}: missing focus IDs: {', '.join(missing_focus)}")
        if missing_related:
            errors.append(f"{rel}: missing related collections: {', '.join(missing_related)}")
        if collection_id in collection.get("related_collection_ids", []):
            errors.append(f"{rel}: collection cannot relate to itself")
        focus_kinds = {node_by_id[item]["kind"] for item in collection.get("focus_ids", []) if item in node_by_id}
        if collection.get("form") == "biographical" and not focus_kinds <= {"person", "organization"}:
            errors.append(f"{rel}: biographical focus must be person or organization nodes")
        if collection.get("form") == "institutional" and not focus_kinds <= {
            "organization", "place", "institution", "topic"
        }:
            errors.append(f"{rel}: institutional focus must be organization/place/institution/topic nodes")
        _narrative_links(root, path, collection, all_ids, errors)

    for path, source in records["source"]:
        if path in invalid_paths:
            continue
        rel = path.relative_to(root)
        source_id = source.get("id")
        if path.stem != source_id:
            errors.append(f"{rel}: filename must match id {source_id}")
        locator = source.get("locator", {})
        if not any(locator.get(key) for key in ("original_url", "archive_url", "public_path", "identifier")):
            errors.append(f"{rel}: source requires at least one locator")
        public_path = locator.get("public_path")
        if public_path:
            public_path_value = Path(public_path)
            if public_path_value.is_absolute() or "\\" in public_path:
                errors.append(f"{rel}: public_path must be a repository-relative POSIX path")
                continue
            if ".." in public_path_value.parts:
                errors.append(f"{rel}: public_path cannot contain parent traversal")
                continue
            if public_path_value.parts and public_path_value.parts[0] in {
                ".git",
                ".work",
                ".codex-work",
                ".venv",
            }:
                errors.append(f"{rel}: public_path cannot point to a private or generated workspace")
                continue
            candidate = (root / public_path_value).resolve()
            try:
                resolved_relative = candidate.relative_to(root.resolve())
            except ValueError:
                errors.append(f"{rel}: public_path escapes repository")
            else:
                if resolved_relative.parts and (
                    resolved_relative.parts[0] in {".git", ".work", ".codex-work", ".venv"}
                    or resolved_relative.parts[:2] == ("data", "generated")
                ):
                    errors.append(f"{rel}: public_path resolves to a private or generated workspace")
                    continue
                if not candidate.is_file():
                    errors.append(f"{rel}: public_path does not exist: {public_path}")
                elif not source.get("hashes"):
                    errors.append(f"{rel}: public_path requires one sha256 hash")
                else:
                    declared = source["hashes"][0]["value"]
                    actual = sha256_file(candidate)
                    if declared != actual:
                        errors.append(f"{rel}: public_path sha256 does not match the source record")
        published = source.get("dates", {}).get("published_at")
        if isinstance(published, str):
            try:
                _partial_date(published)
            except ValueError as exc:
                errors.append(f"{rel}: invalid published_at {published!r}: {exc}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {kind: len(records[kind]) for kind in RECORD_PATTERNS},
    }

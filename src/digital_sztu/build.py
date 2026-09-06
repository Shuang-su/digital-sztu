from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .knowledge import write_knowledge_export
from .privacy import scan_privacy
from .public import public_projection
from .utils import extract_wikilinks, load_json, write_json
from .validation import collect_repository, validate_repository


NODE_FILE_BY_KIND = {
    "person": "people.json",
    "organization": "organizations.json",
    "place": "places.json",
    "institution": "institutions.json",
    "topic": "topics.json",
}


def _generated_output(root: Path) -> Path | None:
    """Reject symlinks in every generated output directory before any write."""
    output = root / "data" / "generated"
    for directory in (
        root / "data",
        output,
        output / "directories",
        output / "knowledge",
    ):
        if directory.is_symlink():
            return None
    return output


def _event_sort_key(event: dict[str, Any]) -> tuple[int, str, int, str]:
    time_value = event["time"]
    anchor = time_value.get("start") or time_value.get("end")
    if not anchor:
        return (1, "9999", 9, event["id"])
    precision_rank = {"day": 0, "month": 1, "year": 2, "unknown": 9}[time_value["precision"]]
    return (0, anchor, precision_rank, event["id"])


def _edge_key(edge: dict[str, Any]) -> tuple[Any, ...]:
    locator = edge.get("locator")
    return (
        edge["from"],
        edge["relation"],
        edge["to"],
        tuple(edge.get("claim_ids", [])),
        tuple(edge.get("source_ids", [])),
        locator is None,
        locator or "",
    )


def _make_edge(
    source: str,
    target: str,
    relation: str,
    *,
    claim_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    locator: str | None = None,
) -> dict[str, Any]:
    return {
        "from": source,
        "to": target,
        "relation": relation,
        "claim_ids": sorted(set(claim_ids or [])),
        "source_ids": sorted(set(source_ids or [])),
        "locator": locator,
    }


def _narrative_edges(root: Path, owner_id: str, path: Path, narrative: str | None) -> list[dict[str, Any]]:
    if not narrative:
        return []
    narrative_path = path.parent / narrative
    text = narrative_path.read_text(encoding="utf-8")
    locator = narrative_path.relative_to(root).as_posix()
    return [
        _make_edge(owner_id, target_id, "wikilink", locator=locator)
        for target_id in extract_wikilinks(text)
    ]


def build_relationships(
    root: Path,
    records: dict[str, list[tuple[Path, dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, list[dict[str, Any]]]]]:
    edges: list[dict[str, Any]] = []

    for path, event in records["event"]:
        for claim in event["claims"]:
            for citation in claim["citations"]:
                edges.append(
                    _make_edge(
                        event["id"],
                        citation["source_id"],
                        citation["role"],
                        claim_ids=[claim["id"]],
                        source_ids=[citation["source_id"]],
                        locator=citation.get("locator"),
                    )
                )
        for link in event["links"]:
            edges.append(
                _make_edge(
                    event["id"],
                    link["target_id"],
                    link["relation"],
                    claim_ids=link["claim_ids"],
                    source_ids=link["source_ids"],
                )
            )
        edges.extend(_narrative_edges(root, event["id"], path, event.get("narrative")))

    for _, node in records["node"]:
        for source_id in node["source_ids"]:
            edges.append(
                _make_edge(
                    node["id"],
                    source_id,
                    "described-by",
                    source_ids=[source_id],
                )
            )

    for path, collection in records["collection"]:
        for event_id in collection["event_ids"]:
            edges.append(_make_edge(collection["id"], event_id, "contains"))
        for focus_id in collection["focus_ids"]:
            edges.append(_make_edge(collection["id"], focus_id, "focuses"))
        for related_id in collection.get("related_collection_ids", []):
            edges.append(_make_edge(collection["id"], related_id, "related-to"))
        edges.extend(_narrative_edges(root, collection["id"], path, collection.get("narrative")))

    unique_edges = sorted({_edge_key(edge): edge for edge in edges}.values(), key=_edge_key)
    all_ids = sorted(
        record["id"]
        for kind in ("event", "node", "collection", "source")
        for _, record in records[kind]
    )
    backlinks: dict[str, dict[str, list[dict[str, Any]]]] = {
        item: {"outgoing": [], "incoming": []} for item in all_ids
    }
    for edge in unique_edges:
        backlinks[edge["from"]]["outgoing"].append(edge)
        backlinks[edge["to"]]["incoming"].append(edge)
    for value in backlinks.values():
        value["outgoing"].sort(key=_edge_key)
        value["incoming"].sort(key=_edge_key)
    return unique_edges, backlinks


def _build_directories(
    output: Path,
    records: dict[str, list[tuple[Path, dict[str, Any]]]],
    edges: list[dict[str, Any]],
) -> dict[str, int]:
    node_by_id = {node["id"]: node for _, node in records["node"]}
    events_by_node: dict[str, set[str]] = defaultdict(set)
    collections_by_node: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge["from"].startswith("event-") and edge["to"] in node_by_id:
            events_by_node[edge["to"]].add(edge["from"])
        if edge["from"].startswith("collection-") and edge["to"] in node_by_id:
            collections_by_node[edge["to"]].add(edge["from"])

    counts: dict[str, int] = {}
    for kind, filename in NODE_FILE_BY_KIND.items():
        items = []
        for _, node in records["node"]:
            if node["kind"] != kind:
                continue
            items.append(
                {
                    "id": node["id"],
                    "name": node["name"],
                    "aliases": node["aliases"],
                    "status": node["status"],
                    "event_ids": sorted(events_by_node[node["id"]]),
                    "collection_ids": sorted(collections_by_node[node["id"]]),
                }
            )
        items.sort(key=lambda item: item["id"])
        write_json(
            output / "directories" / filename,
            {"schema_version": "0.1.0", "kind": kind, "items": items},
            sort_keys=True,
        )
        counts[kind] = len(items)

    by_year: dict[str, list[str]] = defaultdict(list)
    for _, event in records["event"]:
        start = event["time"].get("start")
        bucket = start[:4] if isinstance(start, str) else "undated"
        by_year[bucket].append(event["id"])
    normalized_years = {key: sorted(value) for key, value in sorted(by_year.items())}
    write_json(
        output / "directories" / "by-year.json",
        {"schema_version": "0.1.0", "years": normalized_years},
        sort_keys=True,
    )
    counts["years"] = len(normalized_years)
    return counts


def build_indexes(root: Path, *, privacy_result: dict[str, Any] | None = None) -> dict[str, Any]:
    validation = validate_repository(root)
    if not validation["ok"]:
        return {"ok": False, "errors": validation["errors"], "validation": validation}
    privacy = privacy_result or scan_privacy(root)
    if not privacy["ok"]:
        return {"ok": False, "errors": ["privacy scan blocked the build"], "privacy": privacy}

    records = public_projection(root, collect_repository(root))
    edges, backlinks = build_relationships(root, records)
    output = _generated_output(root)
    if output is None:
        return {
            "ok": False,
            "errors": ["data/generated and its output directories must not be symbolic links"],
        }

    events = [event for _, event in records["event"]]
    events.sort(key=_event_sort_key)
    timeline = {
        "schema_version": "0.1.0",
        "events": [
            {
                "id": event["id"],
                "title": event["title"],
                "status": event["status"],
                "time": event["time"],
                "summary": event["summary"],
                "linked_ids": sorted({link["target_id"] for link in event["links"]}),
            }
            for event in events
        ],
    }

    graph_nodes: list[dict[str, Any]] = []
    for _, event in records["event"]:
        graph_nodes.append({"id": event["id"], "type": "event", "label": event["title"]})
    for _, node in records["node"]:
        graph_nodes.append({"id": node["id"], "type": "node", "kind": node["kind"], "label": node["name"]})
    for _, collection in records["collection"]:
        graph_nodes.append(
            {"id": collection["id"], "type": "collection", "kind": collection["form"], "label": collection["title"]}
        )
    for _, source in records["source"]:
        graph_nodes.append({"id": source["id"], "type": "source", "label": source["title"]})
    graph_nodes.sort(key=lambda item: item["id"])

    event_by_id = {event["id"]: event for _, event in records["event"]}
    collection_items: list[dict[str, Any]] = []
    for _, collection in records["collection"]:
        event_ids = list(collection["event_ids"])
        if collection["order"] in {"chronological", "reverse-chronological"}:
            event_ids.sort(key=lambda item: _event_sort_key(event_by_id[item]))
            if collection["order"] == "reverse-chronological":
                dated = [item for item in event_ids if _event_sort_key(event_by_id[item])[0] == 0]
                undated = [item for item in event_ids if _event_sort_key(event_by_id[item])[0] == 1]
                dated.reverse()
                event_ids = dated + undated
        collection_items.append(
            {
                "id": collection["id"],
                "form": collection["form"],
                "title": collection["title"],
                "focus_ids": collection["focus_ids"],
                "event_ids": event_ids,
            }
        )
    collection_items.sort(key=lambda item: item["id"])

    write_json(output / "timeline.json", timeline, sort_keys=True)
    write_json(
        output / "graph.json",
        {"schema_version": "0.1.0", "nodes": graph_nodes, "edges": edges},
        sort_keys=True,
    )
    write_json(
        output / "backlinks.json",
        {"schema_version": "0.1.0", "items": backlinks},
        sort_keys=True,
    )
    write_json(
        output / "collections.json",
        {"schema_version": "0.1.0", "items": collection_items},
        sort_keys=True,
    )
    directory_counts = _build_directories(output, records, edges)
    knowledge = write_knowledge_export(root, output / "knowledge", records, backlinks)
    if not knowledge["ok"]:
        return {"ok": False, "errors": knowledge["errors"], "knowledge": knowledge}

    return {
        "ok": True,
        "events": len(records["event"]),
        "nodes": len(records["node"]),
        "collections": len(records["collection"]),
        "sources": len(records["source"]),
        "edges": len(edges),
        "directories": directory_counts,
        "knowledge": knowledge,
        "output": output.relative_to(root).as_posix(),
    }


def export_knowledge(root: Path, output: Path) -> dict[str, Any]:
    validation = validate_repository(root)
    if not validation["ok"]:
        return {"ok": False, "errors": validation["errors"], "validation": validation}
    privacy = scan_privacy(root)
    if not privacy["ok"]:
        return {"ok": False, "errors": ["privacy scan blocked the export"], "privacy": privacy}
    records = public_projection(root, collect_repository(root))
    _, backlinks = build_relationships(root, records)
    return write_knowledge_export(root, output, records, backlinks)

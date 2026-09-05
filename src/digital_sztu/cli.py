from __future__ import annotations

import argparse
import json
import platform
import sys
import webbrowser
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from .build import build_indexes, export_knowledge
from .graph import write_viewer
from .discovery import Research, initialize, research_lock
from .chat import load_messages, render_chat
from .ingest import create_manifest
from .privacy import scan_privacy
from .utils import atomic_write_text, ensure_within, find_repo_root
from .validation import validate_repository


def emit(operation: str, result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        envelope = {
            "contract_version": "0.2.0",
            "operation": operation,
            "ok": bool(result.get("ok")),
            "data": result,
        }
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
        return
    status = "OK" if result.get("ok", False) else "FAILED"
    print(f"[{status}] {operation}")
    for key, value in result.items():
        if key == "ok":
            continue
        if isinstance(value, list):
            if value:
                print(f"{key}:")
                for item in value:
                    print(f"  - {item}")
        else:
            print(f"{key}: {value}")


def doctor(root: Path) -> dict[str, Any]:
    required = [
        "README.md",
        "AGENTS.md",
        "connect.config.json",
        ".codex-plugin/plugin.json",
        "schemas/event.schema.json",
        "schemas/node.schema.json",
    ]
    missing = [item for item in required if not (root / item).exists()]
    py_ok = sys.version_info >= (3, 11)
    return {
        "ok": py_ok and not missing,
        "python": platform.python_version(),
        "repository": str(root),
        "missing": missing,
        "runtime": "local-cli-and-skills",
        "mcp_available": False,
        "webmcp_available": False,
    }


def combined_check(root: Path, *, strict: bool = False) -> dict[str, Any]:
    validation = validate_repository(root)
    privacy = scan_privacy(root, strict=strict)
    build = (
        build_indexes(root, privacy_result=privacy)
        if validation["ok"] and privacy["ok"]
        else {"ok": False, "skipped": True}
    )
    return {
        "ok": validation["ok"] and privacy["ok"] and build["ok"],
        "validation": validation,
        "privacy": privacy,
        "build": build,
    }


def _work_output(root: Path, value: Path | None, default: str) -> Path:
    work_path = root / ".work"
    if work_path.is_symlink():
        raise ValueError(".work must be a real directory inside the repository")
    work = work_path.resolve()
    ensure_within(work, root.resolve())
    candidate = (root / value).resolve() if value and not value.is_absolute() else (value.resolve() if value else work / default)
    return ensure_within(candidate, work)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digital-sztu", description="Event-centered archive tooling for Digital SZTU"
    )
    parser.add_argument("--root", type=Path, help="repository root; defaults to auto-discovery")
    sub = parser.add_subparsers(dest="command", required=True)

    for command in ("doctor", "validate", "build"):
        item = sub.add_parser(command)
        item.add_argument("--json", action="store_true", dest="as_json")

    privacy = sub.add_parser("privacy-scan")
    privacy.add_argument("--strict", action="store_true")
    privacy.add_argument("--json", action="store_true", dest="as_json")

    check = sub.add_parser("check")
    check.add_argument("--strict", action="store_true")
    check.add_argument("--json", action="store_true", dest="as_json")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--dry-run", action="store_true", required=True)
    ingest.add_argument("--output", type=Path)
    ingest.add_argument("--json", action="store_true", dest="as_json")

    export = sub.add_parser("export-knowledge")
    export.add_argument("--output", type=Path)
    export.add_argument("--json", action="store_true", dest="as_json")

    validate_chat = sub.add_parser("validate-chat")
    validate_chat.add_argument("path", type=Path)
    validate_chat.add_argument("--json", action="store_true", dest="as_json")

    chat = sub.add_parser("render-chat")
    chat.add_argument("path", type=Path)
    chat.add_argument("--title", required=True)
    chat.add_argument("--output", type=Path, required=True)
    chat.add_argument("--json", action="store_true", dest="as_json")
    graph = sub.add_parser("graph")
    graph.add_argument("--open", action="store_true")
    graph.add_argument("--output", type=Path)
    graph.add_argument("--json", action="store_true", dest="as_json")

    discover = sub.add_parser("discover")
    discover.add_argument("action", choices=("init", "seed", "resume", "status", "review", "export", "promote", "sweep", "inspect", "external"))
    discover.add_argument("--database", type=Path)
    discover.add_argument("--legacy-state", type=Path)
    discover.add_argument("--file", type=Path)
    discover.add_argument("--name")
    discover.add_argument("--id")
    discover.add_argument("--complete", action="store_true")
    discover.add_argument("--limit", type=int, default=100)
    discover.add_argument("--kinds")
    discover.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    operation = args.command
    try:
        root = args.root.resolve() if args.root else find_repo_root()
        from .promotion import recover_promotion
        recover_promotion(root)
        if operation == "doctor":
            result = doctor(root)
        elif operation == "validate":
            result = validate_repository(root)
        elif operation == "privacy-scan":
            result = scan_privacy(root, strict=args.strict)
        elif operation == "build":
            result = build_indexes(root)
        elif operation == "graph":
            result = build_indexes(root)
            if result["ok"]:
                result = write_viewer(root, _work_output(root, args.output, "graph"))
                if args.open:
                    result["opened"] = webbrowser.open(Path(result["output"]).as_uri())
        elif operation == "discover":
            database = _work_output(root, args.database, "discovery/state.sqlite3")
            if args.action == "init":
                result = initialize(database, args.legacy_state)
            else:
                with (nullcontext() if args.action in ("status", "inspect") else research_lock(database)):
                    run = Research(database)
                    try:
                        if args.action == "resume":
                            if args.limit < 1:
                                raise ValueError("limit must be positive")
                            result = run.resume(args.limit, args.kinds.split(",") if args.kinds else None)
                        elif args.action == "status":
                            result = run.status()
                        elif args.action == "inspect":
                            if not args.id:
                                raise ValueError("inspect requires --id")
                            result = {"ok": True, "record": run.state["records"][args.id]}
                        elif args.action == "sweep":
                            queries = json.loads(args.file.read_text(encoding="utf-8")) if args.file else None
                            result = run.sweep(queries, args.complete)
                        elif args.action == "seed":
                            if not args.name:
                                raise ValueError("seed requires --name")
                            run.seed(args.name)
                            result = run.status()
                        elif args.action == "review":
                            if not args.file:
                                raise ValueError("review requires --file")
                            result = run.review(json.loads(args.file.read_text(encoding="utf-8")))
                        elif args.action == "external":
                            if not args.file:
                                raise ValueError("external requires --file")
                            result = run.external(json.loads(args.file.read_text(encoding="utf-8")))
                        elif args.action == "export":
                            result = run.export(database.parent / "export")
                        else:
                            from .promotion import promote
                            result = promote(root, run, args.file)
                    finally:
                        run.close()
        elif operation == "check":
            result = combined_check(root, strict=args.strict)
        elif operation == "ingest":
            output = _work_output(root, args.output, "intake")
            destination, manifest = create_manifest(args.path, output)
            result = {
                "ok": True,
                "mode": "dry-run",
                "manifest": destination.relative_to(root).as_posix(),
                "submission_id": manifest["submission_id"],
                "file_count": len(manifest["files"]),
                "warnings": manifest["warnings"],
            }
        elif operation == "export-knowledge":
            output = _work_output(root, args.output, "knowledge/export")
            result = export_knowledge(root, output)
        elif operation == "validate-chat":
            messages = load_messages(
                args.path.expanduser().resolve(), root / "schemas" / "chat-message.schema.json"
            )
            result = {"ok": True, "messages": len(messages), "normalized": False}
        elif operation == "render-chat":
            messages = load_messages(
                args.path.expanduser().resolve(), root / "schemas" / "chat-message.schema.json"
            )
            output = _work_output(root, args.output, "chat/transcript.html")
            atomic_write_text(output, render_chat(messages, args.title))
            result = {
                "ok": True,
                "output": output.relative_to(root).as_posix(),
                "messages": len(messages),
                "generic_ui": True,
                "normalized": False,
            }
        else:
            raise RuntimeError(f"Unknown command: {operation}")
        emit(operation, result, getattr(args, "as_json", False))
        return 0 if result.get("ok") else 1
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        emit(operation, result, getattr(args, "as_json", False))
        return 2

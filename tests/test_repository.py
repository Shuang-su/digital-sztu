from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from sztu_connect.build import build_indexes, export_knowledge
from sztu_connect.chat import load_messages, render_chat
from sztu_connect.cli import _work_output
from sztu_connect.ingest import create_manifest
from sztu_connect.privacy import scan_privacy
from sztu_connect.utils import ensure_within, find_repo_root, load_json, sha256_file
from sztu_connect.validation import validate_repository


ROOT = find_repo_root(Path(__file__).resolve())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ExampleRepository:
    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        shutil.copytree(ROOT / "schemas", self.root / "schemas")
        shutil.copytree(ROOT / "examples" / "minimal" / "content", self.root / "content")
        shutil.copytree(
            ROOT / "examples" / "minimal" / "sources", self.root / "sources" / "records"
        )
        shutil.copy(ROOT / "connect.config.json", self.root / "connect.config.json")
        (self.root / "README.md").write_text("# Example\n", encoding="utf-8")

    def close(self) -> None:
        self._temporary.cleanup()

    @property
    def event_path(self) -> Path:
        return self.root / "content/events/2024/event-example-structure/event.json"

    def event(self) -> dict[str, object]:
        return load_json(self.event_path)


class RepositoryTests(unittest.TestCase):
    def test_current_repository_validates(self) -> None:
        result = validate_repository(ROOT)
        self.assertTrue(result["ok"], result["errors"])

    def test_empty_skeleton_fixture_validates(self) -> None:
        # Emptiness describes this fixture, not every user's live repository.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "schemas", root / "schemas")
            shutil.copyfile(ROOT / "connect.config.json", root / "connect.config.json")
            result = validate_repository(root)
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(result["counts"], {"event": 0, "node": 0, "collection": 0, "source": 0})

    def test_minimal_example_validates(self) -> None:
        repo = ExampleRepository()
        try:
            result = validate_repository(repo.root)
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(result["counts"], {"event": 1, "node": 5, "collection": 4, "source": 1})
        finally:
            repo.close()

    def test_invalid_calendar_date_fails(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["time"]["start"] = "2024-99"
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("invalid calendar date" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_time_precision_mismatch_fails(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["time"]["precision"] = "day"
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertTrue(any("does not match" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_date_only_time_does_not_require_timezone(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["time"]["timezone"] = None
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertTrue(result["ok"], result["errors"])
        finally:
            repo.close()

    def test_event_year_directory_matches_time(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["time"]["start"] = "2023-09"
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertTrue(any("time bucket" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_missing_citation_source_fails(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["claims"][0]["citations"][0]["source_id"] = "source-missing"
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertTrue(any("missing citation source" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_duplicate_claim_id_fails(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["claims"].append(dict(event["claims"][0]))
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertTrue(any("duplicate claim id" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_missing_link_target_fails(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["links"][0]["target_id"] = "person-missing"
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertTrue(any("missing link target" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_event_link_requires_claim_and_source_evidence(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["links"][0]["claim_ids"] = []
            event["links"][0]["source_ids"] = []
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("non-empty" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_event_link_source_must_be_cited_by_linked_claim(self) -> None:
        repo = ExampleRepository()
        try:
            source_path = repo.root / "sources/records/source-example-documentation.json"
            other = load_json(source_path)
            other["id"] = "source-other"
            other["title"] = "另一来源"
            write_json(repo.root / "sources/records/source-other.json", other)
            event = repo.event()
            event["links"][0]["source_ids"] = ["source-other"]
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("not cited by its claims" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_missing_wikilink_target_fails(self) -> None:
        repo = ExampleRepository()
        try:
            narrative = repo.event_path.parent / "index.md"
            narrative.write_text("[[person-does-not-exist|missing]]\n", encoding="utf-8")
            result = validate_repository(repo.root)
            self.assertTrue(any("missing wikilink targets" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_prohibited_event_with_exclude_passes(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["privacy"]["risk"] = "prohibited"
            event["privacy"]["indexing"] = "exclude"
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertTrue(result["ok"], result)
        finally:
            repo.close()

    def test_restricted_collection_can_be_indexed(self) -> None:
        repo = ExampleRepository()
        try:
            path = repo.root / "content/collections/collection-example-thematic/collection.json"
            collection = load_json(path)
            collection["privacy"]["handling"] = "restricted"
            collection["privacy"]["indexing"] = "include"
            write_json(path, collection)
            result = validate_repository(repo.root)
            self.assertTrue(result["ok"], result)
        finally:
            repo.close()

    def test_backlinks_and_all_directories_are_generated(self) -> None:
        repo = ExampleRepository()
        try:
            result = build_indexes(repo.root)
            self.assertTrue(result["ok"], result)
            backlinks = load_json(repo.root / "data/generated/backlinks.json")["items"]
            incoming = backlinks["person-example"]["incoming"]
            self.assertTrue(
                any(item["from"] == "event-example-structure" for item in incoming), incoming
            )
            for filename in (
                "people.json",
                "organizations.json",
                "places.json",
                "institutions.json",
                "topics.json",
            ):
                value = load_json(repo.root / "data/generated/directories" / filename)
                self.assertEqual(len(value["items"]), 1, filename)
                self.assertEqual(value["items"][0]["event_ids"], ["event-example-structure"])
        finally:
            repo.close()

    def test_node_source_generates_source_backlink(self) -> None:
        repo = ExampleRepository()
        try:
            node_path = repo.root / "content/nodes/people/person-example.json"
            node = load_json(node_path)
            node["source_ids"] = ["source-example-documentation"]
            write_json(node_path, node)
            self.assertTrue(build_indexes(repo.root)["ok"])
            backlinks = load_json(repo.root / "data/generated/backlinks.json")["items"]
            incoming = backlinks["source-example-documentation"]["incoming"]
            self.assertTrue(
                any(item["from"] == "person-example" and item["relation"] == "described-by" for item in incoming)
            )
        finally:
            repo.close()

    def test_history_forms_reuse_one_event(self) -> None:
        repo = ExampleRepository()
        try:
            result = build_indexes(repo.root)
            self.assertTrue(result["ok"], result)
            collections = load_json(repo.root / "data/generated/collections.json")["items"]
            self.assertEqual(
                {item["form"] for item in collections},
                {"annals", "biographical", "institutional", "thematic"},
            )
            self.assertTrue(
                all(item["event_ids"] == ["event-example-structure"] for item in collections)
            )
        finally:
            repo.close()

    def test_knowledge_claim_keeps_source_and_backlinks(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["claims"].append(
                {
                    "id": "claim-example-other",
                    "text": "另一条虚构示例论断。",
                    "kind": "fact",
                    "certainty": "high",
                    "citations": [dict(event["claims"][0]["citations"][0])],
                }
            )
            event["links"][-1]["claim_ids"] = ["claim-example-other"]
            write_json(repo.event_path, event)
            result = build_indexes(repo.root)
            self.assertTrue(result["ok"], result)
            lines = (repo.root / "data/generated/knowledge/chunks.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            chunks = [json.loads(line) for line in lines]
            claim = next(item for item in chunks if item["claim_ids"] == ["claim-example-purpose"])
            self.assertEqual(claim["claim_ids"], ["claim-example-purpose"])
            self.assertEqual(claim["citations"][0]["source_id"], "source-example-documentation")
            self.assertTrue(any(item["other_id"] == "person-example" for item in claim["links"]))
            self.assertFalse(any(item["other_id"] == "topic-example" for item in claim["links"]))
            other = next(item for item in chunks if item["claim_ids"] == ["claim-example-other"])
            self.assertTrue(any(item["other_id"] == "topic-example" for item in other["links"]))
            self.assertFalse(any(item["other_id"] == "person-example" for item in other["links"]))
            self.assertEqual(claim["verification"]["record_status"], "source-backed")
            self.assertEqual(claim["verification"]["claim"]["kind"], "fact")
            self.assertEqual(claim["evidence_role"], "claim-evidence")
            self.assertTrue(all("source_ids" in item and "claim_ids" in item for item in claim["links"]))
            summary = next(
                item
                for item in chunks
                if item["owner_id"] == "event-example-structure" and item["chunk_kind"] == "summary"
            )
            self.assertEqual(summary["evidence_role"], "navigation")
            self.assertEqual(
                summary["claim_ids"], ["claim-example-other", "claim-example-purpose"]
            )
            source_chunk = next(item for item in chunks if item["owner_type"] == "source")
            self.assertEqual(
                source_chunk["source_metadata"]["locator"]["original_url"],
                "https://github.com/Shuang-su/sztu-connect",
            )
            schema = load_json(ROOT / "schemas/knowledge-chunk.schema.json")
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(claim)), [])
        finally:
            repo.close()

    def test_null_and_text_citation_locators_build_deterministically(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            citation = dict(event["claims"][0]["citations"][0])
            citation["locator"] = None
            event["claims"][0]["citations"].append(citation)
            write_json(repo.event_path, event)
            self.assertTrue(build_indexes(repo.root)["ok"])
            first = (repo.root / "data/generated/graph.json").read_bytes()
            self.assertTrue(build_indexes(repo.root)["ok"])
            self.assertEqual(first, (repo.root / "data/generated/graph.json").read_bytes())
        finally:
            repo.close()

    def test_knowledge_preserves_withdrawn_allegation_status(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["status"] = "withdrawn"
            event["claims"][0]["kind"] = "allegation"
            event["claims"][0]["certainty"] = "low"
            write_json(repo.event_path, event)
            self.assertTrue(build_indexes(repo.root)["ok"])
            chunks = [
                json.loads(line)
                for line in (repo.root / "data/generated/knowledge/chunks.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            claim = next(item for item in chunks if item["chunk_kind"] == "claim")
            self.assertEqual(claim["verification"]["record_status"], "withdrawn")
            self.assertEqual(
                claim["verification"]["claim"],
                {"kind": "allegation", "certainty": "low"},
            )
        finally:
            repo.close()

    def test_reverse_chronology_keeps_unknown_time_last(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["id"] = "event-example-undated"
            event["title"] = "未知时间示例"
            event["time"] = {
                "kind": "unknown",
                "start": None,
                "end": None,
                "precision": "unknown",
                "certainty": "unknown",
                "timezone": None,
                "original_text": "时间未知",
            }
            event["links"] = []
            event["narrative"] = None
            write_json(
                repo.root / "content/events/undated/event-example-undated/event.json", event
            )
            collection_path = (
                repo.root
                / "content/collections/collection-example-thematic/collection.json"
            )
            collection = load_json(collection_path)
            collection["order"] = "reverse-chronological"
            collection["event_ids"].append("event-example-undated")
            write_json(collection_path, collection)
            self.assertTrue(build_indexes(repo.root)["ok"])
            items = load_json(repo.root / "data/generated/collections.json")["items"]
            thematic = next(item for item in items if item["id"] == "collection-example-thematic")
            self.assertEqual(
                thematic["event_ids"],
                ["event-example-structure", "event-example-undated"],
            )
        finally:
            repo.close()

    def test_build_is_byte_deterministic(self) -> None:
        repo = ExampleRepository()
        try:
            self.assertTrue(build_indexes(repo.root)["ok"])
            first = {
                path.relative_to(repo.root).as_posix(): path.read_bytes()
                for path in sorted((repo.root / "data/generated").rglob("*"))
                if path.is_file()
            }
            self.assertTrue(build_indexes(repo.root)["ok"])
            second = {
                path.relative_to(repo.root).as_posix(): path.read_bytes()
                for path in sorted((repo.root / "data/generated").rglob("*"))
                if path.is_file()
            }
            self.assertEqual(first, second)
        finally:
            repo.close()

    def test_ingest_id_is_content_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            source.mkdir()
            (source / "note.txt").write_text("example", encoding="utf-8")
            first_path, first = create_manifest(source, root / "out")
            second_path, second = create_manifest(source, root / "out")
            self.assertEqual(first["submission_id"], second["submission_id"])
            self.assertEqual(first_path, second_path)
            self.assertEqual(sha256_file(first_path), sha256_file(second_path))

    def test_privacy_review_does_not_fail_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            phone = "138" + "00138000"
            (root / "note.md").write_text(phone, encoding="utf-8")
            result = scan_privacy(root)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["counts"]["review"], 1)
            self.assertNotIn(phone, json.dumps(result, ensure_ascii=False))

    def test_privacy_secret_is_review_without_echo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = "ghp_" + ("a" * 24)
            (root / "note.md").write_text(secret, encoding="utf-8")
            result = scan_privacy(root)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["counts"]["block"], 0)
            self.assertEqual(result["counts"]["review"], 1)
            self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_quoted_json_password_assignment_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = "supersecret123"
            (root / "config.json").write_text(
                json.dumps({"password": secret}), encoding="utf-8"
            )
            result = scan_privacy(root)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["counts"]["block"], 0)
            self.assertEqual(result["counts"]["review"], 1)
            self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_build_and_export_allow_detected_secrets_as_review(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            secret = "ghp_" + ("z" * 24)
            event["summary"] = f"unsafe {secret}"
            write_json(repo.event_path, event)
            build = build_indexes(repo.root)
            export = export_knowledge(repo.root, repo.root / ".work/knowledge")
            self.assertTrue(build["ok"], build)
            self.assertTrue(export["ok"], export)
            self.assertTrue((repo.root / "data/generated/knowledge/chunks.jsonl").exists())
            self.assertTrue((repo.root / ".work/knowledge/chunks.jsonl").exists())
        finally:
            repo.close()

    def test_private_env_filenames_are_scanned_not_blocked(self) -> None:
        for filename in (".env", ".env.local", ".envrc", ".envrc.local"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / filename).write_text("API_" + "KEY=undetected-format\n", encoding="utf-8")
                result = scan_privacy(root)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["counts"]["block"], 0)
                self.assertEqual(result["scanned_files"], 1)

    def test_env_template_is_scanned_but_not_blocked_by_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env.example").write_text("API_KEY=replace-me\n", encoding="utf-8")
            result = scan_privacy(root)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["counts"]["block"], 0)
            self.assertEqual(result["scanned_files"], 1)

    def test_env_template_contents_are_still_reviewed(self) -> None:
        for filename in (".env.example", "prod.env.example"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                secret = "ghp_" + ("b" * 24)
                (root / filename).write_text(secret, encoding="utf-8")
                result = scan_privacy(root)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["counts"]["block"], 0)
                self.assertEqual(result["counts"]["review"], 1)
                self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_privacy_strict_does_not_fail_on_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            phone = "138" + "00138000"
            (root / "note.md").write_text(phone, encoding="utf-8")
            result = scan_privacy(root, strict=True)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["strict"])
            self.assertEqual(result["counts"]["review"], 1)

    def test_binary_file_gets_review_finding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "photo.jpg").write_bytes(b"\xff\xd8\xff\x00")
            result = scan_privacy(root)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["counts"]["review"], 1)

    def test_schema_invalid_arrays_return_errors_instead_of_crashing(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["links"] = None
            write_json(repo.event_path, event)
            result = validate_repository(repo.root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("not of type 'array'" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_invalid_referenced_records_do_not_crash_semantic_validation(self) -> None:
        repo = ExampleRepository()
        try:
            node_path = repo.root / "content/nodes/people/person-example.json"
            node = load_json(node_path)
            node.pop("kind")
            write_json(node_path, node)
            source_path = repo.root / "sources/records/source-example-documentation.json"
            source = load_json(source_path)
            source["reliability"] = None
            write_json(source_path, source)
            result = validate_repository(repo.root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("missing citation source" in item for item in result["errors"]))
            self.assertTrue(any("missing focus IDs" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_canonical_symlink_is_allowed(self) -> None:
        repo = ExampleRepository()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                outside = Path(temporary) / "event.json"
                outside.write_text(repo.event_path.read_text(encoding="utf-8"), encoding="utf-8")
                repo.event_path.unlink()
                repo.event_path.symlink_to(outside)
                result = validate_repository(repo.root)
                self.assertTrue(result["ok"], result)
        finally:
            repo.close()

    def test_generated_symlink_is_blocked_before_external_write(self) -> None:
        repo = ExampleRepository()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                outside = Path(temporary)
                (repo.root / "data").mkdir()
                (repo.root / "data/generated").symlink_to(outside, target_is_directory=True)
                result = build_indexes(repo.root)
                self.assertFalse(result["ok"])
                self.assertEqual(list(outside.iterdir()), [])
        finally:
            repo.close()

    def test_generated_subdirectory_symlinks_are_blocked_before_any_write(self) -> None:
        for directory, filename in (
            ("knowledge", "chunks.jsonl"),
            ("directories", "people.json"),
        ):
            with self.subTest(directory=directory):
                repo = ExampleRepository()
                try:
                    with tempfile.TemporaryDirectory() as temporary:
                        outside = Path(temporary)
                        existing = outside / filename
                        existing.write_bytes(b"preserve existing output\n")
                        generated = repo.root / "data/generated"
                        generated.mkdir(parents=True)
                        link = generated / directory
                        link.symlink_to(outside, target_is_directory=True)

                        result = build_indexes(repo.root)

                        self.assertFalse(result["ok"], result)
                        self.assertTrue(result["errors"])
                        self.assertEqual(list(generated.iterdir()), [link])
                        self.assertTrue(link.is_symlink())
                        self.assertEqual(list(outside.iterdir()), [existing])
                        self.assertEqual(existing.read_bytes(), b"preserve existing output\n")
                finally:
                    repo.close()

    def test_generated_output_dangling_symlinks_are_blocked_before_any_write(self) -> None:
        for directory in (
            "data",
            "data/generated",
            "data/generated/knowledge",
            "data/generated/directories",
        ):
            with self.subTest(directory=directory):
                repo = ExampleRepository()
                try:
                    with tempfile.TemporaryDirectory() as temporary:
                        outside = Path(temporary)
                        link = repo.root / directory
                        link.parent.mkdir(parents=True, exist_ok=True)
                        link.symlink_to(outside / "missing", target_is_directory=True)

                        result = build_indexes(repo.root)

                        self.assertFalse(result["ok"], result)
                        self.assertTrue(result["errors"])
                        self.assertTrue(link.is_symlink())
                        self.assertEqual(list(outside.iterdir()), [])
                        self.assertFalse((repo.root / "data/generated/timeline.json").exists())
                finally:
                    repo.close()

    def test_work_root_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            (root / ".work").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaises(ValueError):
                _work_output(root, None, "knowledge/export")

    def test_public_path_hash_is_verified(self) -> None:
        repo = ExampleRepository()
        try:
            public_file = repo.root / "public/source.txt"
            public_file.parent.mkdir()
            public_file.write_text("source", encoding="utf-8")
            source_path = repo.root / "sources/records/source-example-documentation.json"
            source = load_json(source_path)
            source["locator"]["public_path"] = "public/source.txt"
            source["hashes"] = [{"algorithm": "sha256", "value": "0" * 64}]
            write_json(source_path, source)
            result = validate_repository(repo.root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("sha256 does not match" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_public_path_cannot_traverse_into_private_work(self) -> None:
        repo = ExampleRepository()
        try:
            private_file = repo.root / ".work/secret.txt"
            private_file.parent.mkdir()
            private_file.write_text("private", encoding="utf-8")
            source_path = repo.root / "sources/records/source-example-documentation.json"
            source = load_json(source_path)
            source["locator"]["public_path"] = "public/../.work/secret.txt"
            source["hashes"] = [
                {"algorithm": "sha256", "value": sha256_file(private_file)}
            ]
            write_json(source_path, source)
            result = validate_repository(repo.root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("parent traversal" in item for item in result["errors"]))
        finally:
            repo.close()

    def test_source_urls_may_embed_credentials_or_secret_queries(self) -> None:
        repo = ExampleRepository()
        try:
            source_path = repo.root / "sources/records/source-example-documentation.json"
            source = load_json(source_path)
            password = "super" + "secret123"
            source["locator"]["original_url"] = (
                "https://alice:" + password + "@" + "example.com/private"
            )
            source["locator"]["archive_url"] = (
                "https://example.com/archive?" + "access_" + "token=opaque-value"
            )
            write_json(source_path, source)
            result = validate_repository(repo.root)
            self.assertTrue(result["ok"], result)
        finally:
            repo.close()

    def test_metadata_only_source_may_expose_public_path(self) -> None:
        repo = ExampleRepository()
        try:
            public_file = repo.root / "public/source.txt"
            public_file.parent.mkdir()
            public_file.write_text("source", encoding="utf-8")
            source_path = repo.root / "sources/records/source-example-documentation.json"
            source = load_json(source_path)
            source["access"] = "metadata-only"
            source["locator"]["public_path"] = "public/source.txt"
            source["hashes"] = [
                {"algorithm": "sha256", "value": sha256_file(public_file)}
            ]
            write_json(source_path, source)
            result = validate_repository(repo.root)
            self.assertTrue(result["ok"], result)
        finally:
            repo.close()

    def test_prohibited_records_are_not_exported(self) -> None:
        repo = ExampleRepository()
        try:
            event = repo.event()
            event["privacy"]["risk"] = "prohibited"
            event["privacy"]["indexing"] = "exclude"
            write_json(repo.event_path, event)
            export = export_knowledge(repo.root, repo.root / ".work/knowledge")
            self.assertTrue(export["ok"], export)
            chunks = (repo.root / ".work/knowledge/chunks.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(event["id"], chunks)
            self.assertNotIn('"risk":"prohibited"', chunks)
            self.assertNotIn('"indexing":"exclude"', chunks)
            self.assertEqual(load_json(repo.event_path), event)
        finally:
            repo.close()

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"id":"first","id":"second"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                load_json(path)

    def test_external_output_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                ensure_within(root.parent / "outside", root / ".work")

    def test_chat_renderer_escapes_html(self) -> None:
        messages = load_messages(
            ROOT / "examples/chat/messages.example.jsonl",
            ROOT / "schemas/chat-message.schema.json",
        )
        messages[0]["text"] = "<script>alert(1)</script>"
        output = render_chat(messages, "Example")
        self.assertNotIn("<script>alert(1)</script>", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertIn("Digital SZTU", output)
        self.assertNotIn("🐔🧱时空", output)

    def test_name_contract(self) -> None:
        config = load_json(ROOT / "connect.config.json")["project"]
        self.assertEqual(config["display_name"], "Digital SZTU")
        self.assertEqual(config["plain_text_name"], "Digital SZTU")
        self.assertEqual(config["accessible_name"], "Digital SZTU")

        plugin = load_json(ROOT / ".codex-plugin" / "plugin.json")
        self.assertEqual(plugin["interface"]["displayName"], "Digital SZTU")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/bootstrap.py"
SPEC = importlib.util.spec_from_file_location("sztu_bootstrap", SCRIPT)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def checkout(parent: Path) -> Path:
    target = parent / "技大 档案"
    target.mkdir()
    for directory in ("schemas", "examples", "src", ".codex-plugin", "scripts"):
        shutil.copytree(ROOT / directory, target / directory,
                        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    for name in ("README.md", "AGENTS.md", "connect.config.json", "requirements.lock",
                 "pyproject.toml", ".gitignore"):
        shutil.copyfile(ROOT / name, target / name)
    return target.resolve()


def snapshot(root: Path) -> dict[str, tuple[str, int]]:
    # Hashes retain byte equality without asking unittest to diff whole wheels.
    # Finder can create .DS_Store independently while a local fixture is open.
    return {path.relative_to(root).as_posix(): (bootstrap.sha256_file(path), path.stat().st_mtime_ns)
            for path in root.rglob("*")
            if path.name != ".DS_Store" and path.is_file() and not path.is_symlink()}


def response(value: object = None, code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, json.dumps(value or {}), "")


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = checkout(Path(self.temporary.name))

    def fake_venv(self) -> Path:
        executable = bootstrap.venv_python(self.root)
        executable.parent.mkdir(parents=True)
        executable.write_text("fixture interpreter", encoding="utf-8")
        (self.root / ".venv/pyvenv.cfg").write_text(
            "include-system-site-packages = false\n", encoding="utf-8")
        return executable

    def runtime_info(self, **changes: object) -> dict[str, object]:
        info = {
            "version": [3, 13, 0], "prefix": str(self.root / ".venv"),
            "source": str(self.root / "src/digital_sztu/__init__.py"),
            "purelib": str(self.root / ".venv/lib/site-packages"),
            "platlib": str(self.root / ".venv/lib/site-packages"), "pip": True,
            "packages": {**bootstrap.locked_packages(self.root), "digital-sztu": "0.1.0"},
        }
        return {**info, **changes}

    def symlink(self, link: Path, target: Path) -> None:
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except OSError as exc:
            self.skipTest(f"Symlink creation requires OS permission: {exc}")

    def registry(self, *, payload: bytes = b"synthetic installer", archived: bool = False,
                 system: str = "macOS", arch: str = "arm64") -> tuple[dict[str, object], Path]:
        asset = {
            "filename": "example.dmg", "platform": system, "arch": arch,
            "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "url": "https://example.invalid/fixed/example.dmg",
        }
        if archived:
            asset["path"] = "fixed/example.dmg"
        write_json(self.root / "importers/registry.json", {
            "schema_version": 1, "tools": [{
                "id": "ciphertalk", "version": "1.2.0", "role": "primary",
                "downloads": [asset],
            }],
        })
        path = (self.root / "importers/fixed/example.dmg" if archived else
                self.root / ".codex-work/downloads/onboarding/ciphertalk/1.2.0/example.dmg")
        return asset, path

    def test_check_missing_environment_is_read_only(self) -> None:
        before = snapshot(self.root)
        with mock.patch.object(bootstrap.platform, "system", return_value="Darwin"), \
                mock.patch.object(bootstrap.shutil, "which", return_value="/tools/git"), \
                mock.patch.object(bootstrap, "run_command",
                                  return_value=subprocess.CompletedProcess([], 0, "git version 2.49.0", "")) as command, \
                mock.patch.object(bootstrap, "urlopen") as network:
            result = bootstrap.bootstrap(self.root, check=True)
        self.assertEqual(result["status"], "pending_user")
        self.assertFalse(result["local_ready"])
        self.assertEqual(result["stages"]["github"]["route"], "local_only")
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual(command.call_args.args[0], ["/tools/git", "--version"])
        self.assertEqual(command.call_count, 1)
        network.assert_not_called()
        self.assertFalse((self.root / ".work").exists())

    def test_unsupported_platform_keeps_manual_path_without_writes(self) -> None:
        before = snapshot(self.root)
        with mock.patch.object(bootstrap.platform, "system", return_value="Linux"):
            result = bootstrap.bootstrap(self.root)
        self.assertEqual(result["status"], "not_applicable")
        self.assertFalse(result["ok"])
        self.assertEqual(before, snapshot(self.root))

    def test_root_conflict_does_not_create_anything(self) -> None:
        target = Path(self.temporary.name) / "unrelated"
        target.mkdir()
        (target / "keep.txt").write_text("user data", encoding="utf-8")
        before = snapshot(target)
        result = bootstrap.bootstrap(target)
        self.assertEqual(result["stages"]["workspace"]["status"], "failed")
        self.assertEqual(before, snapshot(target))

    def test_plugin_cache_is_not_a_user_checkout(self) -> None:
        result = bootstrap.bootstrap(self.root / ".codex/plugins/cache/sztu")
        self.assertEqual(result["status"], "failed")
        self.assertIn("plugin cache", result["stages"]["workspace"]["message"])

    def test_unrelated_file_at_state_path_is_not_overwritten(self) -> None:
        write_json(self.root / bootstrap.STATE, {"my_notes": "keep this"})
        before = snapshot(self.root)
        with mock.patch.object(bootstrap.platform, "system", return_value="Darwin"), \
                mock.patch.object(bootstrap, "run_command") as command:
            result = bootstrap.bootstrap(self.root)
        self.assertEqual(result["status"], "failed")
        self.assertIn("unrelated file", result["stages"]["workspace"]["message"])
        self.assertEqual(before, snapshot(self.root))
        command.assert_not_called()

    def test_old_bootstrap_python_fails_before_writes(self) -> None:
        before = snapshot(self.root)
        with mock.patch.object(bootstrap.sys, "version_info", (3, 10, 9)):
            result = bootstrap.bootstrap(self.root)
        self.assertEqual(result["status"], "failed")
        self.assertIn("3.11", result["stages"]["workspace"]["message"])
        self.assertEqual(before, snapshot(self.root))

    def test_preflight_rejects_output_links_before_any_install(self) -> None:
        for relative in (".venv", ".work", ".work/onboarding/status.json",
                         ".codex-work", ".codex-work/cache/onboarding-pip",
                         ".codex-work/downloads/onboarding"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = checkout(Path(directory))
                outside = Path(directory) / "outside"
                outside.mkdir()
                self.symlink(root / relative, outside)
                before = snapshot(outside)
                with mock.patch.object(bootstrap.platform, "system", return_value="Darwin"), \
                        mock.patch.object(bootstrap, "run_command") as command:
                    result = bootstrap.bootstrap(root)
                self.assertEqual(result["status"], "failed", result)
                command.assert_not_called()
                self.assertEqual(before, snapshot(outside))

    def test_nested_symlinks_and_windows_junctions_are_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        self.symlink(self.root / ".work/onboarding/examples/escape", outside)
        with self.assertRaises(ValueError):
            bootstrap.check_tree(self.root, ".work/onboarding")
        # is_junction() is available on supported Windows Python versions.
        with mock.patch.object(Path, "is_junction", create=True, return_value=True):
            with self.assertRaises(ValueError):
                bootstrap.local_path(self.root, ".work")
        with mock.patch.object(Path, "is_symlink", return_value=False), \
                mock.patch.object(Path, "is_junction", create=True, return_value=False), \
                mock.patch.object(Path, "lstat", return_value=SimpleNamespace(st_file_attributes=0x400)):
            self.assertTrue(bootstrap.is_link(self.root / "windows-311-junction"))

    def test_venv_interpreter_link_is_allowed_but_site_packages_cannot_escape(self) -> None:
        self.symlink(self.root / ".venv/bin/python", Path(sys.executable).resolve())
        bootstrap.check_tree(self.root, ".venv", venv=True)
        outside = Path(self.temporary.name) / "global-packages"
        outside.mkdir()
        self.symlink(self.root / ".venv/lib/site-packages", outside)
        with self.assertRaises(ValueError):
            bootstrap.check_tree(self.root, ".venv", venv=True)

    def test_path_traversal_and_windows_absolute_paths_are_rejected(self) -> None:
        for value in ("../outside", ".work/../../escape", "/outside", r"C:\escape", ".work/file:stream"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bootstrap.local_path(self.root, value)

    def test_existing_non_venv_and_incomplete_venv_are_not_overwritten(self) -> None:
        target = self.root / ".venv"
        target.mkdir()
        (target / "keep.txt").write_text("owned by user", encoding="utf-8")
        with self.assertRaises(ValueError):
            bootstrap.prepare_runtime(self.root, False, [])
        (target / "pyvenv.cfg").write_text("home = unavailable\n", encoding="utf-8")
        before = snapshot(target)
        with mock.patch.object(bootstrap, "run_command") as command:
            result = bootstrap.prepare_runtime(self.root, False, [])
        self.assertEqual(result["reason"], "incomplete_venv")
        self.assertEqual(before, snapshot(target))
        command.assert_not_called()

    def test_global_site_packages_are_not_used_as_an_isolated_install(self) -> None:
        self.fake_venv()
        (self.root / ".venv/pyvenv.cfg").write_text(
            "include-system-site-packages = true\n", encoding="utf-8")
        with mock.patch.object(bootstrap, "run_command") as command:
            result = bootstrap.prepare_runtime(self.root, False, [])
        self.assertEqual(result["reason"], "global_site_packages")
        command.assert_not_called()

    def test_existing_valid_environment_is_reused_without_pip(self) -> None:
        executable = self.fake_venv()
        with mock.patch.object(bootstrap, "command_json", return_value=self.runtime_info()) as probe, \
                mock.patch.object(bootstrap, "run_command") as command:
            result = bootstrap.prepare_runtime(self.root, False, [])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(probe.call_args.args[0][0], str(executable))
        command.assert_not_called()
        self.assertFalse((self.root / ".codex-work").exists())

    def test_old_venv_and_wrong_checkout_require_repair(self) -> None:
        self.fake_venv()
        with mock.patch.object(bootstrap, "command_json",
                               return_value=self.runtime_info(version=[3, 10, 9])):
            self.assertEqual(bootstrap.prepare_runtime(self.root, False, [])["reason"], "old_python")
        with mock.patch.object(bootstrap, "command_json",
                               return_value=self.runtime_info(source="/different/src/__init__.py")):
            self.assertEqual(bootstrap.inspect_runtime(self.root)["reason"], "dependencies")
        with mock.patch.object(bootstrap, "command_json",
                               return_value=self.runtime_info(prefix=str(self.root.parent))):
            with self.assertRaises(ValueError):
                bootstrap.inspect_runtime(self.root)
        with mock.patch.object(bootstrap, "command_json",
                               return_value=self.runtime_info(purelib=str(self.root.parent))):
            with self.assertRaises(ValueError):
                bootstrap.inspect_runtime(self.root)

    def test_fresh_runtime_creation_uses_argument_arrays_and_locked_pins(self) -> None:
        pending = bootstrap.stage("pending_user", "dependencies", reason="dependencies")
        completed = bootstrap.stage("completed", "ready")
        operations: list[dict[str, object]] = []

        def command(args: list[str], root: Path, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[1:3] == ["-m", "venv"]:
                self.fake_venv()
            return response()

        with mock.patch.object(bootstrap, "run_command", side_effect=command) as run, \
                mock.patch.object(bootstrap, "inspect_runtime", side_effect=[pending, completed, completed]):
            first = bootstrap.prepare_runtime(self.root, False, operations)
            second = bootstrap.prepare_runtime(self.root, False, operations)
        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[0].args[0][-1], str(self.root / ".venv"))
        self.assertIn(str(self.root / "requirements.lock"), run.call_args_list[1].args[0])
        self.assertEqual(run.call_args_list[2].args[0][-1], str(self.root))
        self.assertEqual([item["operation"] for item in operations],
                         ["create_venv", "install_locked_dependencies", "install_editable_cli"])

    def test_failed_install_can_resume_without_recreating_venv_or_logging_secrets(self) -> None:
        self.fake_venv()
        pending = bootstrap.stage("pending_user", "dependencies", reason="dependencies")
        completed = bootstrap.stage("completed", "ready")
        failure = subprocess.CompletedProcess([], 1, "private-index-credential", "private-proxy-credential")
        with mock.patch.object(bootstrap, "inspect_runtime", return_value=pending), \
                mock.patch.object(bootstrap, "run_command", return_value=failure):
            with self.assertRaisesRegex(RuntimeError, "依赖安装失败") as error:
                bootstrap.prepare_runtime(self.root, False, [])
        self.assertNotIn("credential", str(error.exception))
        operations: list[dict[str, object]] = []
        with mock.patch.object(bootstrap, "inspect_runtime", side_effect=[pending, completed]), \
                mock.patch.object(bootstrap, "run_command", return_value=response()) as command:
            self.assertEqual(bootstrap.prepare_runtime(self.root, False, operations)["status"], "completed")
        self.assertEqual(command.call_count, 2)
        self.assertNotIn("create_venv", [item["operation"] for item in operations])

    def test_lock_file_requires_exact_unique_versions(self) -> None:
        for text in ("", "jsonschema>=4.20\n", "attrs==1\nattrs==2\n", "-e ./other\n"):
            with self.subTest(text=text):
                (self.root / "requirements.lock").write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    bootstrap.locked_packages(self.root)

    def test_pip_cannot_be_redirected_to_global_install_directories(self) -> None:
        with mock.patch.dict(os.environ, {
            "PYTHONPATH": "/elsewhere", "PYTHONHOME": "/elsewhere", "PIP_TARGET": "/global",
            "PIP_PREFIX": "/global", "PIP_ROOT": "/global", "PIP_USER": "true",
            "PIP_PYTHON": "/other/python", "PIP_LOG": "/elsewhere/pip.log",
            "PIP_REPORT": "/elsewhere/report.json", "PIP_SRC": "/elsewhere/source",
            "PIP_BUILD_TRACKER": "/elsewhere/build-state",
        }):
            env = bootstrap.process_env(self.root)
        for name in (
            "PYTHONPATH", "PYTHONHOME", "PIP_TARGET", "PIP_PREFIX", "PIP_ROOT",
            "PIP_PYTHON", "PIP_LOG", "PIP_REPORT", "PIP_SRC", "PIP_BUILD_TRACKER",
        ):
            self.assertNotIn(name, env)
        self.assertEqual(env["PIP_USER"], "0")
        self.assertEqual(env["PIP_REQUIRE_VIRTUALENV"], "true")
        self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)
        self.assertTrue(env["PIP_CACHE_DIR"].startswith(str(self.root)))

    def test_example_check_and_partial_input_recovery_are_read_only(self) -> None:
        with mock.patch.object(bootstrap, "run_cli") as command:
            self.assertEqual(bootstrap.prepare_example(self.root, True, [])["reason"], "missing_example")
            inputs = bootstrap.example_inputs(self.root)
            revision = bootstrap.example_revision(self.root, inputs)
            destination = self.root / ".work/onboarding/examples" / revision
            name, content = next(iter(inputs.items()))
            path = destination / name
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
            before = snapshot(destination)
            self.assertEqual(bootstrap.prepare_example(self.root, True, [])["reason"], "incomplete_example")
            self.assertEqual(before, snapshot(destination))
        command.assert_not_called()

    def test_edited_example_input_is_not_overwritten(self) -> None:
        inputs = bootstrap.example_inputs(self.root)
        revision = bootstrap.example_revision(self.root, inputs)
        name = next(iter(inputs))
        path = self.root / ".work/onboarding/examples" / revision / name
        path.parent.mkdir(parents=True)
        path.write_text("user changed this", encoding="utf-8")
        with mock.patch.object(bootstrap, "run_cli") as command, self.assertRaises(ValueError):
            bootstrap.prepare_example(self.root, False, [])
        self.assertEqual(path.read_text(encoding="utf-8"), "user changed this")
        command.assert_not_called()

    def test_missing_registry_is_pending_not_tool_install_success(self) -> None:
        self.assertEqual(bootstrap.inspect_tools(self.root, "Darwin", "arm64")["reason"], "registry_pending")

    def test_example_outputs_without_a_receipt_are_not_overwritten(self) -> None:
        inputs = bootstrap.example_inputs(self.root)
        revision = bootstrap.example_revision(self.root, inputs)
        destination = self.root / ".work/onboarding/examples" / revision
        for name, content in inputs.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        transcript = destination / ".work/chat/transcript.html"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("user output without an acceptance receipt", encoding="utf-8")
        before = snapshot(destination)
        for check in (True, False):
            with self.subTest(check=check), mock.patch.object(bootstrap, "run_cli") as command:
                result = bootstrap.prepare_example(self.root, check, [])
            self.assertEqual(result["status"], "pending_user")
            self.assertEqual(result["reason"], "unverified_outputs")
            self.assertEqual(before, snapshot(destination))
            command.assert_not_called()

    def test_delivered_registry_selects_pinned_platform_assets_without_downloads(self) -> None:
        registry = json.loads((ROOT / "importers/registry.json").read_text(encoding="utf-8"))
        write_json(self.root / "importers/registry.json", registry)
        primary = next(tool for tool in registry["tools"] if tool["id"] == "ciphertalk")
        before = snapshot(self.root)
        for system, architecture, expected_platform in (
            ("Darwin", "arm64", "macOS"), ("Windows", "AMD64", "Windows"),
        ):
            with self.subTest(system=system), \
                    mock.patch.object(bootstrap, "installed_ciphertalk", return_value=None), \
                    mock.patch.object(bootstrap, "urlopen") as network:
                result = bootstrap.inspect_tools(self.root, system, architecture)
            self.assertEqual(result["status"], "pending_user")
            items = {item["id"]: item for item in result["items"]}
            self.assertEqual(set(items), {"ciphertalk", "wechatmsg"})
            item = items["ciphertalk"]
            asset = next(asset for asset in primary["downloads"]
                         if asset["platform"] == expected_platform)
            self.assertEqual(item["version"], primary["version"])
            self.assertEqual(item["download_url"], asset["url"])
            self.assertEqual(item["sha256"], asset["sha256"])
            self.assertEqual(item["size_bytes"], asset["size_bytes"])
            self.assertEqual(item["payload"]["reason"], "missing_payload")
            self.assertEqual(items["wechatmsg"]["status"], "not_applicable")
            self.assertFalse(result["execution_tested"])
            network.assert_not_called()
        self.assertEqual(before, snapshot(self.root))

    def test_payload_requires_exact_size_hash_and_actual_lfs_bytes(self) -> None:
        asset, path = self.registry()
        self.assertEqual(bootstrap.verify_payload(path, asset)["reason"], "missing_payload")
        path.parent.mkdir(parents=True)
        path.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:123\nsize 1\n", encoding="utf-8")
        self.assertEqual(bootstrap.verify_payload(path, asset)["reason"], "lfs_pointer")
        path.write_bytes(b"incorrect")
        self.assertEqual(bootstrap.verify_payload(path, asset)["reason"], "payload_mismatch")
        path.write_bytes(b"synthetic installer")
        self.assertEqual(bootstrap.verify_payload(path, asset)["status"], "completed")
        bad_hash = {**asset, "sha256": "0" * 64}
        self.assertEqual(bootstrap.verify_payload(path, bad_hash)["reason"], "payload_mismatch")

    def test_verified_installer_alone_is_not_an_installed_application(self) -> None:
        _, path = self.registry()
        path.parent.mkdir(parents=True)
        path.write_bytes(b"synthetic installer")
        with mock.patch.object(bootstrap, "installed_ciphertalk", return_value=None):
            result = bootstrap.inspect_tools(self.root, "Darwin", "aarch64")
        self.assertEqual(result["status"], "pending_user")
        self.assertEqual(result["items"][0]["payload"]["status"], "completed")
        with mock.patch.object(bootstrap, "installed_ciphertalk",
                               return_value={"version": "1.2.0", "path": "fixture app"}):
            result = bootstrap.inspect_tools(self.root, "Darwin", "arm64")
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["execution_tested"])

    def test_platform_selection_catalog_only_and_source_backup_are_not_installs(self) -> None:
        self.registry(system="Windows", arch="x64")
        with mock.patch.object(bootstrap, "installed_ciphertalk", return_value=None):
            self.assertEqual(bootstrap.inspect_tools(self.root, "Darwin", "arm64")["status"], "not_applicable")
            self.assertEqual(bootstrap.inspect_tools(self.root, "Windows", "AMD64")["status"], "pending_user")
        path = self.root / "importers/registry.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["tools"] += [
            {"id": "research-only", "role": "catalog-only-research"},
            {"id": "wechatmsg", "version": "3.0.0", "role": "windows-historical-source-backup", "downloads": []},
        ]
        write_json(path, value)
        result = bootstrap.inspect_tools(self.root, "Darwin", "arm64")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][1]["status"], "not_applicable")

    def test_registry_rejects_ambiguous_missing_hash_and_outside_payloads(self) -> None:
        asset, _ = self.registry()
        for downloads in ([asset, asset], [{**asset, "sha256": ""}],
                          [{**asset, "path": "../outside.dmg"}],
                          [{**asset, "url": "http://example.invalid/installer"}]):
            with self.subTest(downloads=downloads):
                write_json(self.root / "importers/registry.json", {"schema_version": 1, "tools": [{
                    "id": "ciphertalk", "version": "1.2.0", "role": "primary", "downloads": downloads,
                }]})
                with self.assertRaises(ValueError):
                    bootstrap.inspect_tools(self.root, "Darwin", "arm64")

    def fake_download(self, payload: bytes) -> io.BytesIO:
        stream = io.BytesIO(payload)
        stream.geturl = lambda: "https://example.invalid/exact"
        return stream

    def test_download_is_verified_cached_and_not_repeated(self) -> None:
        asset, path = self.registry()
        operations: list[dict[str, object]] = []
        with mock.patch.object(bootstrap, "urlopen", return_value=self.fake_download(b"synthetic installer")) as network:
            self.assertEqual(bootstrap.download_payload(self.root, path, asset, operations)["status"], "completed")
            before = snapshot(path.parent)
            self.assertEqual(bootstrap.download_payload(self.root, path, asset, operations)["status"], "completed")
        network.assert_called_once_with(asset["url"], timeout=30)
        self.assertEqual(before, snapshot(path.parent))
        self.assertEqual(len(operations), 1)
        self.assertFalse(list(path.parent.glob(".download-*")))

    def test_download_network_failure_or_wrong_bytes_never_leave_an_installer(self) -> None:
        asset, path = self.registry()
        for effect in (URLError("private proxy detail"), self.fake_download(b"wrong bytes")):
            with self.subTest(effect=type(effect).__name__):
                kwargs = {"side_effect": effect} if isinstance(effect, Exception) else {"return_value": effect}
                with mock.patch.object(bootstrap, "urlopen", **kwargs):
                    result = bootstrap.download_payload(self.root, path, asset, [])
                self.assertEqual(result["status"], "failed")
                self.assertNotIn("private proxy", json.dumps(result))
                self.assertFalse(path.exists())
                self.assertFalse(list(path.parent.glob(".download-*")))

    def test_download_checks_space_and_does_not_overwrite_bad_existing_file(self) -> None:
        asset, path = self.registry()
        with mock.patch.object(bootstrap.shutil, "disk_usage", return_value=SimpleNamespace(free=1)), \
                mock.patch.object(bootstrap, "urlopen") as network:
            self.assertEqual(bootstrap.download_payload(self.root, path, asset, [])["reason"], "disk_space")
        network.assert_not_called()
        path.write_bytes(b"user file")
        with mock.patch.object(bootstrap, "urlopen") as network:
            self.assertEqual(bootstrap.download_payload(self.root, path, asset, [])["reason"], "payload_mismatch")
        self.assertEqual(path.read_bytes(), b"user file")
        network.assert_not_called()

    def test_lfs_pointer_remains_untouched_when_exact_payload_is_cached(self) -> None:
        _, path = self.registry(archived=True)
        path.parent.mkdir(parents=True)
        pointer = b"version https://git-lfs.github.com/spec/v1\n"
        path.write_bytes(pointer)
        with mock.patch.object(bootstrap, "installed_ciphertalk", return_value=None), \
                mock.patch.object(bootstrap, "urlopen", return_value=self.fake_download(b"synthetic installer")):
            result = bootstrap.inspect_tools(self.root, "Darwin", "arm64", download=True)
        item = result["items"][0]
        self.assertEqual(item["archived_payload"]["reason"], "lfs_pointer")
        self.assertEqual(item["payload"]["reason"], "payload_verified")
        self.assertEqual(result["status"], "pending_user")
        self.assertEqual(path.read_bytes(), pointer)

    def test_application_version_comparison(self) -> None:
        self.assertTrue(bootstrap.same_version("2026.829.0.0", "2026.829.0"))
        self.assertFalse(bootstrap.same_version("2026.830.0", "2026.829.0"))
        self.assertFalse(bootstrap.same_version("1.2.0-beta", "1.2.0"))

    def test_github_default_does_not_inspect_accounts(self) -> None:
        with mock.patch.object(bootstrap, "run_command") as command, \
                mock.patch.object(bootstrap.shutil, "which") as which:
            result = bootstrap.inspect_github(self.root, False)
        self.assertEqual(result["route"], "local_only")
        command.assert_not_called()
        which.assert_not_called()

    def test_git_must_actually_run_not_only_exist_on_path(self) -> None:
        with mock.patch.object(bootstrap.shutil, "which", return_value=None):
            self.assertEqual(bootstrap.inspect_workspace(self.root)["reason"], "missing_git")
        with mock.patch.object(bootstrap.shutil, "which", return_value="/tools/git"), \
                mock.patch.object(bootstrap, "run_command", return_value=response(code=1)):
            self.assertEqual(bootstrap.inspect_workspace(self.root)["reason"], "git_not_ready")
        with mock.patch.object(bootstrap.shutil, "which", return_value="/tools/git"), \
                mock.patch.object(bootstrap, "run_command",
                                  return_value=subprocess.CompletedProcess([], 0, "git version 2.49.0.windows.1", "")):
            self.assertEqual(bootstrap.inspect_workspace(self.root)["git_version"], "2.49.0")

    def test_github_login_branch_and_fork_routes_never_mutate_remotes(self) -> None:
        config = self.root / ".git/config"
        config.parent.mkdir()
        config.write_text('[remote "origin"]\nurl = https://example.invalid/mine.git\n', encoding="utf-8")
        before = snapshot(config.parent)
        for permission, expected in ((True, "branch"), (False, "fork"), (None, "check_permissions")):
            with self.subTest(permission=permission), \
                    mock.patch.object(bootstrap.shutil, "which", return_value="/tools/gh"), \
                    mock.patch.object(bootstrap, "run_command",
                                      side_effect=[response(), response({"permissions": {"push": permission}})]) as command:
                result = bootstrap.inspect_github(self.root, True)
                self.assertEqual(result["route"], expected)
                self.assertFalse(result["remote_changed"])
                self.assertEqual([call.args[0][:2] for call in command.call_args_list],
                                 [["gh", "auth"], ["gh", "api"]])
        with mock.patch.object(bootstrap.shutil, "which", return_value="/tools/gh"), \
                mock.patch.object(bootstrap, "run_command", return_value=response(code=1)):
            self.assertEqual(bootstrap.inspect_github(self.root, True)["route"], "login")
        with mock.patch.object(bootstrap.shutil, "which", return_value=None):
            self.assertEqual(bootstrap.inspect_github(self.root, True)["route"], "install_gh")
        self.assertEqual(before, snapshot(config.parent))

    def test_partial_success_and_failure_are_saved_as_separate_stages(self) -> None:
        with mock.patch.object(bootstrap.platform, "system", return_value="Darwin"), \
                mock.patch.object(bootstrap, "inspect_workspace", return_value=bootstrap.stage("completed", "ready")), \
                mock.patch.object(bootstrap, "prepare_runtime", return_value=bootstrap.stage("completed", "ready")), \
                mock.patch.object(bootstrap, "prepare_example", return_value=bootstrap.stage("completed", "ready")):
            result = bootstrap.bootstrap(self.root)
        self.assertTrue(result["local_ready"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "pending_user")
        self.assertEqual(result["stages"]["tools"]["reason"], "registry_pending")
        stored = json.loads((self.root / bootstrap.STATE).read_text(encoding="utf-8"))
        self.assertEqual(result, stored)
        with mock.patch.object(bootstrap.platform, "system", return_value="Darwin"), \
                mock.patch.object(bootstrap, "prepare_runtime",
                                  side_effect=subprocess.TimeoutExpired("sensitive-command", 1)):
            failed = bootstrap.bootstrap(self.root)
        self.assertEqual(failed["stages"]["runtime"]["status"], "failed")
        self.assertEqual(failed["stages"]["example"]["status"], "pending_user")
        self.assertNotIn("sensitive-command", json.dumps(failed))

    def test_json_envelope_and_exit_codes_preserve_partial_state(self) -> None:
        for status, code in (("completed", 0), ("pending_user", 1), ("failed", 2), ("not_applicable", 1)):
            with self.subTest(status=status), mock.patch.object(
                bootstrap, "bootstrap", return_value={"ok": status == "completed", "status": status}
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(bootstrap.main(["--root", str(self.root), "--check", "--json"]), code)
                envelope = json.loads(output.getvalue())
                self.assertEqual(envelope["operation"], "bootstrap")
                self.assertEqual(envelope["data"]["status"], status)


@unittest.skipUnless(
    os.environ.get("SZTU_BOOTSTRAP_INTEGRATION") == "1" and platform.system() in ("Darwin", "Windows"),
    "Opt-in macOS/Windows core integration; no GUI app or client acceptance is implied",
)
class BootstrapIntegrationTests(unittest.TestCase):
    def test_real_fresh_repeat_readonly_and_interruption_recovery(self) -> None:
        cache = ROOT / ".codex-work/tmp"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="bootstrap-integration-", dir=cache) as directory:
            root = checkout(Path(directory))
            external_pip_output = Path(directory) / "outside-checkout"
            # Non-empty formal data must not be interpreted as a failed setup.
            shutil.copytree(root / "examples/minimal/content", root / "content")
            shutil.copytree(root / "examples/minimal/sources", root / "sources/records")
            canonical = {key: snapshot(root / key) for key in ("content", "sources")}

            def run(*flags: str) -> dict[str, object]:
                result = subprocess.run(
                    [sys.executable, "-B", str(root / "scripts/bootstrap.py"),
                     "--root", str(root), "--json", *flags],
                    cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=600,
                    env={
                        **os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
                        "PIP_ROOT": str(external_pip_output),
                        "PIP_PYTHON": str(external_pip_output / "python"),
                        "PIP_LOG": str(external_pip_output / "pip.log"),
                        "PIP_REPORT": str(external_pip_output / "report.json"),
                        "PIP_BUILD_TRACKER": str(external_pip_output / "build-state"),
                    },
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                return json.loads(result.stdout)["data"]

            before = snapshot(root)
            self.assertFalse(run("--check")["local_ready"])
            self.assertEqual(before, snapshot(root))
            first = run()
            self.assertTrue(first["local_ready"], first)
            self.assertFalse(first["ok"])  # This fixture deliberately omits the tool registry.
            self.assertEqual(first["stages"]["tools"]["reason"], "registry_pending")
            self.assertEqual(first["stages"]["github"]["route"], "local_only")
            example = first["stages"]["example"]
            for key in ("timeline", "backlinks", "knowledge", "chat_html"):
                self.assertTrue(Path(example[key]).is_file(), key)
            self.assertTrue(example["deterministic"])
            second = run()
            self.assertTrue(second["local_ready"], second)
            self.assertEqual(second["operations"], [])
            before = snapshot(root)
            self.assertTrue(run("--check")["local_ready"])
            self.assertEqual(before, snapshot(root))
            # Remove only our own fixture output to model an interrupted export.
            Path(example["knowledge"]).unlink()
            self.assertEqual(run("--check")["stages"]["example"]["status"], "pending_user")
            resumed = run()
            self.assertTrue(resumed["local_ready"], resumed)
            self.assertEqual([item["operation"] for item in resumed["operations"]],
                             ["example_checks_and_two_builds"])
            # Edited outputs are never silently replaced on a later run.
            Path(example["chat_html"]).write_text("my notes", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(root / "scripts/bootstrap.py"), "--root", str(root), "--json"],
                cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=60,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(Path(example["chat_html"]).read_text(encoding="utf-8"), "my notes")
            self.assertEqual(canonical, {key: snapshot(root / key) for key in ("content", "sources")})
            self.assertFalse(external_pip_output.exists())


if __name__ == "__main__":
    unittest.main()

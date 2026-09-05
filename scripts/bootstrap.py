#!/usr/bin/env python3
"""Prepare a user checkout without installing a client or publishing records.

This entry point deliberately uses only the Python standard library. System
installers, application permissions, and GitHub mutations belong to the guided
Agent workflow, not to this process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import urlopen

# Also keep --check from creating bytecode when importing the shared utilities.
sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from digital_sztu.utils import ensure_within, load_json, sha256_file, write_json


UPSTREAM = "Shuang-su/digital-sztu"
GUIDE = "docs/GETTING_STARTED.md"
STATE = ".work/onboarding/status.json"
PROBE = """
import importlib.metadata as m, importlib.util, json, sys, sysconfig
packages = {}
for name in json.loads(sys.argv[1]):
    try:
        packages[name] = m.version(name)
    except m.PackageNotFoundError:
        packages[name] = None
spec = importlib.util.find_spec("digital_sztu")
print(json.dumps({"version": list(sys.version_info[:3]), "prefix": sys.prefix,
                  "source": spec.origin if spec else None,
                  "pip": importlib.util.find_spec("pip") is not None,
                  "packages": packages, "purelib": sysconfig.get_path("purelib"),
                  "platlib": sysconfig.get_path("platlib")}))
"""


def stage(status: str, message: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "message": message, **details}


def is_link(path: Path) -> bool:
    # Windows directory junctions can escape a checkout without is_symlink().
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        # pathlib.is_junction arrived after our Python 3.11 minimum. Reject
        # reparse points there too, including junctions to other in-repo trees.
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False


def local_path(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts or "\\" in relative or ":" in relative:
        raise ValueError("Expected a repository-relative path without traversal")
    current = root
    for part in value.parts:
        current = current / part
        if is_link(current):
            raise ValueError(f"Path must not pass through a link: {relative}")
    return ensure_within(current, root)


def check_tree(root: Path, relative: str, *, venv: bool = False) -> Path:
    """Preflight every existing output before copying or starting a writer."""
    path = local_path(root, relative)
    if path.exists() and not path.is_dir():
        raise ValueError(f"Expected a directory: {relative}")
    if not path.exists():
        return path
    for directory, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            child = Path(directory) / name
            if is_link(child):
                # Standard venvs symlink their interpreter to the base Python.
                interpreter = (
                    venv and child.parent == path / "bin"
                    and re.fullmatch(r"python(?:\d+(?:\.\d+)?)?", name)
                )
                if interpreter:
                    if not child.is_file():
                        raise ValueError("The virtual environment interpreter link is broken")
                elif venv:
                    ensure_within(child, path)
                else:
                    raise ValueError(f"Output contains a link: {child.relative_to(root)}")
    return path


def process_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    # Inherited pip options must not redirect installs, build state, or detailed
    # logs outside this checkout, nor choose a different interpreter.
    for name in (
        "PYTHONPATH", "PYTHONHOME", "PIP_TARGET", "PIP_PREFIX", "PIP_ROOT",
        "PIP_PYTHON", "PIP_LOG", "PIP_REPORT", "PIP_SRC", "PIP_BUILD_TRACKER",
    ):
        env.pop(name, None)
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_CONFIG_FILE": os.devnull, "PIP_USER": "0",
        "PIP_REQUIRE_VIRTUALENV": "true", "GIT_OPTIONAL_LOCKS": "0",
        "PIP_CACHE_DIR": str(root / ".codex-work/cache/onboarding-pip"),
    })
    return env


def run_command(args: list[str], root: Path, *, timeout: int = 60,
                env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=root, env=env or process_env(root), shell=False,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


def command_json(args: list[str], root: Path) -> dict[str, Any]:
    result = run_command(args, root)
    if result.returncode:
        # Do not persist arbitrary command output: pip/gh may print credentials
        # from the user's index, proxy or authentication configuration.
        raise RuntimeError(f"Command failed (exit {result.returncode}); see {GUIDE}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object from the command")
    return value


def venv_python(root: Path, system: str | None = None) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if (system or platform.system()) == "Windows"
                            else "bin/python")


def locked_packages(root: Path) -> dict[str, str]:
    result = {}
    for line in local_path(root, "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if not match or match[1] in result:
            raise ValueError("requirements.lock must contain unique, exact package pins")
        result[match[1]] = match[2]
    if not result:
        raise ValueError("requirements.lock must not be empty")
    return result


def inspect_runtime(root: Path) -> dict[str, Any]:
    pins = locked_packages(root)
    executable = venv_python(root)
    if not executable.is_file():
        return stage("pending_user", "需要创建或修复项目虚拟环境。", reason="missing_venv")
    info = command_json([str(executable), "-B", "-c", PROBE,
                         json.dumps([*pins, "digital-sztu"])], root)
    if tuple(info["version"]) < (3, 11):
        return stage("pending_user", "现有虚拟环境的 Python 低于 3.11；请先确认迁移方式。",
                     reason="old_python", python=info["version"])
    expected = (root / ".venv").resolve()
    if Path(info["prefix"]).resolve() != expected:
        raise ValueError("Interpreter is not using this checkout's .venv")
    for key in ("purelib", "platlib"):
        ensure_within(Path(info[key]), expected)
    missing = [name for name, version in pins.items() if info["packages"].get(name) != version]
    source = info.get("source")
    linked = bool(source and Path(source).resolve() == root / "src/digital_sztu/__init__.py"
                  and info["packages"].get("digital-sztu"))
    ready = not missing and linked and info["pip"]
    return stage(
        "completed" if ready else "pending_user",
        "项目 Python 与 CLI 可用。" if ready else "需要按锁文件补齐项目依赖。",
        reason="ready" if ready else "dependencies", python=info["version"],
        interpreter=str(executable), missing_packages=missing, editable_checkout=linked,
    )


def prepare_runtime(root: Path, check: bool, operations: list[dict[str, Any]]) -> dict[str, Any]:
    target = check_tree(root, ".venv", venv=True)
    executable = venv_python(root)
    if target.exists() and not (target / "pyvenv.cfg").is_file():
        raise ValueError(".venv already exists but is not a Python virtual environment")
    if target.exists() and re.search(
        r"(?im)^include-system-site-packages\s*=\s*true\s*$",
        (target / "pyvenv.cfg").read_text(encoding="utf-8"),
    ):
        return stage("pending_user", "现有虚拟环境会读取全局包；请确认迁移到隔离环境。",
                     reason="global_site_packages")
    if not executable.is_file():
        if check:
            return stage("pending_user", "尚未创建项目虚拟环境。", reason="missing_venv")
        if target.exists():
            return stage("pending_user", "现有虚拟环境不完整；请核对后修复，不会覆盖或删除。",
                         reason="incomplete_venv")
        result = run_command([sys.executable, "-m", "venv", str(target)], root, timeout=180)
        operations.append({"operation": "create_venv", "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError("创建虚拟环境失败；检查 Python 的 venv/ensurepip 与目录权限。")
        check_tree(root, ".venv", venv=True)
    current = inspect_runtime(root)
    if check or current["status"] == "completed" or current.get("reason") == "old_python":
        return current
    cache = check_tree(root, ".codex-work/cache/onboarding-pip")
    cache.mkdir(parents=True, exist_ok=True)
    commands = [
        [str(executable), "-m", "pip", "install", "-r", str(root / "requirements.lock")],
        [str(executable), "-m", "pip", "install", "--no-deps", "-e", str(root)],
    ]
    for label, command in zip(("install_locked_dependencies", "install_editable_cli"), commands):
        result = run_command(command, root, timeout=300)
        operations.append({"operation": label, "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError("依赖安装失败；检查网络、包索引和磁盘空间后重复运行即可继续。")
    return inspect_runtime(root)


def example_inputs(root: Path) -> dict[str, bytes]:
    inputs = {}
    for source, destination in (
        ("schemas", "schemas"),
        ("examples/minimal/content", "content"),
        ("examples/minimal/sources", "sources/records"),
        ("examples/chat", "examples/chat"),
    ):
        directory = local_path(root, source)
        if not directory.is_dir():
            raise ValueError(f"Missing example input: {source}")
        for item in sorted(directory.rglob("*")):
            item = local_path(root, item.relative_to(root).as_posix())
            if item.is_file():
                inputs[f"{destination}/{item.relative_to(directory).as_posix()}"] = item.read_bytes()
    for name in ("connect.config.json", "AGENTS.md", ".codex-plugin/plugin.json"):
        inputs[name] = local_path(root, name).read_bytes()
    inputs["README.md"] = "# Digital SZTU 示例\n\n仅用于初始化演示，不是真实校园史料。\n".encode()
    if "examples/chat/messages.example.jsonl" not in inputs:
        raise ValueError("Missing synthetic chat example")
    return inputs


def example_revision(root: Path, inputs: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    files = dict(inputs)
    for item in sorted((root / "src/digital_sztu").glob("*.py")):
        files[f"implementation/{item.name}"] = local_path(root, item.relative_to(root).as_posix()).read_bytes()
    files["requirements.lock"] = local_path(root, "requirements.lock").read_bytes()
    for name, value in sorted(files.items()):
        digest.update(name.encode() + b"\0" + hashlib.sha256(value).digest())
    return digest.hexdigest()[:16]


def file_hashes(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): sha256_file(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def run_cli(root: Path, example: Path, arguments: list[str]) -> dict[str, Any]:
    result = command_json([str(venv_python(root)), "-B", "-m", "digital_sztu",
                           "--root", str(example), *arguments, "--json"], root)
    if not result.get("ok"):
        raise RuntimeError(f"Example check failed: {arguments[0]}")
    return result["data"]


def prepare_example(root: Path, check: bool, operations: list[dict[str, Any]]) -> dict[str, Any]:
    inputs = example_inputs(root)
    revision = example_revision(root, inputs)
    relative = f".work/onboarding/examples/{revision}"
    destination = check_tree(root, relative)
    if check and not destination.exists():
        return stage("pending_user", "尚未生成本地示例；运行一次初始化即可。",
                     reason="missing_example")
    # Validate all existing inputs first, then fill only missing files. Never
    # overwrite a user's edits to a previously generated example.
    for name, value in inputs.items():
        path = local_path(root, f"{relative}/{name}")
        if path.exists() and (not path.is_file() or path.read_bytes() != value):
            raise ValueError(f"Existing example input was changed: {name}")
        if check and not path.exists():
            return stage("pending_user", "示例输入尚未复制完成；重复运行初始化即可继续。",
                         reason="incomplete_example")
    if not check:
        for name, value in inputs.items():
            path = local_path(root, f"{relative}/{name}")
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation also protects against concurrent setup.
                with path.open("xb") as handle:
                    handle.write(value)
    receipt_path = local_path(root, f"{relative}/.work/bootstrap-result.json")
    generated = destination / "data/generated"
    transcript = destination / ".work/chat/transcript.html"
    export = destination / ".work/knowledge/chunks.jsonl"
    outputs = (generated, transcript, export)
    if not receipt_path.is_file() and any(
        path.exists() and (not path.is_dir() or any(path.iterdir())) for path in outputs
    ):
        # Without a receipt, even apparently derived files may be user-owned.
        # Do not guess that they came from an interrupted bootstrap invocation.
        return stage("pending_user", "已有示例输出但缺少验收回执；保留文件，请先核对来源与恢复方式。",
                     reason="unverified_outputs")
    for command in ("doctor", "validate", "privacy-scan"):
        run_cli(root, destination, [command])
    run_cli(root, destination, ["validate-chat", str(destination / "examples/chat/messages.example.jsonl")])
    complete = False
    if receipt_path.is_file():
        receipt = load_json(receipt_path)
        existing = file_hashes(generated)
        expected = receipt.get("generated", {})
        if (receipt.get("revision") != revision or not isinstance(expected, dict)
                or any(expected.get(name) != value for name, value in existing.items())
                or (transcript.is_file() and receipt.get("transcript") != sha256_file(transcript))
                or (export.is_file() and receipt.get("export") != sha256_file(export))):
            return stage("failed", "示例输出有改动；保留现场，请核对后另选工作副本或人工恢复。",
                         reason="changed_outputs")
        complete = bool(existing and existing == expected and all(path.exists() for path in outputs))
    if check:
        if not complete:
            return stage("pending_user", "示例输出尚未完成；重复运行初始化即可继续。",
                         reason="incomplete_example")
    elif not complete:
        run_cli(root, destination, ["build"])
        first = file_hashes(generated)
        run_cli(root, destination, ["build"])
        if not first or first != file_hashes(generated):
            raise RuntimeError("Two example builds did not produce identical files")
        run_cli(root, destination, ["export-knowledge", "--output", ".work/knowledge"])
        run_cli(root, destination, [
            "render-chat", str(destination / "examples/chat/messages.example.jsonl"),
            "--title", "Digital SZTU 聊天结构示例", "--output", ".work/chat/transcript.html",
        ])
        write_json(receipt_path, {"revision": revision, "generated": first,
                                  "transcript": sha256_file(transcript), "export": sha256_file(export)})
        operations.append({"operation": "example_checks_and_two_builds", "exit_code": 0})
    return stage("completed", "隔离示例可用；没有添加正式校园记录。", revision=revision,
                 example=str(destination), timeline=str(generated / "timeline.json"),
                 backlinks=str(generated / "backlinks.json"), knowledge=str(export),
                 chat_html=str(transcript), deterministic=True)


def normalized_arch(value: str) -> str:
    return {"aarch64": "arm64", "arm64": "arm64", "amd64": "x64",
            "x86_64": "x64", "x64": "x64"}.get(value.lower(), value.lower())


def verify_payload(path: Path, asset: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return stage("pending_user", "安装包尚未下载。", reason="missing_payload", path=str(path))
    with path.open("rb") as handle:
        if handle.read(128).startswith(b"version https://git-lfs.github.com/spec/v1"):
            return stage("pending_user", "这里只是 Git LFS 指针，不能用作安装包。",
                         reason="lfs_pointer", path=str(path))
    if path.stat().st_size != asset["size_bytes"] or sha256_file(path) != asset["sha256"]:
        return stage("failed", "安装包大小或 SHA-256 不匹配；不要运行或自动更换来源。",
                     reason="payload_mismatch", path=str(path))
    return stage("completed", "安装包大小与 SHA-256 已核对；这不是安装或安全认证。",
                 reason="payload_verified", path=str(path))


def download_payload(root: Path, path: Path, asset: dict[str, Any],
                     operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Fetch an exact registered artifact, never execute it or replace a file."""
    relative = path.relative_to(root).as_posix()
    if not relative.startswith(".codex-work/downloads/onboarding/"):
        raise ValueError("Downloads must go to the project onboarding cache")
    parent = check_tree(root, path.parent.relative_to(root).as_posix())
    if path.exists():
        return verify_payload(local_path(root, relative), asset)
    parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(parent).free < asset["size_bytes"] + 32 * 1024 * 1024:
        return stage("failed", "下载所需磁盘空间不足；未删除或替换任何文件。", reason="disk_space")
    temporary = None
    try:
        with urlopen(asset["url"], timeout=30) as response:
            final_url = urlsplit(response.geturl())
            if final_url.scheme != "https" or final_url.username or final_url.password:
                raise ValueError("Installer redirect must remain credential-free HTTPS")
            with tempfile.NamedTemporaryFile(dir=parent, prefix=".download-", delete=False) as handle:
                temporary = Path(handle.name)
                size = 0
                digest = hashlib.sha256()
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > asset["size_bytes"]:
                        raise ValueError("Downloaded installer exceeds its registered size")
                    handle.write(chunk)
                    digest.update(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        if size != asset["size_bytes"] or digest.hexdigest() != asset["sha256"]:
            raise ValueError("Downloaded installer does not match its registered size/SHA-256")
        if verify_payload(temporary, asset)["status"] != "completed":
            raise ValueError("Downloaded installer is not a verified payload")
        # Same-directory hard link is atomic and fails if another process/user
        # has created the destination. Unlike replace(), it cannot overwrite.
        check_tree(root, parent.relative_to(root).as_posix())
        os.link(temporary, local_path(root, relative))
        operations.append({"operation": "download_verified_tool", "exit_code": 0})
        return verify_payload(path, asset)
    except FileExistsError:
        return verify_payload(local_path(root, relative), asset)
    except ValueError:
        operations.append({"operation": "download_verified_tool", "exit_code": 1})
        return stage("failed", "下载内容未通过固定来源与校验检查；未保留为安装包。",
                     reason="download_mismatch", path=str(path))
    except OSError:
        operations.append({"operation": "download_verified_tool", "exit_code": 1})
        return stage("failed", "下载失败；检查网络、权限和缓存文件系统后重试，不更换来源。",
                     reason="download_failed", path=str(path))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def same_version(actual: str, expected: str) -> bool:
    # Windows PE metadata may append one zero to a three-component app version.
    if not re.fullmatch(r"\d+(?:\.\d+)*", actual) or not re.fullmatch(r"\d+(?:\.\d+)*", expected):
        return actual == expected
    left, right = [int(item) for item in actual.split(".")], [int(item) for item in expected.split(".")]
    while len(left) > 1 and left[-1] == 0:
        left.pop()
    while len(right) > 1 and right[-1] == 0:
        right.pop()
    return left == right


def installed_ciphertalk(root: Path, version: str, system: str) -> dict[str, str] | None:
    """Read installed-app metadata without starting the app or reading chat data."""
    if system == "Darwin":
        for base in (Path.home() / "Applications", Path("/Applications")):
            app = base / "CipherTalk.app"
            info_path = app / "Contents/Info.plist"
            if not info_path.is_file():
                continue
            with info_path.open("rb") as handle:
                info = plistlib.load(handle)
            executable = info.get("CFBundleExecutable", "")
            if (info.get("CFBundleShortVersionString") == version
                    and "ciphertalk" in str(info.get("CFBundleName", "")).lower()
                    and isinstance(executable, str) and Path(executable).name == executable
                    and (app / "Contents/MacOS" / executable).is_file()):
                return {"path": str(app), "version": version, "verification": "installed_bundle_metadata"}
    if system == "Windows":
        bases = [os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")]
        candidates = [Path(base) / suffix for base in bases if base
                      for suffix in ("Programs/CipherTalk/CipherTalk.exe", "CipherTalk/CipherTalk.exe")]
        for path in candidates:
            if not path.is_file():
                continue
            env = process_env(root)
            env["SZTU_BOOTSTRAP_APP"] = str(path)
            result = run_command([
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "$v = (Get-Item -LiteralPath $env:SZTU_BOOTSTRAP_APP).VersionInfo; "
                "@{version=$v.ProductVersion;product=$v.ProductName} | ConvertTo-Json -Compress",
            ], root, env=env)
            if result.returncode:
                continue
            info = json.loads(result.stdout)
            if (same_version(str(info.get("version", "")), version)
                    and "ciphertalk" in str(info.get("product", "")).lower()):
                return {"path": str(path), "version": version, "verification": "installed_executable_metadata"}
    return None


def inspect_tools(root: Path, system: str, machine: str, *, download: bool = False,
                  operations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    path = local_path(root, "importers/registry.json")
    if not path.is_file():
        return stage("pending_user", "当前工作副本尚无附带工具清单；核心环境和示例可以先使用。",
                     reason="registry_pending", items=[])
    registry = load_json(path)
    if registry.get("schema_version") != 1 or not isinstance(registry.get("tools"), list):
        raise ValueError("Unsupported importer registry; read the matching importer guide")
    expected_platform = {"Darwin": "macOS", "Windows": "Windows"}.get(system, system)
    items = []
    for tool in registry["tools"]:
        if not isinstance(tool, dict):
            raise ValueError("Invalid importer entry")
        if str(tool.get("role", "")).startswith("catalog-only"):
            continue
        tool_id, version = tool.get("id", ""), tool.get("version", "")
        if not re.fullmatch(r"[a-z0-9-]+", tool_id) or not re.fullmatch(r"[A-Za-z0-9.+_-]+", version):
            raise ValueError("Invalid tool identity/version")
        downloads = tool.get("downloads", [])
        if not isinstance(downloads, list):
            raise ValueError("Invalid importer downloads")
        matches = [asset for asset in downloads if isinstance(asset, dict)
                   and asset.get("platform") == expected_platform
                   and normalized_arch(str(asset.get("arch", ""))) == normalized_arch(machine)]
        if not matches:
            items.append(stage("not_applicable", "此平台无匹配的已登记安装包；不自动编译源码或替换工具。",
                               id=tool_id, version=version))
            continue
        if len(matches) != 1:
            raise ValueError("Ambiguous installer selection; check the tool registry")
        asset = matches[0]
        filename = asset.get("filename", "")
        if (not isinstance(filename, str) or not filename or Path(filename).name != filename
                or "/" in filename or "\\" in filename
                or type(asset.get("size_bytes")) is not int or asset["size_bytes"] <= 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256", "")))):
            raise ValueError("Installer needs a filename, exact size and SHA-256")
        url = urlsplit(asset.get("url", ""))
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("Installer needs a credential-free HTTPS source")
        payload = None
        if asset.get("path"):
            payload = local_path(root, "importers/" + asset["path"])
        else:
            found = list((root / "importers").rglob(filename))
            if len(found) > 1:
                raise ValueError("Multiple matching local installers; registry must give a path")
            if found:
                payload = local_path(root, found[0].relative_to(root).as_posix())
        cached = local_path(root, f".codex-work/downloads/onboarding/{tool_id}/{version}/{filename}")
        if payload is None:
            payload = cached
        verification = verify_payload(payload, asset)
        archive_status = verification if payload != cached else None
        if verification["status"] == "pending_user":
            # Leave the archived LFS pointer untouched. The same pinned bytes
            # can be fetched into the cache; this does not claim LFS hydration.
            verification = (download_payload(root, cached, asset, operations if operations is not None else [])
                            if download else verify_payload(cached, asset))
            if archive_status and verification.get("reason") == "missing_payload":
                verification = archive_status
        installed = installed_ciphertalk(root, version, system) if tool_id == "ciphertalk" else None
        # An installed application alone does not verify the selected payload;
        # conversely, a verified installer alone does not prove installation.
        status = verification["status"]
        if status == "completed" and not installed:
            status = "pending_user"
        items.append(stage(
            status, "已核对安装包与已安装应用元数据。" if status == "completed"
            else "按清单补齐安装包、完成正常安装并核对应用版本；不会自动运行安装器。",
            id=tool_id, version=version, payload=verification, installation=installed,
            archived_payload=archive_status,
            download_url=asset["url"], size_bytes=asset["size_bytes"], sha256=asset["sha256"],
        ))
    if not items:
        return stage("pending_user", "清单没有可初始化的工具条目；请核对工具归档交付。",
                     reason="empty_registry", items=[])
    status = ("failed" if any(item["status"] == "failed" for item in items)
              else "pending_user" if any(item["status"] == "pending_user" for item in items)
              else "completed" if any(item["status"] == "completed" for item in items)
              else "not_applicable")
    return stage(status, "附带工具按平台分别报告；源码备份和研究目录不视为已安装应用。",
                 items=items, execution_tested=False)


def github_route(authenticated: bool, can_push: bool | None) -> str:
    if not authenticated:
        return "login"
    return "branch" if can_push is True else "fork" if can_push is False else "check_permissions"


def inspect_github(root: Path, requested: bool) -> dict[str, Any]:
    if not requested:
        return stage("not_applicable", "本地使用不要求 GitHub；同步或贡献时再连接。",
                     route="local_only", remote_changed=False)
    if not shutil.which("gh"):
        return stage("pending_user", "同步前需要安装 GitHub CLI。", route="install_gh", remote_changed=False)
    auth = run_command(["gh", "auth", "status", "--hostname", "github.com"], root)
    if auth.returncode:
        return stage("pending_user", "请检查网络或通过 gh auth login --web 在浏览器完成授权。",
                     route=github_route(False, None), remote_changed=False)
    result = run_command(["gh", "api", f"repos/{UPSTREAM}"], root)
    if result.returncode:
        return stage("pending_user", "暂不能读取仓库权限；检查网络或组织授权，不更改当前登录。",
                     route=github_route(True, None), remote_changed=False)
    repository = json.loads(result.stdout)
    permission = repository.get("permissions", {}).get("push")
    route = github_route(True, permission if isinstance(permission, bool) else None)
    return stage(
        "completed" if route != "check_permissions" else "pending_user",
        "可以使用工作分支；提交和推送仍需用户要求。" if route == "branch"
        else "请先查找已有 Fork；没有时经用户确认创建，再核对远端映射。",
        route=route, repository=UPSTREAM, remote_changed=False,
    )


def inspect_workspace(root: Path) -> dict[str, Any]:
    executable = shutil.which("git")
    if not executable:
        return stage("pending_user", "工作副本已定位；请按指南补齐 Git。", reason="missing_git")
    result = run_command([executable, "--version"], root)
    version = re.search(r"^git version ([0-9]+(?:\.[0-9]+)+)", result.stdout)
    if result.returncode or not version:
        return stage("pending_user", "Git 还不能正常运行；完成安装或系统提示后重试。",
                     reason="git_not_ready")
    return stage("completed", "工作副本已定位，Git 可运行。", git_version=version[1])


def bootstrap(root: Path, *, check: bool = False, github: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve()
    system, machine = platform.system(), platform.machine()
    stages: dict[str, Any] = {}
    operations: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "ok": False, "local_ready": False, "mode": "check" if check else "initialize",
        "repository": str(root), "system": system, "architecture": normalized_arch(machine),
        "host_environment": "requires_agent_confirmation",
        "stages": stages, "operations": operations, "guide": GUIDE,
    }
    try:
        if sys.version_info < (3, 11):
            raise ValueError("Python 3.11 or newer is required before running bootstrap")
        parts = tuple(part.lower() for part in root.parts)
        if any(parts[index:index + 2] == ("plugins", "cache") for index in range(len(parts) - 1)):
            raise ValueError("Select a user checkout, not an installed plugin cache")
        required = ("README.md", "AGENTS.md", "connect.config.json", "requirements.lock",
                    "pyproject.toml", "src/digital_sztu/__init__.py", ".codex-plugin/plugin.json")
        missing = [name for name in required if not local_path(root, name).is_file()]
        if missing or load_json(root / "connect.config.json").get("project", {}).get("slug") != "digital-sztu":
            raise ValueError("Select a complete Digital SZTU user checkout; bootstrap does not clone over a directory")
        if system not in ("Darwin", "Windows"):
            stages["workspace"] = stage("not_applicable", "此系统保留手动 CLI 安装；自动初始化仅面向 macOS/Windows。")
            report["status"] = "not_applicable"
            return report
        # No directory is created before all managed paths have been checked.
        for relative in (".work/onboarding", ".codex-work/cache/onboarding-pip",
                         ".codex-work/downloads/onboarding"):
            check_tree(root, relative)
        check_tree(root, ".venv", venv=True)
        previous_state = local_path(root, STATE)
        if previous_state.exists():
            previous = load_json(previous_state)
            if (previous.get("guide") != GUIDE
                    or previous.get("mode") not in ("initialize", "check")
                    or not isinstance(previous.get("stages"), dict)):
                raise ValueError("The onboarding state path contains an unrelated file; it will not be overwritten")
        stages["workspace"] = inspect_workspace(root)
    except Exception as exc:
        stages["workspace"] = stage("failed", str(exc), error_type=type(exc).__name__)
        report["status"] = "failed"
        return report
    for name, action in (
        ("runtime", lambda: prepare_runtime(root, check, operations)),
        ("tools", lambda: inspect_tools(root, system, machine, download=not check, operations=operations)),
        ("example", lambda: prepare_example(root, check, operations)
         if stages["runtime"]["status"] == "completed"
         else stage("pending_user", "基础环境完成后再运行示例。", reason="runtime_pending")),
        ("github", lambda: inspect_github(root, github)),
    ):
        try:
            stages[name] = action()
        except Exception as exc:
            # Known errors are deliberately authored without raw subprocess output.
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else f"{name} 未完成；请按指南检查并重试。"
            stages[name] = stage("failed", message, error_type=type(exc).__name__)
    report["local_ready"] = all(stages[name]["status"] == "completed"
                                for name in ("workspace", "runtime", "example"))
    report["ok"] = all(item["status"] in ("completed", "not_applicable") for item in stages.values())
    report["status"] = ("completed" if report["ok"] else "failed"
                        if any(item["status"] == "failed" for item in stages.values()) else "pending_user")
    report["next_steps"] = [
        {"stage": name, "message": item["message"]}
        for name, item in stages.items() if item["status"] not in ("completed", "not_applicable")
    ]
    if not check:
        try:
            check_tree(root, ".work/onboarding")
            write_json(local_path(root, STATE), report)
        except Exception as exc:
            report.update(ok=False, status="failed")
            stages["state"] = stage("failed", "无法安全保存初始化状态。", error_type=type(exc).__name__)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare or inspect a local Digital SZTU user checkout.")
    parser.add_argument("--root", type=Path, default=PROJECT, help="explicit user checkout, never a plugin cache")
    parser.add_argument("--check", action="store_true", help="inspect only; no installs, builds or writes")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--github", action="store_true", help="also read GitHub authorization and push permission")
    args = parser.parse_args(argv)
    report = bootstrap(args.root, check=args.check, github=args.github)
    if args.as_json:
        print(json.dumps({"contract_version": "0.1.0", "operation": "bootstrap",
                          "ok": report["ok"], "data": report}, ensure_ascii=False, indent=2))
    else:
        print(f"[{report['status']}] Digital SZTU")
        print(f"Repository: {report['repository']}")
        for name, item in report["stages"].items():
            print(f"  {name}: {item['status']} — {item['message']}")
        print(f"Local ready: {report['local_ready']}; guide: {GUIDE}")
    return 0 if report["ok"] else 2 if report["status"] == "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

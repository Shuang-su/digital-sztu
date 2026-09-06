from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Any, Iterable

EXCLUDED_DIRECTORIES = {
    ".git",
    ".work",
    ".codex-work",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "build",
    "dist",
}

TEXT_EXTENSIONS = {
    "",
    ".md",
    ".json",
    ".jsonl",
    ".lock",
    ".txt",
    ".csv",
    ".html",
    ".xml",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".cff",
    ".svg",
    ".css",
    ".js",
    ".pem", ".key", ".crt", ".cer", ".asc",
    ".ini", ".cfg", ".conf", ".properties", ".sql",
    ".sh", ".bash", ".zsh", ".fish", ".log",
}

ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template")

# Local review is advisory; strict publication checks block credential patterns.
CREDENTIAL_PATTERNS = {
    "private-key": re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}"),
    "gitlab-token": re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
    "openai-key": re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    "aws-access-key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "google-api-key": re.compile(r"AIza[A-Za-z0-9_-]{30,}"),
    "slack-token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    "bearer-token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.I),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "cn-id-number": re.compile(r"(?<![A-Za-z0-9])\d{17}[0-9Xx](?![A-Za-z0-9])"),
    "password-assignment": re.compile(
        r"['\"]?(?:password|passwd|cookie|session[_-]?token)['\"]?"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{8,}",
        re.I,
    ),
    "secret-assignment": re.compile(
        r"['\"]?(?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|secret[_-]?key)['\"]?"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}",
        re.I,
    ),
}

_ROOM_WORDS = ("宿" + "舍", "房" + "间", "room")
_PRECISE_ROOM_KIND = "precise-" + "ro" + "om-label"

REVIEW_PATTERNS = {
    "mainland-phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    "student-id-label": re.compile(r"(?:学号|student\s*id)\s*[:：]?\s*[A-Za-z0-9]{6,20}", re.I),
    _PRECISE_ROOM_KIND: re.compile(
        rf"(?:{'|'.join(_ROOM_WORDS)})\s*[:：]?\s*[A-Za-z0-9楼栋座-]{{2,20}}", re.I
    ),
}


def _candidate_paths(root: Path) -> Iterable[Path]:
    # Prune local environments, private research and caches before traversing.
    candidates = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        retained = []
        for name in dirs:
            if name in EXCLUDED_DIRECTORIES or name.endswith('.egg-info'):
                continue
            path = parent / name
            if path.is_symlink():
                candidates.append(path)
            else:
                retained.append(name)
        dirs[:] = retained
        candidates.extend(parent / name for name in files if name != '.DS_Store'
                          and name not in EXCLUDED_DIRECTORIES and not name.endswith('.egg-info'))
    yield from sorted(candidates)


def _finding(
    severity: str,
    kind: str,
    path: str,
    *,
    line: int | None = None,
    message: str,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "severity": severity,
        "kind": kind,
        "path": path,
        "message": message,
    }
    if line is not None:
        value["line"] = line
    return value


def _is_env_template(path: Path) -> bool:
    name = path.name.lower()
    return (
        (name.startswith(".env") or name.startswith(".envrc"))
        and name.endswith(ENV_TEMPLATE_SUFFIXES)
    ) or any(name.endswith(f".env{suffix}") for suffix in ENV_TEMPLATE_SUFFIXES)


def _is_env_named_file(path: Path) -> bool:
    name = path.name.lower()
    return name == ".env" or name.startswith(".env.") or name.startswith(".envrc")


def _looks_like_text(path: Path) -> bool:
    # Unknown extensions, including LICENSE variants, can still hold plain text.
    try:
        with path.open('rb') as stream:
            sample = stream.read(4096)
        import codecs
        codecs.getincrementaldecoder('utf-8')().decode(sample, final=False)
        return b'\0' not in sample
    except (OSError, UnicodeDecodeError):
        return False


def scan_privacy(root: Path, *, strict: bool = False) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    scanned = 0
    for path in _candidate_paths(root):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            findings.append(_finding("block" if strict else "review", "symlink-not-scanned", rel,
                                     message="链接目标未扫描；公开交付应使用经过核查的仓库内实体文件。"))
            continue
        suffix = path.suffix.lower()
        if (
            suffix not in TEXT_EXTENSIONS
            and not _is_env_template(path)
            and not _is_env_named_file(path)
            and not _looks_like_text(path)
        ):
            findings.append(
                _finding(
                    "review",
                    "binary-not-scanned",
                    rel,
                    message="非文本文件未检查内容或位置元数据；公开前确认权利与隐私。",
                )
            )
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        # Iterate lines even for large exports; file size must not hide a tail secret.
        scanned += 1
        try:
            with path.open("r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    for kind, pattern in CREDENTIAL_PATTERNS.items():
                        for match in pattern.finditer(line):
                            findings.append(
                                _finding(
                                    "block" if strict else "review",
                                    kind,
                                    rel,
                                    line=number,
                                    message="检测到凭据或高风险直接标识；需要核查并移除真实秘密，不能随公开交付发布。",
                                )
                            )
                    for kind, pattern in REVIEW_PATTERNS.items():
                        for match in pattern.finditer(line):
                            findings.append(
                                _finding(
                                    "review",
                                    kind,
                                    rel,
                                    line=number,
                                    message="确认该信息有公开来源并且对事实核查必要。",
                                )
                            )
        except UnicodeDecodeError:
            findings.append(
                _finding(
                    "review",
                    "non-utf8-text",
                    rel,
                    message="文本无法按 UTF-8 扫描。",
                )
            )

    counts = {
        severity: sum(item["severity"] == severity for item in findings)
        for severity in ("block", "review", "notice")
    }
    # Ordinary public names and contact context remain advisory in strict mode.
    ok = counts["block"] == 0
    return {
        "ok": ok,
        "strict": strict,
        "scanned_files": scanned,
        "counts": counts,
        "findings": findings,
    }

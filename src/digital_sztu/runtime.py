"""Read-only environment diagnostics and research storage preflight."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

MIN_FREE_BYTES = 256 * 1024 * 1024


def storage_status(path: Path) -> dict:
    target = path.resolve()
    while not target.exists():
        target = target.parent
    free = shutil.disk_usage(target).free
    return {"path": str(path.resolve()), "free_bytes": free,
            "minimum_free_bytes": MIN_FREE_BYTES, "ok": free >= MIN_FREE_BYTES}


def require_storage(path: Path) -> None:
    if not storage_status(path)["ok"]:
        raise OSError(28, "Research storage has less than 256 MiB free; preserve the database and free space before resuming")


def environment_diagnostics(root: Path) -> dict:
    errors, warnings = [], []
    marker = root / ".git"
    if marker.is_file():
        pointer = marker.read_text(encoding="utf-8").strip()
        if pointer.startswith("gitdir:") and not (root / pointer.split(":", 1)[1].strip()).exists():
            errors.append("Worktree registration points to a missing directory; run git worktree repair from the main checkout with the current worktree path")
    venv = root / ".venv"
    python = venv / ("Scripts/python.exe" if __import__('os').name == 'nt' else "bin/python")
    if venv.exists():
        try:
            probe = subprocess.run([str(python), "-B", "-c",
                "import importlib.util,json,sys; s=importlib.util.find_spec('digital_sztu'); print(json.dumps({'prefix':sys.prefix,'module':s.origin if s else None}))"],
                capture_output=True, text=True, timeout=10, check=True)
            found = json.loads(probe.stdout)
            if Path(found['prefix']).resolve() != venv.resolve() or not found['module'] or Path(found['module']).resolve() != root / 'src/digital_sztu/__init__.py':
                errors.append("Virtual environment belongs to another path or cannot import this checkout; preserve it and recreate .venv using requirements.lock")
        except (OSError, ValueError, subprocess.SubprocessError):
            errors.append("Virtual environment cannot start; preserve it and recreate .venv at this checkout's current path")
    else:
        warnings.append("No local .venv; commands may be using another Python environment")
    storage = storage_status(root / '.work/discovery')
    if not storage['ok']:
        errors.append("Insufficient research storage; free space before resuming")
    return {'ok': not errors, 'errors': errors, 'warnings': warnings,
            'research_storage': storage, 'sqlite_temp_store': 'memory',
            'research_database': str(root / '.work/discovery/state.sqlite3')}

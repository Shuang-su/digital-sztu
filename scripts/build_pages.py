#!/usr/bin/env python3
"""Build only allowlisted public static artifacts for GitHub Pages."""
from pathlib import Path
import json
import sys

from digital_sztu.build import build_indexes
from digital_sztu.graph import write_viewer
from digital_sztu.utils import atomic_write_bytes, atomic_write_text, sha256_file

root = Path(__file__).resolve().parents[1]
output = root / '.work/pages'
allowed = {'index.html', 'graph-preview.svg', 'site-manifest.json'}
if (root / '.work').is_symlink() or output.is_symlink():
    raise SystemExit('Pages staging must be inside a real .work directory')
if output.exists() and any(path.is_symlink() or path.name not in allowed or not path.is_file() for path in output.iterdir()):
    raise SystemExit('Pages staging contains unexpected entries; inspect them before building')
built = build_indexes(root)
if not built['ok']:
    print(json.dumps(built, ensure_ascii=False))
    raise SystemExit(1)
viewer = write_viewer(root, output)
atomic_write_bytes(output / 'graph-preview.svg', (root / 'data/generated/graph-preview.svg').read_bytes())
manifest = {'dataset_revision': viewer['dataset_revision'], 'files': []}
for name in ('index.html', 'graph-preview.svg'):
    path = output / name
    if path.stat().st_nlink != 1:
        raise SystemExit('Pages artifacts cannot be hard links')
    manifest['files'].append({'path': name, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)})
atomic_write_text(output / 'site-manifest.json', json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
print(json.dumps({'ok': True, 'output': output.relative_to(root).as_posix(), **manifest}, ensure_ascii=False))

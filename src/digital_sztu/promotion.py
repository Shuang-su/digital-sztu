"""Validate an evidence-reviewed import in isolation, then install it recoverably."""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .public import public_projection
from .utils import atomic_write_bytes, canonical_json, load_json, sha256_bytes, write_json
from .validation import collect_repository, validate_repository, NODE_DIRECTORIES


def record_path(record):
    rid, kind = record['id'], record['type']
    if kind == 'knowledge':
        return Path('content/knowledge') / rid / 'record.json'
    if kind == 'event':
        return Path('content/events') / ((record['time'].get('start') or 'undated')[:4] if record['time'].get('start') else 'undated') / rid / 'event.json'
    if kind == 'node':
        return Path('content/nodes') / NODE_DIRECTORIES[record['kind']] / (rid + '.json')
    if kind == 'source':
        return Path('sources/records') / (rid + '.json')
    if kind == 'collection':
        return Path('content/collections') / rid / 'collection.json'
    raise ValueError('Unknown canonical record type')


def recover_promotion(root, *, already_locked=False):
    if (root / '.work').is_symlink():
        raise ValueError('Promotion work directory must not be a symbolic link')
    journal = root / '.work/promotion-journal.json'
    if not journal.exists():
        return
    if journal.is_symlink():
        raise ValueError('Promotion journal must not be a symbolic link')
    value = load_json(journal)
    if value.get('database') and not already_locked:
        database = root / value['database']
        if database.is_symlink() or not database.resolve().is_relative_to((root / '.work').resolve()):
            raise ValueError('Unsafe research database recovery path')
        from .discovery import research_lock
        try:
            with research_lock(database):
                return recover_promotion(root, already_locked=True)
        except (BlockingIOError, PermissionError) as exc:
            raise ValueError('Canonical promotion is active; retry after the writer finishes') from exc
    if value['state'] == 'committed':
        journal.unlink()
        return
    for entry in value['created']:
        path = root / entry['path']
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Unsafe recovery path')
        if path.exists():
            if sha256_bytes(path.read_bytes()) != entry['sha256']:
                raise ValueError(f'Interrupted import file changed; preserve it for review: {entry["path"]}')
            path.unlink()
    if value.get('mapping_rows'):
        database = root / value['database']
        if database.is_symlink() or not database.resolve().is_relative_to((root / '.work').resolve()):
            raise ValueError('Unsafe research database recovery path')
        connection = sqlite3.connect(database)
        try:
            connection.executemany('DELETE FROM promotions WHERE entity_id=? AND record_id=? AND run_id=?', value['mapping_rows'])
            connection.commit()
        finally:
            connection.close()
    journal.unlink()


def promote(root, run, specification):
    recover_promotion(root, already_locked=True)
    if not run.status()['promotion_ready']:
        raise ValueError('Survey remains partial: finish executable queues, review missing evidence and two no-new rounds before promotion')
    if not specification:
        raise ValueError('Promotion requires --file with reviewed canonical records and research mappings')
    spec = load_json(specification)
    mappings = spec.get('mappings', [])
    if not mappings:
        raise ValueError('Promotion requires research-to-archive mappings')
    records = spec['records']
    ids = {entry['data']['id'] for entry in records}
    if len(ids) != len(records):
        raise ValueError('Duplicate record ID in promotion input')
    mapped = set()
    for mapping in mappings:
        entity = run.state['records'][mapping['entity_id']]
        if entity['verification_status'] != 'confirmed' or not entity.get('evidence'):
            raise ValueError('Only evidence-confirmed research records can be promoted')
        if mapping.get('run_id') != run.run_id:
            raise ValueError('Research run mismatch')
        mapped.update(mapping['record_ids'])
        if not set(mapping['record_ids']) <= ids:
            raise ValueError('Mapping references a record outside this import')
    if mapped != ids:
        raise ValueError('Every imported record must have a research mapping')
    pending = {}
    for entry in records:
        record = entry['data']
        relative = record_path(record)
        if not (root / relative).resolve().is_relative_to(root.resolve()):
            raise ValueError('Record path escapes repository')
        pending[relative] = (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
        if record.get('narrative'):
            if '/' in record['narrative'] or '\\' in record['narrative'] or not record['narrative'].endswith('.md'):
                raise ValueError('Narrative must be a local Markdown filename')
            if not isinstance(entry.get('markdown'), str):
                raise ValueError('Narrative body missing from promotion input')
            pending[relative.parent / record['narrative']] = entry['markdown'].encode()
    work = root / '.work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='promotion-', dir=work) as temporary:
        stage = Path(temporary)
        for directory in ('schemas', 'content', 'sources'):
            if (root / directory).exists():
                shutil.copytree(root / directory, stage / directory, symlinks=True)
        shutil.copyfile(root / 'connect.config.json', stage / 'connect.config.json')
        for path, payload in pending.items():
            target = root / path
            if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent.is_relative_to(root)):
                raise ValueError('Import target has a symbolic link')
            if target.exists():
                same = canonical_json(load_json(target)) == canonical_json(json.loads(payload)) if path.suffix == '.json' else target.read_bytes() == payload
                if not same:
                    raise ValueError(f'Existing canonical record differs; review an explicit update: {path}')
            atomic_write_bytes(stage / path, payload)
        validation = validate_repository(stage)
        if not validation['ok']:
            return {'ok': False, 'errors': validation['errors'], 'installed': 0}
        public = {record['id'] for values in public_projection(stage, collect_repository(stage)).values() for _, record in values}
        if not ids <= public:
            raise ValueError('Import contains records excluded by the public archive policy')
    created = [path for path in pending if not (root / path).exists()]
    journal = work / 'promotion-journal.json'
    run.db.execute('CREATE TABLE IF NOT EXISTS promotions(entity_id TEXT,record_id TEXT,run_id TEXT,PRIMARY KEY(entity_id,record_id,run_id))')
    run.db.commit()
    mapping_rows = [(mapping['entity_id'], rid, run.run_id) for mapping in mappings for rid in mapping['record_ids']
                    if not run.db.execute('SELECT 1 FROM promotions WHERE entity_id=? AND record_id=? AND run_id=?', (mapping['entity_id'], rid, run.run_id)).fetchone()]
    transaction = {'database': run.path.relative_to(root).as_posix(), 'mapping_rows': mapping_rows, 'state': 'installing', 'created': [{'path': path.as_posix(), 'sha256': sha256_bytes(pending[path])} for path in created]}
    write_json(journal, transaction)
    try:
        for path in created:
            atomic_write_bytes(root / path, pending[path])
        for mapping in mappings:
            run.db.execute('CREATE TABLE IF NOT EXISTS promotions(entity_id TEXT,record_id TEXT,run_id TEXT,PRIMARY KEY(entity_id,record_id,run_id))')
            run.db.executemany('INSERT OR IGNORE INTO promotions VALUES (?,?,?)', ((mapping['entity_id'], rid, run.run_id) for rid in mapping['record_ids']))
        run.audit('canonical-promotion', record_ids=sorted(ids), files_created=len(created))
        run.save()
        transaction['state'] = 'committed'
        write_json(journal, transaction)
        journal.unlink()
    except BaseException:
        run.db.rollback()
        recover_promotion(root, already_locked=True)
        raise
    return {'ok': True, 'records': len(ids), 'files_created': len(created), 'idempotent': not created}

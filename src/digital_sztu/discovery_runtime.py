"""Bounded queue selection, transactional indexes and recoverable execution."""
from __future__ import annotations

import errno
import json
import os
import shlex
import sqlite3
import time

from .runtime import require_storage
from .utils import find_repo_root


def install_indexes(db):
    # Expression indexes preserve the legacy JSON bodies and every saved cursor.
    db.execute('SAVEPOINT discovery_indexes')
    try:
        db.execute("CREATE INDEX IF NOT EXISTS queue_order_v2 ON ops(json_extract(body,'$.status'),json_extract(body,'$.priority'),json_extract(body,'$.queued_at'),id)")
        db.execute("CREATE INDEX IF NOT EXISTS queue_kind_v2 ON ops(json_extract(body,'$.status'),json_extract(body,'$.operation'),json_extract(body,'$.priority'),json_extract(body,'$.queued_at'),id)")
        for field in ('record_type', 'verification_status'):
            db.execute(f"CREATE INDEX IF NOT EXISTS records_{field}_v2 ON records(json_extract(body,'$.{field}'))")
    except BaseException:
        db.execute('ROLLBACK TO discovery_indexes')
        raise
    finally:
        db.execute('RELEASE discovery_indexes')


class ResearchRuntime:
    def subprocess_environment(self):
        temporary = self.path.parent / 'tmp'
        if temporary.is_symlink():
            raise ValueError('Research temporary directory must not be a symlink')
        temporary.mkdir(exist_ok=True)
        return {**os.environ, 'TMPDIR': str(temporary), 'TMP': str(temporary),
                'TEMP': str(temporary), 'SQLITE_TMPDIR': str(temporary)}

    def restore_committed(self):
        self.db.rollback()
        state = json.loads(self.db.execute('SELECT body FROM meta WHERE id=1').fetchone()[0])
        for table in ('records', 'edges', 'ops'):
            state[table] = self.state[table]
            state[table].release()
        self.state = state

    def queue_progress(self):
        counts = self.counts('ops', 'status')
        review = self.db.execute("SELECT count(*) FROM ops WHERE json_extract(body,'$.status') IN ('pending','deferred','running','scoped-review-required','missing') AND json_extract(body,'$.operation') IN ('relevance-review','scoped-contributors-review','external-review')").fetchone()[0]
        return {'operations': counts, 'total_operations': sum(counts.values()),
                'remaining_operations': sum(counts.get(k, 0) for k in ('pending','deferred','running','scoped-review-required','missing')),
                'evidence_reviews': review, 'api_calls': self.state.get('api_calls', 0),
                'rate': self.state.get('rate', {}), 'resume_after': {key: value for key, value in self.state.get('blocked_until', {}).items() if value > time.time()}}

    def report_progress(self, force=False):
        callback = getattr(self, '_progress_callback', None)
        if callback is None or (not force and time.monotonic() - self._progress_at < 2):
            return
        current = self.queue_progress()
        current.update(event='discovery-progress', run_id=self.run_id,
                       completed_delta=current['operations'].get('complete', 0) - self._progress_initial['operations'].get('complete', 0),
                       added_operations=current['total_operations'] - self._progress_initial['total_operations'])
        self._progress_at = time.monotonic()
        callback(current)

    def next_operation(self, kinds):
        parameters = []
        where = "json_extract(body,'$.status')='pending' AND json_extract(body,'$.operation') NOT IN ('relevance-review','scoped-contributors-review','external-review') AND NOT EXISTS(SELECT 1 FROM handled_operations h WHERE h.id=ops.id)"
        if kinds:
            where += " AND json_extract(body,'$.operation') IN (" + ','.join('?' for _ in kinds) + ')'
            parameters.extend(kinds)
        row = self.db.execute("SELECT id FROM ops WHERE " + where + " ORDER BY json_extract(body,'$.priority'),json_extract(body,'$.queued_at'),id LIMIT 1", parameters).fetchone()
        return row[0] if row else None

    def resume(self, limit=100, kinds=None, progress=None):
        if limit < 1:
            raise ValueError('limit must be positive')
        self._progress_initial = self.queue_progress()
        self._progress_callback, self._progress_at = progress, 0
        resume_args = ['digital-sztu']
        try:
            resume_args += ['--root', str(find_repo_root(self.path.parent))]
        except FileNotFoundError:
            pass  # Library callers can hold an isolated database outside an archive.
        resume_args += ['discover', 'resume', '--database', str(self.path.resolve()), '--limit', str(limit), '--json']
        if kinds:
            resume_args += ['--kinds', ','.join(kinds)]
        if progress:
            resume_args.append('--progress')
        try:
            require_storage(self.path.parent)
            self.db.execute('CREATE TEMP TABLE IF NOT EXISTS handled_operations(id TEXT PRIMARY KEY)')
            self.db.execute('DELETE FROM handled_operations')
            self.db.commit()
            self.report_progress(force=True)
            result = self._resume(limit, kinds)
            self.report_progress(force=True)
            result['resume_command'] = shlex.join(resume_args)
            if result.get('blocked'):
                result['recovery'] = 'Committed pages are preserved; resolve the reported error or wait until resume_after, then use resume_command.'
                result['resume_after'] = self.queue_progress()['resume_after']
            return result
        except (KeyboardInterrupt, OSError, sqlite3.Error) as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)
            full = (isinstance(exc, OSError) and exc.errno == errno.ENOSPC) or getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL
            if not interrupted and not full:
                raise
            self.restore_committed()
            return {**self.status(), 'ok': False, 'interrupted': interrupted,
                    'blocked': 'interrupted' if interrupted else 'storage-full',
                    'resume_command': shlex.join(resume_args),
                    'recovery': 'Committed pages are preserved. Resolve the interruption or storage shortage, then resume with the same database.'}
        finally:
            self._progress_callback = None

    def review_packet(self, entity_id):
        record = self.state['records'][entity_id]
        operations = [dict(value) for (body,) in self.db.execute(
            "SELECT body FROM ops WHERE id LIKE ? ORDER BY id", (entity_id + '|%',))
            for value in [json.loads(body)]]
        return {'ok': True, 'record': record, 'review_context': {
            'operations': operations, 'source_locator': record.get('readme_current'),
            'campus_evidence': record.get('evidence', []),
            'campus_scope': record.get('relevance_reason'), 'fork_of': record.get('fork_of'),
            'contributor_scope_reason': record.get('contributor_scope_reason'),
            'requires_alternative_evidence': any(op.get('status') == 'missing' for op in operations),
            'instructions': 'Read the primary source; metadata and account affiliation alone do not prove campus relevance.'}}

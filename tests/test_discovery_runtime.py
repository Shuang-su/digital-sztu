from __future__ import annotations

import contextlib
import copy
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from digital_sztu.cli import main
from digital_sztu.discovery import Research, initialize
from digital_sztu.discovery_runtime import install_indexes
from digital_sztu.runtime import environment_diagnostics


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / '.work/discovery/state.sqlite3'
        initialize(self.path)
        self.run = Research(self.path)
        self.run.state.update(all_affiliations_count_policy=True, fork_parent_review_policy=True)
        self.run.state['records']['repo:1'] = {'id': 'repo:1', 'record_type': 'repository', 'verification_status': 'candidate'}
        self.key = self.run.enqueue('repo:1', 'metadata')
        self.run.state['ops'][self.key].update(pages=3, next_endpoint='page-4')
        self.run.save()

    def tearDown(self):
        self.run.close()
        self.temp.cleanup()

    def test_index_migration_preserves_rows_and_cursors(self):
        before = {table: self.run.db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall() for table in ('records','ops','edges','audit','meta')}
        install_indexes(self.run.db)
        self.assertEqual(before, {table: self.run.db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall() for table in before})
        plan = self.run.db.execute("EXPLAIN QUERY PLAN SELECT id FROM ops WHERE json_extract(body,'$.status')='pending' AND json_extract(body,'$.operation')='metadata' ORDER BY json_extract(body,'$.priority'),json_extract(body,'$.queued_at'),id LIMIT 1").fetchall()
        self.assertFalse(any('TEMP B-TREE' in row[-1] for row in plan))

    def test_index_failure_rolls_back_new_indexes(self):
        # A conflicting schema causes migration failure without retaining partial indexes.
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE ops(id TEXT, body TEXT)')
        with self.assertRaises(sqlite3.OperationalError):
            install_indexes(db)
        self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall(), [])
        db.close()

    def test_kind_filter_does_not_complete_other_operations(self):
        other = self.run.enqueue('repo:1', 'contributors', 1)
        self.run.save()
        def execute(op):
            op.update(status='complete')
        with patch.object(self.run, 'api', return_value=(None, {}, None)), patch.object(self.run, 'execute', side_effect=execute):
            result = self.run.resume(1, ['metadata'])
        self.assertEqual(result['processed'], 1)
        self.assertEqual(self.run.state['ops'][other]['status'], 'pending')

    def test_interruption_reloads_committed_page_and_meta(self):
        def interrupted(op):
            op.update(pages=4, next_endpoint='page-5')
            self.run.state['api_calls'] = 4
            self.run.save()
            op.update(pages=5, next_endpoint='page-6')
            self.run.state['api_calls'] = 5
            self.run.state['ops'].flush()
            raise KeyboardInterrupt()
        with patch.object(self.run, 'api', return_value=(None, {}, None)), patch.object(self.run, 'execute', side_effect=interrupted):
            result = self.run.resume(3, ['metadata'])
        self.assertTrue(result['interrupted'])
        self.assertIn('--database', result['resume_command'])
        self.assertEqual(self.run.state['ops'][self.key]['next_endpoint'], 'page-5')
        self.assertEqual(self.run.state['api_calls'], 4)
        self.run.save()
        self.run.close(); self.run = Research(self.path)
        self.assertEqual(self.run.state['ops'][self.key]['pages'], 4)

    def test_disk_full_does_not_attempt_error_commit(self):
        original = copy.deepcopy(self.run.state['ops'][self.key])
        def full(op):
            op.update(pages=999)
            raise OSError(28, 'full')
        with patch.object(self.run, 'api', return_value=(None, {}, None)), patch.object(self.run, 'execute', side_effect=full):
            result = self.run.resume(1, ['metadata'])
        self.assertEqual(result['blocked'], 'storage-full')
        self.assertEqual(self.run.state['ops'][self.key], original)

    def test_progress_is_stderr_jsonl_and_final_stdout_is_one_document(self):
        out, err = io.StringIO(), io.StringIO()
        def execute(run, op):
            op.update(status='complete')
        with patch.object(Research, 'api', return_value=(None, {}, None)), patch.object(Research, 'execute', execute), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(['--root', str(self.root), 'discover', 'resume', '--limit', '1', '--kinds', 'metadata', '--progress', '--json'])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())['ok'])
        frames = [json.loads(line) for line in err.getvalue().splitlines()]
        self.assertEqual(frames[-1]['completed_delta'], 1)
        self.assertNotIn('percent', frames[-1])

    def test_readonly_status_does_not_migrate(self):
        self.run.db.execute('DROP INDEX queue_kind_v2'); self.run.db.commit()
        before = self.path.read_bytes()
        reader = Research(self.path, readonly=True)
        self.assertFalse(reader.status()['promotion_ready'])
        self.assertEqual(reader.db.execute('PRAGMA temp_store').fetchone()[0], 2)
        with self.assertRaises(sqlite3.OperationalError):
            reader.db.execute('CREATE TABLE forbidden(id)')
        reader.close()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNone(self.run.db.execute("SELECT name FROM sqlite_master WHERE name='queue_kind_v2'").fetchone())

    def test_missing_readme_is_visible_in_review_packet(self):
        key = self.run.enqueue('repo:1', 'readme')
        self.run.state['ops'][key]['status'] = 'missing'
        self.run.save()
        self.assertTrue(self.run.review_packet('repo:1')['review_context']['requires_alternative_evidence'])
        self.assertFalse(self.run.status()['promotion_ready'])

    def test_unresolved_review_stays_pending_and_blocks_promotion(self):
        key = self.run.enqueue('repo:1', 'relevance-review')
        self.run.save()
        self.run.review([{'id': 'repo:1', 'verification_status': 'candidate',
                          'relevance_reason': 'Need primary evidence for campus scope'}])
        self.assertEqual(self.run.state['ops'][key]['status'], 'scoped-review-required')
        self.assertFalse(self.run.status()['promotion_ready'])

    def test_legacy_completed_candidate_review_is_reopened_once(self):
        key = self.run.enqueue('repo:1', 'relevance-review')
        self.run.state['ops'][key]['status'] = 'complete'
        self.run.save()
        with patch.object(self.run, 'api', return_value=(None, {}, None)):
            self.run.resume(1, ['nonexistent-kind'])
            self.assertEqual(self.run.state['ops'][key]['status'], 'scoped-review-required')
            before = self.run.db.execute('SELECT count(*) FROM audit').fetchone()[0]
            self.run.resume(1, ['nonexistent-kind'])
            self.assertEqual(self.run.db.execute('SELECT count(*) FROM audit').fetchone()[0], before)

    def test_scoped_review_before_metadata_survives_refresh_and_reopen(self):
        owner = {'id': 7, 'login': 'owner7', 'html_url': 'https://github.com/owner7', 'type': 'User'}
        row = {'id': 91, 'full_name': 'owner7/fork', 'html_url': 'https://github.com/owner7/fork',
               'private': False, 'fork': True, 'owner': owner, 'default_branch': 'main'}
        sid = self.run.repo(row)
        key = sid + '|scoped-contributors-review'
        self.assertNotIn(key, self.run.state['ops'])
        self.run.review([{'id': sid, 'verification_status': 'confirmed', 'category': 'coursework',
                          'relevance_reason': 'Course exercise delta verified in source cells',
                          'evidence': [{'url': 'https://github.com/owner7/fork/commit/abc',
                                        'locator': 'course exercise diff', 'accessed_at': '2026-09-06T00:00:00Z'}],
                          'contributor_scope_reason': 'Only mapped exercise author',
                          'campus_contributors': [{'id': 8, 'login': 'author8',
                                                   'html_url': 'https://github.com/author8'}]}])
        completed = copy.deepcopy(self.run.state['ops'][key])
        self.assertEqual(completed['status'], 'complete')
        self.run.close(); self.run = Research(self.path)
        self.run.repo(row)
        self.run.repo(row)
        self.run.save()
        self.assertEqual(self.run.state['ops'][key], completed)
        self.assertNotIn(sid + '|contributors', self.run.state['ops'])
        self.assertIn('github-account:8', self.run.state['records'])

    def test_readonly_status_keeps_a_consistent_snapshot_during_writer_commit(self):
        reader = Research(self.path, readonly=True)
        try:
            before = reader.status()['operations']
            self.run.state['ops'][self.key]['status'] = 'complete'
            self.run.save()
            self.assertEqual(reader.status()['operations'], before)
            self.assertNotEqual(self.run.status()['operations'], before)
        finally:
            reader.close()

    def test_doctor_detects_moved_worktree_and_invalid_venv(self):
        (self.root/'.git').write_text('gitdir: /missing/old/location')
        (self.root/'.venv').mkdir()
        with patch('digital_sztu.runtime.storage_status', return_value={'ok': True}):
            result = environment_diagnostics(self.root)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['errors']), 2)


if __name__ == '__main__':
    unittest.main()

from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from digital_sztu.discovery import Research, initialize


class SocialExpansionExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'state.sqlite3'
        initialize(self.db)
        self.run = Research(self.db)
        self.row = {'id': 7, 'login': 'tool', 'html_url': 'https://github.com/tool', 'type': 'User'}
        self.sid = self.run.account(self.row, anchor=True)
        self.review = {'id': self.sid, 'verification_status': 'candidate',
                       'relevance_reason': 'Reviewed automatic attribution account; no human campus identity inferred',
                       'expansion_exclusion': 'tool-attribution-account',
                       'evidence': [{'url': 'https://example.org/attribution', 'locator': 'Coauthor settings',
                                     'accessed_at': '2026-09-06T00:00:00Z'}]}
        self.run.save()

    def tearDown(self):
        self.run.close()
        self.temp.cleanup()

    def test_review_preserves_cursor_completed_lists_edges_and_downstream(self):
        key = self.sid + '|followers'
        self.run.state['ops'][key].update(status='deferred', pages=25, returned=2500,
                                         next_endpoint='users/tool/followers?page=26',
                                         graphql_cursor='saved-cursor', pagination_api='rest')
        self.run.state['ops'][self.sid + '|following'].update(status='complete', pages=1, returned=0)
        child = self.run.account({'id': 8, 'login': 'candidate', 'html_url': 'https://github.com/candidate'},
                                 parent=self.sid, distance=1)
        edge = self.run.edge(self.sid, 'followed-by', child, self.review['evidence'][0])
        self.run.save()
        child_before = copy.deepcopy(self.run.state['records'][child])
        edge_before = copy.deepcopy(self.run.state['edges'][edge])
        child_ops = {k: copy.deepcopy(v) for k, v in self.run.state['ops'].items() if k.startswith(child + '|')}
        self.run.review([self.review])
        self.run.close(); self.run = Research(self.db)
        op = self.run.state['ops'][key]
        self.assertEqual(op['status'], 'stopped-policy')
        self.assertEqual(op['policy_stop']['previous_status'], 'deferred')
        self.assertEqual((op['pages'], op['returned'], op['graphql_cursor']), (25, 2500, 'saved-cursor'))
        self.assertEqual(op['next_endpoint'], 'users/tool/followers?page=26')
        self.assertEqual(self.run.state['ops'][self.sid + '|following']['status'], 'complete')
        self.assertEqual(self.run.state['records'][child], child_before)
        self.assertEqual(self.run.state['edges'][edge], edge_before)
        self.assertEqual({k: v for k, v in self.run.state['ops'].items() if k.startswith(child + '|')}, child_ops)
        original = copy.deepcopy(op)
        self.run.review([self.review])
        self.assertEqual(self.run.state['ops'][key], original)

    def test_reencounter_and_rename_do_not_reopen_explicit_exclusion(self):
        self.run.review([self.review])
        self.run.account({**self.row, 'login': 'renamed', 'html_url': 'https://github.com/renamed'}, anchor=True)
        self.run.enqueue(self.sid, 'followers', reopen=True)
        self.assertEqual(self.run.state['ops'][self.sid + '|followers']['status'], 'stopped-policy')
        self.assertEqual(self.run.state['records'][self.sid]['previous_logins'], ['tool'])

    def test_rest_and_graphql_guards_do_not_fetch_excluded_social_pages(self):
        self.run.review([self.review])
        for kind, transport in (('following', 'rest'), ('followers', 'graphql')):
            op = self.run.state['ops'][self.sid + '|' + kind]
            op.update(status='pending', graphql_cursor='saved', pages=2, returned=100, pagination_api=transport)
            self.run.save()
            with patch.object(self.run, 'api', side_effect=AssertionError('Unexpected REST request')), \
                 patch.object(self.run, 'public_query', side_effect=AssertionError('Unexpected GraphQL request')):
                if transport == 'rest': self.run.execute(op)
                else: self.run.list_batch(kind, 1)
            self.assertEqual(op['status'], 'stopped-policy')
            self.assertEqual((op['graphql_cursor'], op['pages'], op['returned']), ('saved', 2, 100))

    def test_invalid_batch_does_not_partially_apply_policy(self):
        invalid = {**self.review, 'evidence': []}
        with self.assertRaises(ValueError): self.run.review([self.review, invalid])
        self.run.save()
        self.assertNotIn('expansion_exclusion', self.run.state['records'][self.sid])
        self.assertEqual(self.run.state['ops'][self.sid + '|followers']['status'], 'pending')
        with self.assertRaises(ValueError):
            self.run.review([{**self.review, 'expansion_exclusion': 'name-looks-like-tool'}])
        self.run.state['records'][self.sid]['record_type'] = 'repository'
        with self.assertRaises(ValueError): self.run.review([self.review])

    def test_confirmation_refreshes_completed_candidate_metadata_once(self):
        rec = self.run.state['records'][self.sid]
        rec.update(record_type='repository', category='unknown')
        key = self.run.enqueue(self.sid, 'metadata')
        self.run.state['ops'][key]['status'] = 'complete'
        review = {k: v for k, v in self.review.items() if k != 'expansion_exclusion'}
        review.update(verification_status='confirmed', category='course-homework')
        self.run.review([review])
        self.assertEqual(self.run.state['ops'][key]['status'], 'pending')
        self.run.state['ops'][key]['status'] = 'complete'
        self.run.review([review])
        self.assertEqual(self.run.state['ops'][key]['status'], 'complete')

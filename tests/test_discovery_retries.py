import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from digital_sztu.discovery import Research, initialize


def response(body, status=200, headers=''):
    raw = body if isinstance(body, str) else json.dumps(body)
    return subprocess.CompletedProcess([], int(status >= 400),
        f'HTTP/2 {status}\n{headers}\n{raw}', '')


class GraphQLRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.sqlite3'
        initialize(self.path)
        self.run = Research(self.path)
        self.run.state['records']['github-account:7'] = {
            'id': 'github-account:7', 'title': 'user7', 'record_type': 'account',
            'account_type': 'User', 'verification_status': 'candidate'}
        self.key = self.run.enqueue('github-account:7', 'repos')
        self.run.state['ops'][self.key].update(pagination_api='graphql',
            graphql_cursor='saved-page-3', pages=3, returned=30)
        self.run.state['list_repos_page_size'] = 10
        self.run.save()
        self.original = copy.deepcopy(self.run.state['ops'][self.key])

    def tearDown(self):
        self.run.close()
        self.temp.cleanup()

    def test_retry_replays_same_cursor_and_commits_page_once(self):
        data = {'a0': {'databaseId': 7, 'results': {'totalCount': 30,
            'pageInfo': {'hasNextPage': False, 'endCursor': None}, 'nodes': []}}}
        with patch('digital_sztu.discovery_graphql.subprocess.run', side_effect=[
                subprocess.TimeoutExpired('gh', 45), response({'data': data})]) as request, \
                patch('digital_sztu.discovery_graphql.time.sleep') as sleep:
            self.assertEqual(self.run.list_batch('repos', 1), (1, None))
        self.assertEqual(request.call_args_list[0], request.call_args_list[1])
        self.assertIn('saved-page-3', request.call_args.kwargs['input'])
        sleep.assert_called_once_with(5)
        self.run.close(); self.run = Research(self.path)
        op = self.run.state['ops'][self.key]
        self.assertEqual((op['pages'], op['returned'], op['status']), (4, 30, 'complete'))
        self.assertIsNone(op['graphql_cursor'])
        self.assertEqual(self.run.state['api_calls'], 2)

    def test_persistent_failure_is_bounded_and_preserves_saved_page(self):
        frames = []
        self.run._progress_callback = frames.append
        self.run._progress_at = float('inf')
        with patch('digital_sztu.discovery_graphql.subprocess.run',
                   return_value=response({'message': 'Unavailable'}, 503)) as request, \
                patch('digital_sztu.discovery_graphql.time.sleep') as sleep:
            self.assertEqual(self.run.list_batch('repos', 1), (0, 'graphql-unavailable'))
        self.assertEqual(request.call_count, 4)
        self.assertEqual(sleep.call_args_list, [call(5), call(15), call(45)])
        self.assertEqual([f['wait_seconds'] for f in frames], [5, 15, 45])
        self.run.close(); self.run = Research(self.path)
        self.assertEqual(self.run.state['ops'][self.key], self.original)
        retries = [json.loads(row[0]) for row in self.run.db.execute('SELECT body FROM audit')
                   if json.loads(row[0])['kind'] == 'graphql-retry']
        self.assertEqual(len(retries), 3)

    def test_invalid_success_response_retries_but_auth_and_rate_do_not(self):
        cases = [(200, 'broken', '', 4, 'graphql-unavailable'),
                 (401, 'broken', '', 1, 'graphql-http-401'),
                 (401, {'message': 'Bad credentials'}, '', 1, 'graphql-http-401'),
                 (403, 'broken', 'Retry-After: 120\n', 1, 'graphql-error'),
                 (429, 'broken', 'Retry-After: 120\n', 1, 'graphql-error'),
                 (429, {'message': 'Rate limited'}, 'Retry-After: 120\n', 1, 'graphql-error'),
                 (503, 'broken', 'Retry-After: 120\n', 1, 'graphql-error'),
                 (503, {'message': 'Unavailable'}, 'Retry-After: 120\n', 1, 'graphql-error')]
        for status, body, headers, attempts, error in cases:
            with self.subTest(status=status, body=body):
                self.run.state['blocked_until'] = {}
                with patch('digital_sztu.discovery_graphql.subprocess.run',
                           return_value=response(body, status, headers)) as request, \
                        patch('digital_sztu.discovery_graphql.time.sleep') as sleep, \
                        patch('digital_sztu.discovery_graphql.time.time', return_value=1000):
                    self.assertEqual(self.run.public_query(['a0:viewer{login}'], 'readme', 1)[1], error)
                    self.assertEqual(request.call_count, attempts)
                    if status in (403, 429, 503):
                        self.assertEqual(self.run.state['blocked_until']['all'], 1120)
                    if attempts == 1:
                        sleep.assert_not_called()

    def test_successful_request_after_failure_gets_its_own_retry_budget(self):
        values = [response('broken'), response({'data': {'a0': {}}})] * 2
        with patch('digital_sztu.discovery_graphql.subprocess.run', side_effect=values), \
                patch('digital_sztu.discovery_graphql.time.sleep') as sleep:
            for _ in range(2):
                self.assertIsNone(self.run.public_query(['a0:viewer{login}'], 'readme', 1)[1])
        self.assertEqual(sleep.call_args_list, [call(5), call(5)])

    def test_existing_query_reduction_precedes_retries(self):
        with patch('digital_sztu.discovery_graphql.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('gh', 45)) as request, \
                patch('digital_sztu.discovery_graphql.time.sleep') as sleep:
            self.assertEqual(self.run.public_query(['a0:viewer{login}'], 'readme', 8),
                             (None, 'query-size-adjusted'))
        self.assertEqual(self.run.state['readme_batch_size'], 4)
        request.assert_called_once()
        sleep.assert_not_called()

    def test_interrupt_during_wait_returns_recovery_and_preserves_cursor(self):
        with patch.object(self.run, '_resume', side_effect=lambda *a: self.run.list_batch('repos', 1)), \
                patch('digital_sztu.discovery_graphql.subprocess.run', return_value=response('broken')), \
                patch('digital_sztu.discovery_graphql.time.sleep', side_effect=KeyboardInterrupt):
            result = self.run.resume(10)
        self.assertEqual(result['blocked'], 'interrupted')
        self.assertIn('--database', result['resume_command'])
        self.assertEqual(self.run.state['ops'][self.key], self.original)

    def test_disk_full_before_retry_prevents_another_request(self):
        with patch.object(self.run, '_resume', side_effect=lambda *a: self.run.list_batch('repos', 1)), \
                patch('digital_sztu.discovery_graphql.subprocess.run', return_value=response('broken')) as request, \
                patch('digital_sztu.discovery_graphql.time.sleep'), \
                patch('digital_sztu.discovery_graphql.require_storage', side_effect=[None, OSError(28, 'full')]):
            result = self.run.resume(10)
        self.assertEqual(result['blocked'], 'storage-full')
        request.assert_called_once()
        self.assertEqual(self.run.state['ops'][self.key], self.original)

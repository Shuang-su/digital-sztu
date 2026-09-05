from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_repository import ExampleRepository, write_json
from digital_sztu.build import build_indexes
from digital_sztu.discovery import Research, initialize
from digital_sztu.graph import viewer_html, write_viewer
from digital_sztu.promotion import promote, recover_promotion
from digital_sztu.utils import load_json, sha256_file
from digital_sztu.validation import validate_repository


def knowledge(repo, rid='knowledge-example'):
    value = repo.event()
    value.update(schema_version='0.2.0', type='knowledge', id=rid, title='中文知识 <测试> & 档案', category='campus-project',
                 validity={'start': None, 'end': None, 'state': 'unknown', 'verified_at': None}, external_ids=['github-repo:123'], narrative=None)
    value.pop('time')
    return value


def seed_state():
    return {'run_id': 'test-run', 'records': {}, 'edges': {}, 'ops': {}, 'aggregate': {'repo_metadata_nonmatches': 0}, 'api_calls': 0, 'no_new_convergence_rounds': 0}


class ModelAndViewsTests(unittest.TestCase):
    def setUp(self):
        self.repo = ExampleRepository()
        self.root = self.repo.root
        self.record = knowledge(self.repo)
        self.path = self.root / 'content/knowledge/knowledge-example/record.json'
        write_json(self.path, self.record)

    def tearDown(self):
        self.repo.close()

    def test_legacy_alias_is_same_implementation(self):
        import sztu_connect.build
        import digital_sztu.build
        self.assertIs(sztu_connect.build, digital_sztu.build)

    def test_unknown_validity_and_cross_record_navigation(self):
        self.record['narrative'] = 'index.md'
        write_json(self.path, self.record)
        self.path.with_name('index.md').write_text('[[event-example-structure|结构]]', encoding='utf-8')
        self.assertTrue(build_indexes(self.root)['ok'])
        result = load_json(self.root / 'data/generated/archive.json')
        detail = result['details'][self.record['id']]
        self.assertIsNone(detail['validity']['start'])
        self.assertNotIn('time', detail)
        self.assertTrue(any(edge['from'] == self.record['id'] and edge['relation'] == 'wikilink' for edge in result['edges']))
        page = self.root / 'data/generated/catalog/records/knowledge-example.md'
        self.assertIn('[结构](event-example-structure.md)', page.read_text())

    def test_invalid_validity_and_duplicate_external_identity(self):
        self.record['validity']['start'] = '2026-02-30'
        write_json(self.path, self.record)
        self.assertFalse(validate_repository(self.root)['ok'])
        self.record['validity']['start'] = None
        other = copy.deepcopy(self.record)
        other['id'] = 'knowledge-other'
        write_json(self.path, self.record)
        write_json(self.path.parent.parent / 'knowledge-other/record.json', other)
        self.assertTrue(any('duplicate external identity' in e for e in validate_repository(self.root)['errors']))

    def test_same_label_different_id_is_not_merged(self):
        other = copy.deepcopy(self.record)
        other.update(id='knowledge-other', external_ids=['github-repo:456'])
        write_json(self.path.parent.parent / 'knowledge-other/record.json', other)
        self.assertTrue(build_indexes(self.root)['ok'])
        nodes = load_json(self.root / 'data/generated/graph.json')['nodes']
        self.assertEqual(sum(n['label'] == self.record['title'] for n in nodes), 2)

    def test_contradiction_is_preserved_in_every_view(self):
        self.record['status'] = 'contested'
        self.record['claims'][0]['citations'].append({'source_id': 'source-example-documentation', 'role': 'contradicts', 'locator': '反证位置', 'note': None})
        write_json(self.path, self.record)
        self.assertTrue(build_indexes(self.root)['ok'])
        graph = load_json(self.root / 'data/generated/archive.json')
        self.assertTrue(any(e['from'] == self.record['id'] and e['relation'] == 'contradicts' for e in graph['edges']))
        self.assertIn('contradicts', (self.root / 'data/generated/catalog/records/knowledge-example.md').read_text())

    def test_hidden_evidence_excludes_dependents_and_stale_pages(self):
        self.assertTrue(build_indexes(self.root)['ok'])
        source_path = self.root / 'sources/records/source-example-documentation.json'
        source = load_json(source_path)
        source['privacy']['indexing'] = 'exclude'
        write_json(source_path, source)
        self.assertTrue(build_indexes(self.root)['ok'])
        self.assertFalse((self.root / 'data/generated/catalog/records/knowledge-example.md').exists())
        for path in (self.root / 'data/generated').rglob('*'):
            if path.is_file():
                text = path.read_text()
                self.assertNotIn('knowledge-example', text, path)
                self.assertNotIn('source-example-documentation', text, path)

    def test_credential_url_never_reaches_public_views(self):
        source_path = self.root / 'sources/records/source-example-documentation.json'
        source = load_json(source_path)
        source['locator']['original_url'] = 'https://example.org/?access_' + 'token=opaque-test'
        write_json(source_path, source)
        self.assertTrue(build_indexes(self.root)['ok'])
        self.assertNotIn(self.record['id'], load_json(self.root / 'data/generated/archive.json')['details'])

    def test_all_formats_use_same_revision_and_build_is_deterministic(self):
        self.assertTrue(build_indexes(self.root)['ok'])
        output = self.root / 'data/generated'
        first = {p.relative_to(output): p.read_bytes() for p in output.rglob('*') if p.is_file()}
        revision = load_json(output / 'graph.json')['dataset_revision']
        for path in ('archive.json', 'graph-preview.svg', 'catalog/README.md', 'knowledge/manifest.json'):
            self.assertIn(revision, (output / path).read_text())
        page = write_viewer(self.root, self.root / '.work/graph')
        self.assertIn(revision, Path(page['output']).read_text())
        self.assertTrue(build_indexes(self.root)['ok'])
        self.assertEqual(first, {p.relative_to(output): p.read_bytes() for p in output.rglob('*') if p.is_file()})

    def test_html_escapes_script_and_has_no_remote_runtime(self):
        self.record['summary'] = '</script><img src=x onerror=alert(1)>'
        write_json(self.path, self.record)
        self.assertTrue(build_indexes(self.root)['ok'])
        text = viewer_html(load_json(self.root / 'data/generated/archive.json'))
        self.assertNotIn(self.record['summary'], text)
        self.assertIn('\\u003c/script\\u003e', text)
        self.assertNotIn('<script src=', text)
        self.assertIn("default-src 'none'", text)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.legacy = self.root / 'state.json'
        write_json(self.legacy, seed_state())
        self.db = self.root / 'state.sqlite3'
        initialize(self.db, self.legacy)
        self.run = Research(self.db)

    def tearDown(self):
        self.run.close()
        self.temp.cleanup()

    def account(self, identifier=7, **kwargs):
        return self.run.account({'id': identifier, 'login': f'user{identifier}', 'html_url': f'https://github.com/user{identifier}', 'type': 'User'}, **kwargs)

    def test_import_does_not_mutate_legacy(self):
        self.assertEqual(self.run.status()['legacy_inputs'][0]['sha256'], sha256_file(self.legacy))
        with self.assertRaises(ValueError):
            initialize(self.db, self.legacy)

    def test_bridge_boundary_and_cycles(self):
        a = self.account(anchor=True)
        b = self.account(8, parent=a, distance=1)
        c = self.account(9, parent=b, distance=2)
        self.assertIn(b + '|followers', self.run.state['ops'])
        self.assertNotIn(c + '|followers', self.run.state['ops'])
        self.account(8, parent=c, distance=2)
        self.run.save()
        self.assertEqual(len(self.run.state['records']), 3)
        self.assertEqual(self.run.state['records'][b]['best_unknown_distance'], 1)

    def test_profile_rename_uses_numeric_identity(self):
        sid = self.account()
        self.run.save()
        seen = []
        def api(endpoint):
            seen.append(endpoint)
            return {'id':7,'login':'renamed','html_url':'https://github.com/renamed','type':'User'}, {}, None
        with patch.object(self.run, 'api', api):
            self.run.profile({}, self.run.state['records'][sid])
        self.assertEqual(seen, ['user/7'])
        self.assertEqual(self.run.state['records'][sid]['title'], 'renamed')
        self.assertEqual(self.run.state['records'][sid]['previous_logins'], ['user7'])

    def test_page_checkpoint_resume_replay_deduplicates(self):
        sid = self.account()
        key = self.run.enqueue(sid, 'followers')
        op = self.run.state['ops'][key]
        responses = [([{'id': 8}], {'link':'<https://api.github.com/users/user7/followers?page=2>; rel="next"'}, None), (None, {}, 'rate-limit')]
        with patch.object(self.run, 'api', side_effect=responses):
            self.run.pages(op, 'users/user7/followers', lambda row, cursor: self.account(row['id']))
        self.assertEqual(op['pages'], 1)
        self.assertEqual(op['status'], 'deferred')
        cursor = op['next_endpoint']
        self.run.save(); self.run.close(); self.run = Research(self.db)
        op = self.run.state['ops'][key]
        with patch.object(self.run, 'api', return_value=([{'id': 8}], {}, None)) as request:
            self.run.pages(op, 'users/user7/followers', lambda row, cursor: self.account(row['id']))
        self.assertEqual(request.call_args.args[0], cursor)
        self.assertEqual(op['status'], 'complete')
        self.assertEqual(len(self.run.state['records']), 2)

    def test_uncommitted_page_disappears_on_process_reopen(self):
        sid = self.account()
        self.run.save()
        self.account(8)
        self.run.state['ops'][self.run.enqueue(sid, 'followers')]['next_endpoint'] = 'page2'
        # Abrupt process closure before save leaves both entity and cursor uncommitted.
        self.run.close(); self.run = Research(self.db)
        self.assertNotIn('github-account:8', self.run.state['records'])
        self.assertNotIn(sid + '|followers', self.run.state['ops'])

    def test_fork_does_not_expand_upstream_contributors(self):
        rid = 'github-repo:123'
        self.run.state['records'][rid] = {'id':rid,'record_type':'repository','title':'a/fork','is_fork':True,'verification_status':'confirmed'}
        op = {'id':rid+'|contributors','entity_id':rid,'operation':'contributors'}
        with patch.object(self.run, 'api') as api:
            self.run.execute(op)
        api.assert_not_called()
        self.assertEqual(op['status'], 'scoped-review-required')

    def test_incomplete_review_cannot_confirm_candidate(self):
        sid = self.account()
        self.run.save()
        with self.assertRaises(ValueError):
            self.run.review([{'id':sid,'verification_status':'confirmed','relevance_reason':'claim without evidence'}])
        self.assertEqual(self.run.state['records'][sid]['verification_status'], 'candidate')

    def test_promotion_gate_does_not_drop_pending_candidates(self):
        self.account(anchor=True)
        self.run.save()
        with self.assertRaisesRegex(ValueError, 'Survey remains partial'):
            promote(self.root, self.run, None)
        self.assertGreater(self.run.status()['operations']['pending'], 0)

    def test_search_truncation_is_not_convergence(self):
        sid = self.account()
        key = self.run.enqueue(sid, 'repository-search')
        with patch.object(self.run, 'api', return_value=({'items':[], 'total_count':1001,'incomplete_results':True}, {}, None)):
            self.run.pages(self.run.state['ops'][key], 'search/repositories?q=SZTU', lambda *_: None, search=True)
        self.assertEqual(self.run.state['ops'][key]['status'], 'restricted')
        self.assertFalse(self.run.status()['promotion_ready'])

    def test_export_preserves_private_research_frontier(self):
        sid = self.account(anchor=True)
        self.run.save()
        self.run.export(self.root / 'export')
        graph = load_json(self.root / 'export/graph.json')
        self.assertEqual(graph['status'], 'partial')
        self.assertEqual(graph['nodes'][0]['id'], sid)
        self.assertGreater(len(graph['frontier']), 0)


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.repo = ExampleRepository()
        self.root = self.repo.root
        self.db = self.root / '.work/discovery/state.sqlite3'
        initialize(self.db)
        self.run = Research(self.db)
        # Isolated converged fixture, never the real research queue.
        self.run.state['no_new_convergence_rounds'] = 2
        self.entity = 'github-repo:123'
        self.run.state['records'][self.entity] = {'id': self.entity, 'record_type': 'repository', 'verification_status': 'confirmed',
            'evidence': [{'url': 'https://example.org', 'locator': 'fixture', 'accessed_at': '2026-09-05T00:00:00Z'}]}
        self.run.save()
        self.record = knowledge(self.repo)
        self.spec = self.root / '.work/promotion.json'
        write_json(self.spec, {'records': [{'data':self.record}], 'mappings':[
            {'run_id':self.run.run_id,'entity_id':self.entity,'record_ids':[self.record['id']]}]})
        self.target = self.root / 'content/knowledge/knowledge-example/record.json'

    def tearDown(self):
        self.run.close()
        self.repo.close()

    def test_success_is_idempotent_and_preserves_existing_sources(self):
        source = self.root / 'sources/records/source-example-documentation.json'
        before = sha256_file(source)
        result = promote(self.root, self.run, self.spec)
        self.assertTrue(result['ok'])
        self.assertEqual(result['files_created'], 1)
        second = promote(self.root, self.run, self.spec)
        self.assertTrue(second['idempotent'])
        self.assertEqual(before, sha256_file(source))
        self.assertEqual(self.run.db.execute('SELECT count(*) FROM promotions').fetchone()[0], 1)

    def test_validation_failure_writes_nothing(self):
        value = load_json(self.spec)
        value['records'][0]['data']['claims'][0]['citations'][0]['source_id'] = 'source-missing'
        write_json(self.spec, value)
        result = promote(self.root, self.run, self.spec)
        self.assertFalse(result['ok'])
        self.assertFalse(self.target.exists())

    def test_existing_different_record_is_not_overwritten(self):
        other = copy.deepcopy(self.record)
        other['summary'] = 'Existing user edit'
        write_json(self.target, other)
        before = self.target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'differs'):
            promote(self.root, self.run, self.spec)
        self.assertEqual(before, self.target.read_bytes())

    def test_exception_after_file_install_rolls_back_files_and_mapping(self):
        with patch.object(self.run, 'save', side_effect=RuntimeError('simulated disk failure')):
            with self.assertRaisesRegex(RuntimeError, 'simulated'):
                promote(self.root, self.run, self.spec)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.run.db.execute('SELECT count(*) FROM promotions').fetchone()[0], 0)
        self.assertFalse((self.root / '.work/promotion-journal.json').exists())

    def test_recovery_preserves_independently_edited_file(self):
        from digital_sztu.utils import sha256_bytes
        write_json(self.target, self.record)
        write_json(self.root / '.work/promotion-journal.json', {'state':'installing','created':[
            {'path':self.target.relative_to(self.root).as_posix(),'sha256':sha256_bytes(self.target.read_bytes())}]})
        self.target.write_text('user correction')
        with self.assertRaisesRegex(ValueError, 'changed'):
            recover_promotion(self.root)
        self.assertEqual(self.target.read_text(), 'user correction')


class ProfileBatchTests(unittest.TestCase):
    setUp = ResearchTests.setUp
    tearDown = ResearchTests.tearDown
    account = ResearchTests.account

    def test_graphql_batch_applies_stable_ids_and_zero_lists(self):
        from types import SimpleNamespace
        sid = self.account(anchor=True)
        self.run.save()
        response = {'data': {'a0': {'databaseId': 7, 'login':'user7','url':'https://github.com/user7','websiteUrl':None,
                    'repositories':{'totalCount':0},'followers':{'totalCount':0},'following':{'totalCount':0},'starredRepositories':{'totalCount':0}},
                    'rateLimit':{'remaining':4999,'resetAt':'2026-09-05T23:00:00Z','cost':1}}}
        with patch('digital_sztu.discovery.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(response),returncode=0)) as request:
            count, error = self.run.profile_batch()
        self.assertEqual((count,error), (1,None))
        self.assertIn('query {', json.loads(request.call_args.kwargs['input'])['query'])
        for op in ('profile','repos','stars','followers','following'):
            self.assertEqual(self.run.state['ops'][sid+'|'+op]['status'], 'complete')

    def test_reused_login_falls_back_to_numeric_identity(self):
        from types import SimpleNamespace
        sid = self.account(anchor=True)
        self.run.save()
        response = {'data': {'a0':{'databaseId':8}}}
        with patch('digital_sztu.discovery.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(response),returncode=0)):
            with patch.object(self.run,'api',return_value=({'id':7,'login':'renamed','html_url':'https://github.com/renamed','type':'User'}, {}, None)) as api:
                count,error = self.run.profile_batch()
        self.assertEqual((count,error), (1,None))
        self.assertEqual(api.call_args.args[0], 'user/7')
        self.assertEqual(self.run.state['records'][sid]['title'],'renamed')

    def test_rate_error_never_marks_batch_complete(self):
        from types import SimpleNamespace
        sid = self.account(anchor=True)
        self.run.save()
        response = {'errors':[{'type':'RATE_LIMITED'}]}
        with patch('digital_sztu.discovery.subprocess.run',return_value=SimpleNamespace(stdout=json.dumps(response),returncode=1)):
            count,error = self.run.profile_batch()
        self.assertEqual(count, 0)
        self.assertEqual(error, 'graphql-error')
        self.assertEqual(self.run.state['ops'][sid+'|profile']['status'], 'pending')


class ReleaseTests(unittest.TestCase):
    def test_public_git_check_blocks_secret_without_echoing_value(self):
        from digital_sztu.public import check_public_records
        repo = ExampleRepository()
        try:
            source = repo.root / 'sources/records/source-example-documentation.json'
            value = load_json(source)
            secret = 'ghp_' + 'X' * 36
            value['notes'] = secret
            write_json(source, value)
            result = check_public_records(repo.root)
            self.assertFalse(result['ok'])
            self.assertNotIn(secret, json.dumps(result))
            self.assertTrue(build_indexes(repo.root)['ok'])
        finally:
            repo.close()

    def test_validity_precision_overlap_does_not_invent_months(self):
        repo = ExampleRepository()
        try:
            record = knowledge(repo)
            record['validity'].update(start='2026-12', end='2026')
            write_json(repo.root/'content/knowledge/knowledge-example/record.json',record)
            self.assertTrue(validate_repository(repo.root)['ok'])
        finally:
            repo.close()


class AdditionalResearchGuards(unittest.TestCase):
    setUp = ResearchTests.setUp
    tearDown = ResearchTests.tearDown
    account = ResearchTests.account

    def test_resume_respects_persisted_rate_reset(self):
        import time
        self.account(anchor=True)
        self.run.state['blocked_until'] = {'all': time.time()+300}
        self.run.save()
        with patch('digital_sztu.discovery.subprocess.run') as request:
            result = self.run.resume(1)
        request.assert_not_called()
        self.assertEqual(result['blocked'], 'rate-deferred')
        self.assertGreater(result['operations']['pending'], 0)

    def test_no_new_round_compares_identities_not_net_count(self):
        self.run.state['records']['github-repo:1'] = {'id':'github-repo:1','record_type':'repository','verification_status':'confirmed'}
        self.run.save()
        self.run.sweep(['SZTU'])
        for op in self.run.state['ops'].values():
            op['status'] = 'complete'
        self.run.state['records']['github-repo:1']['verification_status'] = 'excluded'
        self.run.state['records']['github-repo:2'] = {'id':'github-repo:2','record_type':'repository','verification_status':'confirmed'}
        self.run.save()
        result = self.run.sweep(complete=True)
        self.assertEqual(result['no_new_convergence_rounds'], 0)
        self.assertEqual(self.run.state['sweeps'][-1]['new_confirmed'], 1)

    def test_transient_page_error_keeps_cursor_executable(self):
        sid = self.account()
        op = self.run.state['ops'][self.run.enqueue(sid,'followers')]
        with patch.object(self.run,'api',return_value=(None,{},'http-503')):
            self.run.pages(op,'users/user7/followers',lambda *_:None)
        self.assertEqual(op['status'],'deferred')
        self.assertEqual(op['next_endpoint'],'users/user7/followers')


class ListBatchTests(unittest.TestCase):
    setUp = ResearchTests.setUp
    tearDown = ResearchTests.tearDown
    account = ResearchTests.account

    def response(self, rows, more=False, cursor=None, identifier=7):
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0, stdout=json.dumps({'data': {'a0': {
            'databaseId': identifier, 'login': 'user7', 'url': 'https://github.com/user7',
            'results': {'nodes': rows, 'totalCount': len(rows) + int(more),
                        'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}}}}))

    def row(self, identifier=8):
        return {'__typename':'User', 'databaseId':identifier, 'login':f'user{identifier}', 'url':f'https://github.com/user{identifier}'}

    def test_page_cursor_and_observations_commit_together_and_resume(self):
        sid = self.account(distance=1)
        self.run.save()
        with patch('digital_sztu.discovery.subprocess.run', return_value=self.response([self.row()], True, 'next-page')):
            self.assertEqual(self.run.list_batch('following'), (1, None))
        self.run.close()
        self.run = Research(self.db)
        self.assertEqual(self.run.state['ops'][sid+'|following']['graphql_cursor'], 'next-page')
        self.assertIn('github-account:8', self.run.state['records'])
        with patch('digital_sztu.discovery.subprocess.run', return_value=self.response([self.row(9)])) as request:
            self.run.list_batch('following')
        self.assertIn('after:"next-page"', json.loads(request.call_args.kwargs['input'])['query'])
        self.assertEqual(self.run.state['ops'][sid+'|following']['returned'], 2)
        self.assertEqual(self.run.state['ops'][sid+'|following']['status'], 'complete')
        self.assertEqual(self.run.status()['unfinished_pagination'], 0)

    def test_old_rest_cursor_is_never_restarted_as_graphql(self):
        sid = self.account(anchor=True)
        op = self.run.state['ops'][sid+'|following']
        op.update(pages=1,next_endpoint='https://api.github.com/users/user7/following?page=2')
        self.run.save()
        with patch('digital_sztu.discovery.subprocess.run') as request:
            self.assertEqual(self.run.list_batch('following'), (0,None))
        request.assert_not_called()
        self.assertEqual(op['pages'], 1)

    def test_repeated_cursor_does_not_commit_or_drop_page(self):
        sid = self.account(anchor=True)
        self.run.state['ops'][sid+'|following'].update(pagination_api='graphql',pages=1,returned=100,graphql_cursor='same')
        self.run.save()
        with patch('digital_sztu.discovery.subprocess.run', return_value=self.response([self.row()],True,'same')):
            self.run.list_batch('following')
        op = self.run.state['ops'][sid+'|following']
        self.assertEqual((op['status'],op['returned'],op['graphql_cursor']),('deferred',100,'same'))
        self.assertNotIn('github-account:8', self.run.state['records'])

    def test_social_boundary_is_enforced_before_query(self):
        sid = self.account(distance=2)
        self.run.enqueue(sid,'following')
        self.run.save()
        with patch('digital_sztu.discovery.subprocess.run') as request:
            self.run.list_batch('following')
        request.assert_not_called()
        self.assertEqual(self.run.state['ops'][sid+'|following']['status'],'stopped-policy')

    def test_stale_login_list_is_not_consumed(self):
        sid = self.account(anchor=True)
        self.run.save()
        with patch('digital_sztu.discovery.subprocess.run',return_value=self.response([self.row(88)],identifier=999)):
            with patch.object(self.run,'api',return_value=({'id':7,'login':'renamed','html_url':'https://github.com/renamed','type':'User'}, {}, None)):
                self.run.list_batch('following')
        self.assertEqual(self.run.state['records'][sid]['title'],'renamed')
        self.assertNotIn('github-account:88',self.run.state['records'])
        self.assertEqual(self.run.state['ops'][sid+'|following']['status'],'pending')

    def test_owned_zero_does_not_finish_all_affiliations_list(self):
        sid = self.account(anchor=True)
        self.run.profile_data(self.run.state['ops'][sid+'|profile'],self.run.state['records'][sid],
                              {'id':7,'login':'user7','html_url':'https://github.com/user7','type':'User','public_repos':0})
        self.assertEqual(self.run.state['ops'][sid+'|repos']['status'],'pending')

    def test_missing_node_does_not_commit_partial_list(self):
        sid = self.account(anchor=True)
        self.run.save()
        with patch('digital_sztu.discovery.subprocess.run',return_value=self.response([self.row(),None])):
            self.run.list_batch('following')
        self.assertNotIn('github-account:8',self.run.state['records'])
        self.assertEqual(self.run.state['ops'][sid+'|following']['status'],'deferred')


class PublicBoundaryTests(unittest.TestCase):
    def test_narrative_symlink_is_excluded_from_all_public_formats(self):
        repo = ExampleRepository()
        try:
            value = knowledge(repo)
            value['narrative'] = 'index.md'
            path = repo.root / 'content/knowledge/knowledge-example/record.json'
            write_json(path, value)
            target = path.with_name('private.md')
            target.write_text('private-body-marker',encoding='utf-8')
            try:
                path.with_name('index.md').symlink_to(target.name)
            except OSError:
                self.skipTest('Symlinks unavailable on this host')
            self.assertTrue(build_indexes(repo.root)['ok'])
            payload=load_json(repo.root/'data/generated/archive.json')
            self.assertNotIn(value['id'],payload['details'])
            self.assertNotIn('private-body-marker',json.dumps(payload))
        finally:
            repo.close()

    def test_research_cleaner_retains_names_and_omits_credential_patterns(self):
        from digital_sztu.discovery_policy import clean,url
        original='公开作者 张三 / Manyou Ma '+ 'AKIA' + 'X'*16
        self.assertIn('张三 / Manyou Ma',clean(original))
        self.assertNotIn('AKIA',clean(original))
        self.assertIsNone(url('http://[::1]/private'))
        self.assertIsNone(url(None))

    def test_large_text_is_scanned_beyond_previous_size_limit(self):
        from digital_sztu.privacy import scan_privacy
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            secret='ghp_'+'X'*36
            with (root/'large.jsonl').open('w') as stream:
                for _ in range(9000):stream.write('x'*1024+'\n')
                stream.write(secret+'\n')
            result=scan_privacy(root)
            self.assertEqual(result['scanned_files'],1)
            self.assertTrue(any(f['kind']=='github-token' and f['line']==9001 for f in result['findings']))
            self.assertNotIn(secret,json.dumps(result))

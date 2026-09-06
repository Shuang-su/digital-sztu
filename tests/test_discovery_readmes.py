from __future__ import annotations

import copy
import hashlib
import unittest
from unittest.mock import patch

import test_v02
from digital_sztu.discovery import Research
from digital_sztu.discovery_readmes import readme_entry


class ReadmeBatchTests(unittest.TestCase):
    setUp = test_v02.ResearchTests.setUp
    tearDown = test_v02.ResearchTests.tearDown

    def fixture(self):
        text = '# SZTU 课程资料\n公开课程说明，不推断作者身份。\n'
        raw = text.encode()
        oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        owner = {'__typename':'User','databaseId':7,'login':'user7','url':'https://github.com/user7'}
        metadata = {'databaseId':9,'isPrivate':False,'nameWithOwner':'user7/course','url':'https://github.com/user7/course',
            'description':None,'isFork':False,'isArchived':False,'createdAt':None,'updatedAt':None,
            'defaultBranchRef':{'name':'main','target':{'oid':'1'*40}},'primaryLanguage':None,'licenseInfo':None,
            'owner':owner,'repositoryTopics':{'totalCount':0,'nodes':[]},'parent':None}
        entry = {'name':'README.md','type':'blob','mode':0o100644,'size':len(raw),'oid':oid}
        tree = {'databaseId':9,'isPrivate':False,'root':{'__typename':'Tree','entries':[entry]},'github':None,'docs':None}
        blob = {'databaseId':9,'isPrivate':False,'readme':{'oid':oid,'byteSize':len(raw),'text':text,'isBinary':False,'isTruncated':False}}
        self.run.state['records']['github-repo:9'] = {'id':'github-repo:9','record_type':'repository','title':'user7/course',
            'verification_status':'candidate','evidence':[],'rights':{'status':'link-only'}}
        self.key = self.run.enqueue('github-repo:9','readme',10)
        self.run.save()
        return metadata, tree, blob

    def test_complete_bytes_are_pinned_and_review_stays_manual(self):
        values = self.fixture()
        with patch.object(self.run,'public_query',side_effect=[({'a0':v},None) for v in values]) as query:
            self.assertEqual(self.run.readme_batch(),(1,None))
        self.run.close(); self.run = Research(self.db)
        rec = self.run.state['records']['github-repo:9']
        self.assertEqual(rec['review_readme'],values[2]['readme']['text'])
        self.assertEqual(rec['readme_current']['commit_sha'],'1'*40)
        self.assertIn('/blob/'+'1'*40+'/README.md',rec['readme_current']['url'])
        self.assertEqual(rec['verification_status'],'candidate')
        self.assertEqual(self.run.state['ops']['github-repo:9|relevance-review']['status'],'pending')
        self.assertEqual(self.run.state['ops'][self.key]['status'],'complete')
        self.assertIn('1'*40+':.github',query.call_args_list[1].args[0][0])
        self.assertIn('oid:"'+values[2]['readme']['oid']+'"',query.call_args_list[2].args[0][0])

    def test_private_or_reused_name_stops_before_trees_and_body(self):
        for changes in ({'isPrivate':True},{'databaseId':99}):
            with self.subTest(changes=changes):
                metadata,_,_ = self.fixture()
                # The reused fixture operation must be pending for each independent read.
                self.run.state['ops'][self.key].update(status='pending',readme_rest_required=False)
                self.run.save()
                metadata.update(changes)
                with patch.object(self.run,'public_query',return_value=({'a0':metadata},None)) as query:
                    self.run.readme_batch()
                self.assertEqual(query.call_count,1)
                self.assertNotIn('review_readme',self.run.state['records']['github-repo:9'])
                expected = 'restricted' if changes.get('isPrivate') else 'pending'
                self.assertEqual(self.run.state['ops'][self.key]['status'],expected)

    def test_wrong_hash_or_truncated_text_never_completes(self):
        for changes in ({'text':'different bytes'},{'isTruncated':True},{'byteSize':0}):
            with self.subTest(changes=changes):
                metadata,tree,blob = self.fixture()
                self.run.state['ops'][self.key].update(status='pending',readme_rest_required=False)
                self.run.save()
                blob['readme'].update(changes)
                with patch.object(self.run,'public_query',side_effect=[({'a0':v},None) for v in (metadata,tree,blob)]):
                    self.run.readme_batch()
                self.assertTrue(self.run.state['ops'][self.key]['readme_rest_required'])
                self.assertEqual(self.run.state['ops'][self.key]['status'],'pending')
                self.assertNotIn('review_readme',self.run.state['records']['github-repo:9'])

    def test_interrupted_blob_request_can_replay_without_fake_completion(self):
        metadata,tree,blob = self.fixture()
        with patch.object(self.run,'public_query',side_effect=[({'a0':metadata},None),({'a0':tree},None),(None,'rate-deferred')]):
            self.assertEqual(self.run.readme_batch(),(0,'rate-deferred'))
        self.run.close(); self.run = Research(self.db)
        self.assertEqual(self.run.state['ops'][self.key]['status'],'pending')
        with patch.object(self.run,'public_query',side_effect=[({'a0':v},None) for v in (metadata,tree,blob)]):
            self.run.readme_batch()
        self.assertEqual(self.run.state['ops'][self.key]['status'],'complete')

    def test_readme_precedence_and_ambiguous_selection_fallback(self):
        _,tree,_ = self.fixture()
        tree['github'] = copy.deepcopy(tree['root'])
        tree['github']['entries'][0]['name'] = 'Readme.txt'
        self.assertEqual(readme_entry(tree)['path'],'.github/Readme.txt')
        tree['github']['entries'].append({**tree['github']['entries'][0],'name':'README.md'})
        self.assertIsNone(readme_entry(tree))
        tree['github'] = None
        tree['root']['entries'][0]['mode'] = 0o120000
        self.assertIsNone(readme_entry(tree))


if __name__ == '__main__':
    unittest.main()

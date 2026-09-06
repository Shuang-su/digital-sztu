from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_repository import ExampleRepository, write_json
from digital_sztu.public import check_public_records, public_url, sensitive_text, public_projection
from digital_sztu.privacy import scan_privacy
from digital_sztu.runtime import environment_diagnostics
from digital_sztu.build import build_indexes, export_knowledge


class PublicReleaseTests(unittest.TestCase):
    def test_quoted_assignment_in_record_prose_cannot_hide_behind_json_escaping(self):
        repo = ExampleRepository()
        try:
            event = repo.event()
            secret = 'fixture-' + 'unusable-password'
            event['summary'] = json.dumps({'password': secret})
            write_json(repo.event_path, event)
            result = check_public_records(repo.root)
            self.assertFalse(result['ok'])
            self.assertNotIn(secret, json.dumps(result))
            projection = public_projection(repo.root, {'event': [(repo.event_path, event)]})
            self.assertFalse(projection.get('event'))
        finally:
            repo.close()

    def test_json_escaped_strings_and_unicode_keys_are_scanned_without_echo(self):
        secret = 'fixture-' + 'unusable-password'
        variants = [json.dumps({'text': json.dumps({'password': secret})}),
                    '{"\\u0070assword": ' + json.dumps(secret) + '}']
        for suffix in ('.json', '.jsonl'):
            for text in variants:
                with self.subTest(suffix=suffix, text=text), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    (root / ('data' + suffix)).write_text(text)
                    result = scan_privacy(root, strict=True)
                    self.assertFalse(result['ok'])
                    self.assertNotIn(secret, json.dumps(result))
                    self.assertEqual(result['counts']['block'], 1)

    def test_nested_json_credentials_are_blocked_in_records_and_streams(self):
        secret = 'fixture-' + 'unusable-password'
        for depth in (2, 4, 8):
            nested = json.dumps({'password': secret})
            for _ in range(depth):
                nested = json.dumps(nested)
            repo = ExampleRepository()
            try:
                event = repo.event()
                event['summary'] = nested
                write_json(repo.event_path, event)
                self.assertFalse(check_public_records(repo.root)['ok'])
                self.assertFalse(public_projection(repo.root, {'event': [(repo.event_path, event)]}).get('event'))
                result = scan_privacy(repo.root, strict=True)
                self.assertFalse(result['ok'])
                self.assertNotIn(secret, json.dumps(result))
            finally:
                repo.close()

    def test_decoded_advisory_matches_are_deduplicated_and_do_not_block(self):
        for suffix in ('.json', '.jsonl'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                payload = json.dumps({'text': 'alice@example.com; 学号: ABC123456'})
                payload = payload.replace('@', r'\u0040')
                (root / ('data' + suffix)).write_text(payload)
                result = scan_privacy(root, strict=True)
                self.assertTrue(result['ok'])
                self.assertEqual(sorted(row['kind'] for row in result['findings']), ['email', 'student-id-label'])
                self.assertTrue(all(row['line'] == 1 for row in result['findings']))

    def test_decoding_layers_do_not_create_cross_view_assignments(self):
        harmless = json.dumps('"password" password:')
        self.assertFalse(sensitive_text(harmless))
        for suffix in ('.json', '.jsonl'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / ('data' + suffix)).write_text(harmless)
                self.assertTrue(scan_privacy(root, strict=True)['ok'])
        repo = ExampleRepository()
        try:
            event = repo.event()
            event['summary'] = harmless
            write_json(repo.event_path, event)
            self.assertTrue(check_public_records(repo.root)['ok'])
            self.assertTrue(public_projection(repo.root, {'event': [(repo.event_path, event)]})['event'])
        finally:
            repo.close()

    def test_standard_private_key_headers_are_blocked(self):
        for prefix in ('', 'RSA ', 'DSA ', 'EC ', 'OPENSSH ', 'ENCRYPTED ', 'PGP '):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                suffix = ' BLOCK' if prefix == 'PGP ' else ''
                (root/'key.pem').write_text('-----BEGIN ' + prefix + 'PRIVATE KEY' + suffix + '-----\n')
                self.assertFalse(scan_privacy(root, strict=True)['ok'])

    def test_cloud_signed_urls_are_not_public_source_locators(self):
        for key in ('X-Goog-Credential', 'X-Goog-Signature', 'X-Amz-Credential', 'X-Amz-Signature', 'X-Amz-Security-Token', 'sig'):
            address = 'https://example.org/object?' + key + '=fixture'
            self.assertFalse(public_url(address))
            self.assertTrue(sensitive_text(address))
        self.assertTrue(public_url('https://example.org/object?version=2'))

    def test_build_and_knowledge_export_share_public_projection(self):
        for mode in ('excluded', 'draft'):
            with self.subTest(mode=mode):
                repo = ExampleRepository()
                try:
                    event = repo.event()
                    if mode == 'excluded':
                        event['privacy']['indexing'] = 'exclude'
                    else:
                        event['status'] = 'draft'
                    write_json(repo.event_path, event)
                    canonical = repo.event_path.read_bytes()
                    self.assertTrue(build_indexes(repo.root)['ok'])
                    export = repo.root / '.work/public-export'
                    self.assertTrue(export_knowledge(repo.root, export)['ok'])
                    for directory in (repo.root/'data/generated', export):
                        for path in directory.rglob('*'):
                            if path.is_file():
                                self.assertNotIn(event['id'], path.read_text(), str(path))
                    self.assertEqual(repo.event_path.read_bytes(), canonical)
                finally:
                    repo.close()

    def test_hidden_wikilink_matches_exact_id_in_prose_and_collection_narrative(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = {'node': [], 'event': [], 'collection': []}
            for kind, record in (
                ('node', {'id': 'topic-a', 'privacy': {'indexing': 'exclude'}}),
                ('node', {'id': 'topic-a-long'}),
                ('event', {'id': 'event-visible', 'summary': '[[topic-a-long|Visible]]'}),
                ('event', {'id': 'event-hidden', 'summary': '[[topic-a|Hidden]]'}),
                ('collection', {'id': 'collection-visible', 'narrative': 'index.md'}),
            ):
                path = root / (record['id'] + '.json')
                write_json(path, record)
                rows[kind].append((path, record))
            (root/'index.md').write_text('[[topic-a-long]]')
            projected = public_projection(root, rows)
            self.assertEqual([record['id'] for _,record in projected['event']], ['event-visible'])
            self.assertEqual(projected['collection'][0][1]['narrative'], 'index.md')
            (root/'index.md').write_text('[[topic-a]]')
            self.assertIsNone(public_projection(root, rows)['collection'][0][1]['narrative'])

    def test_plaintext_key_and_config_extensions_are_scanned(self):
        for suffix in ('.pem', '.key', '.ini', '.conf', '.custom'):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / ('account' + suffix)).write_text('-----BEGIN ' + 'PRIVATE KEY-----\nfixture\n')
                self.assertFalse(scan_privacy(root, strict=True)['ok'])

    def test_fragment_credentials_block_while_section_anchors_remain_valid(self):
        for fragment in ('ticket=shortsecret', 'access_token=short', '/callback?auth=short', '%74oken=short'):
            address = 'https://example.org/callback#' + fragment
            self.assertFalse(public_url(address))
            self.assertTrue(sensitive_text(address))
        self.assertTrue(public_url('https://example.org/article#section-2'))

    def test_fragment_credential_in_canonical_record_is_not_publishable(self):
        repo = ExampleRepository()
        try:
            event = repo.event()
            event['summary'] = 'Source: https://example.org/callback#ticket=' + 'shortsecret'
            write_json(repo.event_path, event)
            self.assertFalse(check_public_records(repo.root)['ok'])
        finally:
            repo.close()

    def test_strict_blocks_credential_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = 'ghp_' + 'A' * 32
            with (root/'large.md').open('w') as stream:
                for _ in range(9000):
                    stream.write('ordinary public context ' * 50 + '\n')
                stream.write(secret)
            result = scan_privacy(root, strict=True)
            self.assertFalse(result['ok'])
            self.assertEqual(result['counts']['block'], 1)
            self.assertNotIn(secret, json.dumps(result))
            self.assertGreater((root/'large.md').stat().st_size, 8 * 1024 * 1024)

    def test_public_names_remain_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'note.md').write_text('公开活动主持人：张三；深圳技术大学。', encoding='utf-8')
            self.assertTrue(scan_privacy(root, strict=True)['ok'])

    def test_canonical_restricted_record_is_blocked_before_git_publication(self):
        repo = ExampleRepository()
        try:
            self.assertTrue(check_public_records(repo.root)['ok'])
            event = repo.event()
            event['privacy']['handling'] = 'restricted'
            write_json(repo.event_path, event)
            self.assertFalse(check_public_records(repo.root)['ok'])
        finally:
            repo.close()

    def test_doctor_reports_old_worktree_pointer_and_broken_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'.git').write_text('gitdir: /missing/old-checkout')
            (root/'.venv').mkdir()
            with patch('digital_sztu.runtime.storage_status', return_value={'ok': True}):
                result = environment_diagnostics(root)
            self.assertFalse(result['ok'])
            self.assertEqual(len(result['errors']), 2)


if __name__ == '__main__':
    unittest.main()

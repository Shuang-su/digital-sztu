from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_repository import ExampleRepository, write_json
from digital_sztu.public import check_public_records, public_url, sensitive_text
from digital_sztu.privacy import scan_privacy
from digital_sztu.runtime import environment_diagnostics


class PublicReleaseTests(unittest.TestCase):
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
            result = environment_diagnostics(root)
            self.assertFalse(result['ok'])
            self.assertEqual(len(result['errors']), 2)


if __name__ == '__main__':
    unittest.main()

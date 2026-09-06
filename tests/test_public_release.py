from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_repository import ExampleRepository, write_json
from digital_sztu.public import check_public_records
from digital_sztu.privacy import scan_privacy
from digital_sztu.runtime import environment_diagnostics


class PublicReleaseTests(unittest.TestCase):
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

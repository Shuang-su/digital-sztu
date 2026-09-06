"""Batch complete README reads, falling back to GitHub's REST selection when ambiguous."""
from __future__ import annotations

import hashlib
import json
from urllib.parse import quote

from .discovery_graphql import REPOSITORY_FIELDS, repository_row
from .discovery_policy import now

METADATA = REPOSITORY_FIELDS.replace('defaultBranchRef {name}', 'defaultBranchRef {name target {oid}}')
FOLDERS = (('github', '.github/'), ('root', ''), ('docs', 'docs/'))


def readme_entry(item):
    """Only unambiguous conventional text names use the optimized route."""
    if not isinstance(item.get('root', {}).get('entries') if item.get('root') else None, list):
        return None
    for key, prefix in FOLDERS:
        tree = item.get(key)
        if tree is None or tree.get('__typename') != 'Tree':
            continue
        if not isinstance(tree.get('entries'), list):
            return None
        candidates = [entry for entry in tree['entries'] if entry['name'].lower().startswith('readme')]
        if not candidates:
            continue
        if len(candidates) != 1:
            return None
        entry = candidates[0]
        if (entry['name'].lower() not in ('readme', 'readme.md', 'readme.markdown', 'readme.rst', 'readme.txt')
                or entry['type'] != 'blob' or entry['mode'] not in (0o100644, 0o100755)
                or entry['size'] > 200000):
            return None
        return {**entry, 'path': prefix + entry['name']}
    return None


def repository_query(index, name, fields):
    owner, repository = name.split('/', 1)
    return ('a' + str(index) + ':repository(owner:' + json.dumps(owner) + ',name:' +
            json.dumps(repository) + '){' + fields + '}')


class ReadmeReads:
    def readme_batch(self, limit=8):
        try:
            return self._readme_batch(limit)
        finally:
            # Every exit, including empty/private batches and fallbacks, must
            # release decoded rows. Committed pages remain in SQLite.
            for table in ('records', 'edges', 'ops'):
                self.state[table].release()

    def _readme_batch(self, limit=8):
        keys = [row[0] for row in self.db.execute("""SELECT id FROM ops
            WHERE json_extract(body,'$.operation')='readme' AND json_extract(body,'$.status')='pending'
            AND coalesce(json_extract(body,'$.readme_rest_required'),0)=0
            ORDER BY json_extract(body,'$.priority'),json_extract(body,'$.queued_at'),id LIMIT ?""",
            (min(limit, self.state.get('readme_batch_size', 8)),))]
        if not keys:
            return 0, None

        def fallback(key, reason):
            self.state['ops'][key].update(readme_rest_required=True, readme_batch_fallback=reason)
            self.audit('readme-rest-fallback', operation_id=key, reason=reason)
            self.save()

        def identity(key, item):
            op = self.state['ops'][key]
            if not item or str(item.get('databaseId')) != op['entity_id'].split(':')[-1]:
                fallback(key, 'resolve-current-numeric-identity')
                return False
            if item.get('isPrivate') is not False:
                op.update(status='restricted', error='repository-not-public')
                self.save()
                return False
            return True

        fields = [repository_query(i, self.state['records'][self.state['ops'][key]['entity_id']]['title'],
                  METADATA + ' parent{' + REPOSITORY_FIELDS + '}') for i, key in enumerate(keys)]
        data, error = self.public_query(fields, 'readme', len(keys))
        if error:
            return 0, error
        selected = []
        for i, key in enumerate(keys):
            item = data.get('a' + str(i))
            if not identity(key, item):
                continue
            commit = ((item.get('defaultBranchRef') or {}).get('target') or {}).get('oid')
            if not commit:
                fallback(key, 'empty-or-unresolved-default-branch')
                continue
            row = repository_row(item)
            if item.get('parent') and item['parent'].get('isPrivate') is False:
                row['parent'] = repository_row(item['parent'])
            self.repo(row, via='readme-batch-stable-id-refresh')
            selected.append((key, row['full_name'], commit))
            self.save()
        if not selected:
            return len(keys), None
        fields = []
        for i, (_, name, commit) in enumerate(selected):
            trees = ' '.join(alias + ':object(expression:' + json.dumps(commit + ':' + path.rstrip('/')) +
                '){__typename ... on Tree {entries {name type mode size oid}}}' for alias, path in FOLDERS)
            fields.append(repository_query(i, name, 'databaseId isPrivate ' + trees))
        data, error = self.public_query(fields, 'readme', len(selected))
        if error:
            return 0, error
        blobs = []
        for i, (key, name, commit) in enumerate(selected):
            item = data.get('a' + str(i))
            if not identity(key, item):
                continue
            entry = readme_entry(item)
            if entry is None:
                fallback(key, 'readme-selection-needs-rest')
            else:
                blobs.append((key, name, commit, entry))
        if not blobs:
            return len(keys), None
        fields = [repository_query(i, name, 'databaseId isPrivate readme:object(oid:' + json.dumps(entry['oid']) +
            '){... on Blob {oid byteSize isBinary isTruncated text}}') for i, (_, name, _, entry) in enumerate(blobs)]
        data, error = self.public_query(fields, 'readme', len(blobs))
        if error:
            return 0, error
        for i, (key, name, commit, entry) in enumerate(blobs):
            item = data.get('a' + str(i))
            if not identity(key, item):
                continue
            blob = item.get('readme') or {}
            text = blob.get('text')
            if (blob.get('oid') != entry['oid'] or blob.get('isTruncated') is not False
                    or blob.get('isBinary') is not False or not isinstance(text, str)
                    or blob.get('byteSize', 200001) > 200000):
                fallback(key, 'incomplete-or-unsupported-blob')
                continue
            raw = text.encode('utf-8')
            oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if len(raw) != blob['byteSize'] or oid != entry['oid']:
                fallback(key, 'blob-byte-count-or-hash-mismatch')
                continue
            op = self.state['ops'][key]
            rec = self.state['records'][op['entity_id']]
            self.accept_readme(op, rec, text, {'path': entry['path'], 'sha': entry['oid'],
                'html_url': 'https://github.com/' + name + '/blob/' + commit + '/' + quote(entry['path'], safe='/')})
            rec['readme_current']['commit_sha'] = commit
            self.references(rec)
            op.update(readme_transport='graphql-verified-blob', completed_at=now())
            self.save()
        return len(keys), None

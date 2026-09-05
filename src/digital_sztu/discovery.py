"""Transactional, resumable research state; separate from canonical archives."""
from __future__ import annotations

import json
import os
import subprocess
import time
import sqlite3
from collections.abc import MutableMapping
from contextlib import contextmanager
from pathlib import Path

from .discovery_policy import DiscoveryPolicy, SCOPED_CATEGORIES, now, digest, clean, url
from .discovery_graphql import GraphQLReads, LIST_KINDS, OWNER_AFFILIATIONS
from .utils import atomic_write_text, sha256_file

TABLES = ('records', 'edges', 'ops')
MANUAL = ('relevance-review', 'scoped-contributors-review', 'external-review')
UNFINISHED = ('pending', 'deferred', 'running', 'scoped-review-required')


class Rows(MutableMapping):
    """Cache only touched rows; nested changes commit with the page cursor."""
    def __init__(self, connection, table):
        self.db, self.table, self.cache, self.original = connection, table, {}, {}

    def __getitem__(self, key):
        if key not in self.cache:
            row = self.db.execute(f'SELECT body FROM {self.table} WHERE id=?', (key,)).fetchone()
            if row is None:
                raise KeyError(key)
            self.original[key] = row[0]
            self.cache[key] = json.loads(row[0])
        return self.cache[key]

    def __setitem__(self, key, value):
        self.cache[key] = value

    def __delitem__(self, key):
        raise ValueError('Research rows are retained; use an explicit reviewed status')

    def __iter__(self):
        yield from sorted(set(row[0] for row in self.db.execute(f'SELECT id FROM {self.table}')) | self.cache.keys())

    def __len__(self):
        return self.db.execute(f'SELECT count(*) FROM {self.table}').fetchone()[0] + sum(
            not self.db.execute(f'SELECT 1 FROM {self.table} WHERE id=?', (key,)).fetchone()
            for key in self.cache if key not in self.original)

    def flush(self):
        for key, value in self.cache.items():
            body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            if body != self.original.get(key):
                self.db.execute(f'INSERT INTO {self.table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', (key, body))
                self.original[key] = body

    def release(self):
        self.cache.clear()
        self.original.clear()


class Research(GraphQLReads, DiscoveryPolicy):
    def __init__(self, path: Path):
        self.path = path
        if path.is_symlink() or not path.is_file():
            raise ValueError('Initialize a real SQLite research file first')
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.state = json.loads(self.db.execute('SELECT body FROM meta WHERE id=1').fetchone()[0])
        self.run_id = self.state['run_id']
        for table in TABLES:
            self.state[table] = Rows(self.db, table)

    def close(self):
        self.db.close()

    def audit(self, kind, **values):
        self.db.execute('INSERT INTO audit(body) VALUES (?)', (json.dumps(
            {'run_id': self.run_id, 'at': now(), 'kind': kind, **values}, ensure_ascii=False),))

    def save(self):
        for table in TABLES:
            self.state[table].flush()
        meta = {k: v for k, v in self.state.items() if k not in TABLES}
        self.db.execute('UPDATE meta SET body=? WHERE id=1', (json.dumps(meta, ensure_ascii=False),))
        self.db.commit()

    def counts(self, table, field):
        return dict(self.db.execute(f"SELECT json_extract(body, '$.{field}'), count(*) FROM {table} GROUP BY 1"))

    def status(self):
        ops = self.counts('ops', 'status')
        unfinished = sum(ops.get(key, 0) for key in UNFINISHED)
        missing = ops.get('missing', 0)
        # Missing README still requires alternative-evidence review, not silent discard.
        manual = self.db.execute("SELECT count(*) FROM ops WHERE json_extract(body,'$.status') NOT IN ('complete','not-applicable','stopped-policy','restricted') AND json_extract(body,'$.operation') IN (?,?,?)", MANUAL).fetchone()[0]
        rounds = self.state.get('no_new_convergence_rounds', 0)
        eligible = unfinished == 0 and missing == 0 and manual == 0 and rounds >= 2 and not self.state.get("active_sweep")
        return {'ok': True, 'run_id': self.run_id, 'status': 'converged-with-limitations' if eligible and ops.get('restricted') else 'converged' if eligible else 'partial',
                'operations': ops, 'pending_by_kind': dict(self.db.execute("SELECT json_extract(body,'$.operation'),count(*) FROM ops WHERE json_extract(body,'$.status') IN ('pending','deferred','running','scoped-review-required','missing') GROUP BY 1")),
                'records': self.counts('records', 'record_type'), 'verification': self.counts('records', 'verification_status'),
                'edges': self.db.execute('SELECT count(*) FROM edges').fetchone()[0],
                'unfinished_pagination': self.db.execute("SELECT count(*) FROM ops WHERE (json_extract(body,'$.next_endpoint') IS NOT NULL OR json_extract(body,'$.graphql_cursor') IS NOT NULL) AND json_extract(body,'$.status') != 'complete'").fetchone()[0],
                'no_new_convergence_rounds': rounds, 'promotion_ready': eligible,
                'rate': self.state.get('rate', {}), 'api_calls': self.state.get('api_calls', 0),
                'legacy_inputs': self.state.get('legacy_inputs', [])}

    def profile_batch(self, limit=50):
        """Coalesce public profile reads, while checking each immutable database ID."""
        keys = [row[0] for row in self.db.execute("SELECT id FROM ops WHERE json_extract(body,'$.operation')='profile' AND json_extract(body,'$.status')='pending' ORDER BY json_extract(body,'$.priority'),json_extract(body,'$.queued_at'),id LIMIT ?", (min(limit, self.state.get('profile_batch_size', 50)),))]
        if not keys:
            return 0, None
        fields = []
        for index, key in enumerate(keys):
            rec = self.state['records'][self.state['ops'][key]['entity_id']]
            organization = rec.get('account_type') == 'Organization'
            kind = 'organization' if organization else 'user'
            extra = 'name description' if organization else 'bio company followers(first:1){totalCount} following(first:1){totalCount} starredRepositories(first:1){totalCount}'
            repository_args = 'first:1,privacy:PUBLIC' + ('' if organization else ',ownerAffiliations:' + OWNER_AFFILIATIONS)
            fields.append(f'a{index}: {kind}(login:{json.dumps(rec["title"])})' + '{databaseId login url websiteUrl repositories(' + repository_args + '){totalCount} ' + extra + '}')
        data, error = self.public_query(fields, 'profile', len(keys))
        if error:
            return 0, error
        for index, key in enumerate(keys):
            op = self.state['ops'][key]
            rec = self.state['records'][op['entity_id']]
            row = data.get('a' + str(index))
            if not row or str(row.get('databaseId')) != rec['id'].split(':')[-1]:
                # A stale login can now belong to someone else. Resolve the numeric ID.
                self.profile(op, rec)
            else:
                value = {'id': row['databaseId'], 'login': row['login'], 'html_url': row['url'],
                         'type': rec.get('account_type', 'User'), 'name': row.get('name'), 'description': row.get('description'),
                         'bio': row.get('bio'), 'company': row.get('company'), 'blog': row.get('websiteUrl'),
                         'all_public_repositories': row['repositories']['totalCount'],
                         'followers': (row.get('followers') or {}).get('totalCount'),
                         'following': (row.get('following') or {}).get('totalCount'),
                         'public_stars': (row.get('starredRepositories') or {}).get('totalCount')}
                self.profile_data(op, rec, value)
            self.save()
        for table in TABLES:
            self.state[table].release()
        return len(keys), None

    def resume(self, limit=100, kinds=None):
        handled = set()
        if not self.state.get('all_affiliations_count_policy'):
            # Earlier profile optimization used an owned-only count for an all list.
            self.db.execute("UPDATE ops SET body=json_set(body,'$.status','pending','$.reason','verify all public affiliations') WHERE json_extract(body,'$.operation')='repos' AND json_extract(body,'$.completion_evidence')='stable-identity-profile-count-zero'")
            self.state['all_affiliations_count_policy'] = True
            self.audit('list-count-policy-upgraded', reason='owned count cannot prove all affiliations empty')
            self.save()
        # Refresh the remaining budget once per invocation. Never wait through a rate limit.
        _, _, error = self.api('rate_limit')
        if error and (error not in ('rate-limit', 'rate-deferred', 'verification-reserve') or self.state.get('blocked_until', {}).get('all', 0) > time.time()):
            self.save()
            return {**self.status(), 'processed': 0, 'blocked': error}
        # A previous transient error can be tried again, with the same page cursor.
        self.db.execute("UPDATE ops SET body=json_set(body,'$.status','pending') WHERE json_extract(body,'$.status')='deferred'")
        self.db.commit()
        processed = 0
        while processed < limit:
            candidates = self.db.execute("SELECT id FROM ops WHERE json_extract(body,'$.status')='pending' ORDER BY json_extract(body,'$.priority'),json_extract(body,'$.queued_at'),id")
            selected = None
            for (key,) in candidates:
                if key in handled:
                    continue
                operation = key.rsplit('|', 1)[-1]
                if operation in MANUAL or (kinds and operation not in kinds):
                    continue
                selected = key
                break
            if selected is None:
                break
            if selected.endswith('|profile'):
                count, blocked = self.profile_batch(min(50, limit - processed))
                processed += count
                if blocked == 'query-size-adjusted':
                    continue
                if blocked:
                    return {**self.status(), 'processed': processed, 'blocked': blocked}
                if count:
                    continue
            op = self.state['ops'][selected]
            if op['operation'] in LIST_KINDS and (op.get('pagination_api') == 'graphql' or not op.get('pages') and not op.get('next_endpoint')):
                count, blocked = self.list_batch(op['operation'], min(25, limit - processed))
                processed += count
                if blocked == 'query-size-adjusted':
                    continue
                if blocked:
                    return {**self.status(), 'processed': processed, 'blocked': blocked}
                if count:
                    continue
            try:
                self.execute(op)
                self.save()
            except Exception as exc:
                self.db.rollback()
                for table in TABLES:
                    self.state[table].release()
                op = self.state['ops'][selected]
                op.update(status='deferred', error=type(exc).__name__ + ': ' + clean(str(exc)))
                self.audit('processing-error', operation_id=selected, error=op['error'])
                self.save()
                return {**self.status(), 'processed': processed, 'blocked': op['error']}
            processed += 1
            handled.add(selected)
            blocked = op.get('error') in ('rate-limit', 'rate-deferred', 'verification-reserve')
            for table in TABLES:
                self.state[table].release()
            if blocked:
                break
        return {**self.status(), 'processed': processed}

    def references(self, rec):
        if rec['verification_status'] != 'confirmed':
            return
        addresses = rec.get('reviewed_reference_urls', []) if rec.get('category') in SCOPED_CATEGORIES else rec.get('explicit_repo_links', [])
        for address in addresses:
            sid = 'github-url:' + digest(address.lower().encode())[:24]
            if sid not in self.state['records']:
                self.state['records'][sid] = {'id': sid, 'record_type': 'repository-url', 'title': address, 'url': address,
                                              'verification_status': 'research-only', 'parent_id': rec['id']}
            self.enqueue(sid, 'resolve-repository', 45)

    def external(self, items):
        for item in items:
            if not item.get('title') or not url(item.get('url')):
                raise ValueError('External candidate requires a title and safe public URL')
        for item in items:
            address = url(item['url'])
            sid = 'external:' + digest(address.encode())[:24]
            if sid not in self.state['records']:
                self.state['records'][sid] = {'id': sid, 'record_type': 'external-source', 'title': item['title'],
                    'url': address, 'verification_status': 'candidate', 'category': 'unknown', 'run_id': self.run_id,
                    'evidence': [], 'published_at': None, 'rights': {'status': 'link-only'}}
            self.enqueue(sid, 'external-review', 30)
            self.audit('external-discovery', entity_id=sid, url=address)
        self.save()
        return self.status()

    def execute(self, op):
        if op['operation'] == 'resolve-repository':
            ref = self.state['records'][op['entity_id']]
            from urllib.parse import urlsplit
            endpoint = 'repos/' + urlsplit(ref['url']).path.strip('/')
            row, _, error = self.api(endpoint)
            if error:
                op.update(status='restricted' if error in ('http-404', 'http-451') else 'deferred', error=error)
                return
            sid = self.repo(row, parent=ref['parent_id'], via='explicit-readme-reference')
            if sid:
                ref['resolved_id'] = sid
                self.edge(ref['parent_id'], 'references', sid, self.ev(self.state['records'][ref['parent_id']].get('readme_current', {}).get('url') or self.state['records'][ref['parent_id']]['url'], 'explicit repository link in README', ref['url']))
                if self.state['records'][sid]['verification_status'] == 'candidate':
                    self.enqueue(sid, 'readme', 40)
                    self.enqueue(sid, 'relevance-review', 60)
            op.update(status='complete', completed_at=now())
            return
        if op['operation'] == 'repository-search':
            query = self.state['records'][op['entity_id']]['query']
            from urllib.parse import quote
            def receive(row, endpoint):
                sid = self.repo(row, via='targeted-gap-search')
                if sid and self.state['records'][sid]['verification_status'] == 'candidate':
                    self.enqueue(sid, 'readme', 30)
                    self.enqueue(sid, 'relevance-review', 40)
            self.pages(op, 'search/repositories?per_page=100&q=' + quote(query), receive, search=True)
            return
        result = super().execute(op)
        if op['operation'] == 'readme' and op.get('status') == 'complete':
            self.references(self.state['records'][op['entity_id']])
        return result

    def sweep(self, queries=None, complete=False):
        active = self.state.get('active_sweep')
        if complete:
            if not active:
                raise ValueError('No active targeted sweep')
            status = self.status()
            if any(status['operations'].get(key, 0) for key in UNFINISHED + ('missing',)):
                raise ValueError('Review all pending results and pagination before completing a sweep')
            for key in active['operations']:
                if self.state['ops'][key]['status'] != 'complete':
                    raise ValueError('Restricted or incomplete search cannot prove a no-new round')
            current = {row[0] for row in self.db.execute("SELECT id FROM records WHERE json_extract(body,'$.record_type') IN ('repository','external-source') AND json_extract(body,'$.verification_status')='confirmed'")}
            if 'baseline_confirmed_ids' not in active:
                raise ValueError('Sweep lacks an identity baseline; review the legacy round explicitly')
            added = len(current - set(active['baseline_confirmed_ids']))
            self.state['no_new_convergence_rounds'] = self.state.get('no_new_convergence_rounds', 0) + 1 if added == 0 else 0
            self.state.setdefault('sweeps', []).append({**active, 'finished_at': now(), 'new_confirmed': added})
            self.state.pop('active_sweep')
            self.audit('targeted-sweep-complete', new_confirmed=added)
            self.save()
            return self.status()
        if active:
            raise ValueError('Resume and review the active sweep before starting another')
        status = self.status()
        if any(status['operations'].get(key, 0) for key in UNFINISHED + ('missing',)):
            raise ValueError('Targeted convergence sweeps start after the discovery queue is processed')
        if not queries or not all(isinstance(q, str) and q.strip() for q in queries):
            raise ValueError('Supply explicit targeted search queries with --file')
        round_id = len(self.state.get('sweeps', [])) + 1
        operations = []
        baseline = [row[0] for row in self.db.execute("SELECT id FROM records WHERE json_extract(body,'$.record_type') IN ('repository','external-source') AND json_extract(body,'$.verification_status')='confirmed' ORDER BY id")]
        for query in queries:
            sid = 'search:' + digest((str(round_id) + query).encode())[:24]
            self.state['records'][sid] = {'id': sid, 'record_type': 'search', 'title': query, 'query': query, 'verification_status': 'research-only'}
            operations.append(self.enqueue(sid, 'repository-search', 0))
        self.state['active_sweep'] = {'round': round_id, 'queries': queries, 'operations': operations, 'baseline_confirmed_ids': baseline, 'started_at': now()}
        self.save()
        return self.status()

    def review(self, items):
        # Validate the entire review batch before mutating any record.
        for item in items:
            if item.get('id') not in self.state['records']:
                raise ValueError('Review requires an existing stable entity ID')
            if item.get('verification_status') not in ('confirmed', 'excluded', 'candidate', 'restricted'):
                raise ValueError('Invalid review status')
            if not item.get('relevance_reason'):
                raise ValueError('Review requires an explicit scope/evidence reason')
            if item['verification_status'] == 'confirmed' and not item.get('evidence'):
                raise ValueError('Confirmed review requires source evidence')
            for proof in item.get('evidence', []):
                if not proof.get('url') or not url(proof['url']) or not proof.get('locator') or not proof.get('accessed_at'):
                    raise ValueError('Evidence needs a safe public URL, locator and access time')
            if any(not url(address) for address in item.get('reviewed_reference_urls', [])):
                raise ValueError('Reviewed references require safe public URLs')
            if item.get('campus_contributors') is not None:
                if not item.get('contributor_scope_reason') or not item.get('evidence'):
                    raise ValueError('Scoped contributors require diff/commit evidence and a scope reason')
                for account in item['campus_contributors']:
                    if not account.get('id') or not account.get('login') or not url(account.get('html_url')):
                        raise ValueError('Scoped contributor requires a public stable account ID')
        for item in items:
            rec = self.state['records'][item['id']]
            before = rec['verification_status']
            for key in ('verification_status', 'category', 'relevance_reason', 'gaps', 'derivation_kind', 'count_as_independent_project', 'contributor_scope', 'contributor_scope_reason', 'reviewed_reference_urls'):
                if key in item:
                    rec[key] = item[key]
            for proof in item.get('evidence', []):
                if proof not in rec.setdefault('evidence', []):
                    rec['evidence'].append(proof)
            rec['manual_reviewed_at'] = now()
            for kind in ('relevance-review', 'external-review'):
                op = self.state['ops'].get(rec['id'] + '|' + kind)
                if op:
                    op.update(status='complete', completed_at=now())
            if rec['record_type'] == 'repository' and rec['verification_status'] == 'confirmed':
                # Metadata refresh applies fork and campus-delta contributor policy.
                self.enqueue(rec['id'], 'metadata', 8)
                self.references(rec)
                if before != 'confirmed':
                    self.state['no_new_convergence_rounds'] = 0
            if item.get('resolves_missing_readme'):
                op = self.state['ops'].get(rec['id'] + '|readme')
                if op and op['status'] == 'missing':
                    op.update(status='complete', resolution='alternative evidence reviewed', completed_at=now())
            if item.get('campus_contributors') is not None:
                for row in item['campus_contributors']:
                    aid = self.account(row, parent=rec['id'], via='verified-campus-delta-contributor', anchor=True, priority=18)
                    for proof in item['evidence']:
                        self.edge(aid, 'mapped-campus-delta-author-to', rec['id'], proof)
                op = self.state['ops'].get(rec['id'] + '|scoped-contributors-review')
                if op:
                    op.update(status='complete', completed_at=now())
            self.audit('evidence-review', entity_id=rec['id'], before=before, after=rec['verification_status'], reason=item['relevance_reason'])
        self.save()
        return self.status()

    def export(self, output: Path):
        output.mkdir(parents=True, exist_ok=True)
        if output.is_symlink() or any(p.is_symlink() for p in output.rglob('*')):
            raise ValueError('Research output must not contain symlinks')
        for table, filename in (('records', 'sources.jsonl'), ('edges', 'edges.jsonl'), ('ops', 'operations.jsonl'), ('audit', 'audit.jsonl')):
            with (output / (filename + '.new')).open('w', encoding='utf-8') as stream:
                for (body,) in self.db.execute(f'SELECT body FROM {table} ORDER BY id'):
                    stream.write(body + '\n')
            (output / (filename + '.new')).replace(output / filename)
        result = self.status()
        # Stream the private research graph, including all unfinished operations.
        destination = output / 'graph.json'
        with destination.with_suffix('.json.new').open('w', encoding='utf-8') as stream:
            stream.write(json.dumps({'schema_version': 'research-graph-0.2', 'run_id': self.run_id, 'status': result['status']}, ensure_ascii=False)[:-1])
            for table, key in (('records', 'nodes'), ('edges', 'edges'), ('ops', 'frontier')):
                stream.write(',"' + key + '":[')
                first = True
                for (body,) in self.db.execute(f'SELECT body FROM {table} ORDER BY id'):
                    row = json.loads(body)
                    if table == 'ops' and row.get('status') in ('complete', 'not-applicable'):
                        continue
                    if table == 'records':
                        row = {key: row.get(key) for key in ('id', 'record_type', 'title', 'url', 'verification_status', 'category')}
                    if not first:
                        stream.write(',')
                    stream.write(json.dumps(row, ensure_ascii=False))
                    first = False
                stream.write(']')
            stream.write('}\n')
        destination.with_suffix('.json.new').replace(destination)
        atomic_write_text(output / 'status.json', json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        atomic_write_text(output / 'report.md', '# 校园来源普查\n\n状态：' + result['status'] + '\n\n本目录包含候选与研究网络，不是正式档案，不发布到档案图谱。\n\n```json\n' + json.dumps(result, ensure_ascii=False, indent=2) + '\n```\n')
        return result


@contextmanager
def research_lock(path):
    """An OS lock is released on process exit, including abrupt interruption."""
    lock_path = path.with_suffix('.lock')
    if lock_path.is_symlink():
        raise ValueError('Research lock must be a real file')
    with lock_path.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            stream.write(b'0')
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def initialize(path: Path, legacy: Path | None = None):
    if path.exists() or path.is_symlink():
        raise ValueError('Research database exists; use resume')
    path.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(legacy.read_text(encoding='utf-8')) if legacy else {
        'run_id': now().replace(':', '').replace('-', ''), 'records': {}, 'edges': {}, 'ops': {},
        'api_calls': 0, 'aggregate': {'repo_metadata_nonmatches': 0}, 'no_new_convergence_rounds': 0}
    before = sha256_file(legacy) if legacy else None
    state['legacy_inputs'] = [{'name': legacy.name, 'sha256': before, 'bytes': legacy.stat().st_size}] if legacy else []
    temporary = path.with_suffix('.initializing')
    if temporary.exists() or temporary.is_symlink():
        raise ValueError('Unfinished initialization exists; inspect it before retrying')
    connection = sqlite3.connect(temporary)
    try:
        for table in TABLES:
            connection.execute(f'CREATE TABLE {table}(id TEXT PRIMARY KEY,body TEXT NOT NULL CHECK(json_valid(body)))')
            connection.executemany(f'INSERT INTO {table} VALUES (?,?)', ((key, json.dumps(value, ensure_ascii=False)) for key, value in state.pop(table).items()))
        connection.execute("CREATE INDEX queue ON ops(json_extract(body,'$.status'),json_extract(body,'$.priority'),json_extract(body,'$.queued_at'))")
        connection.execute('CREATE TABLE meta(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        connection.execute('INSERT INTO meta VALUES (1,?)', (json.dumps(state, ensure_ascii=False),))
        connection.execute('CREATE TABLE audit(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        connection.commit()
        if legacy and before != sha256_file(legacy):
            raise ValueError('Legacy input changed during migration')
    except BaseException:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()
    temporary.replace(path)
    run = Research(path)
    try:
        return run.status()
    finally:
        run.close()

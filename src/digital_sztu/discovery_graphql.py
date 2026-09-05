"""Batched public reads with per-list identity and pagination checkpoints."""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime

from .discovery_policy import clean, now

LIST_KINDS = ('repos', 'stars', 'followers', 'following')
OWNER_AFFILIATIONS = '[OWNER,COLLABORATOR,ORGANIZATION_MEMBER]'
ACCOUNT_FIELDS = '__typename login url ... on User {databaseId} ... on Organization {databaseId}'
REPOSITORY_FIELDS = '''databaseId nameWithOwner url description isPrivate isFork isArchived
createdAt updatedAt defaultBranchRef {name} primaryLanguage {name} licenseInfo {spdxId}
owner {''' + ACCOUNT_FIELDS + '''} repositoryTopics(first:20) {totalCount nodes {topic {name}}}'''


def account_row(value):
    if not value or not value.get('databaseId') or not value.get('login') or not value.get('url'):
        raise ValueError('Incomplete public account identity')
    return {'id': value['databaseId'], 'login': value['login'], 'html_url': value['url'], 'type': value['__typename']}


def repository_row(value):
    if not value or not value.get('databaseId') or value.get('isPrivate') is not False:
        raise ValueError('Incomplete or non-public repository in public list')
    topics = value['repositoryTopics']
    if topics['totalCount'] != len(topics['nodes']):
        raise ValueError('Repository topic connection is incomplete')
    return {'id': value['databaseId'], 'full_name': value['nameWithOwner'], 'html_url': value['url'],
            'description': value['description'], 'private': False, 'fork': value['isFork'], 'archived': value['isArchived'],
            'created_at': value['createdAt'], 'updated_at': value['updatedAt'],
            'default_branch': (value['defaultBranchRef'] or {}).get('name'),
            'language': (value['primaryLanguage'] or {}).get('name'),
            'license': {'spdx_id': (value['licenseInfo'] or {}).get('spdxId')},
            'owner': account_row(value['owner']), 'topics': [row['topic']['name'] for row in topics['nodes']]}


class GraphQLReads:
    def reduce_query_size(self, purpose, size):
        if size > 1:
            self.state[purpose + '_batch_size'] = max(1, size // 2)
            self.audit('graphql-query-size-reduced', purpose=purpose, previous=size,
                       next=self.state[purpose + '_batch_size'])
            return True
        if purpose in ('list_' + kind for kind in LIST_KINDS):
            page_size = self.state.get(purpose + '_page_size', 100)
            if page_size > 10:
                self.state[purpose + '_page_size'] = max(10, page_size // 2)
                self.audit('graphql-page-size-reduced', purpose=purpose, previous=page_size,
                           next=self.state[purpose + '_page_size'], reason='keep the same cursor with a smaller page')
                return True
        return False

    def public_query(self, fields, purpose, size):
        """Only constructed query fields are accepted; no user-provided executable query."""
        budget = self.state.get('rate', {}).get('graphql', {})
        if budget.get('remaining', 5000) < 200 and budget.get('reset', 0) > time.time():
            return None, 'verification-reserve'
        if max(self.state.get('blocked_until', {}).get(key, 0) for key in ('graphql', 'all')) > time.time():
            return None, 'rate-deferred'
        query = 'query {' + ' '.join(fields) + ' rateLimit {cost remaining resetAt}}'
        status = None
        self.state['api_calls'] += 1
        try:
            process = subprocess.run(['gh', 'api', 'graphql', '--input', '-', '--include'],
                                     input=json.dumps({'query': query}), capture_output=True, text=True, timeout=45)
            raw, headers, status = process.stdout.replace('\r\n', '\n'), {}, None
            while raw.startswith('HTTP/') and '\n\n' in raw:
                head, raw = raw.split('\n\n', 1)
                status = int(head.splitlines()[0].split()[1])
                for line in head.splitlines()[1:]:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        if key.lower() in ('x-ratelimit-reset', 'x-ratelimit-remaining', 'retry-after'):
                            headers[key.lower()] = value.strip()
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('Unexpected response')
        except (subprocess.TimeoutExpired, ValueError):
            self.audit('graphql-read-error', purpose=purpose, status=status, reason='timeout-or-invalid-response')
            if (status is None or status >= 500) and self.reduce_query_size(purpose, size):
                self.save()
                return None, 'query-size-adjusted'
            self.save()
            return None, 'graphql-unavailable'
        data = result.get('data') or {}
        rate = data.get('rateLimit')
        if rate:
            self.state.setdefault('rate', {})['graphql'] = {
                'remaining': rate['remaining'], 'reset': int(datetime.fromisoformat(rate['resetAt'].replace('Z', '+00:00')).timestamp())}
        errors = result.get('errors', [])
        if errors and all(error.get('type') == 'RESOURCE_LIMITS_EXCEEDED' for error in errors) and self.reduce_query_size(purpose, size):
            self.save()
            return None, 'query-size-adjusted'
        primary = headers.get('x-ratelimit-remaining') == '0' or any(error.get('type') == 'RATE_LIMITED' for error in errors)
        if status in (403, 429) or any(error.get('type') != 'NOT_FOUND' for error in errors):
            retry = max(time.time() + int(headers.get('retry-after', '60')), int(headers.get('x-ratelimit-reset', '0')) if primary else 0)
            if primary and 'x-ratelimit-reset' not in headers:
                retry = max(retry, budget.get('reset', 0), time.time() + 3600)
            self.state.setdefault('blocked_until', {})['graphql' if primary else 'all'] = retry
            self.audit('graphql-read-error', purpose=purpose, types=sorted({str(error.get('type')) for error in errors}), status=status,
                       messages=[clean(error.get('message'), 500) for error in errors[:5]])
            self.save()
            return None, 'graphql-error'
        if not data:
            self.audit('graphql-read-error', purpose=purpose, status=status, reason='no-data')
            if status is not None and status >= 500 and self.reduce_query_size(purpose, size):
                self.save()
                return None, 'query-size-adjusted'
            self.save()
            return None, 'graphql-unavailable'
        self.audit('graphql-public-read', purpose=purpose, requested=size, rate=rate)
        return data, None

    def list_batch(self, kind, limit=10):
        if kind not in LIST_KINDS:
            raise ValueError('Unsupported public list')
        # Keep old REST page links intact. Already started lists never change transport.
        keys = [row[0] for row in self.db.execute("""SELECT id FROM ops
            WHERE json_extract(body,'$.operation')=? AND json_extract(body,'$.status')='pending'
            AND (json_extract(body,'$.pagination_api')='graphql' OR
              (coalesce(json_extract(body,'$.pages'),0)=0 AND json_extract(body,'$.next_endpoint') IS NULL))
            ORDER BY json_extract(body,'$.priority'),coalesce(json_extract(body,'$.pages'),0),id LIMIT ?""",
            (kind, min(limit, self.state.get('list_' + kind + '_batch_size', 10 if kind in ('repos', 'stars') else 25))))]
        selected, fields = [], []
        for key in keys:
            op = self.state['ops'][key]
            rec = self.state['records'][op['entity_id']]
            organization = rec.get('account_type') == 'Organization'
            if organization and kind != 'repos':
                op.update(status='not-applicable', reason='organization has no user social or starred list')
                self.save()
                continue
            if kind in ('followers', 'following') and (rec.get('expansion_exclusion') or rec.get('best_unknown_distance', 99) > 1):
                self.stop_social_operation(op, 'explicit-exclusion:' + rec['expansion_exclusion'] if rec.get('expansion_exclusion') else 'bridge-boundary')
                self.save()
                continue
            connection = {'repos': 'repositories', 'stars': 'starredRepositories'}.get(kind, kind)
            page_size = max(10, min(100, int(self.state.get('list_' + kind + '_page_size', 100))))
            args = 'first:' + str(page_size) + ',after:' + json.dumps(op.get('graphql_cursor'))
            if kind == 'repos':
                args += ',privacy:PUBLIC,orderBy:{field:NAME,direction:ASC}'
                if not organization:
                    args += ',ownerAffiliations:' + OWNER_AFFILIATIONS
            # These two connections contain User, unlike Repository.owner's union.
            payload = REPOSITORY_FIELDS if kind in ('repos', 'stars') else '__typename databaseId login url'
            fields.append('a' + str(len(selected)) + ': ' + ('organization' if organization else 'user') +
                          '(login:' + json.dumps(rec['title']) + ') {databaseId login url results:' + connection +
                          '(' + args + ') {totalCount pageInfo {hasNextPage endCursor} nodes {' + payload + '}}}')
            selected.append(key)
        if not selected:
            return len(keys), None
        data, error = self.public_query(fields, 'list_' + kind, len(selected))
        if error:
            return 0, error
        for index, key in enumerate(selected):
            op = self.state['ops'][key]
            rec = self.state['records'][op['entity_id']]
            item = data.get('a' + str(index))
            if not item or str(item.get('databaseId')) != rec['id'].split(':')[-1]:
                # Resolve renamed IDs; never ingest a new owner of the stale login.
                identity = {'id': key, 'operation': 'identity-refresh'}
                self.profile(identity, rec)
                if identity.get('status') != 'complete':
                    op.update(status=identity.get('status', 'deferred'), error=identity.get('error', 'identity-unverified'))
                self.save()
                continue
            connection = item.get('results') or {}
            page = connection.get('pageInfo') or {}
            cursor = page.get('endCursor') if page.get('hasNextPage') else None
            try:
                if not isinstance(page.get('hasNextPage'), bool) or not isinstance(connection.get('nodes'), list):
                    raise ValueError('Missing list or pagination metadata')
                if page['hasNextPage'] and (not cursor or cursor == op.get('graphql_cursor')):
                    raise ValueError('Pagination cursor did not advance')
                convert = repository_row if kind in ('repos', 'stars') else account_row
                private_count = sum(isinstance(row, dict) and row.get('isPrivate') is True for row in connection['nodes']) if kind in ('repos', 'stars') else 0
                rows = [convert(row) for row in connection['nodes']
                        if not (kind in ('repos', 'stars') and isinstance(row, dict) and row.get('isPrivate') is True)]
            except (ValueError, KeyError, TypeError) as exc:
                op.update(status='deferred', error=clean(str(exc)))
                self.audit('graphql-list-incomplete', operation_id=key, reason=op['error'])
                self.save()
                continue
            for row in rows:
                self.receive_account_list(op, rec, row, 'graphql',
                    locator_prefix=kind + ' of account id=' + str(item['databaseId']) + '; after=' + str(op.get('graphql_cursor')) + '; ')
            op.update(pagination_api='graphql', graphql_cursor=cursor, pages=op.get('pages', 0) + 1,
                      returned=op.get('returned', 0) + len(connection['nodes']), total_count=connection['totalCount'],
                      nonpublic_omitted=op.get('nonpublic_omitted', 0) + private_count,
                      last_observed_at=now(), status='pending' if cursor else 'complete')
            op.pop('error', None)
            if not cursor:
                op['completed_at'] = now()
            self.audit('graphql-list-page', operation_id=key, returned=len(rows), total_returned=op['returned'],
                       page=op['pages'], after=cursor, account_id=item['databaseId'])
            self.save()
        for table in ('records', 'edges', 'ops'):
            self.state[table].release()
        return len(keys), None

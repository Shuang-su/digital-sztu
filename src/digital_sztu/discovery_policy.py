"""Public GET discovery rules migrated from the reviewed September 2026 survey.

No upstream code is executed. Research edges never enter archive views.
"""
import base64, hashlib, json, re, subprocess, time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl
from .privacy import CREDENTIAL_PATTERNS
from .public import public_url
SCHOOL = re.compile('深圳技术大学|深技大|Shenzhen\\s+Technology\\s+University|(?<![A-Za-z])SZTU(?![A-Za-z])|sztu\\.edu\\.cn', re.I)
STRONG = re.compile('深圳技术大学|深技大|Shenzhen\\s+Technology\\s+University|sztu\\.edu\\.cn', re.I)
SCOPED_CATEGORIES = ('secondary-directory', 'campus-adapter-subcomponent', 'campus-information-section', 'campus-system-upstream-reference')
CLUE = re.compile('课程|作业|实验|课设|毕设|毕业|论文|校园|教务|选课|评教|学分|校历|本科|数据结构|编译原理|云计算|srun|\\bACM\\b|机器人|社团|协会|\\bOJ\\b|assignment|homework|course|\\blab\\b|thesis|robomaster|robot|snail|openharmony|\\bFSR\\b', re.I)
SENSITIVE_QUERY = re.compile('^(?:access[_-]?token|token|password|passwd|pwd|secret|api[_-]?key|cookie|signature|credential|authorization|auth|session|sessionid|jsessionid|sso[_-]?ticket|xsid|student[_-]?(?:id|no)|ticket)$', re.I)

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def digest(b):
    return hashlib.sha256(b).hexdigest()

def url(v):
    try:
        p = urlsplit(v or '')
        if not v or not public_url(v):
            return None
        if any((SENSITIVE_QUERY.match(k) for k, _ in parse_qsl(p.query))):
            return None
        if p.hostname in ('localhost', '127.0.0.1', '0.0.0.0') or p.hostname.endswith('.local'):
            return None
        return urlunsplit((p.scheme, p.netloc, p.path.rstrip('/'), p.query, p.fragment))
    except ValueError:
        return None

def excerpt(t):
    t = clean(t, 2000).strip()
    m = SCHOOL.search(t)
    if m:
        t = t[max(0, m.start() - 15):]
    return t[:85] if re.search('[\\u4e00-\\u9fff]', t) else ' '.join(t.split()[:20])[:180]

def clean(value, n=600):
    if value is None:
        return None
    text = str(value)
    for pattern in CREDENTIAL_PATTERNS.values():
        text = pattern.sub('[omitted-sensitive-value]', text)
    text = re.sub('(?i)(password|passwd|cookie|session[_-]?token|api[_-]?key|client[_-]?secret|access[_-]?token)\\s*[=:]\\s*[^\\s<>]+', '[omitted-sensitive-value]', text)
    return re.sub('https?://[^\\s<>]+', lambda m: m[0] if url(m[0]) else '[omitted-sensitive-url]', text)[:n]

class DiscoveryPolicy:

    def ev(self, u, loc, text, basis='direct-public-observation', observed=None):
        return {'url': url(u), 'locator': loc, 'excerpt': excerpt(text), 'basis': basis, 'source_level': 'primary', 'accessed_at': observed or now()}

    def origin(self, rec, via, parent=None, edge=None):
        d = {'via': via, 'parent_id': parent, 'edge_id': edge, 'run_id': self.run_id}
        if d not in rec.setdefault('discovered_via', []):
            rec['discovered_via'].append(d)

    def enqueue(self, sid, op, priority=50, **kwargs):
        key = sid + '|' + op
        q = self.state['ops'].get(key)
        if q:
            q['priority'] = min(q['priority'], priority)
            if kwargs.get('reopen') and q['status'] == 'stopped-policy' and not (
                op in ('followers', 'following') and self.state['records'][sid].get('expansion_exclusion')
            ):
                q['status'] = 'pending'
            return key
        self.state['ops'][key] = {'id': key, 'entity_id': sid, 'operation': op, 'priority': priority, 'status': 'pending', 'queued_at': now(), **kwargs}
        return key

    def stop_social_operation(self, op, reason):
        # Keep the original page/cursor counters and completed observations intact.
        if op['status'] in ('complete', 'not-applicable'):
            return
        if op.get('policy_stop', {}).get('reason') != reason:
            op.setdefault('policy_stop_history', []).append({
                'previous_status': op['status'], 'previous_reason': op.get('reason'),
                'reason': reason, 'stopped_at': now(),
            })
            op['policy_stop'] = op['policy_stop_history'][-1]
        op.update(status='stopped-policy', reason=reason)

    def stop_account_social_expansion(self, rec):
        for kind in ('followers', 'following'):
            op = self.state['ops'].get(rec['id'] + '|' + kind)
            if op:
                self.stop_social_operation(op, 'explicit-exclusion:' + rec['expansion_exclusion'])

    def edge(self, a, rel, b, evidence, context=None):
        assert a in self.state['records'] and b in self.state['records']
        hexid = digest((a + '|' + rel + '|' + b).encode())[:24]
        eid = 'edge:' + '-'.join((hexid[i:i + 4] for i in range(0, 24, 4)))
        item = self.state['edges'].setdefault(eid, {'id': eid, 'source': a, 'relation': rel, 'target': b, 'verification_status': 'observed', 'evidence': [], 'observed_at': evidence.get('accessed_at') or now(), 'recorded_at': now(), 'occurred_at': None, 'discovery_contexts': []})
        if evidence not in item['evidence']:
            item['evidence'].append(evidence)
        if context and context not in item['discovery_contexts']:
            item['discovery_contexts'].append(context)
        return eid

    def account(self, row, parent=None, via='metadata', distance=None, anchor=False, priority=50):
        if not row or not row.get('id') or (not row.get('login')):
            return None
        sid = 'github-account:' + str(row['id'])
        rec = self.state['records'].get(sid)
        if rec is None:
            rec = {'id': sid, 'record_type': 'account', 'verification_status': 'candidate', 'category': 'public-account-entry', 'evidence': [], 'published_at': None, 'rights': {'status': 'metadata-only'}, 'access': 'public', 'student_or_alumni_status': 'unknown', 'run_id': self.run_id}
            self.state['records'][sid] = rec
        old = rec.get('title')
        rec.update(title=row['login'], url=row['html_url'], account_type=row.get('type', 'User'), creator=row['login'], metadata_refreshed_at=now())
        if old and old.lower() != row['login'].lower():
            rec.setdefault('previous_logins', []).append(old)
        self.origin(rec, via, parent)
        if anchor:
            rec['expansion_anchor'] = True
            rec['best_unknown_distance'] = 0
            rec['anchor_basis'] = rec.get('anchor_basis') or via
        elif distance is not None:
            rec['best_unknown_distance'] = min(rec.get('best_unknown_distance', 99), distance)
        if row.get('type') == 'Bot':
            rec.setdefault('expansion_exclusion', 'bot-not-a-person')
            self.stop_account_social_expansion(rec)
            return sid
        if anchor or distance is not None:
            self.enqueue(sid, 'profile', priority)
            self.enqueue(sid, 'repos', priority + 2)
            if row.get('type') != 'Organization':
                self.enqueue(sid, 'stars', priority + 4)
                d = rec.get('best_unknown_distance', 99)
                if d <= 1 and not rec.get('expansion_exclusion'):
                    self.enqueue(sid, 'following', priority + 6, reopen=True)
                    self.enqueue(sid, 'followers', priority + 6, reopen=True)
        return sid

    def repo(self, row, parent=None, via='metadata', retain=True, priority=60):
        if row.get('private') is not False or not row.get('id'):
            return None
        sid = 'github-repo:' + str(row['id'])
        rec = self.state['records'].get(sid)
        if not retain and rec is None:
            return None
        if rec is None:
            rec = {'id': sid, 'record_type': 'repository', 'verification_status': 'candidate', 'category': 'unknown', 'evidence': [], 'published_at': None, 'run_id': self.run_id, 'rights': {'status': 'link-only'}, 'person_identity': 'unknown'}
            self.state['records'][sid] = rec
        owner = row['owner']
        aid = self.account(owner)
        rec.update(url=row['html_url'], title=row['full_name'], creator=owner['login'], owner_id=aid, owner_type=owner.get('type'), description=clean(row.get('description')), topics=[clean(t, 80) for t in row.get('topics', [])], is_fork=row.get('fork'), archived=row.get('archived'), default_branch=row.get('default_branch'), repository_created_at=row.get('created_at'), repository_updated_at=row.get('updated_at'), metadata_refreshed_at=now(), access='public', language=row.get('language'))
        if row.get('license'):
            rec['rights']['declared_code_license'] = row['license'].get('spdx_id')
        self.origin(rec, via, parent)
        e = self.ev('https://api.github.com/repos/' + row['full_name'], 'JSON id=' + str(row['id']) + '; owner.id=' + str(owner['id']), row['full_name'] + ' owner ' + owner['login'])
        eid = self.edge(aid, 'owns', sid, e, {'via': via, 'parent_id': parent})
        self.origin(rec, via, parent, eid)
        if rec['verification_status'] == 'confirmed':
            if rec.get('category') not in SCOPED_CATEGORIES:
                self.account(owner, parent=sid, via='owns-confirmed-campus-source', anchor=True, priority=25)
            if not row.get('fork') and rec.get('category') not in SCOPED_CATEGORIES and (rec.get('contributor_scope') != 'campus-delta-required'):
                self.enqueue(sid, 'contributors', 10)
            else:
                self.enqueue(sid, 'scoped-contributors-review', 70)
        if row.get('parent'):
            p = self.repo(row['parent'], sid, 'fork-parent', priority=90)
            if p:
                rec['fork_of'] = p
                self.edge(sid, 'fork-of', p, self.ev('https://api.github.com/repos/' + row['full_name'], 'JSON parent.id', str(row['parent']['id'])), {'via': 'repository-parent-metadata'})
                if self.state['records'][p]['verification_status'] == 'candidate':
                    self.enqueue(p, 'readme', 80)
                    self.enqueue(p, 'relevance-review', 85)
        return sid

    def api(self, endpoint):
        endpoint = endpoint.removeprefix('https://api.github.com/')
        if not re.match('^(?:repos/|repositories/\\d+|users/|orgs/|user/\\d+|organizations/\\d+/repos|search/(?:repositories|code)|rate_limit)', endpoint):
            raise ValueError('GET endpoint outside research scope')
        if any((SENSITIVE_QUERY.match(k) for k, _ in parse_qsl(urlsplit(endpoint).query))):
            raise ValueError('Sensitive query prohibited')
        bucket = 'search' if endpoint.startswith('search/') else 'core'
        until = max(self.state.get('blocked_until', {}).get(bucket, 0), self.state.get('blocked_until', {}).get('all', 0))
        if time.time() < until:
            return (None, {}, 'rate-deferred')
        rate = self.state.get('rate', {}).get(bucket, {})
        if bucket == 'core' and rate.get('remaining', 5000) < 200 and (rate.get('reset', 0) > time.time()):
            return (None, {}, 'verification-reserve')
        for attempt in (1, 2):
            try:
                p = subprocess.run(['gh', 'api', '--method', 'GET', '--include', endpoint], capture_output=True, text=True, timeout=30, env=self.subprocess_environment())
            except subprocess.TimeoutExpired:
                self.audit('request_error', endpoint=endpoint, error='timeout', attempt=attempt)
                if attempt == 1:
                    continue
                return (None, {}, 'timeout')
            self.state['api_calls'] += 1
            raw = p.stdout.replace('\r\n', '\n')
            headers = {}
            status = None
            while raw.startswith('HTTP/') and '\n\n' in raw:
                head, raw = raw.split('\n\n', 1)
                m = re.match('HTTP/\\S+\\s+(\\d+)', head)
                status = int(m[1]) if m else None
                for line in head.splitlines()[1:]:
                    if ':' in line:
                        k, v = line.split(':', 1)
                        headers[k.lower().strip()] = v.strip()
            try:
                data = json.loads(raw)
            except ValueError:
                data = [] if status == 204 else None
            if 'x-ratelimit-remaining' in headers:
                self.state.setdefault('rate', {})[bucket] = {'remaining': int(headers['x-ratelimit-remaining']), 'reset': int(headers.get('x-ratelimit-reset', '0'))}
            self.audit('request', endpoint=endpoint, status=status, attempt=attempt, rate_bucket=bucket, rate=self.state.get('rate', {}).get(bucket))
            if p.returncode == 0 and data is not None:
                return (data, headers, None)
            limited = status == 429 or (status == 403 and (headers.get('retry-after') or headers.get('x-ratelimit-remaining') == '0' or 'rate limit' in str(data).lower()))
            if limited:
                until = max(time.time() + int(headers.get('retry-after', '60')), int(headers.get('x-ratelimit-reset', '0')))
                self.state.setdefault('blocked_until', {})[bucket] = until
                self.audit('rate_limit', bucket=bucket, retry_at=until)
                return (None, headers, 'rate-limit')
            if attempt == 1 and (status is None or status >= 500):
                time.sleep(1)
                continue
            return (None, headers, 'http-' + str(status) if status else 'transport-error')

    def pages(self, op, endpoint, receive, search=False):
        cursor = op.get('next_endpoint') or endpoint
        op.setdefault('returned', 0)
        op.setdefault('pages', 0)
        start_page = op['pages']
        while cursor:
            data, headers, error = self.api(cursor)
            if error:
                op.update(status='deferred' if error in ('rate-limit', 'rate-deferred', 'verification-reserve', 'timeout', 'transport-error') or error.startswith('http-5') else 'restricted', error=error, next_endpoint=cursor)
                self.save()
                return False
            items = data.get('items', []) if search else data
            if not isinstance(items, list):
                op.update(status='restricted', error='unexpected-response')
                return False
            for row in items:
                receive(row, cursor)
            op['returned'] += len(items)
            op['pages'] += 1
            m = re.search('<([^>]+)>;\\s*rel="next"', headers.get('link', ''))
            cursor = m[1] if m else None
            if cursor and (not cursor.startswith('https://api.github.com/')):
                raise ValueError('Unexpected pagination origin')
            op.update(next_endpoint=cursor, last_observed_at=now())
            if search:
                op.update(total_count=data.get('total_count'), incomplete_results=data.get('incomplete_results', False))
            self.audit('page', operation_id=op['id'], returned=len(items), total_returned=op['returned'], page=op['pages'], next_endpoint=cursor)
            if search and (op.get('incomplete_results') or (op['returned'] >= 1000 and op['returned'] < op.get('total_count', 0))):
                op.update(status='restricted', error='search-incomplete-or-truncated')
                self.save()
                return False
            if not cursor:
                op.update(status='complete', completed_at=now())
            self.save()
            if cursor and op['pages'] - start_page >= 5:
                self.audit('pagination_checkpoint', operation_id=op['id'], reason='fair scheduling quantum; unfinished list remains pending', next_endpoint=cursor)
                return False
        return True

    def rebase_cursor(self, op, endpoint):
        """After numeric identity verification, keep the page on the current slug."""
        current = op.get('next_endpoint')
        if not current:
            return
        old, target = urlsplit(current), urlsplit(endpoint)
        old_parts, new_parts = old.path.strip('/').split('/'), target.path.strip('/').split('/')
        numeric_prefix = {'user': 'github-account:', 'organizations': 'github-account:', 'repositories': 'github-repo:'}
        numeric = old_parts[0] in numeric_prefix
        identity_matches = (len(old_parts) == 3 and
                            op.get('entity_id') == numeric_prefix[old_parts[0]] + old_parts[1]) if numeric else True
        repository_list = old_parts[0] in ('repos', 'repositories')
        if (old.hostname not in (None, 'api.github.com') or old.username or old.password
                or old.scheme not in ('', 'https') or old.port not in (None, 443)
                or (not numeric and len(old_parts) != len(new_parts))
                or not identity_matches or old_parts[-1] != new_parts[-1]
                or old_parts[0] not in ('repos', 'users', 'orgs', *numeric_prefix)
                or repository_list != (new_parts[0] == 'repos')):
            raise ValueError('Pagination endpoint does not belong to this verified list')
        refreshed = urlunsplit(('https', 'api.github.com', '/' + target.path.lstrip('/'), old.query, ''))
        if refreshed != current:
            op['next_endpoint'] = refreshed
            self.audit('pagination-identity-rebased', operation_id=op['id'], previous=clean(current), current=clean(refreshed))

    def profile(self, op, rec):
        d, h, e = self.api('user/' + rec['id'].split(':')[-1])
        if e:
            op.update(status='deferred' if e in ('rate-limit', 'rate-deferred', 'verification-reserve', 'timeout', 'transport-error') or e.startswith('http-5') else 'restricted', error=e)
            return
        self.profile_data(op, rec, d)

    def profile_data(self, op, rec, d):
        if str(d.get('id')) != rec['id'].split(':')[-1]:
            op.update(status='restricted', error='stable-id-mismatch')
            return
        text = '\n'.join((str(d.get(k) or '') for k in (('name', 'description', 'bio', 'company') if d.get('type') == 'Organization' else ('bio', 'company'))))
        self.account(d)
        rec['profile_checked_at'] = now()
        rec['profile_counts'] = {k: d.get(k) for k in ('public_repos', 'followers', 'following')}
        blog = url(d.get('blog'))
        if blog:
            rec['explicit_blog_url'] = blog
        if STRONG.search(text):
            proof = self.ev(d['html_url'], 'public ' + ('organization name/description' if d.get('type') == 'Organization' else 'bio/company'), text, 'public-school-affiliation-self-description; not student identity')
            rec.setdefault('evidence', []).append(proof)
            rec['verification_status'] = 'confirmed'
            rec['campus_relationship'] = 'public-profile-school-association'
            self.account(d, via='public-profile-school-association', anchor=True, priority=22)
        else:
            self.account(d)
        # Exact zero counts resolve empty lists without another API round trip.
        for operation, field in (('repos', 'all_public_repositories'), ('followers', 'followers'), ('following', 'following'), ('stars', 'public_stars')):
            queued = self.state['ops'].get(rec['id'] + '|' + operation)
            if d.get(field) == 0 and queued and queued['status'] == 'pending' and not queued.get('pages') and not queued.get('next_endpoint'):
                queued.update(status='complete', returned=0, pages=0, completed_at=now(), completion_evidence='stable-identity-all-public-affiliations-count-zero' if operation == 'repos' else 'stable-identity-profile-count-zero')
        op.update(status='complete', completed_at=now())

    def readme(self, op, rec):
        metadata, _, failure = self.api('repositories/' + rec['id'].split(':')[-1])
        if failure:
            op.update(status='restricted' if failure in ('http-404', 'http-451') else 'deferred', error=failure)
            return
        if str(metadata.get('id')) != rec['id'].split(':')[-1]:
            op.update(status='restricted', error='stable-id-mismatch')
            return
        if metadata.get('private') is not False:
            op.update(status='restricted', error='repository-not-public')
            rec['readme_current_status'] = 'restricted'
            return
        self.repo(metadata, via='readme-stable-id-refresh')
        d, h, e = self.api('repos/' + rec['title'] + '/readme')
        if e:
            op.update(status='missing' if e == 'http-404' else 'deferred' if e in ('rate-limit','rate-deferred','verification-reserve','timeout','transport-error') or e.startswith('http-5') else 'restricted', error=e)
            rec['readme_current_status'] = op['status']
            return
        if d.get('encoding') != 'base64' or d.get('size', 0) > 200000:
            op.update(status='restricted', error='size-or-encoding-guard')
            return
        try:
            text = base64.b64decode(d.get('content', '')).decode('utf-8')
        except (ValueError, UnicodeDecodeError):
            op.update(status='restricted', error='decode-error')
            return
        self.accept_readme(op, rec, text, d)

    def accept_readme(self, op, rec, text, d):
        """Apply a complete decoded README identically for either public transport."""
        rec['review_readme'] = clean(text, 200000)
        previous_readme_sha = (rec.get('readme_current') or {}).get('sha')
        proofs = []
        for i, line in enumerate(text.splitlines(), 1):
            if SCHOOL.search(line):
                proofs.append(self.ev(d.get('html_url') or rec['url'], 'README ' + d.get('path', '') + ' line ' + str(i), line, 'candidate-school-context; needs scope review'))
            if len(proofs) >= 4:
                break
        rec['readme_current_status'] = 'read'
        rec['readme_current'] = {'path': clean(d.get('path')), 'sha': d.get('sha'), 'url': url(d.get('html_url')), 'line_count': len(text.splitlines()), 'accessed_at': now()}
        rec['current_school_candidates'] = proofs
        if proofs or (previous_readme_sha and previous_readme_sha != d.get('sha')):
            key = self.enqueue(rec['id'], 'relevance-review', 20)
            review = self.state['ops'][key]
            if previous_readme_sha and previous_readme_sha != d.get('sha') and review['status'] == 'complete':
                review.update(status='pending', reason='README evidence revision changed')
        links = []
        for m in re.finditer('https?://github\\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)', text):
            target = 'https://github.com/' + m[1] + '/' + m[2].removesuffix('.git').rstrip('.')
            if target != rec['url'] and target not in links:
                links.append(target)
        rec['explicit_repo_links'] = links
        rec['explicit_repo_links_truncated'] = False
        op.update(status='complete', completed_at=now())
        self.audit('readme_evidence_checked', source_id=rec['id'], school_excerpt_count=len(proofs), lines=len(text.splitlines()), sanitized_readme_persisted=True)

    def execute(self, op):
        rec = self.state['records'][op['entity_id']]
        kind = op['operation']
        sid = rec['id']
        op['started_at'] = op.get('started_at') or now()
        if kind == 'profile':
            self.profile(op, rec)
            return
        if kind == 'metadata':
            d, h, e = self.api('repositories/' + sid.split(':')[-1])
            if e:
                op.update(status='deferred' if e in ('rate-limit', 'rate-deferred', 'verification-reserve', 'timeout', 'transport-error') or e.startswith('http-5') else 'restricted', error=e)
                return
            if str(d.get('id')) != sid.split(':')[-1] or d.get('private') is not False:
                op.update(status='restricted', error='repository-not-public-or-identity-mismatch')
                return
            self.repo(d, via='metadata-refresh')
            if self.state['records'][sid]['verification_status'] == 'candidate':
                self.enqueue(sid, 'readme', 38)
                self.enqueue(sid, 'relevance-review', 60)
            op.update(status='complete', completed_at=now())
            return
        if kind == 'readme':
            self.readme(op, rec)
            return
        if kind in ('relevance-review', 'scoped-contributors-review'):
            return
        if kind == 'contributors':
            if rec.get('is_fork') or rec.get('category') in SCOPED_CATEGORIES or rec.get('contributor_scope') == 'campus-delta-required':
                op.update(status='scoped-review-required', error='do-not-expand-upstream-contributors')
                return
            metadata, _, error = self.api('repositories/' + sid.split(':')[-1])
            if error:
                op.update(status='restricted' if error in ('http-404', 'http-451') else 'deferred', error=error)
                return
            if str(metadata.get('id')) != sid.split(':')[-1]:
                op.update(status='restricted', error='stable-id-mismatch')
                return
            if metadata.get('private') is not False:
                op.update(status='restricted', error='repository-not-public')
                return
            self.repo(metadata, via='contributor-list-identity-refresh')
            if rec.get('is_fork'):
                op.update(status='scoped-review-required', error='do-not-expand-upstream-contributors')
                return

            def receive(row, endpoint):
                aid = self.account(row, parent=sid, via='repository-contributor', anchor=rec.get('verification_status') == 'confirmed' or rec.get('user_requested_seed'), priority=18)
                if not aid:
                    return
                proof = self.ev('https://api.github.com/' + endpoint.removeprefix('https://api.github.com/'), 'contributor id=' + str(row['id']) + '; contributions=' + str(row.get('contributions')), row['login'] + ' listed by GitHub as contributor', 'GitHub account mapping; not identity/membership/original-authorship proof')
                self.edge(aid, 'listed-contributor-to', sid, proof, {'discovered_from': sid})
                self.state['records'][aid].setdefault('contributed_repository_ids', [])
                if sid not in self.state['records'][aid]['contributed_repository_ids']:
                    self.state['records'][aid]['contributed_repository_ids'].append(sid)
            endpoint = 'repos/' + rec['title'] + '/contributors?per_page=100&anon=false'
            self.rebase_cursor(op, endpoint)
            self.pages(op, endpoint, receive)
            return
        if kind in ('following', 'followers') and rec.get('expansion_exclusion'):
            self.stop_social_operation(op, 'explicit-exclusion:' + rec['expansion_exclusion'])
            return
        identity = {'id': op['id'], 'operation': 'identity-refresh'}
        self.profile(identity, rec)
        if identity.get('status') != 'complete':
            op.update(status='deferred' if identity.get('status') == 'deferred' else 'restricted', error=identity.get('error') or 'identity-unverified')
            return
        login = rec['title']
        distance = rec.get('best_unknown_distance', 99)
        if kind in ('following', 'followers'):
            if rec.get('account_type') == 'Organization':
                op.update(status='not-applicable', reason='organization has no user social lists')
                return
            if rec.get('expansion_exclusion') or distance > 1:
                self.stop_social_operation(op, 'bridge-boundary-or-explicit-exclusion')
                return

            def receive(row, endpoint):
                self.receive_account_list(op, rec, row, endpoint)
            endpoint = 'users/' + login + '/' + kind + '?per_page=100'
            self.rebase_cursor(op, endpoint)
            self.pages(op, endpoint, receive)
            return
        if kind in ('repos', 'stars'):
            if kind == 'stars' and rec.get('account_type') == 'Organization':
                op.update(status='not-applicable')
                return

            def receive(row, endpoint):
                self.receive_account_list(op, rec, row, endpoint)
            endpoint = ('orgs/' if rec.get('account_type') == 'Organization' else 'users/') + login + '/repos?per_page=100&type=all' if kind == 'repos' else 'users/' + login + '/starred?per_page=100'
            self.rebase_cursor(op, endpoint)
            self.pages(op, endpoint, receive)
            return
        raise ValueError('Unknown operation ' + kind)

    def receive_account_list(self, op, rec, row, endpoint, locator_prefix=''):
        kind, sid = op['operation'], rec['id']
        distance = rec.get('best_unknown_distance', 99)
        if kind in ('following', 'followers'):
            target = self.account(row, parent=sid, via=kind, distance=min(distance + 1, 2), priority=50 if distance == 0 else 80)
            if not target:
                return
            a, b = (sid, target) if kind == 'following' else (target, sid)
            proof = self.ev('https://api.github.com/' + endpoint.removeprefix('https://api.github.com/'), locator_prefix + kind + ' entry id=' + str(row['id']), row['login'], 'observed-follow-direction-only')
            eid = self.edge(a, 'follows', b, proof, {'discovered_from': sid, 'list': kind, 'unknown_distance': distance + 1})
            self.origin(self.state['records'][target], kind, sid, eid)
            return
        if row.get('private') is not False:
            return
        text = ' '.join([row.get('full_name', ''), row.get('description') or '', ' '.join(row.get('topics') or [])])
        rid = 'github-repo:' + str(row['id'])
        own = kind == 'repos' and str(row.get('owner', {}).get('id')) == sid.split(':')[-1]
        keep = rid in self.state['records'] or SCHOOL.search(text) or (own and (not row.get('fork'))) or CLUE.search(text)
        if not keep:
            self.state['aggregate']['repo_metadata_nonmatches'] += 1
            return
        r = self.repo(row, sid, kind, priority=60)
        if not r:
            return
        if kind == 'stars':
            self.edge(sid, 'starred', r, self.ev('https://api.github.com/' + endpoint.removeprefix('https://api.github.com/'), locator_prefix + 'starred repository id=' + str(row['id']), row['full_name'], 'star observed; not a campus endorsement'), {'discovered_from': sid})
        if self.state['records'][r]['verification_status'] == 'candidate' and (not row.get('fork')):
            self.enqueue(r, 'readme', 35 if SCHOOL.search(text) or CLUE.search(text) else 75)

    def seed(self, name, priority=0):
        if '/' in name:
            d, h, e = self.api('repos/' + name)
            if e:
                raise RuntimeError(e)
            sid = self.repo(d, via='explicit-research-seed')
            self.state['records'][sid]['user_requested_seed'] = True
            self.enqueue(sid, 'readme', priority)
            self.enqueue(sid, 'contributors', priority + 1)
        else:
            d, h, e = self.api('users/' + name)
            if e:
                raise RuntimeError(e)
            self.account(d, via='explicit-research-seed', anchor=True, priority=priority)
        self.save()

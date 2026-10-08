"""Deterministic archive reading views from one public projection."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import os
import re
from importlib.resources import files
from pathlib import Path

from .public import public_url
from .utils import atomic_write_text, load_json, write_json

NAVIGATION = {'contains', 'focuses', 'related-to', 'wikilink', 'categorized-as', 'about'}
EVIDENCE = {'supports', 'contradicts', 'context', 'described-by'}
COLORS = {'event': '#ba6743', 'knowledge': '#347e79', 'node': '#6887ad', 'collection': '#9173a2', 'source': '#9c927f'}
TYPE_NAMES = {'event': '事件', 'knowledge': '知识档案', 'node': '目录对象', 'collection': '专题集合', 'source': '来源'}


def label(record):
    return record.get('title') or record.get('name') or record['id']


def layout(nodes, edges):
    """Stable initial positions and bounded local repulsion, without random state."""
    count = len(nodes)
    points = {}
    for index, node in enumerate(nodes):
        angle = index * math.pi * (3 - math.sqrt(5))
        radius = 20 * math.sqrt(index + 1)
        points[node['id']] = [radius * math.cos(angle), radius * math.sin(angle)]
    # Spatial buckets keep the layout usable with thousands of records.
    for _ in range(80):
        buckets = {}
        shifts = {key: [0.0, 0.0] for key in points}
        for key, (x, y) in points.items():
            buckets.setdefault((int(x // 45), int(y // 45)), []).append(key)
        for key, (x, y) in points.items():
            bx, by = int(x // 45), int(y // 45)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in buckets.get((bx + dx, by + dy), []):
                        if other <= key:
                            continue
                        ox, oy = points[other]
                        vx, vy = x - ox, y - oy
                        distance = max(math.hypot(vx, vy), 0.1)
                        force = min(4, 90 / (distance * distance))
                        for axis, value in enumerate((vx, vy)):
                            delta = value / distance * force
                            shifts[key][axis] += delta
                            shifts[other][axis] -= delta
        for edge in edges:
            a, b = edge['from'], edge['to']
            if a == b:
                continue
            vx, vy = points[b][0] - points[a][0], points[b][1] - points[a][1]
            length = max(math.hypot(vx, vy), .1)
            force = max(-2, min(2, (length - 65) * .012))
            for axis, value in enumerate((vx, vy)):
                shifts[a][axis] += value / length * force
                shifts[b][axis] -= value / length * force
        for key in points:
            points[key] = [round(points[key][axis] + max(-5, min(5, shifts[key][axis])), 4) for axis in (0, 1)]
    return points


def reading_markdown(text, source_path, root, ids):
    # Preserve readable prose, never executable HTML or links to private local material.
    text = re.sub(r'<[^>]*>', lambda match: html.escape(match[0]), text)
    def link(match):
        title, target = match[1], match[2]
        if target.startswith(('https://', 'http://')):
            return f'[{title}]({target})' if public_url(target) else title
        candidate = (source_path.parent / target.split('#')[0]).resolve()
        if candidate in ids:
            return f'[{title}]({ids[candidate]}.md)'
        return title
    text = re.sub(r'!?\[([^\]\n]+)\]\(([^)\n]+)\)', link, text)
    return re.sub(r'\[\[([a-z0-9-]+)(?:\|([^\]]+))?\]\]', lambda m: f'[{m[2] or m[1]}]({m[1]}.md)', text)


def make_payload(root, records, graph, backlinks):
    result = {**graph, 'details': {}}
    positions = layout(graph['nodes'], graph['edges'])
    result['nodes'] = [{**node, 'x': positions[node['id']][0], 'y': positions[node['id']][1]} for node in graph['nodes']]
    result['edges'] = [{**edge, 'kind': 'evidence' if edge['relation'] in EVIDENCE else 'fact' if edge['claim_ids'] else 'navigation'} for edge in graph['edges']]
    for kind, entries in records.items():
        for path, record in entries:
            detail = {**record, 'canonical_path': path.relative_to(root).as_posix(), 'backlinks': backlinks[record['id']]}
            detail['body'] = (path.parent / record['narrative']).read_text(encoding='utf-8') if record.get('narrative') else ''
            result['details'][record['id']] = detail
    return result


def _markdown_escape(text):
    return str(text).replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('\n', ' ')


def write_catalog(root, output, payload, records):
    catalog = output / 'catalog'
    catalog.mkdir(parents=True, exist_ok=True)
    revision = payload['dataset_revision']
    by_path = {path.resolve(): record['id'] for values in records.values() for path, record in values}
    by_id = {node['id']: node for node in payload['nodes']}
    expected = set()
    def write(path, body):
        expected.add(path)
        atomic_write_text(path, body + '\n')
    for rid, item in payload['details'].items():
        path = catalog / 'records' / (rid + '.md')
        canonical = Path(os.path.relpath(root / item['canonical_path'], path.parent)).as_posix()
        lines = [f'# {_markdown_escape(label(item))}', '', f'[档案目录](../README.md) · [正式记录]({canonical})', '',
                 f'> 自动生成的阅读视图，修改请回到正式记录。内容版本：`{revision}`。', '', (item.get('summary') or ''), '']
        if item.get('time'):
            lines += ['时间：' + json.dumps(item['time'], ensure_ascii=False), '']
        if item.get('validity'):
            value = item['validity']
            lines += [f"有效期：{value.get('start') or '未知'} — {value.get('end') or '未知'}；状态：{value['state']}；核验时间：{value.get('verified_at') or '未知'}。", '']
        if item['body']:
            lines += [reading_markdown(item['body'], root / item['canonical_path'], root, by_path), '']
        for claim in item.get('claims', []):
            lines += [f"## 论断 `{claim['id']}`", '', claim['text'], '', f"类型：{claim['kind']}", '']
            for citation in claim['citations']:
                source = payload['details'][citation['source_id']]
                lines += [f"- {citation['role']} · [{_markdown_escape(label(source))}]({source['id']}.md) · {_markdown_escape(citation.get('locator') or '来源整体')}"]
            lines += ['']
        for key in ('original_url', 'archive_url'):
            address = item.get('locator', {}).get(key)
            if address and public_url(address):
                lines += [f'[{"原始来源" if key == "original_url" else "存档来源"}]({address})', '']
        if item.get('locator', {}).get('public_path'):
            lines += ['来源本地路径仅在正式记录中保存；该阅读视图未复制附件。', '']
        edges = item['backlinks']['outgoing'] + item['backlinks']['incoming']
        if edges:
            lines += ['## 相关档案与反向链接', '']
            for edge in edges:
                other = edge['to'] if edge['from'] == rid else edge['from']
                direction = '→' if edge['from'] == rid else '←'
                lines += [f"- {direction} {edge['relation']} · [{_markdown_escape(by_id[other]['label'])}]({other}.md)"]
        write(path, '\n'.join(lines))
    index = ['# Digital SZTU 档案目录', '', f'内容版本：`{revision}`。', '', '这些页面由正式 JSON／Markdown 档案生成，不包含研究候选或社交发现网络。', '']
    for kind, title in TYPE_NAMES.items():
        nodes = [node for node in payload['nodes'] if node['type'] == kind]
        index += [f'- [{title}（{len(nodes)}）](categories/{kind}.md)']
        lines = [f'# {title}', '', '[返回档案目录](../README.md)', '', f'内容版本：`{revision}`。', '']
        lines += [f"- [{_markdown_escape(node['label'])}](../records/{node['id']}.md)" for node in nodes] or ['暂无公开档案。']
        write(catalog / 'categories' / (kind + '.md'), '\n'.join(lines))
    write(catalog / 'README.md', '\n'.join(index))
    for path in catalog.rglob('*.md'):
        if path not in expected:
            path.unlink()  # This directory is owned entirely by the generator.


def svg_preview(payload):
    nodes = [node for node in payload['nodes'] if node['type'] != 'source']
    by_id = {node['id']: node for node in nodes}
    edges = [edge for edge in payload['edges'] if edge['from'] in by_id and edge['to'] in by_id]
    # The overview explicitly describes any omission; all displayed edges are real.
    label_ids = {node['id'] for node in nodes[:40]}
    xs, ys = [node['x'] for node in nodes], [node['y'] for node in nodes]
    lowx, highx, lowy, highy = min(xs, default=-1), max(xs, default=1), min(ys, default=-1), max(ys, default=1)
    scale = min(880 / max(highx - lowx, 1), 350 / max(highy - lowy, 1))
    pos = {node['id']: (90 + (node['x'] - lowx) * scale, 120 + (node['y'] - lowy) * scale) for node in nodes}
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="620" viewBox="0 0 1100 620" role="img">',
             '<title>Digital SZTU 公开档案关系概览</title>',
             f'<desc>{html.escape(payload["dataset_revision"])}；显示 {len(nodes)} 个非来源节点及 {len(edges)} 条真实关系。来源在交互详情中查看，最多显示 40 个标签。</desc>',
             '<rect width="1100" height="620" fill="#f6f5ef"/>',
             '<g font-family="system-ui, sans-serif" fill="#203a38"><text x="42" y="48" font-size="25" font-weight="650">Digital SZTU</text>',
             '<text x="42" y="76" font-size="14">深圳技术大学 · 数字档案关系图谱</text>']
    for edge in edges:
        x1, y1 = pos[edge['from']]; x2, y2 = pos[edge['to']]
        dash = ' stroke-dasharray="3 5"' if edge['kind'] == 'navigation' else ''
        parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#b9c5bc" stroke-width="1.1"{dash}/>')
    label_boxes = []
    for node in nodes:
        x, y = pos[node['id']]
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{COLORS[node["type"]]}"><title>{html.escape(node["label"])}</title></circle>')
        if node['id'] in label_ids:
            title = node['label'][:30] + ('…' if len(node['label']) > 30 else '')
            width = sum(10 if ord(char) > 255 else 6 for char in title)
            left = x + 8 if x + width + 8 < 1070 else x - width - 8
            box = (left, y - 6, left + width, y + 7)
            if not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in label_boxes):
                label_boxes.append(box)
                parts.append(f'<text x="{left:.2f}" y="{y+4:.2f}" font-size="10">{html.escape(title)}</text>')
    if not nodes:
        parts.append('<text x="42" y="270" font-size="19">暂无可公开展示的正式档案</text>')
    parts += [f'<text x="42" y="550" font-size="13">{len(nodes)} 个档案节点 · {len(edges)} 条关系 · 来源在详情中查看 · 标签最多 40 个</text>',
              '<text x="42" y="576" font-size="12">实线：档案关系　虚线：导航关系　点击预览，打开交互图谱</text>',
              f'<text x="42" y="602" font-size="9" fill="#697b72">{html.escape(payload["dataset_revision"])}</text></g></svg>']
    return '\n'.join(parts) + '\n'


def write_archive_views(root, output, records, graph, backlinks):
    payload = make_payload(root, records, graph, backlinks)
    write_json(output / 'archive.json', payload, sort_keys=True)
    atomic_write_text(output / 'graph-preview.svg', svg_preview(payload))
    write_catalog(root, output, payload, records)
    return {'dataset_revision': payload['dataset_revision'], 'records': len(payload['nodes'])}


def viewer_html(payload):
    assets = files('digital_sztu').joinpath('assets')
    css = assets.joinpath('graph.css').read_text(encoding='utf-8')
    js = assets.joinpath('graph.js').read_text(encoding='utf-8')
    template = assets.joinpath('graph.html').read_text(encoding='utf-8')
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    digest = lambda text: base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
    policy = f"default-src 'none'; style-src 'sha256-{digest(css)}'; script-src 'sha256-{digest(js)}'; img-src data:; base-uri 'none'; form-action 'none'"
    return template.replace('@@CSP@@', policy).replace('@@CSS@@', css).replace('@@DATA@@', data).replace('@@JS@@', js)


def write_viewer(root: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or any(path.is_symlink() for path in output.rglob('*')):
        raise ValueError('Viewer output must not contain symlinks')
    payload = load_json(root / 'data/generated/archive.json')
    destination = output / 'index.html'
    atomic_write_text(destination, viewer_html(payload))
    return {'ok': True, 'output': str(destination), 'dataset_revision': payload['dataset_revision']}

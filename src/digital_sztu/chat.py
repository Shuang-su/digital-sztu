from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .utils import load_json


def load_messages(path: Path, schema_path: Path) -> list[dict[str, Any]]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    messages: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            failures = list(validator.iter_errors(value))
            if failures:
                details = "; ".join(f.message for f in failures)
                raise ValueError(f"line {number}: {details}")
            messages.append(value)
    return messages


def render_chat(messages: list[dict[str, Any]], title: str) -> str:
    items: list[str] = []
    for message in messages:
        side = " self" if message.get("is_self") else ""
        sender = html.escape(message.get("sender_display") or "未知参与者")
        timestamp = html.escape(message.get("timestamp") or "时间未知")
        if message.get("redacted") or message.get("kind") == "redacted":
            body = '<span class="redacted">[该消息已脱敏]</span>'
        else:
            text = message.get("text")
            body = html.escape(text) if text else f"[{html.escape(message.get('kind', 'other'))}]"
            body = body.replace("\n", "<br>")
        reply = ""
        if message.get("reply_to"):
            reply = f'<div class="reply">回复 {html.escape(message["reply_to"])}</div>'
        items.append(
            f'<article class="message{side}" id="{html.escape(message["id"])}">'
            f'<div class="meta"><strong>{sender}</strong><time>{timestamp}</time></div>'
            f'<div class="bubble">{reply}{body}</div></article>'
        )
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
body {{ margin: 0; background: #eef1f5; color: #17202a; }}
main {{ max-width: 760px; margin: 0 auto; min-height: 100vh; background: #f7f8fa; box-shadow: 0 0 40px rgba(0,0,0,.08); }}
header {{ position: sticky; top: 0; padding: 18px 22px; background: rgba(255,255,255,.92); backdrop-filter: blur(14px); border-bottom: 1px solid #dfe4ea; z-index: 1; }}
header h1 {{ margin: 0; font-size: 18px; }}
header p {{ margin: 6px 0 0; font-size: 12px; color: #667085; }}
.transcript {{ padding: 24px 18px 48px; }}
.message {{ display: flex; flex-direction: column; align-items: flex-start; margin: 18px 0; }}
.message.self {{ align-items: flex-end; }}
.meta {{ display: flex; gap: 10px; align-items: baseline; margin: 0 8px 5px; font-size: 12px; color: #667085; }}
.meta time {{ font-variant-numeric: tabular-nums; }}
.bubble {{ max-width: min(72ch, 82%); padding: 11px 14px; border-radius: 15px 15px 15px 4px; background: white; border: 1px solid #e4e7ec; line-height: 1.55; overflow-wrap: anywhere; }}
.self .bubble {{ border-radius: 15px 15px 4px 15px; background: #d9fdd3; }}
.reply {{ margin-bottom: 8px; padding: 7px 9px; border-left: 3px solid #98a2b3; background: rgba(0,0,0,.04); color: #475467; font-size: 12px; }}
.redacted {{ color: #667085; font-style: italic; }}
@media (prefers-color-scheme: dark) {{
  body {{ background: #0b1118; color: #eef2f6; }} main {{ background: #111923; }} header {{ background: rgba(17,25,35,.92); border-color: #263241; }}
  .bubble {{ background: #182330; border-color: #2b3948; }} .self .bubble {{ background: #16452f; }} .meta, header p, .redacted {{ color: #a8b3c2; }}
}}
</style>
</head>
<body>
<main>
<header><h1>{safe_title}</h1><p>Digital SZTU：通用聊天记录重建；不代表微信官方界面或认证。</p></header>
<section class="transcript">{''.join(items)}</section>
</main>
</body>
</html>"""

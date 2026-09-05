---
name: fact-check-event
description: Trace Digital SZTU event claims to source locators, compare support and counterevidence, check time and identity uncertainty, and produce a fact-check matrix. Use for 核查, 纠错, 争议, duplicate-event, or provenance questions; remain read-only unless the user asks to apply corrections.
---

# Fact-check an event

1. Work in the user-selected Digital SZTU clone. If an Event exists, read it, every cited Source, linked Event/Node, and generated backlinks. If the user only supplies a statement or provenance question, give a limited initial assessment from the available material; do not invent records or locators to satisfy this workflow. Use the pinned local CLI environment from `README.md` only when a CLI check is needed.
2. For each Claim report: text, kind, certainty, Event time, supporting Source locators, contradicting Source locators, independence groups, and unresolved questions.
3. Count only `supports` Citations from different non-empty independence groups as corroboration. Do not count copies, context, counterevidence, OCR, AI summaries, or vector search results as independent sources.
   For chat Sources, read [the chat workflow](../../docs/CHAT_IMPORT.md). Check the supplied export against its recorded SHA-256 when the original is available, then resolve each citation to the original message, time and surrounding context. Distinguish server IDs, database-local IDs and exporter-generated indexes; keep large IDs as strings. A missing original is an evidence gap, not a reason to invent a locator. Re-exports of one conversation belong to the same independence group.
4. Verify that Event-to-Node relationships use the right identity. Similar names or aliases do not prove they are the same person, organization, place, or institution.
5. Preserve conflicting evidence. “Not yet confirmed” is not the same as “disproved.”
6. When asked to apply a correction, edit the smallest Claim/Citation/Link scope, explain the evidence change, rebuild, and keep Git history intact.

Do not assign governance roles or turn a fact-check report into an authority-based publication decision.

Keep three findings separate: tool provenance, continuity of the supplied export's bytes, and the truth of a message's assertion. A matching tool/archive checksum or an upstream “Safe” name does not prove either chat authenticity or a Claim. Record actual inspection and untested assumptions explicitly; do not require access to an account or private database to complete a limited, read-only evidence report.

For an onboarding suggestion, use [the shared exploration flow](../../docs/GETTING_STARTED.md#5-探索材料与历史线索) for scope and reporting, and assess only the available evidence. A Computer History observation should lead back to the original page, file or message; a retained summary is not independent corroboration. Distinguish event, message, publication, export, file-metadata and observation times rather than filling an unknown event date from the time someone opened a file.

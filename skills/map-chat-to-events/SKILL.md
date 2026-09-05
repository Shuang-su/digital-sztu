---
name: map-chat-to-events
description: Help choose a pinned third-party chat export tool or use a user-selected export as a traceable Digital SZTU Source; map to chat JSONL and candidate Events only when requested. Use for chat-history material, not account access or an automatic platform parser.
---

# Map chat material

Work in the user-selected Digital SZTU clone, not the plugin cache. Read [the chat workflow](../../docs/CHAT_IMPORT.md); reuse the pinned local CLI when a CLI operation is needed. If the environment is missing, follow `docs/GETTING_STARTED.md` first.

## Route the request

- **Initial exploration:** when routed from authorized onboarding, follow [the shared exploration flow](../../docs/GETTING_STARTED.md#5-探索材料与历史线索). Read supplied exports directly; list newly discovered candidates before batch reading. Locate useful messages and evidence gaps without requiring JSONL, a full-account export or a formal Source/Event. Use the guide's guarded report only within the permitted output scope. A tool installation still pending does not prevent reading an existing export.
- **No export yet:** consult [the tool directory](../../importers/README.md) and `importers/registry.json`. Match the user's OS, CPU architecture, desktop WeChat version or iOS-backup route. Ask only for missing information that changes the choice. Give the fixed upstream download or preserved source entry and its actual limitations; a source archive is not a ready-to-run installer. Stop at guidance unless the user requests further action. Do not silently download, install, rebuild, launch a tool, extract keys, or access an account.
- **Export already supplied:** do not send the user back to export it again. Inspect only the selected files and calculate their hashes read-only. If a saved private inventory is useful and within the allowed output scope, use `digital-sztu ingest <path> --dry-run --json`; despite its name, this writes a manifest under `.work/`. Do not run it for a strictly read-only request or an output scope that excludes `.work/`. Keep originals unchanged; a Source can cite the original export directly. JSONL conversion is optional, not an admission requirement.
- **Structured mapping requested:** follow the format notes in `docs/CHAT_IMPORT.md` and `schemas/chat-message.schema.json`. Respect the user's private output scope (normally `.work/`), validate with `digital-sztu validate-chat <file> --json`, and render only if useful or requested. The renderer requires an output under `.work/`; do not silently widen a narrower output scope. Keep a locator mapping back to the original; the renderer is not an independent source.

## Preserve the evidence

Record the actual exporter/version, export scope, file SHA-256 and available original message locators. Preserve large server IDs as strings, and distinguish them from database-local IDs or export-array indexes. Keep source text, original time and timezone uncertainty, reply relationships and relevant display names. Missing identity is not permission to infer an account or merge names.

When asked to create records, create Source metadata before candidate Events. Cite the selected file and precise original message location, not the importer's release URL. Preserve a truthful identifier if the original is private; do not invent a public URL or publish the original merely to make the citation clickable.

A matching archive hash establishes which tool snapshot was preserved; an export hash establishes which supplied bytes were inventoried. Neither proves that the export was unedited or that statements in it are true. Choose the appropriate `memory`, `allegation`, `uncertain`, or `fact` Claim kind, retain counterevidence, and link Nodes only on a clear identity match. Repeated or re-exported messages do not become independent corroboration.

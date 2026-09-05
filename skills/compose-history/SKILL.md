---
name: compose-history
description: Arrange existing source-linked Digital SZTU events as 编年体, 纪传体, 典制体, 纪事本末体, or another focused collection without duplicating event facts. Use when the user asks for a chronology, biography, institutional history, or thematic narrative.
---

# Compose a historical view

1. Work in a user-selected Digital SZTU clone with the pinned local CLI installed as described in `README.md`. Read `docs/HISTORY_FORMS.md` and choose `annals`, `biographical`, `institutional`, or `thematic` from the user's requested form.
2. Reuse existing Event IDs. If the narrative needs a fact not present in any Event, create or request that Event first rather than embedding an uncited fact in the Collection.
3. Use `focus_ids` for the people, organizations, places, institutions, or topics that define the view.
4. Use `chronological` ordering when time should determine order; preserve unknown dates as unknown. Use `curated` only when narrative sequence is intentional.
5. Do not copy Claim text or Sources into the Collection. Backlinks will make each Event and focus Node aware of the Collection.
6. Run `digital-sztu check --json` and inspect `data/generated/collections.json`.

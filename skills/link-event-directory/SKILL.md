---
name: link-event-directory
description: Inspect, create, or repair Digital SZTU event relationships and Obsidian-style backlinks across event, person, organization, place, institution, topic, source, and collection indexes. Use for linking, backlinks, related directories, aliases, or dangling references; not for inventing evidence.
---

# Link events and directories

1. Work in a user-selected Digital SZTU clone with the pinned local CLI installed as described in `README.md`. Load the Event, its Claims and Sources, then search existing Nodes by ID, name, and alias.
2. Treat fuzzy name matches as candidates, not identity. If identity cannot be established, keep separate Nodes and report the ambiguity.
3. Store each evidence-bearing relationship once in the originating Event `links[]`. Every Link requires at least one `claim_id` and one `source_id`, and each Source must be cited by one of those Claims. Use a Markdown wikilink for navigation-only associations.
4. Use a short kebab-case relation that describes the direction from Event to target, such as `involves`, `held-by`, `occurs-at`, `changes`, `about`, `follows`, `corrects`, or `related-to`.
5. Use Markdown `[[id|label]]` only for navigation or prose references; do not use it to bypass Claim/Citation evidence.
6. Run `digital-sztu build --json`. Confirm the target has an incoming entry in `data/generated/backlinks.json` and the Event appears in each applicable `data/generated/directories/*.json` file.
7. Never hand-edit `data/generated/`, and never write reciprocal Event lists into Node files.

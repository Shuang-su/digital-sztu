---
name: setup-digital-sztu
description: Set up, resume, or check a local Digital SZTU working copy, then help find a first campus recording idea through authorized material and history exploration. Use for getting started, environment preparation, or continuing onboarding; it does not automatically create formal records or publish anything.
---

# Set up Digital SZTU

Locate the user's working copy or the folder they selected for it. An installed plugin cache is not their archive. Do not overwrite an unrelated directory, an existing environment, or uncommitted files; do not install all Agent clients.

Read the shared [getting-started guide](../../docs/GETTING_STARTED.md) in full. If the skill was installed without the guide, read `https://raw.githubusercontent.com/Shuang-su/digital-sztu/main/docs/GETTING_STARTED.md`, then obtain the user checkout as directed there. After selecting the checkout, read its root `AGENTS.md` and local guide; use that checkout's scripts and existing state.

Follow the guide's environment detection, tool preparation, isolated example and recovery flow. Confirm the shell operates on the selected local workspace before installing anything. Reuse a valid environment and run the helper with an explicit absolute `--root`; use `--check --json` for a check-only request. Setup-only and check-only requests do not authorize personal material or history exploration. Do not use a client's `/init` to rewrite project instructions.

The helper handles repeatable project-local preparation. The Agent handles official system installers, normal application installation and user authorization as described in the guide, using available Computer Use for appropriate graphical steps. Computer Use and Computer History have separate capability and permission checks; neither is added to the bootstrap script. An installer file alone is not an installed application. If the registry or platform artifact is missing, report that dependency without substituting another tool or claiming completion.

Read each stage's status, not only the exit code. Distinguish a usable local core from pending tools, and distinguish installed-app metadata from an actual launch test. Open or link the generated example results, report the working-copy location and outstanding user actions. Pending optional capabilities do not block reading already supplied material within the user's authorization.

For a full onboarding request with explicit material and history authorization, continue into [first exploration](../../docs/GETTING_STARTED.md#5-探索材料与历史线索). Reuse choices already made in this task; ask once for missing scope instead of inferring consent from the guide, a saved report, or a quoted prompt. The guide defines candidate discovery, inventory-before-batch-reading, all-retained-history coverage, original-source checks and the guarded local report. Follow that shared flow rather than scanning the whole computer or creating a second instruction copy. Strictly read-only requests receive conversational results, without an inventory/report write.

Give evidence-backed recording suggestions and invite the user to choose an event. Only a recording request enters `record-campus-event`; use `map-chat-to-events` for original export interpretation and `fact-check-event` for a limited evidence check when needed. Exploration does not create formal Source/Event/Node records, copy original material or publish. Only continue into GitHub setup when the user asks to synchronize or contribute; setup and exploration do not authorize account login, remote changes, push, PR or merge.

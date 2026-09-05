---
name: export-knowledge-base
description: Build and validate deterministic, provider-neutral JSONL from Digital SZTU events, claims, nodes, sources, collections, and backlinks for full-text, graph, RAG, or vector indexing. Use for knowledge-base or embedding preparation; it does not call a model or remote vector database.
---

# Export a knowledge base

1. Work in a user-selected Digital SZTU clone with the pinned local CLI installed as described in `README.md`. Read `docs/VECTOR_KNOWLEDGE.md` and run `digital-sztu check --json`.
2. Use committed `data/generated/knowledge/` for the reproducible public dataset, or run `digital-sztu export-knowledge --output .work/knowledge/export --json` for a local copy.
3. Preserve `chunk_id` as the logical identity and use `revision_id` to decide whether a chunk needs re-embedding.
4. Require every retrieved Claim to remain traceable to Event ID, Claim ID, Source ID, and locator. Similarity is discovery, not evidence.
5. Keep provider-specific embeddings in `.work/knowledge/<dataset-revision>/<model-id>/` and validate revision matches before loading.
6. Do not add provider SDKs, send content over the network, read API keys, or write to a remote vector database unless the user explicitly requests and scopes that integration.
7. Never export objects with `privacy.indexing: exclude` or `privacy.risk: prohibited`.

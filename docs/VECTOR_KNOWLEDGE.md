# 向量知识库适配

## 目标

`digital-sztu build` 与 `digital-sztu export-knowledge` 把 Event、Node、Collection 与 Source 生成供应商无关 JSONL。它可供全文搜索、RAG、图检索或任意向量数据库消费，但核心仓库不依赖远程服务、模型或 API key。

```text
data/generated/knowledge/chunks.jsonl
data/generated/knowledge/manifest.json
```

## Chunk

v0.1 导出：

- Event summary
- 每个 Event Claim
- Node metadata
- Collection summary
- Source metadata

每个 chunk 包含稳定 `chunk_id`、内容 `revision_id`、适用于其类型的时间、史体、核查状态、Claim/Citation 与带 Claim／Source／locator 的关系。Event summary、Node、Collection 与 Source metadata 可携带自动生成的 incoming backlinks；Claim chunk 则只保留属于当前 Claim 的证据关系。Source chunk 还保留公开 locator、hash、access、rights 与 reliability，因此独立 JSONL 消费者无需猜测来源位置。

`evidence_role` 明确区分 `claim-evidence`、`navigation`、`directory-metadata` 与 `source-metadata`。Event summary 聚合其 Claim IDs 与 Citations，但仍是导航摘要；事实回答应落回 Claim chunk。Claim chunk 只携带绑定当前 Claim 的 Citation 与语义关系，不继承同一 Event 中其他 Claim 的对象关联。

长 Markdown 暂不按容易漂移的段落序号切块；未来用显式锚点扩展。

## Embedding sidecar

embedding 默认写入：

```text
.work/knowledge/<dataset-revision>/<model-id>/embeddings.jsonl
```

每行通过 `chunk_id + revision_id` 连接公开 chunk。Revision 不匹配时拒绝加载。模型、维度和向量不进入 canonical Event，也不由 build 联网生成。

## 核查边界

向量相似度只发现候选。任何新 Event 或回答都必须回到 `event_id`、`claim_id`、Citation locator 与 Source。`privacy.indexing: exclude` 和 `privacy.risk: prohibited` 的对象不会进入公共知识 JSONL。

## v0.2 扩展

Knowledge Record 与 Event 共用证据结构，作为 `owner_type: knowledge` 进入知识 JSONL。有效期与核验时间保留在时间元数据中，未知值不补齐。新导出格式是 `digital-sztu-knowledge-jsonl@0.2`；已有 Event 等记录的 chunk URN 保持原 `sztu-connect` 命名空间，新 Knowledge Record 使用 `digital-sztu` 命名空间。内容变动通过哈希识别，不因项目更名改变已有稳定 ID。

导出与图谱、SVG、Markdown 阅读页使用同一公开投影和内容版本。`indexing: exclude`、受限处理和禁止公开的内容不会进入这份导出；原始材料的保存方式与检索输入分别管理。

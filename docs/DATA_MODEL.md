# 数据模型

## 事件与持续性知识

发生在某个时间的事使用 Event；项目资料、课程资源与持续性校园信息使用 Knowledge Record。Agent 从来源中整理时间或有效期、论断和关系，查找或创建相关目录 Node，再由构建器生成反向链接和目录索引。正文不会复制到目录节点。

```text
Source ──> Claim ──> Event ──> Node / Event
                              │
                              └─ build ──> Backlinks + Directories
```

## Event

```json
{
  "schema_version": "0.1.0",
  "id": "event-example-structure",
  "type": "event",
  "title": "结构示例",
  "status": "source-backed",
  "time": {
    "kind": "point",
    "start": "2024-09",
    "end": null,
    "precision": "month",
    "certainty": "exact",
    "timezone": "Asia/Shanghai",
    "original_text": "2024 年 9 月"
  },
  "summary": "这是结构示例，不代表真实校园事件。",
  "claims": [],
  "links": [],
  "privacy": {
    "risk": "none",
    "handling": "as-recorded",
    "indexing": "include"
  },
  "provenance": {
    "created_by": "human",
    "created_at": "2026-09-02T00:00:00Z",
    "input_hashes": []
  },
  "narrative": "index.md"
}
```

路径是 `content/events/<start-year|undated>/<event-id>/event.json`。若设置 `narrative`，文件必须与 Event JSON 同目录。

## Time：事件的必填坐标

时间是 Event 的属性，不是项目核心对象。

```text
kind       point | range | before | after | unknown
precision  day | month | year | unknown
certainty  exact | approximate | unknown
start/end  YYYY | YYYY-MM | YYYY-MM-DD | null
```

- `point` 只有 `start`；`range` 同时有 `start` 与 `end`。
- `before` 只有 `end`；`after` 只有 `start`。
- `unknown` 没有端点，精度和确定性均为 `unknown`。
- 不为排序补造日期；`2024-09` 不得改成 `2024-09-01`。
- `precision` 表示来源实际给出的年月日粒度；`certainty` 表示证据对事件时间的确定程度，不是 Agent 的抽取置信度。
- 只有日期而没有时刻时不强制填写 `timezone`；缺失就保持 `null`，不得为了通过校验补造时区。
- `original_text` 保留来源的原始时间表达，例如“约 2024 年秋”，便于复核标准化结果。

## Claim 与 Citation

每个事实在 Claim 层核查：

```json
{
  "id": "claim-example-purpose",
  "text": "此事件仅演示字段结构。",
  "kind": "fact",
  "certainty": "high",
  "citations": [
    {
      "source_id": "source-example-documentation",
      "role": "supports",
      "locator": "README: examples/minimal",
      "note": "仓库内说明"
    }
  ]
}
```

Citation `role` 为 `supports`、`contradicts` 或 `context`。Locator 可写页码、章节、网页锚点、消息 ID 或音视频时间码。`fact` 与 `allegation` 至少一项 `supports`。

## Event Link

```json
{
  "relation": "involves",
  "target_id": "person-example",
  "claim_ids": ["claim-example-purpose"],
  "source_ids": ["source-example-documentation"],
  "note": "关系由所引来源说明"
}
```

`target_id` 可指向另一个 Event，或人物、组织、地点、制度、主题 Node。每条语义 Link 必须绑定至少一个 Claim 和一个 Source，且所列 Source 必须确实出现在对应 Claim 的 Citation 中。关系只写在发出它的 Event；构建器为目标生成 incoming backlink。这样实现双向可达而不手工维护两份事实。没有证据、只用于导航的关联应写成 Markdown wikilink，而不是空证据 Link。

v0.1 推荐关系词为 `involves`、`held-by`、`occurs-at`、`changes`、`about`、`follows`、`corrects`、`supersedes`、`disputes`、`related-to`。确需扩展时使用能从 Event 指向目标理解的 kebab-case 动词，并在同类关系中保持一致。

## Node：相关目录

Node 只保存稳定 ID、名称、别名、简短说明与说明本身的来源：

```text
content/nodes/people/person-*.json
content/nodes/organizations/org-*.json
content/nodes/places/place-*.json
content/nodes/institutions/institution-*.json
content/nodes/topics/topic-*.json
```

新 Event 提到的对象若已存在，Agent 复用其 ID；若不存在，可创建 `status: stub` 的最小 Node。Node 不保存 Node→Node 历史事实关系，也不手写 `event_ids`；事实关系属于 Event，相关事件由 `data/generated/directories/*.json` 与 `backlinks.json` 自动列出。Node 的非空 `summary` 必须有 `source_ids`。

ID 使用稳定的小写 kebab-case，不把可变显示名或数组序号当作身份。同一事件可优先使用“主题短名＋最精确已知时间”；发生碰撞时增加可核查的地点／组织限定或短内容摘要，不覆盖既有 ID。身份不确定的同名 Node 保持分开，并把原始名称放入 `aliases`。

## Markdown wikilink

Event 叙事可以使用：

```markdown
[[person-example|某人物]]
[[event-related-example|相关事件]]
```

构建器校验目标存在，并以 `wikilink` 关系生成 backlink。Wikilink 用于导航；可核查的事实关系仍放在 Event JSON Link 中并绑定 Claim/Source。

## Collection

Collection 用 `event_ids` 和 `focus_ids` 组织多种史体，不复制事件事实。`chronological` 顺序由 Event 时间生成，`curated` 顺序保留作者排列。

## Source

Source 记录标题、类型、locator、日期、哈希、公开方式、权利与独立性。来源可以是 `metadata-only`；权利未知不阻止记录来源存在，但不能据此复制原件。

## v0.2：Knowledge Record

项目资料、课程资源和持续性校园信息使用 `content/knowledge/<knowledge-id>/record.json`。它与 Event 共用 Claim、Citation、Link、privacy 和 provenance；不为了满足事件时间而把“读取日期”或“GitHub 创建日期”当作事件发生日期。

必填 `type: knowledge`、`schema_version: 0.2.0`、稳定 `knowledge-*` ID、`category` 和 `external_ids`。其余标题、摘要、论断、正文与 Event 一致。`external_ids` 用来源稳定身份防止重复导入，例如 `github-repo:123`，不是会变化的登录名。

```json
{
  "validity": {
    "start": null,
    "end": null,
    "state": "unknown",
    "verified_at": null
  },
  "external_ids": ["github-repo:123"],
  "research_origin": {"run_id": "batch-id", "entity_id": "github-repo:123"}
}
```

有效期 `start`／`end` 允许年、月、日精度或 `null`，不得补全未知的月日。`verified_at` 是核验时间，允许为空。`state` 为 `current`、`superseded` 或 `unknown`；可通过 `superseded_by` 指向另一条知识档案，但不改写旧记录或静默丢弃反证。

Event 和 Knowledge Record 可彼此引用，也可引用 Node；正向关系仍只写一次。Collection 允许 `event_ids` 与 `knowledge_ids`，合计至少一条记录。所有关系生成对应反向链接。v0.1 Event／Node／Source／Collection 继续可读；历史 ID 和第三方存档不会因为包名迁移改变。

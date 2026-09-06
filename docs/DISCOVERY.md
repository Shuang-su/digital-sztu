# 校园来源普查

来源普查是一项证据研究，不是公开档案。`discover-campus-sources` 共用 Skill 负责阅读、范围判断与复核；`digital-sztu discover` 负责可恢复的执行和输出。

## 开始与恢复

需要已安装的 GitHub CLI `gh` 及正常授权，使用公开只读 REST 请求与批量 GraphQL 查询，不读取令牌内容。无 GitHub 授权不影响已有正式档案的本地构建。

```bash
digital-sztu discover init --json
digital-sztu discover seed --name owner/repository --json
digital-sztu discover resume --limit 100 --progress --json
digital-sztu discover status --json
```

恢复旧版状态时，在尚未初始化的新研究目录中执行：

```bash
digital-sztu discover init --legacy-state /path/to/old/state.json --json
```

旧状态仅被读取，导入记录其 SHA-256 与字节数，保留原批次 ID、队列状态、发现路径、分页游标与历史审计引用。默认数据库是 `.work/discovery/state.sqlite3`，`--database .work/another-run/state.sqlite3` 可独立运行另一个范围。没有固定机器路径或默认历史批次。

`--limit` 是单次操作数量，不是调查完成条件。`--progress` 每隔约两秒在标准错误输出已提交进度 JSONL；标准输出仍只有最终 JSON 文档。进度包含本批完成增量、新增操作、剩余操作、证据复核积压和限流恢复时间，不提供固定总量百分比。Ctrl+C 返回退出码 130 和恢复命令；磁盘不足返回明确错误，保留已提交页，未提交页从原游标重放。

状态和单条检查以只读模式打开数据库。索引以事务安装，保留旧 JSON 行；SQLite 排序使用连接内存，GitHub 子进程临时文件使用数据库旁的 `tmp/`，不依赖系统盘临时目录。研究写入前检查数据库所在卷至少保留 256 MiB 空间；`digital-sztu doctor --json` 可检查当前虚拟环境、工作区指针及存储位置。

REST 分页按最多五页的公平执行片段提交，GraphQL 列表按逐页批次提交，未读页保持在队列中。每页新增实体、关系与下一页游标在 SQLite 同一事务中提交；未提交页中断后重新读取。profile 查询按最多 50 个账号合并为一次只读 GraphQL 请求，逐项核对数字 ID；改名或旧登录名被复用时回到数字 ID 查询。仓库、星标和关注列表也支持自适应批量查询；出现资源限制时缩小同类批次。已开始的 REST 列表继续原分页，不切换到 GraphQL 游标。只有与查询范围一致的确切零计数可以完成尚未开始的空列表任务；拥有仓库数为零不能代表全部公开参与仓库为空，已有分页断点不以计数替代。REST 与 GraphQL 各自保留额度，服务级退避对两者同时生效。所有限流与错误保留状态，不通过换账号或继续限流请求推进。

对经公开证据复核的工具／自动署名账号，可在 `discover review` 条目中设置 `expansion_exclusion: "tool-attribution-account"`；只对账号生效，必须附原因和来源定位。它停止该账号尚未完成的 following/followers 扩展，记录原状态与停止原因，保留原游标、已读页、贡献边以及所有已发现的下游候选和队列。已经完成的列表不改写；再次遇到账号或改名不解除排除。不能仅凭用户名、GitHub User 类型或贡献者映射判定校园真人身份。

账号和仓库使用 GitHub 数字 ID，名字改变不会创建另一对象。账号列表前刷新数字身份，避免把旧登录名的新持有人当作原账号。

README 的批量读取先检查数字身份与公开状态，再从固定默认分支提交选择文件，最后核对完整 UTF-8 字节数和 Git blob 哈希。按 [GitHub 的 README 规则](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes)中 `.github`、根目录、`docs` 的优先顺序处理无歧义的常见文本文件；多版本、特殊格式或不能完整验证的正文转回 REST，仍须人工判定校园关联。数字 ID 形式的旧 REST 分页链接也要与任务实体一致，才可保留原页码恢复。

批次缩小到一个账号后，如果仍遇到列表查询超时，可以继续缩小单页数量，最少每页 10 项；游标、已读页和累计数量保持不变。限流响应不采用此重试路径，仍保存服务端退避边界。

## 证据复核

```bash
digital-sztu discover inspect --id github-repo:123 --json
digital-sztu discover review --file .work/reviews.json --json
```

`inspect` 的 `review_context` 同时列出相关操作、README 原文定位、已有校园证据、fork 上游、增量范围说明和替代证据缺口；不会自动给出确认结论。

复核文件是数组，每项至少包含 `id`、`verification_status`、`relevance_reason`。确认项还需 `evidence` 数组，每条证据包含公开 `url`、`locator`、`accessed_at`；可补短摘录、原文哈希与证据说明。不要仅凭关键词或账号学校简介把个人仓库认定为校园项目。复核后仍为 `candidate` 时，操作保持 `scoped-review-required` 并阻止入库；不会因为写过一次复核意见就视为已解决。旧版误标完成的候选复核会在恢复时一次性重新排队，并保留审计记录。

明确与校园直接相关的项目、课程作业、校园适配部分可以入选；仅有作者学校关联、通用收藏或无关上游项目不据此入选。fork 和大型上游仓库使用 `scoped-contributors-review`：先核对校园增量 diff／commit，再用 `campus_contributors` 提供可映射账号；必须附 `contributor_scope_reason` 和对应证据，不扩展全部上游贡献者。

README 缺失时，核查相关源文件、文档或官方页面。在说明替代证据后，可以用 `resolves_missing_readme: true` 完成人工复核；来源不可访问时保留明确限制，不通过假造完成状态清空队列。

对于站外材料，用现有网络搜索与只读浏览工具发现和阅读，再把候选登记到同一台账：

```bash
digital-sztu discover external --file .work/external-candidates.json --json
```

候选文件是 `[{"title": "来源标题", "url": "https://example.org/page"}]`，后续仍需要证据复核。工具不会执行所发现项目的代码、宏或安装脚本。

## 桥接与完成条件

确认校园锚点 A 可以发现未知 B，B 可以再发现一层 C；未知 C 的公开资料、仓库和星标可以筛查，不能继续向外扩展社交关系，除非另有独立校园证据。关注和星标只表示所观察到的动作，不证明身份、成员资格、项目作者或学校背书。

全部规则内可执行队列、必要分页与缺失来源复核完成后，再进行定向补漏：

```bash
digital-sztu discover sweep --file .work/targeted-queries.json --json
digital-sztu discover resume --limit 100 --json
# 阅读、复核全部新增候选后：
digital-sztu discover sweep --complete --json
```

查询文件是明确的 GitHub 仓库搜索字符串数组。根据学校名称变体、课程、主题和已知缺口制定查询，并同步复核站外引用。出现新相关项目会重置连续无新增轮数；需要连续两轮无新增。搜索截断、未完成页或未读候选不能视为“无新增”。受限访问可以作为完成报告中的限制，但不能伪装成已读或无关。

## 导出与正式入库

`discover export` 在数据库旁生成 `export/`，保留 `sources.jsonl`、`operations.jsonl`、`edges.jsonl`、`audit.jsonl`、`graph.json`、`status.json` 和 `report.md`。研究图谱不会发布到 README 或 Pages；包括大文件在内的交付需要逐项扫描与检查。

仅当 `status` 返回 `promotion_ready: true` 时允许入库。输入格式：

```json
{
  "records": [
    {"data": {"id": "knowledge-example", "type": "knowledge"}, "markdown": "可选正文"}
  ],
  "mappings": [
    {"run_id": "当前批次 ID", "entity_id": "github-repo:123", "record_ids": ["knowledge-example"]}
  ]
}
```

示例省略了正式记录的必填字段，实际输入需完整通过 Schema 和引用校验。Source、Knowledge Record 以及有证据的 Event／Node／Collection 均明确列入 `records`，每条都有研究映射。不能由账号关系自动生成真实人物或历史事件。

```bash
digital-sztu discover promote --file .work/promotion.json --json
digital-sztu check --json
```

入库先在隔离目录验证全部新旧引用和公开投影，然后写入带恢复日志的事务。异常会移除本次新建文件；突然中断后，下次 CLI 调用先恢复未完成事务。已有不同内容不会被覆盖，相同输入重复运行不会创建重复记录。成功映射保存在研究数据库；正式记录本身保留 `research_origin`、`external_ids`、provenance 和引用定位。

增量贡献者复核允许先于仓库元数据刷新提交；明确提供 `campus_contributors` 后会保存该项复核完成状态，后续刷新或中断恢复不重新生成同一待办。没有明确提交增量复核的 fork 仍保留待核任务。

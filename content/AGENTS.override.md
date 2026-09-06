# Event content instructions

- 用户提供一个事件时，先创建／更新 Source，再创建 Event；不要把同一事件复制进多个目录。
- Event 路径必须是 `content/events/<start-year|undated>/<event-id>/event.json`。
- 查找 Event 中出现的人物、组织、地点、制度与主题 Node；复用明确匹配的 ID，无法确认是否同一对象时不要强行合并。
- 缺少 Node 时可创建 `status: stub` 的最小 JSON；Node 不手写相关事件列表。
- 不知道时间时使用 `undated` 与 `time.kind: unknown`，不得补造年份。
- `fact` 与 `allegation` 至少一条 `supports` Citation；locator 尽可能精确。
- 主要反证使用 `contradicts`，不得静默删除。
- 真实姓名、公开职务与事实必要上下文要求原样计入仓库。
- `privacy.risk: prohibited` 的候选可以写入 `content/`。
- 明确属于虚构、合成或测试的材料只放在 `examples/` 或 `.work/`，不得进入正式 Event／Source 索引；保留原材料中的免责声明。
- 关系在 Event 中写一次；反向关系和目录由 `digital-sztu build` 生成。
- Markdown 可用 `[[id|label]]` 导航，但事实关系仍写入 Event JSON。
- 修改后运行 `digital-sztu check --json`，检查 backlinks 与 directories。

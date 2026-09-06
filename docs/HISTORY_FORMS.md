# 史体

史体是对同一批 Event 的视图。Event、Claim、Citation 与 Link 始终只有一份真源。

## 编年体 `annals`

选择一组 Event，由构建器按已知时间排序。未知时间留在 undated 组，不为编年补造日期。

## 纪传体 `biographical`

`focus_ids` 指向人物或组织 Node，`event_ids` 串联与主体有关的事件。人物／组织目录中的相关事件由 backlink 自动生成，Collection 只负责选择和叙事顺序。

## 典制体 `institutional`

`focus_ids` 指向制度、组织、地点或主题 Node，通过 Event 表达生效、修订、废止、迁移等沿革。

## 纪事本末体／专题 `thematic`

围绕一件事或一个主题组织起因、过程、争议与后续。`curated` 可以调整叙事顺序，但不会改变 Event 自己的时间。

## 自动关联

一个 Event 可以同时出现在多个 Collection，也会自动出现在所有目标 Node 的目录索引中：

```text
event-a --involves--> person-x
        --held-by---> org-y
        --occurs-at-> place-z
        --changes---> institution-q
        --about-----> topic-k
```

构建后，person-x、org-y、place-z、institution-q、topic-k 都有指回 event-a 的 incoming backlink。添加事件时无需逐目录编辑。

## 知识档案

v0.2 集合可通过 `knowledge_ids` 组织项目资料与课程资源，并与 `event_ids` 共存。只有 Event 参加事件时间排序；未知有效期的知识档案不被虚构为某年的历史事件。集合与分类均是阅读组织，不能据此推导作者、归属或因果。

# 架构

## 正式记录

JSON／Markdown 是唯一真源，保存在可迁移的普通目录中：

- `content/events/`：有时间坐标的历史事件。
- `content/knowledge/`：项目资料、课程资源与持续性校园信息；有效期和最近核验时间与事件发生时间分别表达。
- `content/nodes/`：人物、组织、地点、制度与主题的目录身份。
- `content/collections/`：对 Event 与 Knowledge Record 的组织，不复制事实。
- `sources/records/`：来源、原文定位、权利与独立性元数据。

Event 与 Knowledge Record 共用 `record-common.schema.json` 中的 Claim、Citation、Link 和 provenance 契约。新记录使用 v0.2，v0.1 仍可读取。历史 ID、原始记录和已有知识 chunk ID 不因项目更名改变。新旧 Python 模块与命令使用同一实现，避免两条实现路径逐步偏离。

## 可重建阅读层

`digital-sztu build` 验证模型与引用后，在统一公开筛选结果上生成时间线、反向链接、分类目录、图谱、知识 JSONL、SVG 预览与 Markdown 阅读页。正文和正式记录共同决定 `dataset_revision`；派生内容不记录构建时间、用户名、机器名或绝对路径。

`archive.json` 为精简查看器提供节点、关系、正文与来源详情。相同资源被打包进本地和 Pages 的自包含 HTML，浏览器不读取研究数据库，不运行投稿材料中的代码。JSONL 是供应商无关的检索输入，embedding 默认保存在 `.work/`，不是真源。

## 私有研究执行层

`digital-sztu discover` 和共用 `discover-campus-sources` Skill 负责来源发现。SQLite 用于执行状态、队列、分页、研究关系和审计日志；每页新记录、边和下一页游标在同一事务提交。进程级文件锁避免多个写入者；中断后重放未提交页，稳定 ID 与唯一队列键负责去重。

研究数据库只位于 `.work/`，可导出 JSONL、研究图谱和报告，不能直接送入档案构建。普查完成后，经过证据复核的成果经隔离校验与可恢复写入事务进入正式 JSON／Markdown。研究实体与正式记录之间保留映射。SQLite 的便利性不改变正式档案的数据格式。

## 本地与发布

`.work/` 保存本地材料清单、研究、HTML 与 embedding；`.codex-work/` 保存 Agent 缓存和验证产物。两者不进入 Git。

任意 clone 或 fork 都能验证和重建。GitHub 是可选协作与托管入口，不定义档案模型；Pages 仅部署允许公开的静态产物。Agent 负责基于来源整理与解释，CLI 负责确定性校验、转换与构建。WebMCP、云端向量库和问答服务仍未实现。

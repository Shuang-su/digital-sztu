# 执行记录

工程和研究为不同交付阶段。本记录持续更新，不代表完整普查或 v0.2 已发布。

## 环境与已完成验证

- 4 个移动后的既有工作区已由 git worktree repair 修复，无 worktree prune、历史重写或研究记录删除。
- 主目录、命名工作区、升级工作区的虚拟环境保留备份后重建；依赖按 requirements.lock 安装。独立主分支工程修复工作区使用新的本地环境。
- 系统卷剩余空间在检查期间不足 1 GiB，首次完整测试被新增 256 MiB 研究写入预检阻止；改用项目卷测试暂存后通过。未执行系统盘清理。
- 真实研究状态制作 SQLite 一致性备份，integrity_check 为 ok；副本和真实索引迁移前后 records、ops、edges、audit、meta 的行数及整体 SHA-256 均一致。副本索引迁移约 0.47 秒，状态查询约 0.11 秒；这是本机单次测量，不代表网络研究吞吐提升倍数。
- 升级分支测试 196 项通过（2 项默认跳过）；独立主分支修复测试 124 项通过（2 项默认跳过）。测试临时目录显式设在项目卷。
- 新测试覆盖索引失败回滚、过滤保留其他任务、中断后的已提交页与元数据、空间不足无错误二次写入、stderr 进度与单份 stdout JSON、只读状态不迁移、缺失来源提示、移动环境诊断，以及超过 8 MiB 文件尾部凭据检查。
- 旧第三方归档离线哈希和目录树校验通过，无网络或上游代码执行。
- 两个分支的 check 与两次构建确定性通过；严格扫描没有阻断项。正式内容仍为零，不能把空图构建通过描述成真实内容发布验收。

## 待完成

- 保存本阶段 checkpoint、服务端 PR/CI/合并核验。
- 持续执行规则内普查、原文与校园增量复核、连续两轮定向补漏。
- 达到 promotion_ready 后正式入库，完成真实三种视图、本地及线上浏览和来源跳转核验，再合并完整 v0.2、发布 Pages。

## 主分支工程检查点与审查修复

- 已推送检查点 35a90ba07038571a009ad9132ee4c0b7ecfc7667，创建 PR #6。该检查点的 Linux check、macOS 与 Windows 初始化 CI 均成功。
- 自动审查提出明文密钥/配置扩展名漏扫与 URL fragment 认证参数漏检，均已补充修复。未知扩展名先以有限 UTF-8 样本识别文本；普通节标题锚点仍允许。
- 修复后 127 项单元测试通过（2 项默认平台集成跳过）；严格扫描、公开正式记录检查与 check 通过。等待更新后 CI，再进行合并核验。

- 后续审查的两项问题也已修复：公开投影按完整 wikilink ID 匹配排除项，避免短 ID 错误排除长 ID；环境诊断单测隔离磁盘空间条件。新增回归后 128 项测试通过（2 项默认平台集成跳过）。

## 公开导出后续修复检查点

- PR #6 已合并，主分支 b95971c9dfe477e94a3a5179bd4750da81d9131e 的 CI 成功。合并后到达的审查继续在独立分支 codex/public-export-hardening 处理。
- 补齐加密/DSA/PGP 私钥标头和云存储签名 URL 参数检查；主分支 build 与 export-knowledge 共用公开投影。修正旧测试中要求导出禁止索引记录的过期预期，增加真源保持不变验证。
- 131 项单元测试通过（2 项默认跳过），check 通过；尚未推送或合并本次后续修复。
- 本次用户询问普查是否完成：实时状态仍为 partial、promotion_ready=false；已完成 25,304 个操作，pending 57,142，未完成分页 453，两轮无新增补漏尚为 0。这些是当时快照，不能当成项目数量或固定完成百分比。

## JSON 转义扫描与研究快照核验

- 最新私有研究快照 7 个文件，共 207,631,637 字节，已完整流式扫描，JSONL 字段另行解码检查。sources.jsonl 在既有上游 README 的配置示例中发现 2 处编号式密码占位命中，逐项核验为示例，未观察到可用真实凭据；原研究资料保持不变，不将其描述为零模式命中或作为正式摘录。
- 该核验暴露仅扫描序列化 JSON 会漏掉字符串内带引号的赋值。正式记录公开检查现同时检查解码字段；JSON/JSONL 隐私扫描逐行解码字符串 token，覆盖嵌套示例和 Unicode 转义字段名，不因大文件加载上限跳过。报告不回显值，并合并原文/解码视图同一行同类型的重复提示。
- 新增真实漏检形式的回归验证：带引号的赋值在公开投影中被排除、public-check 阻断，JSON 与 JSONL 的嵌套转义及 Unicode 字段名由严格扫描阻断。133 项单元测试通过（2 项默认跳过）。本修复作为独立工程更新，不提前入库或发布档案图谱。

### PR #9 review follow-up

- Fixed nested JSON string inspection with eight bounded decoding passes; original and intermediate views remain available to credential and advisory matching.
- Unicode-escaped advisory information now shares decoded scanning and per-line deduplication; advisory findings remain nonblocking.
- Main-compatible suite: 135 tests passed (2 skipped). Nested canonical record exclusion and JSON stream blocking were exercised with synthetic values; outputs do not echo them.

- Boundary review: reserve an additional decoding pass for the enclosing JSON field; regression now exercises exactly eight nested wrappers as well as depths two and four.

### Continuation: independent decoding views

- Latest user request: 继续。 Survey and two no-new rounds still precede archive promotion and Pages.
- Addressed review 3943509907: credential and advisory patterns now match each decoding view independently. Public record inspection preserves serialized field boundaries, avoiding cross-view or cross-field synthetic matches.
- Added harmless scalar and canonical-record regression; nested credential and Unicode advisory coverage remains.

- Independent-view main-compatible regression suite: 136 tests successful, 2 skipped.

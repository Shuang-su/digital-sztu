# 执行记录

工程和研究为不同交付阶段。本记录持续更新，不代表完整普查或 v0.2 已发布。

## 环境与已完成验证

- 4 个移动后的既有工作区已由 git worktree repair 修复，无 worktree prune、历史重写或研究记录删除。
- 主目录、命名工作区、升级工作区的虚拟环境保留备份后重建；依赖按 requirements.lock 安装。独立主分支工程修复工作区使用新的本地环境。
- 系统卷剩余空间在检查期间不足 1 GiB，首次完整测试被新增 256 MiB 研究写入预检阻止；改用项目卷测试暂存后通过。未执行系统盘清理。
- 真实研究状态制作 SQLite 一致性备份，integrity_check 为 ok；副本和真实索引迁移前后 records、ops、edges、audit、meta 的行数及整体 SHA-256 均一致。副本索引迁移约 0.47 秒，状态查询约 0.11 秒；这是本机单次测量，不代表网络研究吞吐提升倍数。
- 升级分支测试 203 项通过（2 项默认跳过）；独立主分支修复最初 124 项、审查修复后 128 项通过（2 项默认跳过）。测试临时目录显式设在项目卷。
- 新测试覆盖索引失败回滚、过滤保留其他任务、中断后的已提交页与元数据、空间不足无错误二次写入、stderr 进度与单份 stdout JSON、只读状态不迁移、缺失来源提示、移动环境诊断，以及超过 8 MiB 文件尾部凭据检查。
- 旧第三方归档离线哈希和目录树校验通过，无网络或上游代码执行。
- 两个分支的 check 与两次构建确定性通过；严格扫描没有阻断项。正式内容仍为零，不能把空图构建通过描述成真实内容发布验收。

## 待完成

- 独立工程 PR #6 已合并，主分支为 b95971c9dfe477e94a3a5179bd4750da81d9131e。完整 v0.2 保持草稿 PR #7。
- 持续执行规则内普查、原文与校园增量复核、连续两轮定向补漏。
- 达到 promotion_ready 后正式入库，完成真实三种视图、本地及线上浏览和来源跳转核验，再合并完整 v0.2、发布 Pages。

## 当前研究状态

8 个旧批次输入再次逐个核对 SHA-256，全部不变。目录修复后的研究执行已恢复；上一个执行片段新增完成 268 项操作，新发现保留了 1,079 项操作。收到继续指令后从已提交断点重放，未将没有最终输出的执行片段记为完成。

## 真实恢复与证据复核

- 对本任务的研究进程发送 SIGINT，退出码 130，最终标准输出为有效 JSON；恢复命令包含当前绝对 root 和 database。已提交页保留，后续 integrity_check 为 ok。
- 完整读取 5 份固定提交 README 并核对 Git blob 哈希；1 个项目以作者自述的校园用途确认，4 个保留具体证据缺口。补读 MyCOS 源码只作文本核查，不执行脚本、不推断实际效果或学校授权。
- 发现 2 条旧候选记录仍为 candidate，但关联复核操作被旧实现标记 complete。修复 review 的状态转移并增加一次性审计迁移；不能通过未决复核制造完成。新增复核项继续处于 scoped-review-required。
- 私有证据、研究图谱和队列保持在 .work；公开交付不包含它们。全部正式记录仍待完成普查后入库。

## 同步审查修复

PR #6 的明文密钥/配置漏扫、URL fragment 认证参数、wikilink 前缀误匹配和诊断测试空间依赖均同步到升级分支。实际执行中恢复了两条历史未决候选复核，6 条 scoped-review-required 保持阻止入库；没有把它们标为无关或丢弃。

## 服务端核验与派生交付检查

- PR #6 合并时间：2026-09-06T07:43:09Z；最终代码 3f5923e 的 Linux、macOS、Windows 和 Bugbot 检查全部成功。本地主目录已快进至服务端 main，新旧命令检查通过，工作区干净。
- 升级检查点 6af67932f9759d0cc94a35f36539a083793673ca 已推送，草稿 PR #7 的 Linux、macOS、Windows 检查全部通过；Pages 构建和部署按条件跳过。
- 私有研究导出 7 个文件，共 178,404,842 字节，逐行检查无凭据模式命中；8 个旧批次输入哈希不变。研究与正式档案继续分开。
- 合并主分支时保留 v0.2 的 CLI、图谱公开边界说明和更新后的工程记录；所有生产源文件修复均已在升级分支存在。
- PR #6 合并后到达的后续审查提出额外 PEM 形式、云签名 URL 和 v0.1 派生投影问题，作为后续独立修复处理，不能把此前检查通过表述为已覆盖所有格式。

## 同步后续公开检查修复

- 保留 v0.2 现有构建投影，补齐私钥标头和云存储签名参数检查，并增加投影/导出回归。206 项单元测试通过（2 项默认跳过）。
- 普查实时快照仍为 partial，pending 57,142，未完成分页 453，补漏轮次 0；当前 resume 进程仍在推进。尚未正式入库或发布图谱。

## PR #8 工程合并与新一批证据复核

- 后续公开导出修复 PR #8 已正常合并，主分支为 d858c736c3f4bd9414c2e58da8262d3fab7ba58b；PR 最终 head 2b216337b183dd3fdff3266a4191ea869aff66d2 的 Linux、macOS、Windows 与 Bugbot 检查均成功。升级分支同步修复，保留 v0.2 内容版本计算与多形式图谱构建。
- 用户再次确认按普查、两轮补漏、正式入库、图谱发布顺序执行。新批 33 条原文复核写入后逐条回读通过：17 条确认或复确认（净新增 5 个确认实体）、7 条有依据的范围排除、9 条仍为候选并保留补证要求。另将简介里的成绩预览工具链接作为独立研究来源保留，记录公开 API 404 访问缺口。
- 本批复核使用固定提交及 Git blob 字节/哈希验证；缓存中经既有流程脱敏的两份 README 明确不作为原始字节副本。私有复核目录初次 19 个 JSON 文件共 1,102,240 字节逐项扫描，无凭据模式命中；该目录不作为公开档案提交。后续派生关系检查仍在添加材料。
- 真实工作进程经 SIGINT 返回 130，33 条复核成功保存后 SQLite integrity_check 为 ok；研究已从保存的分页断点恢复。阶段快照为 completed 26,037、pending 61,477、missing 337、unfinished pagination 858、no-new rounds 0，promotion_ready 仍为 false。不得把本工程合并视为普查、正式入库或 Pages 已完成。

## 阶段复核、缺失材料与恢复执行

- 在 33 条原文复核后，补充 1 条访问缺口、4 条代码派生关系复核和 6 条缺失 README 的替代证据复核，累计 44 条写入、40 个不同研究实体；最终意见已从 SQLite 回读，6 个缺失操作均带有 alternative evidence reviewed 解决记录。
- 核心脚本对照验证原始字节：三个成绩提醒仓库 blob 完全相同，第四个仅 CRLF/LF 不同。保留工作流差异，尚不认定原创者，也不计成四个独立校园项目。
- README 批次正常返回 processed=200：41 个成功读取、159 个转入缺失材料复核，没有通过自动排除清空候选。随后从已提交状态继续执行完整操作队列。
- 44 个私有 JSON/JSONL 研究产物共 1,619,126 字节完成原文和解码字符串扫描，无凭据模式命中；另检查阶段 Markdown 报告并加入哈希清单。8 个旧批次输入再次流式哈希验证，全部保持不变。研究产物和账号关系不提交为正式档案。
- check、public-check、严格扫描成功，20 个派生文件连续构建一致；合并同步后的 206 项单元测试通过（2 项默认跳过），checkpoint 0b0a1f057a5e771fb0b728ed1e42cdfa8596665c 的 Linux/macOS/Windows CI 均成功。无正式内容，不能以此代替真实图谱验收。
- Issue #2 阶段进展已回写并从服务端比对全文：https://github.com/Shuang-su/digital-sztu/issues/2#issuecomment-5558059856 。PR #6 的三项晚到审查回复也已从服务端核对；修复由已合并 PR #8 交付。
- 阶段快照：completed 26,244、pending 64,132、missing 495、unfinished pagination 892。普查仍 partial、promotion_ready=false、两轮无新增补漏 0/2；仍未正式入库或发布 Pages。

## JSON 转义扫描与研究快照核验

- 最新私有研究快照 7 个文件，共 207,631,637 字节，已完整流式扫描，JSONL 字段另行解码检查。sources.jsonl 在既有上游 README 的配置示例中发现 2 处编号式密码占位命中，逐项核验为示例，未观察到可用真实凭据；原研究资料保持不变，不将其描述为零模式命中或作为正式摘录。
- 该核验暴露仅扫描序列化 JSON 会漏掉字符串内带引号的赋值。正式记录公开检查现同时检查解码字段；JSON/JSONL 隐私扫描逐行解码字符串 token，覆盖嵌套示例和 Unicode 转义字段名，不因大文件加载上限跳过。报告不回显值，并合并原文/解码视图同一行同类型的重复提示。
- 新增真实漏检形式的回归验证：带引号的赋值在公开投影中被排除、public-check 阻断，JSON 与 JSONL 的嵌套转义及 Unicode 字段名由严格扫描阻断。208 项单元测试通过（2 项默认跳过）。本修复作为独立工程更新，不提前入库或发布档案图谱。

### PR #9 review follow-up

- Fixed nested JSON string inspection with eight bounded decoding passes; original and intermediate views remain available to credential and advisory matching.
- Unicode-escaped advisory information now shares decoded scanning and per-line deduplication; advisory findings remain nonblocking.
- Main-compatible suite: 135 tests passed (2 skipped). Nested canonical record exclusion and JSON stream blocking were exercised with synthetic values; outputs do not echo them.

- Upgrade suite after review follow-up: 210 tests passed (2 skipped); check, strict privacy scan, and public-check succeeded.

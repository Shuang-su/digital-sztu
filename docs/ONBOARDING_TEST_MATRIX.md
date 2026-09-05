# 初始化验收记录

记录日期：2026-09-03。共用流程见 [上手指南](GETTING_STARTED.md)，基础初始化见 [上一阶段记录](changes/20260903-agent-first-onboarding/completion.md)，材料探索见 [本轮变更记录](changes/20260903-onboarding-first-exploration/completion.md)，远端验证见 [发布检查记录](changes/20260903-onboarding-first-exploration/publication.md)。

文档可读取、单元测试通过、核心脚本运行成功、客户端完整体验成功是不同层级的证据。只有实际记录了客户端版本、操作系统、执行模式和完整过程，才能把对应组合标为已验收。

## 核心自动化

| 环境 | 实际执行 | 结果与边界 |
|---|---|---|
| macOS 15.5（24F74），arm64；Python 3.13.5；Git 2.49.0 | 本地项目和全新隔离工作副本运行 bootstrap；安装锁定依赖；示例、重复运行、只读检查与中断恢复 | 核心流程通过，已有正式记录时也不要求清空。正式工具清单已合入并能选中本平台安装包；当前 payload 未下载、应用未安装，整体为 `pending_user`，本地核心为 `local_ready: true`。 |
| GitHub Actions Windows Server 2025，Python 3.13.15 | `windows-latest` 实际运行 38 项 bootstrap 测试与 7 项报告边界测试 | 全部通过，包括真实 junction 创建和拒绝越界；这是 Windows CI 核心验证，不是用户宿主机或客户端图形安装验收。 |
| GitHub Actions macOS，`macos-26-arm64`，Python 3.13.14 | `macos-latest` 实际运行 38 项 bootstrap 测试与 7 项报告边界测试 | bootstrap 全部通过；边界测试通过 6 项、按平台跳过 Windows junction 1 项。 |
| GitHub Actions Ubuntu 24.04，Python 3.13.15 | 内容 / 源码存档检查、117 项单元测试、构建及派生文件无差异检查 | 通过，单元测试按平台跳过 2 项。Linux 手动 CLI 路径保留；bootstrap 仍为 `not_applicable`，不宣称自动安装受支持。 |

首轮远端证据为 [PR #4 的 Checks](https://github.com/Shuang-su/digital-sztu/actions/runs/33733219921)，对应提交 `85b48d535325f13a5378699726a7e5e8fede51b6`。上述版本来自该次实际日志；后续 runner 更新不自动沿用此版本结论，最终合并状态与检查见 [PR #4](https://github.com/Shuang-su/digital-sztu/pull/4)。

自动化包含：工作副本与目录冲突、缺失 / 旧环境、固定依赖安装失败后恢复、中文及空格路径、只读模式无写入、符号链接 / junction 和输出越界、下载失败、LFS 指针、哈希错误、安装包与应用状态区分、GitHub 可选与权限路由、示例恢复及已有内容保护。

上一阶段 109 项测试通过。本轮使用 `SZTU_BOOTSTRAP_INTEGRATION=1` 运行全套 117 项测试：116 项通过，1 项需要 Windows 的真实 junction 测试在 macOS 跳过。保留真实核心环境集成、正式工具清单选择、继承环境变量的安装 / 日志输出隔离、没有回执的示例输出保护，新增文档路由和报告路径边界测试。后者实际执行指南中的 Python 检查，不用文案关键词命中代替文件系统验证。

其中一次复验在临时目录清理时受到 `.DS_Store` 残留影响；保留失败证据后，同一全套命令重跑通过，没有忽略异常或放宽初始化断言。详情见本轮完成记录。

核心集成夹具刻意不复制工具清单，验证依赖未齐时本地仍可使用；工具测试使用合成安装包和模拟网络 / 权限，不下载安装真实应用。正式 `importers/registry.json` 和两份源码存档已从 `621de40` 合入，源码离线校验通过，但这些结果不代表图形安装包已验收。

上一阶段隔离示例 `5000e42b5aa1c92f` 的聊天 HTML 已在本地浏览器预览，两条合成消息、回复标识及项目标题正常；时间线和反向链接中的示例关联、Claim 到 Source 的引用已核对。本轮规则与插件提示变化后，只调用现有示例阶段生成新的 `fe73d42d7b4923d0`，重新完成示例校验、两次构建、知识导出和聊天 HTML；没有运行真实工具下载 / 安装阶段。随后 `bootstrap --check --json` 的 `local_ready` 为 `true`，附带工具仍为 `pending_user`，不能将退出码 1 解读为核心不可用或全部安装完成。

本轮 README 经过 GitHub Markdown API 渲染及本地浏览器查看，快速开始锚点、阅读顺序与开发者折叠区正常；相对链接和章节目标另由单元测试验证。没有登录账号、访问聊天数据库或采集 Computer History。

## 首次探索的合成试跑

使用 `tests/onboarding_exploration_cases.py` 生成隔离夹具，由独立 Agent 从案例请求和工作副本的 `setup-digital-sztu` Skill 开始执行。环境、文件、消息、时间和 Computer History 状态均为合成数据；Computer Use / History 的工具响应只模拟，不连接真实客户端能力。安装与核心示例在案例中已设为就绪，真实核心流程另由上表验证。

报告路径回归覆盖中文及空格路径、检查不创建父目录、已有报告与原件不变、文件 / 父目录链接、悬空链接和工作副本外路径。Windows junction 已在上述 Windows CI 实际执行并通过；macOS 按平台跳过，不将此结果扩展为用户客户端或宿主机完整验收。

独立试跑完成 9 种场景：完整探索、仅检查、暂停下只读、授权恢复、首次启用 / 无历史、不支持、历史权限不足、报告路径链接、正常材料续读 / 文件权限不足。报告路径案例的首轮诊断仍触达目标文件元数据，修订指引后由另一位独立 Agent 复测，未再访问目标并继续在对话中完成可独立探索；共 10 次执行。

实际读取、报告、恢复与跳过结果在本轮变更记录中逐项记录，并核对合成原件哈希不变、只有授权报告新增或更新。这些行为观察不计入 117 项单元测试，也不是九种客户端的真实安装验收。真实材料探索、原生 Computer History 启用与系统授权均未执行。

## 客户端完整体验

下表的执行模式来自第一方文档核对。版本栏“未采集”表示尚未进行该组合的完整体验，不是未知版本已经通过。

| 客户端 | 客户端版本 | 操作系统 | 待验收执行模式 | 状态 |
|---|---|---|---|---|
| Claude Code | 未采集 | macOS / Windows 待实测 | 本地项目，`CLAUDE.md` 导入 | 待验证 |
| WorkBuddy | 未采集 | macOS / Windows 待实测 | 本地工作空间，Craft | 待验证 |
| Codex | 未采集完整体验版本 | macOS / Windows 待实测 | 本地项目；有 / 无项目插件两种入口 | 待验证；在 Codex 内开发和测试脚本不等于完成首次安装体验 |
| DeepSeek Harness | 未采集 | macOS / Windows 待实测 | 官方 `dsh` 本地工作区 | 实验入口，待验证 |
| Kimi Code | 未采集 | macOS / Windows 待实测 | 本地 CLI 会话 | 待验证 |
| ZCode | 未采集 | macOS / Windows 待实测 | 项目工作区任务 | 待验证 |
| Cursor | 未采集 | macOS / Windows 待实测 | 本地 Agent | 待验证 |
| TraeWork | 未采集 | macOS / Windows 待实测 | 本地任务；Windows 使用 Code 模式 | 待验证 |
| QoderWork | 未采集 | macOS / Windows 待实测 | 已授权 Working Folder，确认实际命令环境 | 待验证 |

每次实测应补齐下列证据，不仅填写一个勾：

1. 日期、客户端版本、系统版本、架构、执行模式和 checkout SHA；
2. 一句话入口能否取到指南，项目规则是否加载，能否定位用户工作副本；
3. Python / Git 与项目虚拟环境的检查和安装结果；
4. 适用工具的清单版本、实体 / SHA-256、实际安装位置、应用版本及启动结果；
5. 示例 HTML 的实际预览、时间线和来源引用、两次构建一致性；
6. Computer Use 是否真实可用、安装窗口与系统权限是否完成；与 Computer History 分别记录，不相互替代；
7. 用户授权的材料范围、候选清单与分批读取、原件保护、历史摘要与原始事件的各自覆盖范围，以及建议能否回到材料；
8. 关闭后重新打开工作副本，是否能继续使用；中断与授权交接是否可恢复；
9. GitHub 未登录时的本地成功路径，以及有明确同步请求时的分支 / Fork 路径；
10. 仍需用户操作或失败的步骤及其原因。

不要在这里填写账号凭据、完整活动流或用户原件。公开提示词中的 `main/docs/GETTING_STARTED.md` URL 必须在指南进入默认分支后另行验证；本地文件和渲染通过不能证明远端链接已发布。

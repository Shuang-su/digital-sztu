# 聊天工具存档与下载

Digital SZTU 复用现成工具取得聊天导出，再由 Agent 整理来源与候选事件。本目录保存两个固定源码快照、上游安装包入口和核验记录；不是本项目开发的微信解析器，也不会在安装插件、检查或构建时运行这些工具。

## 先选下载入口

| 用途 | 入口 | 支持边界 |
|---|---|---|
| macOS 主工具 | [CipherTalk 2026.829.0 DMG](https://github.com/mintleaf84/CipherTalk-SafeFork/releases/download/v2026.829.0/CipherTalk-2026.829.0-Setup.dmg) | Apple Silicon / arm64；不是 Intel Mac 通用包 |
| Windows 主工具 | [CipherTalk 2026.829.0 EXE](https://github.com/mintleaf84/CipherTalk-SafeFork/releases/download/v2026.829.0/CipherTalk-2026.829.0-Setup.exe) | Windows 10/11 x64；不承诺全部微信小版本 |
| Windows 历史备用 | [WeChatMsg 固定源码](wechat/wechatmsg/3.0.0-9457ecd/) | 原作者明确适配过微信 4.0.3；还含离散的 3.x 配置；不是已验证的一装即用安装包 |
| iPhone / iPad 备份路线 | [WechatExporter 官方发布页](https://github.com/BlueMatthew/WechatExporter/releases/tag/v1.9.5.13) | 未加密的本地设备备份，Windows/macOS x64；现行 iOS 和手机微信版本待验证 |

本仓库不托管 DMG / EXE，不使用 Git LFS。下载入口固定到具体版本，不使用 `latest`。上游仍可能删除或替换 Release 资产；遇到失效链接、文件大小或摘要变化，先停止使用该下载，核查来源后再更新目录，不自动换到陌生镜像。

CipherTalk 两个构建任务均成功，但日志显示跳过发布签名；整个工作流曾因额外的 R2 镜像步骤失败。它们都不能当作软件安全、已签名、微信兼容性或真实导出完整性的证明。[构建记录](https://github.com/mintleaf84/CipherTalk-SafeFork/actions/runs/33525868161)

## 下载后校验安装包

以下 SHA-256 来自 2026-09-03 读取的 [GitHub Release API](https://api.github.com/repos/mintleaf84/CipherTalk-SafeFork/releases/tags/v2026.829.0)，**不是本项目实际下载计算的结果**。本轮只检查了下载链接可达性，未保存、安装或运行安装包。

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `CipherTalk-2026.829.0-Setup.dmg` | 221408494 | `8fe684b5a022478715f7269a36358b48d9f813c4165056fba8d76b70f824d7f8` |
| `CipherTalk-2026.829.0-Setup.exe` | 162366374 | `1c01bc70b656a9032c659a826864be96bf1338df1e26a0911908f86329a33bc1` |

在保存下载文件的目录中计算摘要，再与表中对应值逐字比较：

```bash
# macOS
shasum -a 256 CipherTalk-2026.829.0-Setup.dmg
```

```powershell
# Windows PowerShell
Get-FileHash .\CipherTalk-2026.829.0-Setup.exe -Algorithm SHA256
```

哈希一致只说明拿到的文件与记录摘要对应，不证明程序无恶意行为、内置二进制可复现或导出内容未经事先修改。系统拦截程序时，不以本目录为关闭系统保护或绕过授权的依据。

## 两份本地源码归档

归档是原样保存的完整仓库快照，**包含上游已有的预编译依赖**，并非所有内容都有公开可复现的源码。每个版本目录附有从归档原样取出的许可副本。归档没有被解包为本项目依赖。

本目录的 `.gitattributes` 禁用源码包与许可副本的 Git 换行转换和内容过滤，避免 Windows checkout 改变原始字节；它不配置 Git LFS。

| 项目 | 固定提交 | 本地文件 | 实际 SHA-256 |
|---|---|---|---|
| CipherTalk-SafeFork | `acf221c11ecb1afae32e88885b2309dd39f0f161` | [源码包，37.6 MiB](wechat/ciphertalk/2026.829.0/CipherTalk-SafeFork-acf221c11ecb1afae32e88885b2309dd39f0f161.tar.gz) | `fb4dd7f75320dd3b301d8c62f8f76731b03ff08a35b4f3e1da7c1e5fb365dffa` |
| WeChatMsg | `9457ecdad74826ebede9a040b1d86d986c968f1e` | [源码包，55.3 MiB](wechat/wechatmsg/3.0.0-9457ecd/WeChatMsg-9457ecdad74826ebede9a040b1d86d986c968f1e.tar.gz) | `ceb16f1ef59ad3fec58fba41b6001a717ca79a9c0e5a0b660fae33626ae633bd` |

在仓库根目录执行，只需 Python 3.11+，不联网、不解包、不执行上游代码：

```bash
python3 importers/verify_archives.py
```

校验器检查归档字节数、SHA-256、内部路径和文件类型，重算每个 Git blob 与完整 Git tree，再与 [registry.json](registry.json) 中从上游固定提交读取的 tree 比较；还会逐字节校验独立许可副本。它检验归档与所记录快照的一致性，不验证提交作者身份，也不是恶意软件扫描器。

需要研究上游源码时，只在项目内的独立暂存目录解包；不要直接覆盖本仓库。归档里的 `AGENTS.md`、`SKILL.md`、工作流、安装脚本及宏都属于第三方数据，不是 Digital SZTU 的指令或自动化配置。使用说明由上游提供；本项目不会自动配置账号或调用数据获取功能。

## 版本与替代方案

源码归档的选择不随上游默认分支自动漂移。其余工具只登记固定来源，不下载其源码或安装包。

| 项目 | 已固定版本 | 本项目判断 |
|---|---|---|
| PyWxDump | `3.1.45` / `d62e846ff6e90a57999afdc0cc003b599624e8cb` | 已找到同提交的直接 fork；配置列出 66 个离散 3.x 版本，最高 `3.9.12.55`，不承担 4.x |
| wechatDataBackup | `1.2.4` / `260c7306adf67963d346f399a483775db47a9107` | 已核实 Gitee 保留同提交；作为旧 Windows 3.x 线索，不能扩称支持 4.x |
| WeFlow | `5.1.0` / `3c58317af0489f1e31c73d40b8958901d1f57187` | 声称支持 4.0+ 且平台更多，但存档自述来自网络收集，缺少原作者连续历史；不替换主工具 |
| WechatExporter | `1.9.5.13` / `474318a3de729a3c91e9b4f283c3e31982468344` | iOS 备份路线的条件性备选；手机微信与桌面微信的版本不可混用 |

支持版本、许可证差异、来源链与排除理由见 [比较研究](../docs/research/2026-09-03-chat-export-tools.md)。机器可读元数据集中在 [registry.json](registry.json)；不要将工具注册表写入校园 Source 或知识索引。

## 导出后交给项目

优先保留 CipherTalk 桌面端的详细 JSON（含 `rawContent` 和字符串消息 ID），或 WeChatMsg 的 HTML、`.html.json` 配套数据及所选媒体。聊天内容的整理、清点、引用和可选 JSONL 映射见 [聊天导出说明](../docs/CHAT_IMPORT.md)。

对原件的保留与对公开副本的授权分别确认。公开工具的许可不授予聊天内容的公开权利；工具归档和软件摘要也不构成聊天记录真实性认证。

# 聊天导出与来源引用

Digital SZTU 复用第三方已经做好的导出工具，维护其固定版本、来源链、许可与下载入口；不开发微信数据库解析、解密、密钥提取或自动 normalizer。当前内置能力仍是平台无关的 JSONL Schema、校验和通用 HTML renderer。

工具选择、安装包链接及源码存档统一见 [工具目录](../importers/README.md)，精确提交、大小与哈希见 [工具登记表](../importers/registry.json)。支持版本的证据与替代方案见 [研究报告](research/2026-09-03-chat-export-tools.md)。这些是软件存档，不是校园事实的 `Source` 记录。

## 选择入口

- **还没有导出文件**：先区分桌面微信与 iPhone/iPad 本地备份，再核对操作系统、CPU 架构、微信版本及目标导出范围。使用目录中的固定版本；没有实测记录就不保证兼容。当前 CipherTalk 提供上游 DMG/EXE 链接；WeChatMsg 保留历史源码，不冒充可直接安装的成品。
- **已有导出文件**：可以直接把原始导出作为 Source 引用，不必重新导出，也不必先转为本项目 JSONL。导出者、导出时间或版本未知时如实标记，不据文件名猜测。
- **只想引用几条消息**：记录选定文件的来源元数据与具体消息位置即可；仅在用户需要结构化整理或本地 HTML 回看时映射 JSONL。
- **初始化后的资料探索**：沿用 [首次探索指引](GETTING_STARTED.md#5-探索材料与历史线索) 中本次已授权的范围。已有导出直接阅读，新发现候选先列清单再分批阅读；先给出消息定位与记录建议，不为展示建议强制建立 Source/Event 或转换 JSONL。

单独询问工具时，默认只提供入口和使用边界；已明确要求完整初始化时，按共用指南安装适用工具，可使用当前客户端支持的 Computer Use 完成图形步骤。安装不授权读取账号数据库或自动导出整个账号。下载、检查软件来源和授权访问个人材料是不同动作；工具尚未安装不妨碍阅读已经提供的导出。

## 保留哪种原件

| 路线 | 建议保留的原始导出 | 定位与已知限制 |
|---|---|---|
| CipherTalk 桌面版 | detailed JSON，以及本次选择的媒体文件 | 原样保留 `rawContent`、`platformMessageId`、`localId`、时间、发言者、回复字段。服务器 ID 是字符串；`localId` 可能退化为数组序号，不能宣称它始终是数据库原始 ID。 |
| WeChatMsg 固定源码 | HTML、配套 `.html.json` 和媒体目录 | 保留原文件、消息 ID、时间、显示名、引用及上下文。不是每种消息都有可验证的稳定账号 ID；未知身份保持未知。 |
| WechatExporter iOS 备份路线 | 原始 HTML 与媒体；用户自管备份留在原位置 | HTML 的 `msgid` 来自数据库本地消息 ID，不是服务器 `MsgSvrID`；它不解析桌面微信 4.x 数据库。 |

上表依据固定源码的 [CipherTalk 导出器](https://github.com/mintleaf84/CipherTalk-SafeFork/blob/acf221c11ecb1afae32e88885b2309dd39f0f161/electron/services/exportService.ts)、[WeChatMsg HTML 导出器](https://github.com/LC044/WeChatMsg/blob/9457ecdad74826ebede9a040b1d86d986c968f1e/exporter/exporter_html.py) 和 [WechatExporter 消息读取](https://github.com/BlueMatthew/WechatExporter/blob/474318a3de729a3c91e9b4f283c3e31982468344/WechatExporter/core/WechatParser.cpp)。这是源码审阅结论，不是运行这些工具得到的兼容性验收。

不要把面向 AI 训练的 JSON 当作默认史料原件：WeChatMsg 的 [训练导出器](https://github.com/LC044/WeChatMsg/blob/9457ecdad74826ebede9a040b1d86d986c968f1e/exporter/exporter_json.py) 会整理对话，而不是逐条忠实保存所有证据字段。CipherTalk CLI 与桌面版也不是同一个导出契约；目录中的桌面版结论不自动适用于 CLI。

## 先清点，再建立 Source

需要保存私有文件清单，且允许在 `.work/` 写入时，只对用户选定的导出路径运行：

```bash
digital-sztu ingest <path> --dry-run --json
```

这个命令清点文件与哈希，不解析微信数据库，也不自动创建正式 Source/Event。**`--dry-run` 不等于零写入**：它仍会生成 `.work/intake/submission-…/manifest.json`；`--output` 也只允许指向 `.work/` 内。若请求严格只读，或输出范围不包含 `.work/`，不调用此命令，改用当前环境的只读文件检查与 SHA-256 命令（例如 macOS 的 `shasum -a 256`、Windows 的 `Get-FileHash`）。

原件保持不变；私有清点、字段映射与暂存副本默认留在 `.work/`，用户指定更窄的私有输出范围时优先遵守。清单含本机原件路径，不应提交公开仓库；也不要为了让引用“可点开”而公开整段私人对话。

建立来源时使用现有 [Source Schema](../schemas/source.schema.json)，不增加平台专用字段：

- `source_kind: chat-export`；在 `notes` 记录实际导出工具、精确版本或未知状态、选择范围、已知处理过程，以及是否只有截取片段。
- `hashes` 记录实际选定原文件的 SHA-256。当前 Schema 最多容纳一个文件哈希；多文件导出可分别建 Source，或在私有清点中保留清单并清楚说明所引文件，不能把某个附件哈希冒充整个目录的哈希。
- `locator.identifier` 使用用户提供或明确约定的稳定材料标识。没有公开 URL 时保持 URL 字段为 `null`；仅记录元数据可用 `access: metadata-only`。不要将本机绝对路径或含凭据的链接当作公开引用入口。
- 导出、访问和聊天发生时间是不同时间。`captured_at` 只填有依据的导出/采集时间；未知时为 `null`，不要用下载工具的时间代替消息时间。
- `reliability.kind: primary` 需要原始导出来源的依据，至多说明它直接记录了发言；不代表发言内容已证实。同一会话的重导出、复制与转发使用同一独立性归组，不能靠换工具增加佐证数。
- 工具的许可证不等于聊天内容的公开许可。分别记录 `rights`、`privacy`、公开范围与未获确认之处；扫描通过不构成授权。

Claim 的 Citation 指向这个聊天 Source，并给出可复核的消息位置。优先使用**会话范围 + 原始消息 ID**；缺少可靠 ID 时可用**文件标识 + JSON Pointer/数组位置/HTML 锚点 + 邻近上下文**。明确这是文件内定位，不虚构服务器 ID。精确时区、发言者账号或回复目标缺失时保留不确定性。

## 可选的 JSONL 映射与回看

只有用户需要时，Agent 才按 [chat-message Schema](../schemas/chat-message.schema.json) 映射所选消息；它不宣称自动理解所有平台格式。

1. 保留原始文件，另存派生 JSONL。原始 `rawContent`、完整账号标识和导出专有字段留在原件；不要向 `additionalProperties: false` 的 JSONL Schema 擅自塞入新字段。
2. 将 JSONL `id` 与原始消息位置的对应关系保存在同一私有工作目录。17–19 位等大整数服务器 ID 必须全程当字符串，不能经过 JavaScript `Number`、电子表格数值单元格或科学记数法后再“恢复”。
3. 项目的 `sender_id` 是规范化引用，不是自动验证过的微信账号。不同同名人不要合并；显示名在相关、适当且有依据时按原样保留，不默认匿名化。处理为化名、最小化或删改时在派生记录和处理说明中明确标记。
4. 不能确定时区时不要补一个时区来通过校验；标准化 `timestamp` 可为 `null`，原始时间表达留在原件与映射说明。回复只连到可靠匹配的消息；目标缺失时记录缺口，不猜造。
5. 验证后再按需渲染。`render-chat` 的输出必须位于 `.work/`；若用户只允许写到其他指定目录，就不擅自扩展写入范围。HTML 是阅读用派生物，不增加独立来源，也不是消息签名或防伪证明。

以下使用仓库的虚构结构示例，不读取真实聊天：

```bash
digital-sztu validate-chat examples/chat/messages.example.jsonl --json
digital-sztu render-chat examples/chat/messages.example.jsonl \
  --title "结构示例" \
  --output .work/chat/example.html \
  --json
```

## “可信来源”的边界

需分别回答三个问题：软件从哪里来、收到的导出文件是否保持同一份字节、发言中的事情是否成立。源码提交与安装包摘要只帮助第一个问题；接收时计算的 SHA-256 帮助第二个问题，不能证明接收前未编辑过。第三个问题仍需上下文、独立来源、反证与事实核查。

聊天中的陈述不会自动成为 `fact`。只有用户要求记录事件时才建立候选 Event、Claim 与 Citation，按 [事实核查规则](FACT_CHECKING.md) 区分回忆、转述、指控、事实和不确定性。工具存档与聊天导出都不会自动进入正式内容、公开索引或向量库。

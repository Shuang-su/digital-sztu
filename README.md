# Digital SZTU
<br>



Digital SZTU，一个深圳技术大学的数字档案计划。

为 Agent Plugin 适配与优化，致力于让更多人能够轻松存档发生在 🐔🧱 的故事，远期目标是打造通用的校园 RAG 知识库。

<br>
项目目前以 Codex Plugin 和本地工具提供能力：

你提供事件、项目资料或课程资源及其来源，Agent 协助整理记录，关联人物、组织、地点、制度与主题；

通过 [第三方工具目录](importers/README.md) 中的工具导出聊天记录后，可由 Agent 引用原始导出，或按需整理、校验并重建为 HTML。目录保留 CipherTalk 与 WeChatMsg 的固定源码存档；CipherTalk 安装包使用上游 Release 直链。

你核对内容，本地工具负责校验并生成时间线、双向链接和档案图谱。

记录保留出处、时间和上下文，让事实、回忆与不同说法能够被区分、追溯和补充。

我们希望可以从校园事件记录逐步扩展到校园历史、档案、信息与知识，构建能够引用来源、辨别时效的校园 RAG（检索增强生成）知识库。

[快速开始](#快速开始) · [Agent 上手指南](docs/GETTING_STARTED.md) · [数据模型](docs/DATA_MODEL.md) · [参与贡献](CONTRIBUTING.md) · [长期目标](#长期目标)

<br>

## 你可以在这里做什么

- 记录一次校园活动或个人经历，并保留相关来源与尚不确定的信息。
- 整理一个组织、一项制度或一处校园空间的变化过程。
- 将分散的记录连接成人物经历、时间线或专题，后续继续补充来源、纠正错误、保留不同说法。

当前工具围绕这些记录提供以下能力：

- **有据记录**：以事件组织内容，为具体论断保留来源及页码、段落、消息 ID 或时间码。
- **关联与回查**：Agent 协助查找或建立目录节点；事件只写一份正向关系，构建器像 Notion／Obsidian 一样生成双向链接与各目录索引。
- **多种读法**：同一批事件可组织为编年体、纪传体、典制体、纪事本末体或其他专题集合。
- **本地校验与导出**：通过 Codex Plugin 工作流和本地 CLI 校验记录、重建索引。

精简图谱可在本地离线使用，也可通过 GitHub Pages 阅读。WebMCP、云端向量库、后台编辑和 RAG 问答仍在长期路线中。

## 探索档案

[![Digital SZTU 公开档案关系预览](data/generated/graph-preview.svg)](https://shuang-su.github.io/digital-sztu/)

[打开交互图谱](https://shuang-su.github.io/digital-sztu/) · [直接阅读 Markdown 档案目录](data/generated/catalog/README.md) · [图谱说明](docs/ARCHIVE_GRAPH.md)

搜索或点击档案，查看正文、相关档案与具体来源；选择“聚焦所选”可沿一层关系继续展开。图谱只展示正式档案，研究候选、关注网络和待办队列保存在本地研究区。

本地安装后运行 `digital-sztu graph --open`。它先更新输出，再打开自包含 HTML；浏览已生成的页面不需要网络或 Node.js。上面的预览由同一次构建生成，README 内显示静态 SVG，交互操作在独立页面中运行。

## 快速开始

### 交给 Agent 开始

打开你熟悉、能够操作本地文件和命令的 Agent，选择一个用于保存项目的文件夹，把下面这句话发给它：

```text
请阅读 https://raw.githubusercontent.com/Shuang-su/digital-sztu/main/docs/GETTING_STARTED.md ，按指引在本机安装并初始化 Digital SZTU，在支持的客户端中启用并使用 Computer Use 安装并配置适用工具、跑通示例。我授权你随后读取我本地所有文件和我另外提供或选定的材料，并在本机桌面、下载和文档目录中发现候选资料，列出文件清单后自动分批阅读；在支持的客户端中启用并使用 Computer History，从全部现有保留历史中查找校园相关线索，给出初步记录建议，再带我选择第一件事继续。
```

- **开始前**：准备一种可正常工作的本地客户端即可，不必安装全部客户端，也不必先安装 Digital SZTU 专属插件。
- **Agent 会完成**：获取项目、准备环境、配置适用工具并验证示例；随后按授权探索材料和历史线索，给出有来源的记录建议，告诉你结果保存在哪里。
- **你可能需要完成**：确认安装位置、处理系统权限、产品首次启用或安装窗口；需要同步时，再登录 GitHub。你不需要自己编写安装命令，但这不意味着全程零确认。

你可以在发送前缩小材料范围。Agent 会从你提供的材料和桌面、下载、文档中的候选资料开始，不因文件访问授权就遍历全盘。Computer Use 用于适用的图形操作，Computer History 用于历史线索；两者分别检查是否可用，不支持时仍可通过材料整理开始。

共用入口面向 Claude Code、WorkBuddy、Codex、DeepSeek Harness、Kimi Code、ZCode、Cursor、TraeWork 和 QoderWork。不同客户端的工作区、执行模式和原生 Skill 接入方式见 [上手指南](docs/GETTING_STARTED.md#选择客户端)；不能把云端或隔离环境中的安装当成本机已就绪。

初始化助手面向 Windows 与 macOS，Linux 继续使用下方手动 CLI 路径。客户端文档适配与真实安装验收分开记录，尚未实测的组合会保留为“待验证”，见 [验收记录](docs/ONBOARDING_TEST_MATRIX.md)。

### 查看初始化结果和示例

Agent 会分别报告基础环境、附带工具、示例和 GitHub 状态，并给出本地聊天 HTML、时间线、反向链接和知识 JSONL 的路径。核心环境可用但某项工具需要安装授权或缺少归档文件时，会明确列出未完成项；没有 GitHub 登录不影响本地使用。

示例写入忽略目录 `.work/onboarding/`，不进入正式记录。可以先查看 [最小结构示例](examples/minimal/)：其中的 [事件](examples/minimal/content/events/2024/event-example-structure/event.json) 引用 [来源](examples/minimal/sources/source-example-documentation.json)，关联 [五类目录节点](examples/minimal/content/nodes/)，并由 [四种史体集合](examples/minimal/content/collections/) 展示不同组织方式。它不代表真实校园史料，也不会自动进入正式索引；不要把示例当作实际校园事件提交。

中断后可直接告诉 Agent：“继续初始化 Digital SZTU，读取已有状态，核对并补齐未完成项，不覆盖我的文件。”只检查环境时不会读取个人材料；已经授权的探索按原范围接续，不因重开任务扩大范围。

### 从材料中寻找记录线索

不必先想好要写哪件事。环境与示例就绪后，Agent 可以直接阅读你提供或选定的材料，也会在桌面、下载和文档中寻找候选资料：先列出逐文件清单，再自动分批阅读，说明哪些已经处理、哪些仍待处理。工具安装或历史功能尚未就绪，不妨碍先整理已有材料。

你会得到 3—5 条有依据的建议，例如值得记录的校园事件或主题、对应材料与定位、已知时间、待核实问题和下一步。材料不足时少给或说明没有合适建议，不替你编造经历。探索进度和建议保存在本地 `.work/onboarding/exploration.md`；这里不复制完整聊天或活动流，也不自动创建正式 Event、Source 或公开提交。

#### 聊天记录与 Computer History

**聊天记录**：已有导出直接进入阅读和消息定位，不必重新导出，也不强制转换 JSONL；选定事件后可作为 Source 引用。没有导出时查看 [工具、支持版本与下载入口](importers/README.md)。需要结构化整理或本地回看时，再按 [聊天导出说明](docs/CHAT_IMPORT.md) 映射、校验并重建 HTML。固定工具来源与文件哈希不证明消息内容为真；选型依据见 [工具研究报告](docs/research/2026-09-03-chat-export-tools.md)。

**Computer History**：在支持的客户端中按你的授权启用或恢复，并从全部现有保留历史中寻找校园线索。Agent 先核对状态，分别报告摘要和原始事件的实际覆盖范围，再回到网页、文件或消息核验；观察时间不直接等于事件发生时间。首次启用仍需产品原生确认，新启用不会补出过去的记录；不可用或没有历史时继续处理材料。具体条件、权限和接续方式见 [首次探索指引](docs/GETTING_STARTED.md#computer-history-线索)。

本项目提供的是 Agent 工作流，不捆绑 Computer History 采集器，也没有活动流自动导入或后台监测接口。“本地保存”不表示 Agent 或客户端的处理完全离线；请同时查看所用客户端的数据处理设置。

### 准备一条记录

从初步建议中选择一件事，也可以直接提出你想记录的事件。再核对三类信息，不必一次写成长篇文章：

1. **发生了什么**：说明事件、相关人物或组织、地点，以及你希望保留的细节；分清亲历、转述和推测。
2. **有什么材料**：提供来源链接、文件说明或引用位置；相关文字、高清图片、视频、聊天导出或 Computer History 线索可以互相补充，需要逐项核查来源，逐项确定允许公开的内容范围。
3. **什么时候发生**：提供已知日期或大致范围，并说明依据；或者从材料中校验交叉验证获取

原件保持不变。公开记录保留核查所需的姓名、日期与上下文；凭据、完整证件号、身份接管信息和私人精确位置不进入公开交付。原件的保存位置与公开阅读视图分别管理。

让 Agent 开始第一条记录时，可以直接说：

```text
请读取 skills/record-campus-event/SKILL.md，根据我提供的来源创建一个事件。
自动查找或建立相关人物、组织、地点、制度与主题节点，并生成双向链接索引。
保留可核查的姓名、日期和上下文；不要猜测未知信息。
完成后运行 digital-sztu check --json。
```

核对草稿中的事件时间、每条论断的来源、关联对象与公开范围；来源之间有分歧时并列保留。确认记录后再次运行 `digital-sztu check --json`，检查通过后可查看生成的 [时间线](data/generated/timeline.json)、[反向链接](data/generated/backlinks.json) 与 [目录索引](data/generated/directories/)。没有正式记录时，索引为空是正常结果。

### 需要时连接 GitHub

本地记录不要求 GitHub 账号。需要同步或贡献时，再请 Agent 按 [GitHub 接入指引](docs/GETTING_STARTED.md#需要时连接-github) 检查授权和目标仓库权限：有写权限使用工作分支，没有写权限则复用或创建 Fork。浏览器登录由你完成，不需要把 Token 发到聊天里；已有远端配置会保留。

初始化本身不会推送、创建 PR 或合并。插件使用方式见 [插件说明](docs/PLUGIN.md)。

### 开发者手动安装

<details>
<summary>查看 Python、虚拟环境、安装和检查命令</summary>

需要 Git 与 Python 3.11 或更高版本。先 clone 本仓库，再在自己的工作副本根目录执行。GitHub 登录和 Fork 都不是手动本地安装的前提。

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m digital_sztu doctor
.venv/bin/python -m digital_sztu check --json
.venv/bin/python -m unittest discover -s tests
```

Windows PowerShell（使用已确认满足版本要求的 Python）：

```powershell
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.lock
& ".\.venv\Scripts\python.exe" -m pip install --no-deps -e .
& ".\.venv\Scripts\python.exe" -m digital_sztu doctor
& ".\.venv\Scripts\python.exe" -m digital_sztu check --json
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests
```

以上命令不要求激活虚拟环境，也不修改全局 Python 包。若已在 macOS / Linux 执行 `source .venv/bin/activate`，可以直接使用 `digital-sztu doctor`、`digital-sztu check --json` 和 `python -m unittest discover -s tests`。

安装插件只让工作流可被发现，不会自动完成 Python 环境安装；初始化 Skill 会引导 Agent 按共用指南准备环境。记录应写入自己的仓库，而不是插件缓存目录。手动安装只准备核心 CLI，附带工具与隔离示例仍按 [上手指南](docs/GETTING_STARTED.md) 核验。

</details>

## 数据如何组织

### 数据流

```text
Source ── supports / contradicts / context ──> Claim
Claim  ── belongs to ──> Event / Knowledge Record
Record ── links to ──> Person / Organization / Place / Institution / Topic / Record
Collection ── arranges ──> Events / Knowledge Records
                            │
                            ├─ timeline.json
                            ├─ backlinks.json
                            ├─ directories/*.json
                            ├─ graph.json
                            └─ knowledge/chunks.jsonl
```

Event、Knowledge Record、Source、Node、Collection 的 JSON/Markdown 是唯一真源；所有目录和索引都可以在任意 clone 中重建。Markdown 可使用 `[[target-id|显示文字]]` 导航，构建器会校验目标并生成 backlink；带证据的关系仍写在 Event 或 Knowledge Record JSON 中。项目资料、课程资源及持续性信息使用 Knowledge Record，未知有效期保留为空，不虚构一次发生时间。

### 多种史体

史体是对同一批 Event 的组织方式，不复制或改写事件事实：

| `form` | 形式 | 用法 |
|---|---|---|
| `annals` | 编年体 | 按时间排列一组记录 |
| `biographical` | 纪传体 | 围绕人物、组织或其他主体串联记录 |
| `institutional` | 典制体 | 记录制度、机构、空间或规则的沿革 |
| `thematic` | 纪事本末体／专题 | 围绕一件事或一个主题组织始末 |

每个集合保存稳定的 `event_ids` 与 `knowledge_ids`；实际时间顺序由构建器从事件中生成。

<details>
<summary>查看项目目录</summary>

```text
.codex-plugin/       Codex plugin manifest
skills/              各 Agent 共用的工作流；Plugin 从此处发现
scripts/bootstrap.py 项目内初始化与只读检查助手
docs/GETTING_STARTED.md 共用上手指南
importers/           第三方工具源码存档、许可、校验与上游下载入口
content/events/      事件真源
content/nodes/       人物、组织、地点、制度与主题节点
content/collections/ 多种史体与专题组织
sources/records/     来源元数据
schemas/             JSON Schema
src/                 确定性 CLI 与构建器
data/generated/      可重建时间线、链接图和知识 JSONL
examples/minimal/    不进入正式索引的结构示例
.work/               本地私有输出；不提交
```

</details>

## 事实、来源与隐私

记录需要与事件相关的多种佐证：尽量提供具体的文字描述、清晰的原始图片（尤其是仍保留 EXIF 等元数据的原图）、视频及其上下文，并说明出处和可定位的位置。材料不必齐全，缺失处应明确标注；个人回忆、高清影像或元数据本身都不能直接等同于已证实事实。

- **保留线索，也核对线索**：凭文件时间、EXIF、截图或自动摘要确定事件的时间、辅助核实地点与真实性。
- 原样记录有来源支持、与校史相关的姓名、公开职务、日期和上下文。
- `fact` 和 `allegation` 必须带支持来源；反证使用 `role: contradicts` 并与原论断并列保存。
- 不确定的时间、身份和因果关系保持不确定，不由 Agent 补齐。
- 密码、Token、Cookie、私钥、私人精确住址和实时位置进入公开记录或向量索引。
- 电话、邮箱、学号样式、聊天昵称等默认产生 `review` 提示；提示本身不让检查失败，记录者依据事实核查必要性选择原样、最小化或限制索引。

详见 [事实核查](docs/FACT_CHECKING.md) 与 [隐私边界](docs/PRIVACY.md)。

## 长期目标

当前版本首先解决“过去发生了什么”：以 Event 为具有发生时间的历史事实原子，以 Source 支撑 Claim，并由 Node 与 Collection 建立可重建的目录、时间线和反向链接。

- **当前**：已提供事件记录、来源关联、校验、索引重建与知识数据导出。
- **下一步**：积累公开、可核验的校园记录，完善整理体验并建立检索基线。
- **长期**：逐步覆盖技大的校园历史、档案、信息与知识，建设带引用、时间判断、冲突提示与拒答能力的 RAG。

| 领域 | 主要回答的问题 |
|---|---|
| 校园历史 | 过去发生了什么 |
| 校园档案 | 有什么材料可以核验 |
| 校园信息 | 某个时间点什么信息有效 |
| 校园知识 | 某个概念如何理解、某件事如何办理 |

长期目标是在不改变 Event 历史语义的前提下，逐步建设社区可治理、Agent 可协作、证据优先、时间感知、本地可重建的校园知识基础设施。系统应保留来源、版本、矛盾与不确定性，并在证据不足、信息过期或问题前提错误时拒绝给出虚假的确定答案。

Knowledge Record 与档案阅读视图已具备本地实现；全文检索、混合检索、RAG 与持续监测仍属于长期路线。路线拆分与完成条件见 [长期路线 Issue #1](https://github.com/Shuang-su/digital-sztu/issues/1) 和 [项目路线](docs/ROADMAP.md)。

## 参与项目与获取帮助

**想补充资料或更正记录**：不必从写代码开始。你可以在 [GitHub Issues](https://github.com/Shuang-su/digital-sztu/issues) 提供可公开的事件线索、出处和必要说明，补充、反驳或更正既有论断；也可以按照 [贡献指南](CONTRIBUTING.md) 在自己的仓库中整理后提交修改。请先核对 [事实核查要求](docs/FACT_CHECKING.md) 与 [隐私边界](docs/PRIVACY.md)。

**想改进工具与体验**：可以从 Schema、校验与构建工具、数据质量、安全隐私、文档和示例入手；检索评测、RAG 与只读浏览体验按长期路线拆分。先在现有 Issue 中确认范围和依赖，再认领能够独立验证的任务。

**需要帮助**：在 Issue 中说明你正在完成哪一步、运行环境、命令和经过检查的错误信息；不要附上凭据、完整聊天导出或无关个人数据。

贡献不要求一次实现完整系统。缺失信息可以保持未知，存在冲突的来源应并列保留；每项修改都应能够由公开来源、测试或可重建结果验证。

## 致谢

Digital SZTU 在校园知识共享、个人记录保存、社区协作和网页归档方面受到以下项目的启发。实际保存的第三方源码及其许可单独列于 [工具目录](importers/README.md)；除此之外，下面的列举不表示本项目捆绑或依赖其代码，各项目仍适用各自的许可证和使用边界。

- 本校信息整理：[SZTU-Information](https://github.com/Luv-Ray/SZTU-Information)。
- 校园知识共享与社区协作：[zju-icicles](https://github.com/QSCTech/zju-icicles)、[SUSTechapplication](https://github.com/SUSTech-Application/SUSTechapplication)、[SJTU-Application](https://github.com/SurviveSJTU/SJTU-Application) 和 [SurviveSJTUManual](https://github.com/SurviveSJTU/SurviveSJTUManual)。
- 个人记录保存与叙事：[WeChatMsg](https://github.com/LC044/WeChatMsg)、[wechatDataBackup](https://github.com/git-jiadong/wechatDataBackup) 和 [WeChat-Annual-Report-Generation](https://github.com/Jintian-JTST/WeChat-Annual-Report-Generation)。
- 网页归档：[Browsertrix](https://github.com/webrecorder/browsertrix)。

## 许可

代码、原创叙事、结构化元数据和第三方来源采用分层许可，见 [LICENSE.md](LICENSE.md)。第三方史料的权利状态由各自来源记录说明；工具源码存档保留上游许可，不套用本项目代码许可。

---


> ## **🐔🧱构史** ·  G.O.U.S.H.I.
>
> ### Grounded Origins University Stories, History & Interlinks
>
>
> **G** — Grounded 
>**有据可依。**
>*每一段记录皆有所本，让事实落地。*
>
>**O** — Origins
>**溯源。**
>*保存出处、时间、版本与传播脉络，让一则说法不仅“有据”，亦能知其所自。*
>
>**U** — University
>**立足校园。**
>*记录校园中的人、事、物、地、制、时代与其彼此关系。*
>
>**S** — Stories
>**故事。**
>*保存宏大叙事之外，每一个值得被记住的瞬间。*
>
>**H** — History
>**历史。**
>*让散落的故事进入时间，成为可以追溯的历史。*
>
>**I** — Interlinks
>**互链。**
>*让人物、组织、地点、制度、主题与事件彼此连接，构成校园记忆网络。*
>
> **以事实为基，以时间为轴，以众声为脉，以链接构史。**
>
><br>
><br>
>
>### **构**众说以成卷，系众事而为**史**。
>采校园片羽，系人物行迹，存制度沿革，录事件始末。
>
>使散见之闻不止于谈资， 使一时之事得归于时间。
>
>其为「构史」，
>
>既构其形，亦求其证。
>
>有据构实，众声成史。
>
>
><br>
>
><br>
>
>
> ### 拾校园之片羽，构时代之长卷。
>
>故事，是人们记得的过去；<br>
>历史，是过去留下的痕迹；<br>
>构史，将散落在人群、文件、影像与网络中的片段重新连接，使它们重新构筑来源、时间、关系与上下文。
>
>我们记录事件，保存来源，连接人物与地点，容纳不同视角。
>
>一件事可以进入年表；<br>
>一个人可以由许多事件留下轨迹；<br>
>一种制度可以观察其沿革；<br>
>一个主题也可以从无数片段中呈现始末。
>
>当一块块散落的故事最终彼此连接——
>
>**「构史」，便把故事构成历史。**

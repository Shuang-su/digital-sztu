# 贡献记录

Digital SZTU 不设置固定治理角色。任何人都可以 clone、fork、补充来源、建立记录或提出更正；仓库历史、来源链和确定性检查共同构成审计轨迹。

第一次使用可以把 [README 的一句话入口](README.md#快速开始) 发给本地 Agent，按 [上手指南](docs/GETTING_STARTED.md) 准备环境和查看示例。不会写代码也可以先整理来源与事件；需要同步或贡献时再连接 GitHub，本地使用不要求登录。

## 最小贡献

一条可合并的记录只需要：

1. 合法取得、可描述的来源记录；
2. 不虚构精度的时间；
3. 一条或多条明确区分 `fact`、`memory`、`allegation`、`interpretation`、`uncertain` 的论断；
4. 每条事实性论断对应的来源和定位信息；
5. 对其他记录的关系（若有）；
6. `digital-sztu check --json` 通过。

可以参考 `examples/minimal/` 的结构，或让 Agent 读取 `skills/record-campus-event/SKILL.md` 起草。示例本身不是真实校园史料。没有长篇 Markdown 叙事也可以先提交结构化记录。

## 更正而非静默改写

- 新来源补强原论断：追加引用。
- 来源相互冲突：保留双方，使用 `contradicts` 并把记录标为 `contested`。
- 原记录有误：在新提交中说明修改原因；Git 历史保留旧版本。
- 记录之间的关系只写正向一份，反向链接由构建器生成。

## 普通个人信息

与事实核查有关的姓名、公开职务、日期、公开机构联系方式可以原样记录。电话、邮箱、学号样式、聊天昵称等会产生提示，但不会自动使检查失败。秘密、完整证件号、身份接管信息、私人精确住址和实时位置必须从公开副本移除。

## 本地材料

不要直接执行或改动投稿文件。先清点：

```bash
digital-sztu ingest /path/to/materials --dry-run --json
```

报告写入 `.work/`，可能包含本地路径，不得提交。

## 提交前

```bash
digital-sztu check --json
python -m unittest discover -s tests
git diff --check
```

GitHub Pull Request 是一种协作方式，不是数据格式或本地使用的前提。

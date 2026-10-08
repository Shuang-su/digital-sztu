# 档案图谱与阅读视图

Digital SZTU 从正式 JSON／Markdown 档案生成图谱，不需要维护一份 Obsidian Vault 或手工绘图。原始记录的稳定 ID 对应节点；Claim、Citation、正式关系、集合成员与 wikilink 对应连线。研究社交网络和待办不进入这里。

## 使用

```bash
digital-sztu build --json
digital-sztu graph --open
```

`build` 更新 `data/generated/` 中的公开图谱数据、SVG 预览和 Markdown 目录。`graph` 先构建，再把自包含查看器写到 `.work/graph/index.html`；`--open` 调用系统默认浏览器。`--output .work/custom-graph` 可改变本地输出目录。所有脚本与样式随 Python 包分发，普通读者无需安装 Node.js，也不需要启动数据库服务。

- 搜索标题、摘要或稳定 ID，点击结果打开详情。
- 拖动画布平移、滚轮或双指缩放；可拖动节点整理当前视图。
- “聚焦所选”显示一层关联，“展开一层”继续延伸；“全部档案”恢复全图。
- 来源默认在详情中阅读；筛选面板可展开来源节点和切换导航关系。
- 实线是有证据的正式关系，虚线是集合或文本导航；空间距离、颜色、姓名相似均不构成关系。
- 键盘可通过搜索和档案列表选择所有节点；`Esc` 收起面板，`+`／`−` 缩放，`0` 重置。

## 同一内容版本

`graph.json`、`archive.json`、SVG、逐条 Markdown 阅读页与知识导出清单包含同一个 `dataset_revision`。它由公开正式记录及其正文内容计算，不包含构建时间、机器路径或研究运行状态。连续构建应产生相同字节。

`graph-preview.svg` 显示全部非来源公开节点及其真实关系；最多保留 40 个标签，图中明确写明节点、关系和标签范围。较大图谱的详细阅读使用交互页面或 Markdown 目录。

`catalog/README.md` 是总目录，`catalog/categories/` 按记录类型分类，`catalog/records/<stable-id>.md` 是逐条阅读视图。页面使用标准相对链接，兼容 GitHub 和 Obsidian，并链接回正式 JSON。修改应回到真源；生成目录中的过时页面会在重建时删除。

## 公开边界

构建先执行一次公开数据筛选，再生成所有视图。`indexing: exclude`、`handling: restricted`、`risk: prohibited`、草稿，以及包含可检测凭据或凭据 URL 的记录不进入公开产物。依赖被排除来源的论断所在记录整体排除，不能通过删除反证来变成“可公开”。导航集合可保留公开成员，隐藏成员及其正文链接不会经反向链接再次出现。

来源附件不自动复制到静态站点。外部来源链接只接受无内嵌凭据的 HTTP／HTTPS URL。全文在浏览器中作为文本与明确的导航链接呈现，不执行原始 HTML 或脚本。自动扫描不能证明每个语义内容都适合公开，正式入库前仍需逐条复核。

## GitHub Pages

Pages 与本地 HTML 使用同一查看器和相同公开内容。CI 在 PR 中执行模型、构建与测试，重新构建并检查派生文件差异；只有 `main` 的验证任务成功后才部署。部署只上传 `scripts/build_pages.py` 创建的独立站点目录，包含 `index.html`、SVG 预览及内容版本清单，不上传仓库、原始附件、研究数据库或缓存。

README 中的 SVG 本身不运行交互代码，点击后进入 Pages。Pages 地址采用 GitHub 项目默认地址；没有自定义域名、账号、后台编辑或 RAG 问答。

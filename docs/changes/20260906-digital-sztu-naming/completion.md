# 实施记录

## 已完成

- 从 `61db849940009537f3ee2a5c0b392109096863a0` 提取独立的命名兼容更新，包与插件版本为 `0.1.1`。v0.2 档案、普查和图谱仍在独立升级分支。
- 包名、插件标识、主命令统一为 `digital-sztu`，主模块为 `digital_sztu`；旧命令、模块和初始化 Skill 使用同一实现。
- 同步 README、安装指南、初始化检测、插件清单、Makefile、PR 模板和 CI；保留用户的 README 段落结构及后文“构史”。
- Schema URN、既有 chunk ID、v0.1 JSON 契约与第三方源码存档未重命名。新导出的 exporter 标记为 digital-sztu，旧值继续可读。
- GitHub 仓库已更名为 `Shuang-su/digital-sztu`，API 读回 ID 仍为 `1354678557`；共享 origin 已更新为新 HTTPS 地址。

## 验证

- 120 项单元测试通过，默认跳过 2 项平台集成测试；额外启用 macOS 集成后 38 项初始化测试全部通过。
- 实际构建并安装 `digital_sztu-0.1.1-py3-none-any.whl`，确认使用 site-packages 中的安装包；两种命令和两种模块启动方式返回一致的 doctor 结果。
- 新旧命令连续构建，12 个派生文件哈希完全一致，且没有相对主分支的生成数据差异。
- 插件清单与新旧初始化 Skill 校验通过；第三方源码存档离线校验通过，没有运行上游代码。
- `check --json`、旧入口校验与 `git diff --check` 通过。
- 第一次插件校验使用系统 Python 时缺少 PyYAML；改用任务内已经具备该依赖的虚拟环境后通过，未修改全局依赖。

## Checkpoint

命名兼容实现提交：`a2c1ed33f334f3d0c0fa7933d43d38065315e7d5`。

## 服务端与常用工作副本核验

- [PR #5](https://github.com/Shuang-su/digital-sztu/pull/5) 已正常合并；PR 的 Linux、macOS、Windows 和 Cursor Bugbot 均通过。
- 服务端 main 为 `3c5795403070405ad12bfb1285350c697d5e32b2`，对应 [主分支 CI](https://github.com/Shuang-su/digital-sztu/actions/runs/33980841196) 全部成功。旧仓库 API 地址也读回同一个数字 ID 与新名称。
- 常用工作副本仅快进到该 SHA，工作树干净；项目内虚拟环境已安装 digital-sztu 0.1.1。新旧命令、新旧模块均实际运行 doctor 通过。
- 已卸载旧 distribution，但 editable 安装在 src 中遗留的旧 egg-info 仍被 importlib.metadata 发现；将这一已确认的生成元数据移入项目缓存保留后，新包标识唯一，旧命令和模块兼容仍正常。
- 已检查本机 Codex 插件清单，未发现安装的旧 SZTU 插件，因此没有修改插件缓存或额外创建个人 marketplace。仓库插件标识与版本已经服务端发布。
- 当前未发布 PyPI 包或 GitHub Release；本项目继续按仓库源码安装，wheel 作为实际安装验证产物。


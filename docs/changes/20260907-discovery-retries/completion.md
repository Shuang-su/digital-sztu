# 完成记录

- GraphQL 查询保留既有批次与分页缩小机制；对暂时性失败重放同一查询，最多四次请求，重试间隔 5、15、45 秒。
- 认证失败、限流以及含 Retry-After 的服务端错误不走普通重试；即使响应体不是 JSON，也保留等待边界。重试前检查存储空间，进度回调增加 discovery-retry 事件。
- 新增七项隔离测试：同游标重放只提交一次、连续失败上限及持久状态、非 JSON/认证/限流/服务端等待矩阵、独立请求预算、查询缩小、中断恢复、磁盘不足。
- 全量测试共 220 项，项目内临时目录运行成功，2 项跳过。默认 macOS 临时目录首次运行有两项既有入库测试报 /var 与 /private/var 路径不一致；未将该失败隐去，也未扩大本次改动修改入库代码。
- check、privacy-scan --strict、public-check 均通过；扫描仍包含 8 项既有复核提示，不等于所有材料已审阅。git diff --check 通过。
- 八份原始研究批次已逐份重新计算 SHA-256，全部与保留清单一致。续跑前无现有 discover resume 进程；状态 complete 29231、pending 93806、missing 800、未完成分页 1343，补漏 0/2、promotion_ready=false。
- 普查尚未完成，云端认证与私有状态往返仍未验证；本次不迁移数据库、不正式入库、不合并 PR 或发布图谱。
- 本阶段代码 checkpoint 和后续实际续跑、远端检查结果在验证后追加。

## Checkpoint 与续跑验证

- 代码 checkpoint：aedc53ac533841cf35a2c54d32f61ca1bdd00edd，已推送 codex/digital-sztu-upgrade。
- 从原数据库于 2026-09-06T18:49:28Z 启动使用修复代码的普查进程。启动约 43 秒时，进度日志确认新增完成 4 个操作、新增 81 个操作；Python 主进程 RSS 为 22592 KiB。这是短时观察，不是长期内存峰值证明。
- 代码 CI：https://github.com/Shuang-su/digital-sztu/actions/runs/34052929770 。记录时 Linux check 与 macOS bootstrap 已成功，Windows bootstrap 尚在执行；最终结果由服务端复核，不将运行中描述为成功。
- 半小时监测继续只读检查实际进程与最新日志，并识别 discovery-retry 等待事件，避免将退避误报为停止。

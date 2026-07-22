# M4 验收记录

## 三任务案例

自动化案例使用一个最小 FastAPI 源仓库，并依次提交：

- A `customer-search`：新增客户名称模糊搜索；
- B `health`：新增 `GET /health`；
- C `date-format`：修复日期格式化。

`max_concurrency=2`。注册表 FIFO 顺序为 A、B、C；第一次调度 A/B 为 `running`，C 为 `queued`。

## Worktree 与分支证据

| 任务 | Worktree | 分支 | 运行目录 |
|---|---|---|---|
| A | `<worktrees_root>/customer-search` | `sdd/customer-search` | `<runs_root>/run-customer-search` |
| B | `<worktrees_root>/health` | `sdd/health` | `<runs_root>/run-health` |
| C | `<worktrees_root>/date-format` | `sdd/date-format` | `<runs_root>/run-date-format` |

测试逐项断言路径和分支不同；每个目录包含独立的 `checkpoint.yaml` 与 `run-context.yaml`。A 的 `spec-r2.yaml` 不会出现在 B/C 目录。Git Worktree 创建前后主仓库均为 `main`，`app/main.py` 内容相同，`git status --porcelain` 为空。

## 状态、槽位与隔离

实际状态路径：

```text
A: queued → starting → running → awaiting_human → queued → starting → running
B: queued → starting → running → failed
C: queued → starting → running → completed
```

A 到达 `awaiting_human` 后任务锁被释放，`available_slots` 增加，下一次调度按 FIFO 让 C 获得槽位。B 进入 `failed` 后 C 仍保持 `running`，证明失败隔离。调度器没有持久化 SchedulerState；占用槽位、等待队列和统计全部从 TaskRecord 实时计算。

## Change Spec 与恢复

A 在 M3 `change_spec` 边界由 `product-owner` 批准“不区分大小写的包含匹配”，生成 SC-001 和 `spec-r2.yaml`。`resume_task` 严格验证 TaskRecord、Worktree、Checkpoint、RunContext 和任务锁，只将 A 放回 `queued`。C 完成并释放槽位后 A 再次运行；`M3Runner.resume` 从原 Checkpoint 恢复到 Brainstorming，`spec_version == 2`。没有复制或更改 M3 的修订、反馈路由和恢复规则。

## 清理结果

自动化验收覆盖并通过：

- 非终态拒绝清理；
- Archive 缺失拒绝清理；
- 活动锁存在拒绝清理；
- 未归档工作区修改拒绝清理；
- 合法终态任务移除 Worktree；
- `sdd/<task-id>` 分支、`runs/<run-id>` Archive 和终态 TaskRecord 保留；
- 清理一个任务时另一个任务的 Worktree 仍存在。

## 完整测试与 CI

2026-07-22 本地最终验证：

```text
.venv/bin/python -m pytest -q
81 passed in 8.80s

.venv/bin/python -m compileall -q src tests
passed (no output)

git diff --check
passed (no output)
```

全量 81 项包含原有 M1、M2、M3 测试和新增 M4 测试，因此兼容性回归通过。按任务边界未 push、未创建 PR，远端 CI 尚未触发；本地执行了与 CI 对等的完整 Pytest、compileall 和 diff 检查。创建 PR 后仍应以远端 CI 结果作为最终合入门禁。

## 安全边界与结论

验收期间没有 merge、push、PR、自动部署、`git reset`、`git clean`、强制删除 Worktree 或自动删除任务分支。没有新增 WorktreeRecord、SchedulerState、TaskContext、JobRecord 或 WorkerRecord，也没有实现任何 M5 及以后能力。

最终结论：**M4 本地验收通过，具备创建 M4 PR 的代码与文档条件；远端 CI 待 PR 创建后执行。**

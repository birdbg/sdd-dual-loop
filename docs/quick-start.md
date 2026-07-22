# M4 快速开始

## 安装

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[test]'
```

目标仓库必须是干净的 Git 主 Worktree，并具有 `main`（或提交时明确指定的 `base_ref`）。

## 初始化、提交与启动

```python
from sdd.scheduler import LocalScheduler

scheduler = LocalScheduler(
    runs_root="/workspace/sdd-state/runs",
    worktrees_root="/workspace/sdd-worktrees",
    max_concurrency=2,
)
scheduler.submit_task("/absolute/path/to/repository", "customer-search", run_id="run-customer-search")
scheduler.submit_task("/absolute/path/to/repository", "health", run_id="run-health")
scheduler.submit_task("/absolute/path/to/repository", "date-format", run_id="run-date-format")
started = scheduler.start_ready_tasks()  # customer-search、health
print(scheduler.get_scheduler_summary())  # date-format 仍 queued
print([(item.task_id, item.status) for item in scheduler.list_tasks()])
```

获得 `running` 后，用 `prepare_run_context` 将现有 M3 上下文绑定到 Worktree，再通过 `runner_for(task)` 取得复用的 `M3Runner`：

```python
task = scheduler.get_task("customer-search")
context = scheduler.prepare_run_context(task.task_id, "新增客户名称模糊搜索")
runner = scheduler.runner_for(task)
# 按 M3 的 Purpose/Brainstorming/Plan/Verify/Dev/Test/Refactor API 推进 context。
```

## 人工暂停、恢复与归档

M3 把 RunContext 持久化为 `awaiting_human` 或 `blocked` 后：

```python
scheduler.sync_from_context(task.task_id, context)  # 释放槽位
# 对 awaiting_human 使用 runner.apply_spec_change(...)
# 对 blocked 使用 runner.unblock(...)
scheduler.resume_task(task.task_id)                 # 只进入 queued
scheduler.start_ready_tasks()                       # 有槽位才恢复 running
```

两个根目录必须位于目标仓库及所有已登记 Git Worktree 之外。状态位于 `<runs_root>/tasks.yaml`，运行上下文和 Checkpoint 分别位于 `<runs_root>/<run-id>/run-context.yaml` 与 `checkpoint.yaml`，归档入口是 `<runs_root>/<run-id>/archive.md`。

终态任务只有在 Archive 存在、锁已释放，且当前 Diff、变化路径和文件哈希均能被该运行的 Archive 与操作证据完整解释时才能清理：

```python
scheduler.cleanup_task(task.task_id)
```

这只移除 Worktree；分支、`runs/<run-id>` 和终态 TaskRecord 均保留。

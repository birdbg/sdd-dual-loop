# SDD Dual Loop M4 使用手册

## 1. 系统定位

本框架把经过验证的需求变更送入受约束的软件开发循环。M4 面向一台机器、一个源仓库中的多个独立任务：每个任务有物理隔离的 Git Worktree 和持久化运行证据。

## 2. 双环结构说明

意图环是 Purpose → Brainstorming → Plan → Verify → Archive；执行环是 Plan → Dev → Test → Refactor → Plan。Plan 是唯一共享桥梁。M4 是外部运行管理层，不新增主节点。

## 3. M1 至 M4 能力边界

- M1：固定双环模型和最小顺序路径。
- M2：真实仓库发现、受限工具、测试反馈与分支隔离。
- M3：Checkpoint、RunContext、安全恢复、Change Spec、跨环反馈与修订归档。
- M4：Worktree、TaskRecord、注册表、锁、FIFO、并发槽位和终态清理。

## 4. 环境要求

Python 3.11+、Git（支持 `git worktree`）和目标 FastAPI/Python 仓库。目标路径必须是主 Worktree 的 Git 顶层目录；`base_ref` 必须可解析为提交。

## 5. 安装步骤

```bash
git clone <framework-url> sdd-dual-loop
cd sdd-dual-loop
python3.11 -m venv .venv
.venv/bin/pip install -e '.[test]'
```

## 6. 仓库初始化

```bash
cd /path/to/target
git init -b main
git add .
git commit -m 'baseline'
```

确保 `git status --porcelain` 没有意外修改。M4 不切换主仓库分支。

## 7. 创建第一个单任务

```python
from sdd.scheduler import LocalScheduler
scheduler = LocalScheduler(
    "/workspace/sdd-state/runs", "/workspace/sdd-worktrees", max_concurrency=2
)
task = scheduler.submit_task("/path/to/target", "health", run_id="run-health")
print(task.worktree_path, task.branch)
```

`runs_root` 与 `worktrees_root` 必须位于目标仓库及所有已登记 Git Worktree 之外；调度器会在创建目录前拒绝仓库内路径。

## 8. 提交多个任务

```python
for task_id, run_id in [("customer-search", "run-a"), ("health", "run-b"), ("date-format", "run-c")]:
    scheduler.submit_task("/path/to/target", task_id, run_id=run_id)
```

## 9. 设置 max_concurrency

`LocalScheduler(..., max_concurrency=2)` 允许最多两个 `starting`/`running` 任务。值必须大于零；首版是受控状态机，不启动线程池、Worker 或守护进程。

## 10. 查看任务列表

```python
for task in scheduler.list_tasks():
    print(task.task_id, task.status, task.run_id)
```

## 11. 查看任务状态

```python
print(scheduler.get_task("health"))
print(scheduler.get_scheduler_summary())
```

状态只有 `queued`、`starting`、`running`、`awaiting_human`、`blocked`、`completed`、`failed`、`cancelled`。

## 12. 查看 Worktree 目录

```python
from pathlib import Path
task = scheduler.get_task("health")
print(Path(task.worktree_path).resolve())
```

固定形状是 `<worktrees_root>/<task-id>`。

## 13. 查看任务分支

```bash
git -C /path/to/target worktree list
git -C /path/to/target branch --list 'sdd/*'
```

分支固定为 `sdd/<task-id>`。

## 14. 查看 RunContext

```python
from sdd.state_store import load_run_context
context = load_run_context(task.run_id, scheduler.runs_root)
print(context.status, context.current_node)
```

## 15. 查看 Checkpoint

```python
from sdd.checkpoint import load_checkpoint
checkpoint = load_checkpoint(task.run_id, scheduler.runs_root)
print(checkpoint.last_completed_node, checkpoint.resume_allowed)
```

## 16. 查看 Spec、Plan、Verify 修订

```bash
ls runs/run-a/spec-r*.yaml runs/run-a/plan-r*.yaml runs/run-a/verify-r*.yaml
```

每个 run_id 使用独立目录，修订文件不可覆盖。

## 17. 处理 awaiting_human

M3 持久化人工边界后，把结果同步给调度器：

```python
scheduler.sync_from_context(task.task_id, context)
assert scheduler.get_task(task.task_id).status == "awaiting_human"
```

该状态释放槽位，但保留 Worktree、Checkpoint 和锁以外的全部证据。

## 18. 执行人工 Change Spec

```python
runner = scheduler.runner_for(task)
context = runner.apply_spec_change(
    context,
    reason="明确模糊匹配语义",
    changes=["不区分大小写的包含匹配"],
    approved_by="product-owner",
)
```

Change Spec 仍由 M3 执行并返回 Brainstorming，不由 TaskRecord 表达业务状态。

## 19. 恢复任务

```python
scheduler.resume_task(task.task_id)  # awaiting_human/blocked → queued
scheduler.start_ready_tasks()        # FIFO 且受并发限制
task = scheduler.get_task(task.task_id)
context = scheduler.runner_for(task).resume(task.run_id, task.worktree_path)
```

## 20. 解除 blocked 任务

```python
runner = scheduler.runner_for(task)
context = runner.resume(task.run_id, task.worktree_path)
context = runner.unblock(context, target_node="verify", reason="依赖已恢复")
scheduler.resume_task(task.task_id)
```

解除必须有审计原因；不能把终态任务恢复为 running。

## 21. 取消任务

```python
scheduler.cancel_task("date-format")
```

只允许 queued、running、awaiting_human、blocked；取消不回滚代码、不删归档、不删分支。

## 22. 清理终态任务

```python
scheduler.cleanup_task("health")
```

必须是终态、`cleanup_allowed=true`、Archive 存在、Checkpoint/RunContext 的 run_id 一致且没有锁。若 Worktree 含正常的未提交开发修改，当前 Diff 必须与 `code-diff.patch` 完全一致，所有变化路径必须存在于 ToolOperation/CodeChange，最终文件哈希也必须一致；任何额外未跟踪文件都会拒绝清理。验证通过后以普通（非 `--force`）方式移除 Worktree。

## 23. 查看 Archive

```python
print((scheduler.runs_root / task.run_id / "archive.md").read_text())
```

同目录还保留测试、工具操作、路由、修订和代码 diff。

## 24. 常见错误与排查

- “repository must be the Git top-level”：传入仓库根目录，不要传子目录。
- “task branch already exists”：该 task_id 已经使用；框架不会替你删除分支。
- “already locked”：先确认记录的 PID；陈旧锁也不会静默覆盖，显式 `release_task_lock` 会写入 `stale-locks.log`。
- “persisted status does not match”：检查 `tasks.yaml`、Checkpoint 和 RunContext 是否属于同一 run_id。
- “unarchived changes”：检查当前 Diff 是否仍等于 `code-diff.patch`，以及路径和最终 SHA-256 是否都有本次运行证据；额外文件或归档后的改动必须人工处理。

## 25. 安全边界

框架不运行 `git reset`、`git clean`，不强制删除 Worktree，不自动 merge、push、创建 PR 或删除任务分支。任务工具只接收该任务的 `worktree_path`；主仓库不应被任务代码修改。

## 26. 当前不支持的功能

不支持分布式 Worker、消息队列、Redis/数据库、Web 管理端、多 Agent、多模型/Prompt/Skill/Tool Registry、多仓库协同、自动 PR/merge/push/deploy、企业权限、多租户、跨机器恢复、长期记忆或知识图谱。

## 27. 完整命令示例

```python
from sdd.scheduler import LocalScheduler
scheduler = LocalScheduler(
    runs_root="/workspace/sdd-state/runs",
    worktrees_root="/workspace/sdd-worktrees",
    max_concurrency=2,
)
scheduler.submit_task("/path/to/target", "health", run_id="run-health")
scheduler.start_ready_tasks()
task = scheduler.get_task("health")
context = scheduler.prepare_run_context(task.task_id, "新增 GET /health")
runner = scheduler.runner_for(task)
# 使用 M3Runner 现有 API 填充并推进 Purpose、Brainstorming、Plan、Verify 与执行环。
print(scheduler.get_scheduler_summary())
```

## 28. 三任务演示案例

提交 A `customer-search`、B `health`、C `date-format`，并发设为 2。第一次 `start_ready_tasks()` 让 A/B running，C queued。A 的 M3 RunContext 进入 awaiting_human 并 `sync_from_context` 后释放槽位；再次调度让 C running。B failed 不改变 C。A 经 `apply_spec_change` 和 `resume_task` 回到 queued，待 C/其他任务释放槽位后再次启动，并用 `runner.resume(run_id, worktree_path)` 从原 Checkpoint 恢复。最后逐个生成 Archive 和清理终态 Worktree；三个 `runs/<run-id>` 与三个 `sdd/<task-id>` 始终独立。

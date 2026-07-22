# SDD Dual Loop

一个以“意图环 + 执行环”为核心的软件开发工作流实验项目。

当前里程碑是 **M4：本地多任务物理隔离与受控并发**。M4 在不改变双环节点的前提下，用 Git Worktree、严格本地注册表、任务锁和 FIFO 槽位管理复用 M3Runner。

- [快速开始](docs/quick-start.md)
- [完整使用手册](docs/user-guide.md)
- [M4 范围与完成标准](docs/milestones/M4.md)
- [M4 验收记录](docs/milestones/M4-acceptance.md)

架构总纲见 [`docs/dual-loop-architecture.md`](docs/dual-loop-architecture.md)。该文件是项目“宪法”，MVP 实施期间不随意修改。

## 当前状态

每个任务的 M3 状态保存在框架的 `runs/<run-id>/` 目录，外部任务记录保存在 `runs/tasks.yaml`。恢复会严格核对 TaskRecord、Worktree、Checkpoint、RunContext、当前 Git 分支、基线提交和可解释的工作区修改；恢复只重新排队，不绕过并发限制。

系统支持单仓库内的本机多任务，每个任务使用 `.sdd-worktrees/<task-id>` 和 `sdd/<task-id>`。框架不会自动 merge、push、创建 PR 或删除任务分支。

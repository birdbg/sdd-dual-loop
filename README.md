# SDD Dual Loop

一个以“意图环 + 执行环”为核心的软件开发工作流实验项目。

当前里程碑是 **M3：可恢复的变更驱动双环**。框架在 M2 的仓库扫描、独立分支、受限文件工具和真实测试之上，支持反馈跨环回流、人工 Change Spec、Checkpoint 保存、RunContext 本地 YAML 持久化、安全恢复、多次人工规格修订，以及 Spec、Plan、Verify 的完整修订历史；边界见 [`docs/milestones/M3.md`](docs/milestones/M3.md)，验收记录见 [`docs/milestones/M3-acceptance.md`](docs/milestones/M3-acceptance.md)。

架构总纲见 [`docs/dual-loop-architecture.md`](docs/dual-loop-architecture.md)。该文件是项目“宪法”，MVP 实施期间不随意修改。

## 当前状态

M3 状态保存在框架的 `runs/<run-id>/` 目录。恢复会严格核对 Checkpoint、RunContext、当前 Git 分支、基线提交和可解释的工作区修改；它只返回恢复后的上下文，不会自动执行节点。

系统仍然只处理单仓库、单任务、单工作分支并顺序执行。首次运行使用 `git switch -c sdd/<run-id>` 创建分支，不使用 Git Worktree；恢复不会重复创建已有分支。运行结束后目标仓库仍停留在工作分支，框架不会自动切回、merge 或 push。

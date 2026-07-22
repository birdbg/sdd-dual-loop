# SDD Dual Loop

一个以“意图环 + 执行环”为核心的软件开发工作流实验项目。

当前里程碑是 **M2：未知 FastAPI 仓库的最小自主闭环**。框架可从仓库证据发现源码、入口、路由、测试和依赖配置，在独立 Git 分支上通过受限文件工具开发，并记录测试返工和完整归档；边界见 [`docs/milestones/M2.md`](docs/milestones/M2.md)。

架构总纲见 [`docs/dual-loop-architecture.md`](docs/dual-loop-architecture.md)。该文件是项目“宪法”，MVP 实施期间不随意修改。

## 当前状态

M2 支撑组件位于 `sdd.repository`、`sdd.workspace` 和 `sdd.tools`。执行环根据真实测试输出分类回流，最多返工两次；不会自动合并或推送目标仓库。

M2 当前使用 `git switch -c sdd/<run-id>` 创建隔离分支，不使用 Git Worktree。运行结束后目标仓库仍停留在该工作分支，框架不会自动切回原分支；请在检查或处理 Diff 后由使用者手动切换分支。

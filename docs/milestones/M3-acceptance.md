# M3 验收记录

## 案例与初始歧义

固定案例为“为订单接口增加按客户名称搜索功能”。`spec-r1.yaml` 故意没有确定大小写、精确或包含匹配、多结果返回方式，以及无结果使用空列表还是 404。Verify 明确拒绝该规格并产生 `spec_ambiguous` 反馈。

## 路由与人工变更

RoutingDecision 记录 `verify → change_spec`，运行进入 `awaiting_human`。产品负责人通过 `apply_spec_change` 人工批准 SC-001，明确：不区分大小写、包含匹配、返回全部匹配结果、无结果返回 HTTP 200 和空列表。Change Spec 没有修改 Purpose，也没有直接进入 Dev，而是返回 Brainstorming。

`spec-r1.yaml` 保留原始歧义；`spec-r2.yaml` 包含四项人工决定。新的 `plan-r2.yaml` 关联 Spec r2，新的 `verify-r2.yaml` 同时关联 Spec r2 与 Plan r2。小型连续性测试再次进入人工边界，生成 SC-002 与 `spec-r3.yaml`，证明实现没有写死一次变更。

## 两次中断与恢复

- 第一次中断点：Verify 路由到 change_spec，Checkpoint 状态为 `awaiting_human`。
- 第一次恢复点：`resume_run` 从 change_spec 恢复，仅返回 RunContext；随后人工执行 SC-001。
- 第二次中断点：Plan r2 已完成，Checkpoint 当前节点为 Verify。
- 第二次恢复点：从 Verify 继续，Brainstorming 和 Plan 没有重复执行，工作分支也没有重复创建。

恢复前检查目标路径是 Git 顶层目录、当前分支等于 `sdd/order-search`、基线提交仍存在且属于当前分支历史，并拒绝所有未被 tool_operations 或已有运行状态解释的修改。恢复过程没有 switch、reset、clean、checkout、merge 或 push。

## 执行、测试与归档

Dev 实现客户名称 `casefold()` 后的包含搜索，返回全部结果；无匹配自然返回空列表和 HTTP 200。真实 Pytest 首次执行通过。Refactor 判定实现已经最小且不做行为变更，随后真实 Pytest 复测再次通过。

归档位于测试运行的 `runs/order-search/`，包含所有 Spec、Plan、Verify 修订，SpecChange、RoutingDecision、Checkpoint、RunContext、测试执行、Refactor 结果和代码 Diff。Archive 明确目标仓库仍停留在工作分支，系统不会自动切回、merge 或 push。

## CI 与边界

最终本地验证命令：

```text
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src tests
git diff --check
```

CI 等价测试结果通过。M4 能力没有前移：没有 Worktree、并发、队列、Worker、数据库、多仓库、多 Agent、多模型、Registry、Web 管理页面、PR、merge、push 或部署能力。

## 结论

passed

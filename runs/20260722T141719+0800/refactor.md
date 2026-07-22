# Refactor

## 检查

Dev 后的三个非法 ID 测试分别覆盖 `0`、`-1` 和非整数，但测试结构完全相同，存在不必要的重复。

## 实际修改

使用 `pytest.mark.parametrize` 合并为一个参数化测试，同时保留三个独立用例。生产代码未作行为变更。

## 复测

- 命令：`.venv/bin/python -m pytest examples/fastapi-user-query/tests -q`
- 退出码：`0`
- 结果：`6 passed, 1 warning in 0.10s`

重构前后均为六个 pytest case，需求覆盖没有减少。

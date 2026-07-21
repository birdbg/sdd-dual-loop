# FastAPI User Query 示例

这是 M1 的首个真实验证案例。它模拟一个已经存在的小型 FastAPI 项目：项目当前能够列出内存中的用户，但尚未提供按用户 ID 查询的接口。

双环流程需要读取 [`requirement.md`](requirement.md)，在不扩大范围的前提下完成新接口、执行单元测试，并保存全过程产物。案例基线不得提前实现 `GET /users/{user_id}`，否则无法验证 Development 节点是否真正修改代码。

## 当前基线

- `GET /users` 返回已有用户列表
- 用户数据保存在本地内存中
- 已有测试只验证基线列表接口
- 目标查询接口及其测试尚未实现

## 运行基线测试

在仓库根目录安装测试依赖后执行：

```bash
python -m pytest examples/fastapi-user-query/tests
```

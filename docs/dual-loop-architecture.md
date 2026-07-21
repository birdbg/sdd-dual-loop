# 双环架构总纲

> 本文件是项目的架构“宪法”。以下框架在 MVP 实施期间保持冻结，不随意修改。

## 1. 意图环

```text
Purpose
→ Brainstorming
→ Plan
→ Verify
→ Archive
→ Purpose
```

## 2. 执行环

```text
Plan
→ Dev
→ Test
→ Refactor
→ Plan
```

## 3. 双环反馈

```text
实现问题
→ Dev / Test / Refactor

计划问题
→ Plan

规格问题
→ Change Spec
→ Brainstorming
→ Plan
→ Verify

目标问题
→ Purpose
```

## 4. 核心产物

- Purpose
- BrainstormResult
- Spec
- Plan
- CodeChange
- TestResult
- RefactorResult
- VerifyResult
- ExecutionFeedback
- SpecChange
- Archive

## 5. 工具定位

| 工具 | 定位 |
| --- | --- |
| OpenSpec | 意图环 |
| Superpowers | 执行环 |
| Harness | 测试支撑、用例和执行约束 |
| Khafu | 协作智能体和编排补充 |
| OpenMole | 扩展工具能力 |

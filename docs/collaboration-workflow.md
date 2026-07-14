# 五人协作工作流

## 分支

- 成员1：`feat/integration-*`
- 成员2：`feat/handwriting-*`
- 成员3：`feat/vectorization-*`
- 成员4：`feat/ui-*`
- 成员5：`feat/device-*`

## 每个模块的最低结构

```text
src/<module>/README.md
src/<module>/__init__.py
src/<module>/examples/
tests/<module>/
```

## 合并前检查

1. 模块能在自己的目录中独立运行。
2. 输入输出符合 [统一轨迹接口](stroke-interface.md)。
3. 示例和测试已更新。
4. Pull Request 说明负责人、接口版本、测试结果和对其他模块的影响。
5. 成员1完成一次集成测试后再合并到 `main`。

## 每周集成

每周固定从 `main` 拉取所有模块，使用同一份样例任务跑通：文字 → 笔迹/图形 → 页面排版 → 轨迹导出 → 设备任务。失败项记录到 Issue，并标明负责人和截止日期。

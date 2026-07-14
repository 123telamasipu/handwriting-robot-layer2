# 输入输出数据格式 v0.1

所有模块交换 JSON 数据，文本编码统一为 UTF-8。协议字段采用 `snake_case`。

## 任务输入

```json
{
  "schema_version": "0.1",
  "task_id": "task-20260714-001",
  "task_type": "text",
  "payload": { "text": "你好" },
  "options": { "speed": 50, "scale": 1.0 },
  "created_at": "2026-07-14T10:00:00+08:00"
}
```

`task_type` 初步支持 `text`、`trajectory`、`file`。实际范围应在模块设计完成后确认。

## 状态输出

```json
{
  "schema_version": "0.1",
  "task_id": "task-20260714-001",
  "state": "running",
  "progress": 0.35,
  "message": "正在书写第 2 个字符",
  "error": null,
  "updated_at": "2026-07-14T10:00:05+08:00"
}
```

状态值见 `state-machine.md`。协议变更需提升版本号并在 Pull Request 中注明兼容性。

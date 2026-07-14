# 任务状态机 v0.1

```text
created -> validating -> ready -> running -> completed
              |           |         |
              +-----------+---------+-> failed
                            running <-> paused
                            running ----> cancelled
```

| 状态 | 含义 |
|---|---|
| `created` | 已接收任务 |
| `validating` | 校验格式和参数 |
| `ready` | 可下发设备 |
| `running` | 设备执行中 |
| `paused` | 暂停，可恢复 |
| `completed` | 成功完成 |
| `failed` | 失败，需携带错误信息 |
| `cancelled` | 用户或系统取消 |

状态迁移应记录时间、触发者和原因。终态为 `completed`、`failed`、`cancelled`。

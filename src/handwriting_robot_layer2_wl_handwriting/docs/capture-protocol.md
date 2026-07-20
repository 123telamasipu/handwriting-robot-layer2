# 统一采集数据与传输协议 v1.0

## 用途

本协议统一手机触控笔、手指、浏览器鼠标、桌面鼠标和数位板的输入数据。所有输入最终转换为 `RecordingBuffer`、`Stroke` 和 `StrokePoint`，再由 `SampleStore` 保存，避免为每种设备建立互不兼容的数据格式。

该协议描述的是成员2内部的“采集样本”数据，不替代模块对外输出的 `StrokeDocument` v0.1。

## 提交格式

完整示例见 [`../examples/capture_submission.json`](../examples/capture_submission.json)。

```json
{
  "schema_version": "1.0",
  "writer_id": "user_01",
  "writer_name": "测试用户",
  "character": "你",
  "variant": 1,
  "status": "complete",
  "client": {
    "application": "mobile_web",
    "user_agent": "Mozilla/5.0 ...",
    "viewport": {
      "width_px": 390,
      "height_px": 844,
      "device_pixel_ratio": 3
    },
    "pointer_types": ["touch"]
  },
  "strokes": [
    {
      "points": [
        {
          "x": 0.15,
          "y": 0.20,
          "t_ms": 0,
          "pressure": 0.5,
          "x_tilt": 0,
          "y_tilt": 0,
          "rotation": 0,
          "tangential_pressure": 0,
          "source": "touch"
        }
      ]
    }
  ]
}
```

## 字段约定

| 字段 | 类型 | 约定 |
|---|---|---|
| `schema_version` | string | 当前固定为 `1.0` |
| `writer_id` | string | 必填，用作书写者目录标识 |
| `writer_name` | string | 可选姓名或脱敏备注 |
| `character` | string | 单个 Unicode 字符，并且必须在目标字符集中 |
| `variant` | integer | `1`～`5` |
| `status` | string | `draft` 或 `complete` |
| `client` | object | 浏览器和视口等采集环境信息 |
| `strokes` | array | 按落笔顺序排列的笔画 |

## 轨迹点约定

- `x`、`y`：归一化坐标，范围为 `[0.0, 1.0]`，原点位于画布左上角。服务端会把轻微越界值限制回有效范围。
- `t_ms`：从当前样本首次落笔开始计算的毫秒时间，必须为非负整数。
- `pressure`：归一化压力，范围为 `[0.0, 1.0]`；设备不支持压感时使用 `0.5`。
- `x_tilt`、`y_tilt`：笔相对于屏幕的倾角；设备不支持时使用 `0.0`。
- `rotation`：触控笔旋转角；浏览器 Pointer Events 的 `twist` 会映射到此字段。
- `tangential_pressure`：切向压力；设备不支持时使用 `0.0`。
- `source`：统一输入来源，允许 `touch`、`pen`、`mouse` 或 `tablet`。

每次落笔到抬笔形成一个 `Stroke`。客户端不得把多个独立落笔合并成同一笔画。

## 输入来源映射

| 原始输入 | 统一 `source` |
|---|---|
| 浏览器手指触控 | `touch` |
| 浏览器 Pointer Events `pen` / `stylus` | `pen` |
| 浏览器或桌面鼠标 | `mouse` |
| PySide6 `QTabletEvent` | `tablet` |

## HTTP 接口

手机服务使用同源 JSON API：

| 方法与路径 | 用途 |
|---|---|
| `GET /api/health` | 服务健康检查 |
| `GET /api/config` | 获取目标字符集、变体范围和默认书写者 |
| `GET /api/progress` | 获取指定书写者完成进度 |
| `GET /api/sample` | 读取指定字符和变体的草稿或正式样本 |
| `POST /api/sample` | 保存草稿或正式样本 |

访问令牌通过 URL 查询参数 `token` 或请求头 `X-Access-Token` 传递。JSON 统一使用 UTF-8 和 `snake_case` 字段。

## 校验与限制

- 请求体最大 5 MiB。
- 单个样本最多 256 个笔画、50000 个轨迹点。
- 坐标、压力、倾角和旋转必须是有限数值，拒绝 `NaN` 和无穷值。
- 时间最大为 24 小时。
- 浏览器环境字符串会截断到固定长度，避免把任意大文本写入样本。
- 服务端根据字符重新读取目标字符元数据，不信任客户端提交的序号、字频或笔画数。
- 所有保存操作复用 `SampleStore` 的原子 JSON 写入方式。

## 保存后的样本

服务端会把统一轨迹写入现有样本格式，并额外保存经过清理的 `capture_context`。常用字段包括：

```json
{
  "coordinate_system": {
    "type": "normalized",
    "x_range": [0.0, 1.0],
    "y_range": [0.0, 1.0],
    "origin": "top-left"
  },
  "input_sources": ["touch"],
  "capture_context": {
    "application": "mobile_web"
  }
}
```

桌面旧样本没有 `capture_context` 时仍然有效，协议修改保持向后兼容。未来出现不兼容字段调整时必须提升 `schema_version` 并同步更新示例和测试。

# 统一轨迹接口 v0.1

文字模块和图形模块都输出相同的 `StrokeDocument`。排版模块负责把局部轨迹放到页面坐标系；设备模块只接收排版后的有序笔画，不关心文字或图形来源。

```json
{
  "schema_version": "0.1",
  "type": "stroke_document",
  "source": "handwriting",
  "user_id": "user_01",
  "page": { "width_mm": 210.0, "height_mm": 297.0 },
  "strokes": [
    {
      "points": [[10.0, 20.0], [10.4, 20.3]],
      "pen_down": true,
      "order": 1
    }
  ]
}
```

排版完成后，每个页面任务还必须包含：

- `origin_mm`：页面原点
- `scale`：缩放比例
- `rotation_deg`：旋转角度
- `region`：书写区域边界
- `strokes`：按设备执行顺序排列的笔画

## 模块交付规则

每个模块目录必须有自己的 README、示例输入、示例输出和最少一组测试。模块可以独立运行，但不得把设备、界面或其他模块代码复制进来。

## 兼容性

接口字段变更必须更新版本号、示例和测试。成员1负责合并接口变更；设备模块拒绝没有 `schema_version` 的任务。

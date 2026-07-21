# 标准有序笔画骨架与风格化轨迹生成说明

## 用途

本步骤解决“未录字符如何生成轨迹”的接口和基线算法问题：输入标准字符的有序笔画骨架及用户风格档案，输出符合仓库 `StrokeDocument` v0.1 的毫米坐标轨迹。

当前实现是可解释、可复现的几何基线，不是训练完成的生成模型。它用于先打通“标准骨架 → 用户风格 → 写字机轨迹”链路，并为后续更复杂的少样本模型提供统一输入输出格式。

## 骨架格式

骨架库采用 UTF-8 JSON，类型为 `ordered_stroke_skeleton_library`。每个字符必须包含：

- 单个 Unicode 字符及对应 `U+XXXX` 编码；
- 连续且从 1 开始的笔画顺序；
- 每笔的 `stroke_type`；
- 至少两个 `[x, y]` 点；
- 左上角原点、`[0, 1]` 范围的标准字形坐标；
- 数据来源、授权方式和是否为权威数据。

简化示例：

```json
{
  "character": "永",
  "unicode": "U+6C38",
  "stroke_count": 5,
  "strokes": [
    {
      "order": 1,
      "stroke_type": "dot",
      "points": [[0.48, 0.10], [0.52, 0.15], [0.51, 0.21]]
    }
  ]
}
```

完整演示库位于 `resources/demo_ordered_stroke_skeletons.json`。其中只包含手工绘制的“永”“文”，仅用于程序联调，不是权威字形或正式笔顺数据集。

## 生成流程

1. 校验骨架库的坐标、字符、笔画数量和顺序。
2. 读取用户风格档案中的字面大小、重心和变化尺度。
3. 读取横画角度、竖画倾斜和笔画直线度。
4. 对标准骨架按弧长重新采样。
5. 保持笔画首尾和整体结构，施加轻微曲线与种子控制的变化。
6. 按目标字符尺寸转换成毫米坐标。
7. 保留标准骨架的笔画边界与笔顺，生成 `StrokeDocument`。
8. 根据用户归一化速度和停顿生成辅助 `motion_hints`。

`motion_hints` 只是上层风格提示。设备模块仍需根据电机速度、加速度、机械行程和安全限制重新规划，不能直接把提示当作设备指令。

## 运行方法

使用公开的合成风格示例：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_style_generator.cmd `
  src\handwriting_robot_layer2_wl_handwriting\examples\style_generation_request.json `
  runtime_data/output/style_generated_document.json
```

真实用户默认风格档案位于：

```text
runtime_data/handwriting/style_profiles/<writer_id>/style_profile_v1.json
```

请求中可以省略 `style_profile_path`，程序会按 `user_id` 从上述位置加载。正式骨架库接入后，通过 `skeleton_library_path` 指定其路径；不指定时只会加载演示骨架库。

## 随机种子

- 相同风格档案、骨架、文本、参数和 `random_seed` 得到相同结果；
- 更换种子会改变字面尺寸、重心、倾斜和轻微曲线；
- `variation_strength=0` 可关闭用户内随机变化，只保留风格档案的中位数特征；
- `glyph_occupancy` 控制字符实际轨迹占目标字框的比例，默认 `0.78`；
- 随机变化不会调整笔画数量、笔顺或笔画边界。

`char_width_mm` 和 `char_height_mm` 表示目标字符框，而不是采集窗口大小。生成器使用用户宽高比和相对尺寸波动填充该字框，避免把采集界面中约 28% 的字面占比直接复制到纸面后导致输出过小。

## 输出兼容性

顶层字段继续遵循 `StrokeDocument` v0.1：`schema_version`、`type`、`source`、`user_id`、`page` 和 `strokes`。

额外的 `generation` 字段记录生成方法、风格指纹、骨架来源、字符到笔画序号映射、运动提示、警告和限制。不了解扩展字段的下游模块可以忽略它。

## 当前限制

- 演示骨架只有“永”“文”，不能覆盖第一阶段 1000 个常用汉字；
- 需要接入授权清晰、笔顺正确且保留笔画边界的正式骨架库；
- 几何基线能够迁移整体风格，但不能学习复杂偏旁比例和特定笔画写法；
- 未经过真实写字机误差、速度和可读性评估；
- 不能使用普通字体轮廓直接代替中心线笔画骨架。

## 完成条件

- 骨架库来源和授权信息齐全；
- 所有目标字符通过格式、笔画顺序和坐标校验；
- 相同种子生成结果可复现；
- 输出笔画顺序和骨架一致；
- 对生成字符进行可读性和用户相似度人工评估；
- 交给设备模块前完成页面边界和机械限制检查。

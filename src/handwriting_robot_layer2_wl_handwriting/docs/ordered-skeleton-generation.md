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
7. 当前安全基线保留标准楷书骨架的笔画边界与笔顺，生成 `StrokeDocument`。
8. 根据用户归一化速度和停顿生成辅助 `motion_hints`。

`motion_hints` 只是上层风格提示。设备模块仍需根据电机速度、加速度、机械行程和安全限制重新规划，不能直接把提示当作设备指令。

## 运行方法

使用公开的合成风格示例：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_style_generator.cmd `
  src\handwriting_robot_layer2_wl_handwriting\examples\style_generation_request.json `
  runtime_data/output/style_generated_document.json
```

真实用户默认个人字体档案位于：

```text
runtime_data/handwriting/style_profiles/<writer_id>/personal_font_profile_v1.json
```

请求中可以省略档案路径，程序会按 `user_id` 自动查找上述清单，并校验清单引用的 `style_profile_v1.json` 和 `automatic_alignment_v1.json` 的 SHA-256、书写者 ID 与样本一致性。也可显式指定：

```json
{
  "user_id": "user_01",
  "text": "你好世界",
  "personal_font_profile_path": "runtime_data/handwriting/style_profiles/user_01/personal_font_profile_v1.json",
  "hanzi_writer_package_dir": "runtime_data/external/hanzi-writer-data-2.0.1"
}
```

为兼容旧调用，显式提供 `style_profile_path` 时仍走原来的整体风格生成，不会自动启用同目录个人字体清单。`personal_font_profile_path` 与 `style_profile_path` 不能同时提供。正式骨架库通过 `skeleton_library_path` 指定，汉字也可通过 `hanzi_writer_package_dir` 按需加载；两者不能同时提供。

如果同目录存在 `personal_font_deployment_v1.json`，生成器会优先加载该文件，并校验其引用的个人字体清单和批量评估报告哈希。该策略可以让某些高/中置信字符因实际评估退化而自动回退。显式指定时使用 `personal_font_deployment_path`；它不能与 `personal_font_profile_path` 或 `style_profile_path` 同时使用。

## 个人字体生成策略

- 已采且自动评估通过：使用该字符实测的字面宽高、重心、横画角度、竖画倾斜和直线度，并与用户整体先验进行保守融合；
- 已采但自动评估发现退化：即使自动对齐为 `high`/`medium`，也强制使用安全回退；
- 已采但自动对齐为 `low`：忽略不可靠的字符级对应，使用“标准骨架 + 用户整体风格”的安全回退；
- 未采字符：使用标准骨架和用户整体先验迁移，无需逐字补录；
- 三类策略都保留标准骨架的笔画数量、顺序和边界，不生成连笔曲线；
- 输出 `generation.characters[]` 会记录 `personal_font_strategy`、`alignment_confidence`、`deployment_policy_applied` 和始终为 `false` 的 `ligature_applied`，便于下游追踪来源。

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
- 几何基线能够迁移整体风格，并为高/中置信已采字符复用字符级布局和倾斜特征，但不能重建真实样本内部的复杂偏旁形变或连笔曲线；
- 人类日常行书可能连写、少抬笔或改变部件形态；当前生成器只把楷书骨架作为结构底稿，尚未合成用户专属行书连接轨迹；
- 后续应从用户真实样本学习“哪些笔画可以连接、连接曲线如何经过、连接时是否抬笔”，不能把相邻楷书笔画端点直接连成直线；
- 未经过真实写字机误差、速度和可读性评估；
- 不能使用普通字体轮廓直接代替中心线笔画骨架。

## 完成条件

- 骨架库来源和授权信息齐全；
- 所有目标字符通过格式、笔画顺序和坐标校验；
- 相同种子生成结果可复现；
- 输出笔画顺序和骨架一致；
- 对生成字符进行可读性和用户相似度人工评估；
- 交给设备模块前完成页面边界和机械限制检查。

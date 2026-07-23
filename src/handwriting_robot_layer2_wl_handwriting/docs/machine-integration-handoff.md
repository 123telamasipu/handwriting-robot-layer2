# 写字机联调轨迹交付包

## 目标和边界

该工具从最终个人字体部署策略中自动挑选具有代表性的字符，生成供成员1和成员5联调审核的 `StrokeDocument`。它只完成成员2范围内的软件接口与几何预检：

- 不控制写字机；
- 不生成串口、G-code 或其他设备命令；
- 不代替正式页面排版；
- 不把 `motion_hints` 当作设备速度或加速度命令；
- 不把软件预检通过解释为可以直接落笔。

交付包始终设置 `machine_ready: false`，状态为 `ready_for_layout_and_device_review`。

## 自动选择场景

默认每类选择两个字符：

- `enhanced`：批量评估改善最大的字符级增强；
- `evaluated_fallback`：自动对齐为高/中置信，但批量评估退化而被强制回退；
- `low_confidence_fallback`：自动对齐低置信的安全回退；
- `unseen_global_style`：没有真实采集样本、使用用户整体风格迁移；
- `mixed_smoke`：从四类中各取一个字符形成混合联调文本。

选择规则是确定性的，相同部署策略、候选字符和参数会得到相同结果。

## 运行

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_machine_handoff.cmd `
  runtime_data\handwriting\style_profiles\user_01\personal_font_deployment_v1.json `
  runtime_data\external\hanzi-writer-data-2.0.1 `
  runtime_data\handwriting\machine_handoff\user01_v1 `
  --unseen-candidates 好世界的字 `
  --characters-per-scenario 2 `
  --random-seed 23
```

输出包括 `handoff_manifest.json` 和 `stroke_documents/` 下的 5 个 `StrokeDocument`。清单记录每个文件的 SHA-256、所选字符、预期策略和软件预检统计。真实用户交付包必须继续保存在被 Git 忽略的 `runtime_data/`。

## 软件预检

每份轨迹会检查：

- `StrokeDocument` v0.1 类型、来源和用户信息；
- 页面尺寸、有限坐标及页面范围；
- 从 1 开始连续的笔画顺序；
- 字符到笔画序号的完整映射；
- 每笔都是明确的 `pen_down` 段；
- 部署策略与实际字符策略一致；
- 未生成行书连接轨迹；
- 每笔都有对应的运动提示且时长、停顿非负；
- 最大相邻点距不超过软件预检阈值；
- 生成器使用了已验证的个人字体部署策略。

这些检查只能证明接口和二维轨迹自洽，不能证明设备运动安全。

## 成员1和成员5必须完成的审核

成员1负责：

- 将模块局部轨迹放入正式页面区域；
- 补充页面任务要求的 `origin_mm`、`scale`、`rotation_deg` 和 `region`；
- 生成集成层的有序设备任务。

成员5负责：

- 使用标定结果完成页面坐标到机器坐标映射；
- 检查机械行程、限位、纸张夹持和笔架高度；
- 把运动提示转换为经过验证的设备速度、加速度和抬笔参数；
- 先进行不落笔空跑和急停验证；
- 使用低速、废纸和单个测试场景开始真实落笔。

只有上述审核完成并有设备测试记录后，集成/设备模块才能自行决定是否把任务标记为可执行。

## 当前 user_01 私有结果

- 场景字符：增强“他一”，高置信评估回退“二火”，低置信回退“图家”，未采字符“好世”，混合文本“他二图好”；
- 共 5 个 `StrokeDocument`、62 笔、1557 个轨迹点；
- 最大相邻点距约 `0.205 mm`；
- 所有坐标在 A4 页面范围内，笔顺连续，部署策略匹配；
- 生成连笔数为 0；
- 软件预检通过，机械和页面审核仍为 `pending`。

# 行书笔画自动对齐说明

## 目标

个人字体库的建立默认不要求逐字人工审核。该工具自动将用户自然手写的实际落笔段与规范楷书有序骨架匹配，支持：

- 一段实际轨迹对应一笔楷书；
- 一段实际轨迹内部合并连续多笔楷书；
- 多段实际轨迹共同对应一笔楷书；
- 对复杂字符仍保持连续、单侧合并的可解释映射，不在自动阶段使用容易产生歧义的多段对多笔映射。

程序使用保持笔顺的动态规划，同时比较组内轨迹形状、合并间隙和映射复杂度，选择总代价最低的完整覆盖方案。它不需要人工逐笔标注训练集。

当用户落笔段数与楷书骨架笔画数相同时，第一版按笔顺逐笔对应；用户段数较少时只搜索“一段合并连续多笔”，用户段数较多时只搜索“连续多段拆分一笔”。不会在同一字符中先合笔再拆笔来凑数量，从而避免大量无意义等价解。

## 使用

推荐直接运行一键个人字体档案命令，它会同时完成风格分析、自动对齐和安全回退配置：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_personal_font_profile.cmd `
  user_01 `
  --hanzi-writer-package-dir runtime_data\external\hanzi-writer-data-2.0.1
```

只单独重跑自动对齐时使用：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_automatic_alignment.cmd `
  runtime_data\handwriting\processed\user_01\style_probe_v1 `
  runtime_data\external\hanzi-writer-data-2.0.1 `
  runtime_data\handwriting\style_profiles\user_01\automatic_alignment_v1.json
```

## 自动化策略

- `high` 和 `medium`：自动接受并进入用户分析档案，不要求人工确认；
- `low`：进入可选复核清单，但不阻塞字体库建立；
- 低置信字符仍可使用现有“楷书骨架 + 用户整体风格变形”安全基线，只是不启用字符级连笔学习；
- 人工审核只用于提高少量复杂字符的效果，不是系统运行的前置条件。

因此即使存在低置信字符，个人字体档案仍可达到 100% 可用：高、中置信字符保留自动对应信息，低置信字符自动回退到明确抬笔的标准骨架风格化轨迹。

当前 `user_01` 的 100 字一键建库结果为：100 字全部无需人工审核即可使用，86 字获得高/中置信自动精细对齐，14 字采用安全回退。人工审核必需数为 0。

报告记录最佳方案、次优方案、总代价、归一化代价和两者差距，便于以后调整阈值。相同输入和参数会得到相同结果。

## 接入轨迹生成

`style_generator_cli` 现在会在默认风格目录自动查找 `personal_font_profile_v1.json`。也可以在请求中显式设置 `personal_font_profile_path`。加载时会验证清单和两个子产物的一致性及 SHA-256，任何篡改、混用书写者或样本数量不一致都会停止生成。

生成器按字符自动选择：

- `high`/`medium` 已采字符：`automatic_correspondence_features`，复用字符实测的布局、倾斜和直线度并与整体先验融合；
- `low` 已采字符：`safe_standard_skeleton_fallback`；
- 未采字符：`global_style_unseen_character_fallback`。

这里的“自动对应特征”只决定哪些字符级测量可以可信使用。它不会按照对齐分组合并或拆分写字机笔画，也不会合成连笔。输出继续保留标准骨架的笔画边界和明确抬笔。

## 边界

- 自动对齐只学习“实际落笔段与楷书笔画的对应关系”，不会自动画出笔画之间的连接线；
- Hanzi Writer 中心线是非权威结构参考，不能替代专业书法笔画标注；
- 用户一个落笔段内部可能包含复杂连笔，自动对齐只能判断它可能对应连续多笔，尚不能精确恢复内部笔界；
- 未建立安全连接曲线模型前，写字机轨迹继续保留明确抬笔。

# 生成轨迹几何相似度报告

## 用途

该功能比较风格生成器输出的字符轨迹与同一用户的真实数位板样本，形成可复现的 JSON 基线报告。它用于比较不同生成器版本和参数，不替代人工可读性评价，也不控制写字机。

评估只读取预处理后的 `glyph` 表示，不读取或提交原始私有笔迹。报告应继续保存在 Git 忽略的 `runtime_data/` 下。

## 指标

- `global_shape_score`：忽略笔画对应关系后的整体轨迹覆盖相似度。
- `ordered_stroke_score`：笔画数一致时，按笔顺逐笔比较中心线形状。
- `stroke_count_score`：真实样本与生成结果的笔画数一致程度。
- `aspect_ratio_score`：归一化前字形宽高比的一致程度。
- `direction_score`：八方向轨迹长度分布的一致程度。
- `strict_kaishu_score`：严格参考楷书骨架笔画边界的诊断分数，仅用于检查骨架与拆笔差异。
- `running_script_score`：面向日常行书/自然手写的主要分数，不要求与楷书骨架逐笔一一对应，重点比较整体形状、宽高比和方向分布。
- `overall_score`：为兼容旧报告暂时等于 `strict_kaishu_score`；自然笔迹分析应读取 `running_script_score`。

不同字符的书写习惯和骨架数据可能存在拆笔差异。因此应重点比较“同一批字符、同一预处理配置”下不同生成器版本的相对变化，不应把分数直接解释为识别率或自然度。

## 运行

先使用风格生成器生成一批在真实样本中也存在的字符，再在仓库根目录运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_similarity_report.cmd `
  runtime_data\handwriting\processed\user_01\style_probe_v1 `
  runtime_data\output\user01_generated_probe.json `
  runtime_data\handwriting\reports\user01_geometry_similarity.json
```

也可以直接调用 Python：

```powershell
py -3 -m src.handwriting_robot_layer2_wl_handwriting.similarity_cli `
  <processed_dir> <generated_stroke_document.json> <report.json> `
  --variant 1
```

生成文档中的字符如果没有对应的处理样本，不会导致整份报告失败，而会进入 `skipped` 并标记 `reference_not_found`。

## 自动诊断

报告的 `diagnosis` 字段会把低分原因拆开，避免将“拆笔方式不同”直接当成字形失败：

- `likely_running_script_variant`：用户自然书写与楷书骨架的笔画边界不同，但整体形状仍较接近，属于可能的行书连笔或拆笔变化，不自动视为错误。
- `running_script_variant_and_shape_difference`：存在行书式笔画边界差异，同时整体几何也有明显偏差。
- `shape_difference`：笔画数一致，但整体形状、逐笔形状、宽高比或方向分布存在偏差。
- `no_major_geometry_issue`：现有阈值下没有发现主要几何问题。

`review_queue` 按高、中、低优先级排列。分类只用于筛选，修改生成器前仍需查看真实轨迹和生成轨迹的叠加图。

楷书骨架在这里是字符结构参考，不是对人类行书笔画边界的硬约束。当前 `user_01` 的 100 字基线中，23 字存在笔画数差异，其中 18 字被判断为“整体形状尚可、可能是行书连笔或拆笔变化”；54 字没有主要几何问题。严格楷书评分均值为 `0.774136`，行书容错评分均值为 `0.816907`。应优先参考 `running_script_score` 和高优先级复核队列。这些统计来自私有报告，不随代码提交。

## Python 接口

```python
import json
from pathlib import Path

from src.handwriting_robot_layer2_wl_handwriting import build_similarity_report

document = json.loads(Path("generated.json").read_text(encoding="utf-8"))
report = build_similarity_report(Path("processed/user_01"), document, variant=1)
```

## 限制

- 当前指标只评价二维中心线几何，不评价字义、可读性、压感和写字机动力学。
- 真实笔画数与标准楷书骨架不一致时，严格逐笔顺序分数为 0，但行书评分不会因此直接降为失败。
- 当前只能容忍和识别行书式连笔差异，尚不能自动生成经过验证的连笔连接轨迹。
- 分数没有统一的“合格线”；首次运行结果应作为基线，并结合人工抽查和后续落笔测试判断。

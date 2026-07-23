# 行书笔画对齐人工审核说明

## 定位

人工审核现在是可选增强流程，不再是建立个人字体库的必要步骤。主流程使用 [`automatic-running-script-alignment.md`](automatic-running-script-alignment.md) 中的自动动态规划对齐；只有低置信复杂字符在需要进一步提高质量时才进入本审核流程。

## 目的

本步骤可将少量低置信用户落笔段与规范楷书骨架笔画进行人工对应。它用于补充两个自动方法难以稳定判断的问题：

1. 用户一个连续落笔段是否合并了多笔楷书笔画；
2. 相邻真实落笔段之间是否存在符合该用户习惯的行书连接关系。

审核结果仍然只是研究标注，不会自动开启连笔生成，也不会直接交给写字机。

## 生成审核包

默认只选择连接候选报告中的高置信字符：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_alignment_review.cmd generate `
  runtime_data\handwriting\reports\user01_connection_candidates_v1.json `
  runtime_data\handwriting\processed\user_01\style_probe_v1 `
  runtime_data\external\hanzi-writer-data-2.0.1 `
  runtime_data\handwriting\alignment_reviews\user01_v1
```

生成内容：

- `alignment_review.json`：需要人工填写的映射与候选决策；
- `previews/U+XXXX.svg`：左侧为用户实际落笔段 `O1...`，右侧为楷书骨架笔画 `K1...`；
- 左图虚线：程序筛选的连接候选，只用于定位，不代表允许连写。

当前 `user_01` 审核包已生成 5 个字符：“安、室、家、差、江”。其中“家”为实际 9 个落笔段对照楷书骨架 10 笔，其余四字的实际落笔段数与骨架笔画数相同。所有字符和候选均保持 `pending`，不会进入轨迹生成。

## 映射关系

`alignment_groups` 支持：

- `one_to_one`：一个实际落笔段对应一笔楷书；
- `observed_joins_standard`：一个实际落笔段内部合并多笔楷书；
- `observed_splits_standard`：多个实际落笔段共同对应一笔楷书；
- `many_to_many`：复杂连续区域，需要多段对应多笔。

每组编号必须连续并保持书写顺序，不能重复使用同一落笔段或楷书笔画。只有完整覆盖双方全部笔画且所有连接候选已有决定时，字符才能标记为 `approved`。

连接候选的 `review_decision` 可填写：

- `allow_ligature`：书法结构上允许研究连接，但仍需另建连接曲线模型；
- `reject_ligature`：只是端点接近，不应连写；
- `uncertain`：当前样本不足，保留待定；
- `pending`：尚未审核。

## 校验

编辑 JSON 后运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_alignment_review.cmd validate `
  runtime_data\handwriting\alignment_reviews\user01_v1\alignment_review.json
```

## 安全边界

- Hanzi Writer 骨架不是权威书法标注，只作为有序结构参考。
- `allow_ligature` 不包含具体连接轨迹、曲率、速度或压力。
- 审核通过后仍需学习或设计连接曲线，并单独进行无落笔和低速设备验证。
- 私有审核文件和预览包含个人笔迹，不提交 Git。

# 用户字体风格特征提取说明

## 用途

本步骤读取清洗后的 `dynamics`、`canvas` 和 `glyph` 轨迹，生成一个可复现的用户字体风格档案。该档案用于描述个人书写习惯，并为下一阶段“标准有序笔画骨架转换为用户风格轨迹”提供参数先验。

风格档案本身不能凭空生成未采集字符。未录字符生成还需要标准字符的有序笔画骨架，并需要单独实现和评估轨迹变形算法。

## 提取的特征

### 字面布局

从 `canvas` 提取：

- 字面宽度、高度、面积和宽高比；
- 字符包围盒中心；
- 墨迹点重心；
- 相对画布中心的横向和纵向偏移。

这些特征用于恢复用户自然书写时的字面大小、重心与留白习惯。

### 书写动态

从 `dynamics` 提取：

- 有效书写时长、落笔时长和笔画间停顿；
- 归一化轨迹速度及速度分位数；
- 平均压力、压力波动、落笔和收笔压力；
- 横向倾角、纵向倾角和合成倾角。

速度单位是“归一化画布长度/秒”，不能直接当作写字机毫米速度。生成 `StrokeDocument` 后，还需要根据目标字高和设备限制换算。

### 字形几何

从 `glyph` 提取：

- 笔画长度、直线度、转角和拐点比例；
- 近似横画角度和竖画倾斜角；
- 横、竖、斜向轨迹占比；
- 八方向轨迹分布；
- 笔画起点和终点的平均位置。

这些是统计先验，不是汉字笔画语义分类。后续生成器仍应使用带笔顺和笔画类型的标准骨架。

## 运行方法

先完成预处理，再在仓库根目录运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_style_analysis.cmd user_01
```

默认读取：

```text
runtime_data/handwriting/processed/user_01/style_probe_v1/
```

默认输出：

```text
runtime_data/handwriting/style_profiles/user_01/style_profile_v1.json
```

自定义输入、输出或最低样本数量：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_style_analysis.cmd `
  user_01 `
  --processed-dir runtime_data/handwriting/processed/user_01/style_probe_v1 `
  --output runtime_data/handwriting/style_profiles/user_01/style_profile_v1.json `
  --minimum-samples 20
```

## 输出结构

- `quality`：代表字覆盖率、可信度和传感器警告；
- `style_features`：全体样本的中位数、均值、标准差和分位数；
- `generation_priors`：后续轨迹生成器可直接读取的稳健中位数与变化尺度；
- `group_profiles`：10 个代表字符组的分组统计；
- `sample_features`：每个字符的特征，便于异常定位和后续模型训练；
- `source`：处理样本组合指纹和预处理参数，用于结果追踪。

相同处理样本和分析参数会得到相同档案，不写入当前时间等非确定字段。

## 隐私和边界

- 风格档案属于个人生物行为特征，只写入被 Git 忽略的 `runtime_data/`；
- 不提交真实样本、处理轨迹、风格档案或个人可识别信息；
- 本模块只生成字体特征和后续书写轨迹，不控制写字机；
- 设备速度、加速度、抬落笔高度和通信由设备模块负责。

## 完成条件

- 100 个代表字符全部进入档案；
- 代表字覆盖率为 100%，没有特征提取失败；
- 所有数值有限，方向分布之和接近 1；
- 风格档案在相同输入下可复现；
- 对主要统计结果进行人工合理性检查后，再进入标准骨架风格化。

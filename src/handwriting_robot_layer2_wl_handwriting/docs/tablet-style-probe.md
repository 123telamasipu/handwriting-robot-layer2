# 数位板用户笔迹试采说明

## 目标

第一轮只采集一名用户的 100 个代表汉字，每个字符先录入 1 次。目的不是立即建立完整字库，而是验证数位板数据是否适合后续用户字体分析和写字机轨迹生成。

手机采集作为探索功能保留，本阶段只接受数位板样本。

## 代表字符

试采字符位于 `resources/style_probe_charset.json`，覆盖：

- 基础笔画和独体字；
- 左右、上下、包围和半包围结构；
- 复杂多部件结构；
- 实验报告、测量和仪器记录常用汉字。

字符集严格包含 100 个唯一汉字，全部属于第一阶段目标字符集。

## 采集前准备

1. 安装数位板官方 Windows 驱动。
2. 在驱动面板中确认压感测试正常，并关闭不需要的快捷键和系统墨迹手势。
3. 安装桌面采集依赖：

```powershell
py -3 -m pip install -r src/handwriting_robot_layer2_wl_handwriting/requirements.txt
```

4. 选择稳定坐姿和握笔方式，整个会话尽量不要改变数位板映射区域。
5. 使用脱敏的 `writer_id`，不要把姓名、学号写进编号。

## 启动试采

在仓库根目录运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_tablet_probe.cmd `
  --writer-id user_01 `
  --device-model "数位板型号" `
  --session-notes "第一轮自然书写试采"
```

脚本自动启用：

- `--style-probe`：只显示 100 个代表字符；
- `--require-tablet`：禁用鼠标绘制，并拒绝非数位板正式样本；
- 自动会话编号：`tablet-年月日-时分秒`。

如需指定批次编号，可增加：

```powershell
--session-id tablet-user01-round01
```

## 书写要求

1. 按平时习惯自然书写，不要为了临摹屏幕字体而刻意改变风格。
2. 每次落笔到抬笔会记录为一个笔画。
3. 写错、误触或断笔时使用“撤销上一笔”或“清空重写”。
4. 第一轮每字只保存变体 1，不需要重复录入。
5. 每完成 20～30 字可休息，避免疲劳导致后半段风格明显变化。
6. 保存前确认界面显示“输入设备：数位板”。

## 数据内容

每个样本保存：

- 归一化轨迹坐标；
- 笔画顺序和轨迹点时间；
- 压力、倾角、旋转和切向压力；
- 输入来源 `tablet`；
- 会话编号、采集模式、声明设备型号；
- Qt 首次识别到的数位板名称、指针类型和设备能力。

会话记录保存于：

```text
runtime_data/handwriting/writers/<writer_id>/sessions/
```

样本保存在同一用户目录的 `samples/` 下。整个 `runtime_data/` 不提交 Git。

## 生成采集质量报告

完成或中途检查时运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_collection_report.cmd `
  user_01 `
  --output runtime_data/handwriting/reports/user_01-style-probe.json
```

报告包含：

- 完成数量和缺失字符；
- 数位板来源样本数量；
- 平均笔画数、轨迹点数和书写时长；
- 压力最小值、最大值和平均值；
- 点数过少、时长过短、整体书写范围过小或不是数位板来源的待复查样本。

质量规则只用于初筛。细长的“一”等合法字形不会仅因高度较小被判为异常；仍应人工查看后决定是否重录。

## 第一轮完成条件

- 100 个字符全部有变体 1；
- 所有正式样本的 `input_sources` 均包含 `tablet`；
- 质量报告没有明显误触、空白或极短样本；
- 至少抽查 10 个简单字和 10 个复杂字，轨迹与屏幕书写一致。

满足后进入下一步：清洗样本并提取大小、宽高比、重心、倾斜、笔画速度和压力等用户字体风格特征。

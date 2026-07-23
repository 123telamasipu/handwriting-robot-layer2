# 成员2：个人笔迹处理

本模块负责采集个人字符笔迹、管理用户字符库、检查文本覆盖率，并将已有笔迹样本转换为统一的 `StrokeDocument` v0.1。接口定义见 [`docs/stroke-interface.md`](../../docs/stroke-interface.md)。

本模块不控制写字机、不负责设备通信，也不实现最终页面排版。当前导出器提供的横向字符放置只用于模块联调；正式换行、区域约束和图文混排由集成/排版模块完成。

## 当前完成情况

| 能力 | 状态 | 说明 |
|---|---|---|
| 第一阶段目标字符集 | 已完成 | 1000 个常用汉字、8 个实验记录领域补充汉字、132 个字母/数字/符号，共 1140 个不重复字符 |
| 笔记本鼠标与数位板采集 | 已完成 | PySide6 桌面程序；保留落笔/抬笔边界、时间、压感及倾角等可用数据 |
| 用户字库与断点续录 | 已完成 | 草稿、正式样本和同字多变体分开保存 |
| 覆盖率与缺字清单 | 已完成 | 输入文本后返回已有字、缺字和覆盖率 |
| 随机种子字迹变化 | 已完成 | 对已有样本进行确定性的变体选择以及轻微大小、倾斜和位置扰动 |
| `StrokeDocument` 导出 | 已完成 | 提供 Python API 和命令行接口 |
| 手机浏览器采集 | 已完成 | 笔记本启动局域网服务，手机通过手指或触控笔采集并保存到同一用户字库 |
| 多设备统一采集协议 | 已完成 | 统一 `touch`、`pen`、`mouse`、`tablet` 的坐标、时间、压力和倾角字段 |
| 数位板 100 字风格试采包 | 已完成 | `user_01` 已完成 100/100 个真实数位板样本，质量报告无缺失或待复核样本 |
| 样本清洗与标准化 | 已完成 | 100/100 个样本完成非破坏性去重、时间归零、轻度平滑和等弧长重采样，并输出 `dynamics`/`canvas`/`glyph` 三套表示 |
| 用户字体风格特征提取 | 已完成 | `user_01` 的 100/100 个样本已生成高可信度风格档案，包含布局、速度、停顿、压力、倾角、方向、倾斜和曲率特征 |
| 标准骨架风格化生成 | 已完成基线 | 已接入 Hanzi Writer Data 2.0.1，1008/1008 个目标汉字可按需转换；字母和符号仍需独立骨架来源 |
| 少样本生成模型 | 待研究 | 当前几何基线不能充分学习复杂偏旁比例和特定笔画写法，后续可在统一骨架接口上升级模型 |
| 作文、笔记扫描图处理 | 延后 | 扫描图需要分割和人工校正，不纳入第一阶段 |

当前方案与仓库的成员2边界一致，也满足 README、示例、测试和统一轨迹接口要求。与最初任务书相比，扫描/OCR 被明确延期；第一阶段聚焦一至两名书写者的数位轨迹，不采集大量人员样本。

## 目录结构

```text
handwriting_robot_layer2_wl_handwriting/
├── charset.py          # 目标字符集读取与查询
├── models.py           # 采集点、笔画和录制缓冲区
├── storage.py          # 用户档案、草稿、样本和清单存储
├── collector_app.py    # 桌面采集程序入口
├── collector_ui.py     # 鼠标/数位板采集界面
├── mobile_server.py    # 手机局域网采集服务
├── capture_protocol.py # 多输入设备数据校验与归一化
├── collection_report.py # 数位板试采进度与质量报告
├── preprocessing.py    # 原始样本清洗与标准化算法
├── preprocessing_cli.py # 清洗批处理命令行入口
├── style_analysis.py  # 用户字体布局、动态和几何风格特征
├── style_analysis_cli.py # 风格档案命令行入口
├── skeleton.py         # 标准有序笔画骨架校验与覆盖率
├── style_generator.py  # 标准骨架到用户风格 StrokeDocument
├── style_generator_cli.py # 风格化轨迹命令行入口
├── hanzi_writer_adapter.py # 第三方汉字中心线适配与覆盖报告
├── hanzi_writer_cli.py # Hanzi Writer Data 校验和转换入口
├── web/                # 手机采集页面
├── renderer.py         # 覆盖率检查、随机变化和轨迹导出
├── export_cli.py       # 命令行导出入口
├── resources/          # 可公开提交的目标字符集
├── examples/           # 示例输入和输出
└── tools/              # Windows 采集与导出启动脚本
```

真实用户样本默认写入仓库根目录的 `runtime_data/handwriting/`，该目录已被 Git 忽略。

## 环境安装

在仓库根目录运行：

```powershell
py -3 -m pip install -r src/handwriting_robot_layer2_wl_handwriting/requirements.txt
```

只有运行桌面图形采集程序需要 PySide6。手机采集服务、字符集、存储和导出 API 不依赖 PySide6。

## 启动采集程序

在仓库目录双击或调用：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_collector.cmd
```

该脚本会自动定位仓库根目录；从其他工作目录启动时，使用脚本的绝对路径即可。

也可在仓库根目录运行：

```powershell
py -3 -m src.handwriting_robot_layer2_wl_handwriting.collector_app `
  --writer-id user_01 `
  --writer-name "测试用户"
```

没有数位板时可以按住鼠标左键书写，用于流程验证。鼠标没有真实压感，不建议把鼠标样本作为最终训练数据。程序支持自动保存草稿、撤销、清空、按字符查找、1～5 个同字变体和跳到下一未完成字符。

可用参数：

```powershell
py -3 -m src.handwriting_robot_layer2_wl_handwriting.collector_app --help
```

### 数位板 100 字试采

当前采集主线使用数位板。第一轮只录入 100 个结构多样的代表汉字，每字 1 次，用于验证用户字体分析所需的数据质量：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_tablet_probe.cmd `
  --writer-id user_01 `
  --device-model "数位板型号"
```

此入口会禁用鼠标绘制，并拒绝不包含 `tablet` 来源的正式样本。完整操作、字符选择和完成条件见 [`docs/tablet-style-probe.md`](docs/tablet-style-probe.md)。

采集中途或完成后生成质量报告：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_collection_report.cmd `
  user_01 `
  --output runtime_data/handwriting/reports/user_01-style-probe.json
```

### 清洗和标准化

完成 100 字试采后运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_preprocessing.cmd user_01
```

处理不会修改原始样本，输出位于 `runtime_data/handwriting/processed/user_01/style_probe_v1/`。详细算法、三套轨迹表示和参数说明见 [`docs/preprocessing.md`](docs/preprocessing.md)。

### 用户字体风格分析

完成清洗后运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_style_analysis.cmd user_01
```

风格档案默认写入 `runtime_data/handwriting/style_profiles/user_01/style_profile_v1.json`。它为后续标准字形骨架个性化提供布局、动态、压力和几何参数，但不会单独生成未录字符。详见 [`docs/style-analysis.md`](docs/style-analysis.md)。

### 未录字符风格化轨迹

使用演示骨架和公开合成风格运行完整链路：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_style_generator.cmd `
  src\handwriting_robot_layer2_wl_handwriting\examples\style_generation_request.json `
  runtime_data/output/style_generated_document.json
```

输出继续使用 `StrokeDocument` v0.1，并保留标准骨架的笔顺和笔画边界。演示骨架不适合正式书写；格式、算法、参数和数据源要求见 [`docs/ordered-skeleton-generation.md`](docs/ordered-skeleton-generation.md)。

### 1008 汉字骨架数据

下载并校验固定版本 Hanzi Writer Data：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\download_hanzi_writer_data.cmd
```

该数据对本项目 1000 个常用汉字和 8 个领域补充汉字实现 100% 覆盖。第三方数据只存放在被 Git 忽略的 `runtime_data/external/`，生成器按请求字符即时转换，不提交整套数据。许可证、坐标转换、覆盖率检查和调用方法见 [`docs/hanzi-writer-data.md`](docs/hanzi-writer-data.md)。

## 手机浏览器采集

手机与笔记本连接同一 Wi-Fi 后，在仓库根目录运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_mobile_collector.cmd `
  --writer-id user_01 `
  --writer-name "测试用户"
```

终端会显示带六位访问令牌的“手机访问”地址，例如：

```text
http://192.168.0.104:8765/?token=123456
```

用手机浏览器打开该地址即可录入。手机页面支持触控笔、手指和鼠标，笔画结束后自动保存草稿，并能恢复采集进度。详细用途、操作和网络排查见 [`docs/mobile-collector.md`](docs/mobile-collector.md)。

手机和桌面采集共用归一化左上角坐标以及同一组 `StrokePoint` 字段。数据结构、设备来源映射、HTTP 接口和限制见 [`docs/capture-protocol.md`](docs/capture-protocol.md)。

## Python 调用

在仓库根目录或已将仓库根目录加入 `PYTHONPATH` 的环境中调用：

```python
from pathlib import Path

from src.handwriting_robot_layer2_wl_handwriting import (
    RenderOptions,
    SampleStore,
    analyze_coverage,
    load_target_charset,
    render_text,
)

entries = load_target_charset()
store = SampleStore(
    Path("runtime_data/handwriting"),
    writer_id="user_01",
)

coverage = analyze_coverage("你好", store)
if not coverage["missing_characters"]:
    document = render_text(
        "你好",
        store,
        RenderOptions(random_seed=42),
    )
```

相同的用户样本、文本和 `random_seed` 会得到相同输出，便于复现实验；更换随机种子会改变已有变体的选择和轻微扰动。文本包含未采集字符时，`render_text()` 会抛出 `ValueError`，调用方应先读取 `analyze_coverage()` 生成补写清单。

## 命令行导出

请求格式见 [`examples/render_request.json`](examples/render_request.json)。运行：

```powershell
py -3 -m src.handwriting_robot_layer2_wl_handwriting.export_cli `
  src/handwriting_robot_layer2_wl_handwriting/examples/render_request.json `
  runtime_data/output/stroke_document.json
```

从其他工作目录调用时，可使用自动定位仓库根目录的脚本。请求、输出和 `--data-dir` 建议传绝对路径：

```powershell
C:\path\to\handwriting-robot-layer2\src\handwriting_robot_layer2_wl_handwriting\tools\run_export.cmd `
  C:\path\to\request.json C:\path\to\output.json
```

只检查覆盖率、不生成轨迹：

```powershell
py -3 -m src.handwriting_robot_layer2_wl_handwriting.export_cli `
  src/handwriting_robot_layer2_wl_handwriting/examples/render_request.json `
  runtime_data/output/coverage.json `
  --coverage-only
```

示例请求默认使用 `demo_user`。如果本地没有该用户的“你”“好”样本，完整导出失败是预期行为；先运行采集程序录入，或使用 `--coverage-only` 查看缺字。

## 数据与隐私

- `resources/` 只保存公开目标清单，不保存任何真实笔迹。
- `runtime_data/`、原始扫描图、姓名、学号和其他个人信息不得提交到 Git。
- 对外共享测试数据时使用脱敏的合成样本，并确认书写者已经授权。
- 自定义 `--data-dir` 时也应选择 Git 忽略目录，提交前执行 `git status` 检查。
- 手机服务仅用于可信局域网，默认访问令牌不能替代 HTTPS；不要把端口映射到公网。

单个采集样本采用归一化左上角坐标，包含字符、变体、输入来源和有序笔画。渲染输出采用毫米坐标，字段遵循 `docs/stroke-interface.md` v0.1。

## 测试

```powershell
py -3 -m unittest discover `
  -s tests/handwriting_robot_layer2_wl_handwriting `
  -v
```

测试使用临时目录和合成轨迹，不包含真实用户样本。

## 几何相似度评估

风格生成轨迹可与同一字符的预处理数位板样本进行归一化几何比较。工具输出整体形状、逐笔形状、笔画数、宽高比和方向分布分数，供生成器版本间做相对比较。运行方式、指标解释和限制见 [`docs/geometry-similarity.md`](docs/geometry-similarity.md)。

用户自然行书中的相邻落笔段可以进行只读连接候选分析，提取端点距离、离笔停顿和方向连续性，但不会生成连笔路径。使用方法和安全边界见 [`docs/running-script-connection-analysis.md`](docs/running-script-connection-analysis.md)。

高置信候选可生成私有人工审核包，将用户实际落笔段与规范楷书骨架笔画进行有序映射。标注格式、SVG 预览和校验方法见 [`docs/running-script-alignment-review.md`](docs/running-script-alignment-review.md)。

个人字体库的默认主流程使用有序动态规划自动完成行书落笔段与楷书骨架的匹配，高、中置信结果自动接受，低置信结果只进入可选复核，不阻塞建库。见 [`docs/automatic-running-script-alignment.md`](docs/automatic-running-script-alignment.md)。

一键建立个人字体档案：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_personal_font_profile.cmd `
  user_01 `
  --hanzi-writer-package-dir runtime_data\external\hanzi-writer-data-2.0.1
```

该命令不会要求逐字审核；低置信字符自动回退到明确抬笔的安全骨架轨迹。

建立档案后，轨迹生成请求只需提供 `user_id`、文字和正式骨架来源；程序会自动查找并校验 `personal_font_profile_v1.json`。高/中置信已采字符使用字符级实测布局与倾斜特征，低置信字符安全回退，未采字符使用用户整体风格迁移。详细请求字段和输出策略见 [`docs/ordered-skeleton-generation.md`](docs/ordered-skeleton-generation.md)。

字符级增强上线前可运行多随机种子批量对照评估，自动识别改善、稳定和退化字符，并给出无需逐字人工审核的安全回退名单。见 [`docs/personal-font-evaluation.md`](docs/personal-font-evaluation.md)。

评估完成后生成 `personal_font_deployment_v1.json`。轨迹生成器会优先加载该带哈希策略，实际执行 55/45 的逐字增强与回退；任何个人字体清单或评估报告变更都会使旧策略校验失败，避免静默使用过期名单。

最终部署策略可以生成写字机联调轨迹交付包，自动覆盖增强、评估回退、低置信回退、未采字符和混合文本，并执行软件预检。交付包不会控制设备，始终等待成员1完成页面任务组织、成员5完成机械安全审核。见 [`docs/machine-integration-handoff.md`](docs/machine-integration-handoff.md)。

## 其他成员配合

成员1需要完成正式页面 `region` 变换和有序设备任务组织；成员5需要完成坐标标定、机械限位、速度/加速度、空跑、急停和低速落笔审核；成员4通过集成层调用用户档案，不能直接操作私有样本或设备。各成员需要接收和回传的字段、测试顺序与当前阻塞项见 [`docs/team-integration-checklist.md`](docs/team-integration-checklist.md)。

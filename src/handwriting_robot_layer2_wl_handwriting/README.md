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
| 少样本风格学习与未录字符生成 | 待研究 | 当前随机种子不能生成未采集字符；需要引入标准字形骨架与风格迁移/轨迹生成模型 |
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

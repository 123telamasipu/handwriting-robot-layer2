# Hanzi Writer Data 标准骨架接入说明

## 选择原因

本项目使用 Hanzi Writer Data 的 `medians` 作为汉字有序中心线骨架来源。与普通字体轮廓相比，`medians` 具备以下优势：

- 每个字符按书写顺序保存多个独立笔画；
- 每个笔画由中心线点序列表示，适合转换为写字机轨迹；
- 不需要从封闭字体轮廓反推笔画中心线；
- 对第一阶段 1000 个常用汉字和 8 个领域补充汉字全部覆盖。

该数据由 Hanzi Writer Data 发布，来源说明指向 Make Me a Hanzi 和 Arphic 字体。它是高覆盖第三方笔顺中心线数据，但不是国家标准认证字形，因此生成结果会保留 `non_authoritative_skeleton_library` 警告。

## 固定版本

当前适配器针对：

- npm 包：`hanzi-writer-data`；
- 版本：`2.0.1`；
- npm 压缩包解压大小：约 32 MB；
- 本项目下载压缩包 SHA-512：`9DB43033E31AAF21A8ABBA4130864B09DDE516AD379D7B89BB092ED7EE946E32F9F2E53EF4E50B55C324A0DBCDB894A8215EDFD5B6CF45F0F80FF2D06B94BBAA`。

项目不会静默跟随 `latest`。升级版本时必须重新核对许可证、字段结构、哈希、覆盖率和生成结果。

## 下载方法

在仓库根目录运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\download_hanzi_writer_data.cmd
```

脚本会：

1. 从 npm 官方注册表下载固定版本；
2. 校验 SHA-512；
3. 解压到 `runtime_data/external/hanzi-writer-data-2.0.1/package/`；
4. 确认 `package.json` 和 `ARPHICPL.TXT` 存在。

整个第三方数据目录被 Git 忽略，不会进入项目提交。

## 许可证和分发策略

数据包声明使用 Arphic Public License，许可证正文位于数据包的 `ARPHICPL.TXT`。许可证允许使用、复制和修改，但分发原数据或派生数据时包含保留许可证、说明修改和使修改版本按相同条件可获得等要求。

本项目采用保守策略：

- Git 只提交适配代码、固定版本下载脚本和说明；
- 不把 9,575 个第三方字符 JSON 直接提交到仓库；
- 本地按请求文本即时读取和转换 `medians`；
- 私有覆盖报告和派生轨迹保存在 `runtime_data/`；
- 如果未来需要对外分发转换后的整套骨架，必须单独完成许可证合规审核，并随数据保留 `ARPHICPL.TXT` 和修改说明。

项目源代码仍可按仓库许可证发布；第三方字体数据及其派生整库遵循其自身许可证。本说明不替代正式法律意见。

数据源：

- [Hanzi Writer Data npm 包](https://www.npmjs.com/package/hanzi-writer-data)
- [Hanzi Writer Data 项目](https://github.com/chanind/hanzi-writer-data)
- [Make Me a Hanzi](https://github.com/skishore/makemeahanzi)

## 坐标转换

Hanzi Writer Data 的 `medians` 使用接近 `1024 × 1024` 的左下角坐标，部分笔锋点会自然超出标称画布。适配器执行：

1. 将 Y 轴翻转为左上角原点；
2. 读取字符全部中心线点的真实包围盒；
3. 按最大边等比例归一化；
4. 居中到 `[0, 1]`，默认保留 5% 边距；
5. 保留笔画数量、笔画顺序和每笔点顺序。

不能简单把超出 `0–1024` 的点截断，否则会改变撇、捺、钩等笔锋形态。

Hanzi Writer Data 没有提供本项目所需的统一 `stroke_type` 分类，因此适配结果暂时标为 `unknown`。这不影响轨迹执行，但会限制按笔画语义进行更精细的风格迁移。

## 覆盖率检查

下载完成后运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_hanzi_writer_adapter.cmd `
  coverage `
  runtime_data\external\hanzi-writer-data-2.0.1\package `
  runtime_data\handwriting\reports\hanzi-writer-data-2.0.1-coverage.json
```

当前实测结果：

- 1000 个常用汉字：1000/1000；
- 8 个领域补充汉字：8/8；
- 汉字合计：1008/1008，覆盖率 100%；
- 完整目标字符集：1008/1140，覆盖率 88.42%；
- 缺失的 132 项全部是字母、数字、标点、数学或科学符号；
- 通过转换校验的汉字中无无效字符。

字母和符号需要独立的单线字体或手工骨架来源，不能由汉字数据源补齐。

## 风格化生成

请求 JSON 中指定本地数据包目录：

```json
{
  "schema_version": "1.0",
  "user_id": "user_01",
  "text": "好世界",
  "hanzi_writer_package_dir": "runtime_data/external/hanzi-writer-data-2.0.1/package",
  "options": {
    "random_seed": 42,
    "char_width_mm": 12.0,
    "char_height_mm": 12.0,
    "glyph_occupancy": 0.78
  }
}
```

然后运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_style_generator.cmd `
  runtime_data\output\request.json `
  runtime_data\output\stroke_document.json
```

程序只转换文本中实际需要的字符，不预先复制或生成整套派生骨架库。

## 当前完成状态

- 目标 1008 个汉字全部通过中心线转换校验；
- `user_01` 未采集字符“好世界”已成功生成；
- 生成结果含 20 笔和 436 个轨迹点；
- 坐标、页面边界、笔画顺序和重复生成一致性校验通过；
- 字符可读，但仍需后续进行用户相似度和写字机实际书写评估。

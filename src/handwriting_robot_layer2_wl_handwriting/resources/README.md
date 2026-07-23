# 第一阶段目标字符集

本目录只存放可公开提交的目标字符清单，不包含任何人的笔迹样本。

## 文件

- `target_charset_phase1.csv`：采集程序使用的主清单，包含序号、字符、Unicode、类别、阶段、字频、拼音、笔画数和来源。
- `target_charset_phase1.txt`：每行一个目标字符，方便人工检查或导入其他工具。
- `common_hanzi_top1000.txt`：第一阶段 1000 个现代汉语常用汉字参考表。
- `letters_symbols.json`：字母、数字、标点、数学符号和理工科符号分类。
- `charset_summary.json`：数量与去重结果。
- `style_probe_charset.json`：数位板用户字体分析第一轮使用的 100 个结构代表汉字，分为 10 组。
- `demo_ordered_stroke_skeletons.json`：仅用于生成链路联调的“永”“文”手工骨架；非权威数据，正式使用前必须替换。

## 选取规则

1. 从 Jun Da 现代汉语单字字频表的公开 CSV 整理中按 `frequency_rank` 排序。
2. 只保留《通用规范汉字表》一级字范围内的规范汉字，取前 1000 个。
3. 补充实验报告和测量记录中常用、但未进入前 1000 的 8 个汉字：`仪姓曲析械阻频骤`。
4. 加入大小写英文字母、数字、常用中英文标点、数学符号和理工科符号。
5. 按 Unicode 字符去重；空格和换行不作为需要录入字形的字符。

最终结果为 1008 个汉字和 132 个非汉字字符，共 1140 个不重复字符。其中第一阶段的核心汉字严格为 1000 个，其余为补充项，可在核心汉字后按演示文本需要采集。

## 数据来源

- Jun Da, *Modern Chinese Character Frequency List*。
- [`ruddfawcett/hanziDB.csv`](https://github.com/ruddfawcett/hanziDB.csv) 的 `hanzi_db.csv` 公开整理，用于字频、拼音和笔画数字段。
- 教育部、国家语言文字工作委员会：《通用规范汉字表》（2013），一级字表共 3500 字。
- [`shengdoushi/common-standard-chinese-characters-table`](https://github.com/shengdoushi/common-standard-chinese-characters-table) 的一级字公开文本整理，用于规范字范围过滤。
- GB/T 15834-2011《标点符号用法》，用于标点类别参考。
- 国际单位制和大学理工科实验报告常见写法，用于数学、科学符号与领域汉字补充。

字符清单用于研究与采集规划。项目对外发布或重新分发第三方字段前，应再次核对原始仓库许可证、标准文本引用方式和当前授权状态。

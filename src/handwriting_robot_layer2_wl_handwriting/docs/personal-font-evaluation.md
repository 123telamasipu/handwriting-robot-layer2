# 个人字体生成批量对照评估

## 用途

该工具自动比较两种轨迹生成方式：

- 基线：只使用用户整体风格；
- 候选：为高/中置信已采字符加入字符级布局、倾斜和直线度特征。

评估在多个固定随机种子下重复运行，并使用同一批预处理数位板样本计算严格楷书分数和行书容错分数。它用于阻止字符级增强导致自动退化，不要求逐字人工审核，也不控制写字机。

## 运行

在仓库根目录运行：

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_personal_font_evaluation.cmd `
  runtime_data\handwriting\processed\user_01\style_probe_v1 `
  runtime_data\handwriting\style_profiles\user_01\personal_font_profile_v1.json `
  runtime_data\external\hanzi-writer-data-2.0.1 `
  runtime_data\handwriting\reports\user01_personal_font_comparison_v1.json `
  --seeds 0,17,42
```

真实样本和报告必须保存在被 Git 忽略的 `runtime_data/`。

## 自动质量门

工具逐字计算候选相对基线的 `running_script_score` 差值，并分类为：

- `improved`：差值大于 `meaningful_delta`；
- `stable`：差值在正负阈值内；
- `regressed`：差值小于负阈值；
- `severe_regression`：差值达到严重退化阈值。

质量门还会检查：

- 所有字符是否均有真实参考；
- 两种生成方式的笔画顺序和边界是否一致；
- 是否意外生成连笔；
- 整体平均差值、退化比例和严重退化数量。

质量门失败只表示“不能给所有高/中置信字符统一启用字符级增强”，不会阻塞个人字体库建立。报告会生成 `deployment_recommendation`：保留改善或稳定字符的增强策略，退化字符自动回退到标准骨架与用户整体风格，人工审核必需数仍为 0。

## 当前 user_01 结果

3 个固定种子下，100 字基线行书容错均值为 `0.816387`，全部启用候选特征后为 `0.819829`，平均提高 `0.003442`。其中 37 字改善、32 字稳定、31 字退化，6 字严重退化，因此“全量启用”质量门失败。

按逐字自动回退后，建议 55 字保留字符级增强、45 字使用安全回退；投影行书容错均值为 `0.828209`，相对基线提高 `0.011822`。所有对照输出的笔画数量、顺序和边界一致，未生成连笔。

## 限制

- 几何分数不等于可读性、字义正确率或主观相似度；
- 该报告只评估已有真实样本的字符，未采字符仍需单独测试；
- 评估通过名单由 `personal_font_deployment_v1.json` 独立保存，不修改原始个人字体清单；生成器会优先自动发现并验证该部署产物。
- 每次重建个人字体清单或重新运行评估后，都必须重新生成部署策略；哈希不一致时生成器会拒绝加载旧策略。

## 生成部署策略

```powershell
src\handwriting_robot_layer2_wl_handwriting\tools\run_personal_font_deployment.cmd `
  runtime_data\handwriting\style_profiles\user_01\personal_font_profile_v1.json `
  runtime_data\handwriting\reports\user01_personal_font_comparison_v1.json `
  runtime_data\handwriting\style_profiles\user_01\personal_font_deployment_v1.json
```

部署策略记录个人字体清单与评估报告的 SHA-256，并保存每个已采字符的最终策略。默认轨迹生成请求无需增加字段；若同目录存在有效部署策略，程序会优先加载。也可以通过 `personal_font_deployment_path` 显式指定。

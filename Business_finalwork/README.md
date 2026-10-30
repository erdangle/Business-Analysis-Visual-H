# 零售订单利润归因与客户价值研究

本项目使用 Tableau 官方 Superstore 示例数据，完成零售订单利润归因、客户价值分层、品类结构诊断、亏损风险预警、销售预测和交互式数据看板。全部分析、图表和看板均由 Python 代码生成，不使用 Power BI、Tableau 制图或以 Excel 截图替代结果。

## 仓库位置

- GitHub仓库：https://github.com/erdangle/Business-Analysis-Visual-H
- 最终项目目录：https://github.com/erdangle/Business-Analysis-Visual-H/tree/main/Business_finalwork
- 上传位置：仓库根目录，与 `Business_Analysis`、`Data Visualization` 同级。

## 项目内容

- 单文件分析程序：`main.py`
- 15 张 Nature 风格模板复现图
- 8 张业务模型图
- 1 张 ECharts 交互式经营看板截图
- `dashboard动态演示.mp4`：交互式看板操作录屏
- RFM、同期群、ABC、波士顿矩阵、逻辑回归和 Holt-Winters 六类模型
- 清洗后的订单、客户、商品、RFM 和同期群数据
- 模型结果 CSV/JSON 与可离线打开的交互式 HTML 看板
- 完整期末论文

## 数据来源

- 数据源：Tableau Sample - Superstore
- URL：https://public.tableau.com/app/sample-data/sample_-_superstore.xls
- 获取方式：Tableau 官方示例文件直接下载
- 获取日期：2026-10-27
- 分析截止：2026-09-30
- 原始文件 SHA-256：`5045ED4FEC49CAE2CC0DFC5AB0D204BA09EFA767FE00C996822499E8CC42FBBD`
- 许可说明：Tableau 官方示例数据，页面未单独标注开放数据许可证；本项目仅用于课程学习与非商业研究。

本项目未使用爬虫，也未使用未授权的网页解析方式获取数据。

## 核心结果

- 清洗后订单明细 8,943 条、订单 4,462 笔、客户 801 名。
- 销售额 203.94 万美元，利润 26.33 万美元，利润率 12.91%。
- 退货订单率 5.74%，亏损明细占比 18.47%。
- 重要价值客户占 35.58%，贡献 58.47% 销售额。
- 8 个 A 类品类贡献 78.04% 销售额。
- 亏损预警测试集 AUC 0.984，召回率 93.95%。
- Holt-Winters 三次滚动回测 MAPE 20.59%。

## 环境与运行

建议使用 Python 3.10 或更高版本。在项目根目录执行：

```powershell
cd Business_finalwork
python -m pip install -r requirements.txt
python run_all.py
```

也可以直接运行主程序：

```powershell
python main.py
```

程序会检查 `data/raw/sample_-_superstore.xls`，文件缺失时自动从官方地址下载。随后依次完成数据清洗、模型计算、图表生成和看板输出。

`run_all.py` 在 `main.py` 运行结束后，会尝试调用本机 Chrome 或 Edge 生成看板截图；浏览器不可用时会跳过截图，不影响 HTML 看板生成。

## 目录结构

```text
Business-Analysis-Visual-H/
├── Business_Analysis/
├── Data Visualization/
├── Business_finalwork/
│   ├── main.py
│   ├── run_all.py
│   ├── requirements.txt
│   ├── README.md
│   ├── NOTICE.md
│   ├── .gitignore
│   ├── echarts.min.js
│   ├── 零售订单利润归因与客户价值研究.docx
│   ├── dashboard动态演示.mp4
│   ├── data/
│   │   ├── raw/
│   │   │   └── sample_-_superstore.xls
│   │   └── clean/
│   │       ├── orders_clean.csv
│   │       ├── customer_dim.csv
│   │       ├── customer_rfm.csv
│   │       ├── product_dim.csv
│   │       └── cohort_retention.csv
│   └── outputs/
│       ├── dashboard.html
│       ├── figures/
│       │   ├── n01_regional_sales.png ... n15_category_dumbbell.png
│       │   ├── m01_rfm_segments.png ... m08_profit_quality.png
│       │   └── Superstore交互式经营看板.png
│       └── tables/
│           ├── analysis_summary.json
│           ├── boston_matrix.csv
│           ├── category_summary.csv
│           ├── discount_summary.csv
│           ├── forecast_backtest.csv
│           ├── forecast_next_6m.csv
│           ├── loss_model_coefficients.csv
│           ├── loss_model_roc.csv
│           ├── monthly_summary.csv
│           ├── region_summary.csv
│           ├── rfm_summary.csv
│           ├── state_summary.csv
│           └── subcategory_summary.csv
└── README.md
```

## 输出文件

### 数据

- `data/clean/orders_clean.csv`：清洗后的订单主表。
- `data/clean/customer_dim.csv`：客户维度表。
- `data/clean/product_dim.csv`：商品维度表。
- `data/clean/customer_rfm.csv`：客户RFM指标与分层。
- `data/clean/cohort_retention.csv`：客户同期群留存矩阵。

### 图表

- `outputs/figures/n01_*.png` 至 `n15_*.png`：课程图表模板复现。
- `outputs/figures/m01_*.png` 至 `m08_*.png`：业务模型图。
- `outputs/figures/Superstore交互式经营看板.png`：看板截图。

### 模型结果

- `outputs/tables/analysis_summary.json`：主要指标与模型摘要。
- `outputs/tables/rfm_summary.csv`：RFM分层结果。
- `outputs/tables/boston_matrix.csv`：品类波士顿矩阵。
- `outputs/tables/discount_summary.csv`：折扣区间利润分析。
- `outputs/tables/forecast_next_6m.csv`：未来6个月销售预测。
- `outputs/tables/loss_model_roc.csv`：亏损预警ROC结果。

### 交互式看板

双击 `outputs/dashboard.html` 即可在浏览器中打开。看板包含：

- 区域、品类、客户细分三个筛选器。
- 销售额、利润、利润率、订单量、客户数、退货率六项KPI。
- 州销售额、品类利润率、月度销售与利润、折扣利润、品类销售结构五类联动图。
- 最近20条订单明细。
- 点击图形元素后钉住详情的交互功能。
- `dashboard动态演示.mp4` 提供完整操作演示。

项目根目录保留了 `echarts.min.js` 本地缓存，断网环境下也可直接打开看板。

## 复现说明

- 逻辑回归训练集/测试集比例为 75%:25%，随机种子为 `20261027`。
- RFM散点图使用同一随机种子抽样，最多展示500名客户。
- 其他统计、RFM分层、ABC分类、波士顿矩阵和预测模型均使用全量清洗数据。
- Holt-Winters使用2023年1月至2026年9月的45个月销售序列，并采用三次滚动起点回测。

## 图表清单

模板复现图：

1. 区域销售规模
2. 重点州销售额
3. 前十品类销售贡献
4. 区域与品类结构
5. 客户类型品类偏好
6. 季度销售同比
7. 订单履约周期
8. 月度销售趋势
9. 月度利润率
10. 销售额与利润
11. 区域销售规模指数
12. 品类销售规模
13. 销售规模与利润率
14. 品类利润率参考
15. 重点品类同期变化

业务模型图：

1. RFM客户分层与销售贡献
2. RFM客户分布
3. 客户同期群留存
4. 品类ABC帕累托图
5. 品类波士顿矩阵
6. 亏损风险预警模型
7. Holt-Winters销售预测
8. 品类利润质量诊断

## 局限说明

Tableau Superstore为公开教学示例数据，不包含采购成本、广告曝光、访问行为、退款成本等字段，因此本文的利润指标不能替代完整贡献毛利分析，GMV和销售额也不能直接代表真实经营利润。数据经过匿名或演示化处理，结论不宜直接外推至真实零售企业。

## GitHub 仓库

GitHub仓库链接：https://github.com/erdangle/Business-Analysis-Visual-H

最终项目目录：https://github.com/erdangle/Business-Analysis-Visual-H/tree/main/Business_finalwork

上传时请保持文件夹名称为 `Business_finalwork`，放在仓库根目录下，与 `Business_Analysis` 和 `Data Visualization` 同级。

# 大屏风格库

为国家统计局各主题数据大屏维护的备选视觉风格。每种风格提供：背景、卡片语言、字体、
ECharts 调色板、坐标轴/分隔线/悬浮卡颜色规格（见 `themes.js` 中的 `window.BI_STYLES`）。

## 使用状态

| 风格 | 状态 | 已用于 |
| --- | --- | --- |
| 工程蓝图 Blueprint / Tactical HUD | ✅ 已使用 | 建筑业（`建筑业/generate_bi_dashboard.py`，深蓝图纸底+白网格+线框卡片） |
| 极光渐变 Aurora UI | ✅ 已使用 | 文化第一版（`文化/generate_bi_dashboard.py`，深底青紫粉光晕+半透明卡片） |
| Bento Grid 便当格 | ✅ 已使用 | 文化第二版（`文化/generate_bi_dashboard_bento.py`，浅灰底白卡混排+Apple 配色） |
| 玻璃拟态 Glassmorphism | ✅ 已使用 | 人民生活（`人民生活/generate_bi_dashboard.py`，浅色暖渐变+磨砂卡片，含全国/城镇/农村口径切换） |
| 瑞士国际主义 Swiss Typographic | ✅ 已使用 | 价值指数（`价值指数/generate_bi_dashboard.py`，白底黑字红色强调+发丝网格） |
| 赛博终端 Cyberpunk Terminal | ⬜ 未使用 | 任意主题的极客感变体（风格库中最后一个备用风格） |

## 选型建议

- 人民生活 → ✅ 已交付两件：**Glassmorphism 玻璃拟态大屏**（`人民生活/generate_bi_dashboard.py`，
  含全国/城镇/农村口径切换）+ **Jupyter Notebook 逐表可视化分析**（`人民生活数据可视化.ipynb`）
- 备选：Cyberpunk Terminal（任意主题的酷炫版）、Swiss（打印/论文友好）

## 用户偏好（后续大屏必须遵守）

- **不得出现工程图签栏 / titleblock / 制表信息**（图名、图号、比例、制表人、日期等
  元信息表格）。该元素曾在建筑业蓝图风首版中出现，已按用户要求移除；
  后续所有主题（人民生活 / 价值指数 / 文化 等）一律不加，头部只保留
  标题 + 副标题 + 数据来源说明。

## 复用方法

1. 打开 `themes.js`，选定主题对象；
2. 在新生成器的模板根节点写入其 `bg` / `card` 规格（CSS）；
3. `palette` 传入 ECharts `color`，`axis` / `split` / `text` / `muted` 抄入轴与图例样式，
   `tipBg` / `tipBorder` 抄入 tooltip；
4. 数字字体统一用 `fonts.num`，标题用 `fonts.title`。

## 调研依据（2025–2026 主流趋势）

- Glassmorphism 为 2025 主导趋势，Neumorphism 因可读性问题退居辅助元素：
  [Neumorphism vs. Glassmorphism: What's Winning in 2025](https://www.opendesignsin.com/blog/neumorphism-vs-glassmorphism-whats-winning-in-2025-web-design)
- Bento Grid 作为新一代网格卡片风格在仪表盘场景崛起（Apple 设计语言）：
  [DESIGN.md Library](https://designmd.app/library)、
  [Vibe Coding Guide 2026](https://hellopm.co/vibe-coding)
- Terminal / Cyberpunk / Tactical HUD / Aurora 等风格在数据密集型界面长期存在独立谱系：
  [Hyperplasma Skill Registry](https://www.aipm-registry.com/skills/hyperplasma-skills/hyperplasma/1.0.0)、
  [Grok-4.5 HTML Collection](https://github.com/MiaAI-Lab/Grok-4.5-HTML-Collection)

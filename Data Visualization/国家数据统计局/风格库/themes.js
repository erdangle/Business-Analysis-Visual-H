// ============================================================
// 国家统计局数据大屏 · 备选风格库 themes.js
// 用途：为后续主题大屏（人民生活 / 价值指数 / 文化 等）提供
//       可直接内联进生成器的 ECharts 主题对象 + 设计规格。
// 用法：把选定主题对象复制进生成器模板，CSS 变量写入根节点，
//       palette 传入 ECharts color，axis/split/tooltip 抄入公共样式。
// 状态：blueprint（工程蓝图）已被「建筑业」使用，见其 generate_bi_dashboard.py；
//       以下 5 个主题尚未使用。
// 来源依据：2025-2026 主流趋势调研（Glassmorphism 居首、Bento Grid 上升、
//       Terminal/Cyberpunk 与 Tactical HUD 长期存在于数据密集型界面）。
// ============================================================

window.BI_STYLES = {

  /* ---------- 1. 玻璃拟态 Glassmorphism（适合：人民生活 · 温暖通透） ---------- */
  glassmorphism: {
    name: "Glassmorphism 玻璃拟态",
    mood: "磨砂玻璃卡片浮在柔和渐变背景上，通透现代",
    bg: "linear-gradient(135deg,#e0f2ff 0%,#f3e8ff 45%,#ffe8f0 100%)",
    card: "rgba(255,255,255,0.55) + backdrop-filter:blur(18px) + 1px rgba(255,255,255,0.7) 描边 + 20px 大圆角 + 柔影",
    fonts: { title: '"PingFang SC","Microsoft YaHei",sans-serif', num: '"SF Pro Display","Segoe UI",sans-serif' },
    palette: ["#4f7cff", "#a06bff", "#ff7eb3", "#33c9b0", "#ffb648", "#6b8cff"],
    axis: "rgba(60,80,140,0.45)", split: "rgba(60,80,140,0.10)", text: "#2a3555", muted: "rgba(42,53,85,0.6)",
    tipBg: "rgba(255,255,255,0.9)", tipBorder: "rgba(255,255,255,0.9)",
    note: "文字对比度需专门校验；卡片务必加 1px 浅描边防止与背景糊在一起"
  },

  /* ---------- 2. Bento Grid 便当格（适合：价值指数 · 清爽模块化） ---------- */
  bento: {
    name: "Bento Grid 便当格",
    mood: "日式便当盒式圆角模块，Apple 发布会气质，浅色大留白",
    bg: "#f5f5f7",
    card: "#ffffff + 22px 圆角 + 无边框 + 大间距网格（大小卡片混排，重要图占 2x2）",
    fonts: { title: '"PingFang SC","Microsoft YaHei",sans-serif', num: '"SF Pro Display",system-ui' },
    palette: ["#0071e3", "#34c759", "#ff9f0a", "#ff375f", "#bf5af2", "#8e8e93"],
    axis: "rgba(60,60,67,0.4)", split: "rgba(60,60,67,0.08)", text: "#1d1d1f", muted: "rgba(60,60,67,0.55)",
    tipBg: "rgba(255,255,255,0.98)", tipBorder: "rgba(0,0,0,0.05)",
    note: "核心是布局：1 张主图 + 多张小卡混排；数字用超大字号（40px+）"
  },

  /* ---------- 3. 赛博终端 Cyberpunk Terminal（适合：任意主题 · 极客感） ---------- */
  cyber: {
    name: "Cyberpunk Terminal 赛博终端",
    mood: "CRT 黑底、荧光绿/品红、等宽字体、扫描线与光标闪烁",
    bg: "#050a06 + repeating-linear-gradient 扫描线(rgba(0,255,140,0.03) 0 1px, transparent 1px 3px)",
    card: "rgba(6,20,10,0.85) + 1px #00ff8c55 边框 + 直角(0 圆角) + 左上角 '▮' 光标装饰",
    fonts: { title: '"Microsoft YaHei",sans-serif', num: '"Cascadia Mono","Consolas",monospace' },
    palette: ["#00ff8c", "#ff2fb3", "#00d9ff", "#ffe14d", "#b46bff", "#ffffff"],
    axis: "rgba(0,255,140,0.6)", split: "rgba(0,255,140,0.12)", text: "#c8ffe3", muted: "rgba(0,255,140,0.55)",
    tipBg: "rgba(3,12,6,0.95)", tipBorder: "#00ff8c66",
    note: "数字全用等宽字体；标题可加 text-shadow 荧光晕；慎用大面积荧光避免刺眼"
  },

  /* ---------- 4. 极光渐变 Aurora UI（适合：文化 · 柔和梦幻） ---------- */
  aurora: {
    name: "Aurora UI 极光渐变",
    mood: "深底上大片青紫粉渐变光晕缓慢流动，卡片半透明",
    bg: "#0b1020 + 多层 radial-gradient(rgba(94,234,212,0.16) / rgba(167,139,250,0.14) / rgba(244,114,182,0.10)) 错位铺开",
    card: "rgba(17,24,46,0.6) + 1px rgba(148,163,255,0.22) 边框 + 16px 圆角 + 内侧渐变高光",
    fonts: { title: '"PingFang SC","Microsoft YaHei",sans-serif', num: '"Segoe UI",system-ui' },
    palette: ["#5eead4", "#a78bfa", "#f472b6", "#60a5fa", "#fbbf24", "#e2e8f0"],
    axis: "rgba(200,210,255,0.5)", split: "rgba(200,210,255,0.09)", text: "#e6ecff", muted: "rgba(230,236,255,0.6)",
    tipBg: "rgba(13,18,38,0.95)", tipBorder: "rgba(148,163,255,0.3)",
    note: "背景光晕用 2-3 层即可，太多会抢数据；ECharts 面积图配 0.25 透明度渐变最佳"
  },

  /* ---------- 5. 瑞士国际主义 Swiss Typographic（适合：严谨对比 · 学术汇报） ---------- */
  swiss: {
    name: "Swiss Typographic 瑞士国际主义",
    mood: "白底、黑字、一两个高饱和强调色、粗网格与大号无衬线数字，几乎零装饰",
    bg: "#ffffff",
    card: "无边框无阴影，仅以 1px #e5e5e5 分隔线与严格 8px 网格对齐 + 左对齐标题",
    fonts: { title: '"Helvetica Neue","Microsoft YaHei",sans-serif', num: '"Helvetica Neue",Arial' },
    palette: ["#e63312", "#111111", "#0057ff", "#8c8c8c", "#ffd100", "#e5e5e5"],
    axis: "#111111", split: "#e5e5e5", text: "#111111", muted: "#8c8c8c",
    tipBg: "#ffffff", tipBorder: "#111111",
    note: "红色仅用于强调与告警；标题一律左对齐、加粗、可全大写英文小标"
  }
};

# -*- coding: utf-8 -*-
'''文化产业 · 季度数据 BI 大屏生成器（Bento Grid 便当格风 · 浅色版）
================================================================

自包含的可视化项目：仅用 Python 标准库即可在本机（VS Code / PyCharm / 命令行）运行，
无需 pip 安装任何第三方包。风格：Bento Grid —— 浅灰底、白色大圆角卡片混排、
超大数字、Apple 式配色（与同目录「Aurora 极光渐变版」互为备选；选型依据见 ../风格库/README.md）。

功能
----
1. 读取 data/ 目录下的 6 张国家统计局文化产业季度表（2025Q2—2026Q2，共 5 期，
   营收/利润为累计值口径，资产总计为季末存量口径）；
2. 解析、校验并派生指标（九大类占比、增长最快/最慢行业等）；
3. 生成「Bento 便当格风」交互式 BI 大屏 HTML 并自动在浏览器中打开。

使用方法
--------
在本文件夹内打开终端，执行：
    python generate_bi_dashboard_bento.py            # 生成大屏并自动打开浏览器
    python generate_bi_dashboard_bento.py --no-open  # 只生成文件，不打开浏览器

首次运行会自动下载 ECharts 图表库并缓存为本文件夹下的 echarts.min.js（此后完全离线可用）。

输出：文化BI大屏-便当格.html（双击也可随时打开）。
数据来源：国家统计局「数据库 — 季度数据」。
'''

import json
import re
import sys
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / 'data'
ECHARTS_CACHE = BASE / 'echarts.min.js'
OUTPUT_HTML = BASE / '文化BI大屏-便当格.html'

QMAP = {'一': 1, '二': 2, '三': 3, '四': 4}

# =====================================================================
# 一、数据解析（与 Aurora 版相同：按指标行前缀抽取）
# =====================================================================

MAIN_SPEC = [
    ('rev', '规模以上文化及相关产业企业营业收入累计值'),
    ('revGrowth', '规模以上文化及相关产业企业营业收入累计增长'),
    ('profit', '规模以上文化及相关产业企业利润总额累计值'),
    ('profitGrowth', '规模以上文化及相关产业企业利润总额累计增长'),
    ('assets', '规模以上文化及相关产业企业资产总计季末值'),
    ('assetsYoy', '规模以上文化及相关产业企业资产总计同比增长'),
    ('mfg', '规模以上文化制造业企业营业收入累计值'),
    ('mfgGrowth', '规模以上文化制造业企业营业收入累计增长'),
    ('wholesale', '规模以上文化批发和零售业企业营业收入累计值'),
    ('wholesaleGrowth', '规模以上文化批发和零售业企业营业收入累计增长'),
    ('service', '规模以上文化服务业企业营业收入累计值'),
    ('serviceGrowth', '规模以上文化服务业企业营业收入累计增长'),
    ('core', '规模以上文化核心领域企业营业收入累计值'),
    ('coreGrowth', '规模以上文化核心领域企业营业收入累计增长'),
    ('related', '规模以上文化相关领域企业营业收入累计值'),
    ('relatedGrowth', '规模以上文化相关领域企业营业收入累计增长'),
    ('mfgShare', '规模以上文化制造业企业营业收入所占比重累计值'),
    ('wholesaleShare', '规模以上文化批发和零售业企业营业收入所占比重累计值'),
    ('serviceShare', '规模以上文化服务业企业营业收入所占比重累计值'),
    ('coreShare', '规模以上文化核心领域企业营业收入所占比重累计值'),
    ('relatedShare', '规模以上文化相关领域企业营业收入所占比重累计值'),
]

INDUSTRIES = [
    ('新闻信息服务', '规模以上新闻信息服务营业收入累计值'),
    ('内容创作生产', '规模以上内容创作生产营业收入累计值'),
    ('创意设计服务', '规模以上创意设计服务营业收入累计值'),
    ('文化传播渠道', '规模以上文化传播渠道营业收入累计值'),
    ('文化投资运营', '规模以上文化投资运营营业收入累计值'),
    ('文化娱乐休闲', '规模以上文化娱乐休闲服务营业收入累计值'),
    ('文化辅助中介', '规模以上文化辅助生产和中介服务营业收入累计值'),
    ('文化装备生产', '规模以上文化装备生产营业收入累计值'),
    ('文化消费终端', '规模以上文化消费终端生产营业收入累计值'),
]


def parse_file(fp):
    text = fp.read_text(encoding='utf-8-sig')
    quarters, rows = None, {}
    for line in text.splitlines():
        if '\t' not in line:
            continue
        cells = [c.replace(',', '').strip() for c in line.split('\t')]
        first = re.sub(r'\s+', '', cells[0] or '')
        if first == '指标':
            quarters = []
            for c in cells[1:]:
                if not c:
                    continue
                m = re.match(r'(\d{4})年第([一二三四])季度', c)
                if m:
                    quarters.append('%sQ%d' % (m.group(1), QMAP[m.group(2)]))
            continue
        if not first or first.startswith(('注', '数据库', '时间', '数据来源')):
            continue
        vals = []
        for c in cells[1:]:
            try:
                vals.append(float(c))
            except ValueError:
                vals.append(None)
        while vals and vals[-1] is None:
            vals.pop()
        rows[first] = vals
    return quarters, rows


def load_data():
    if not DATA_DIR.exists():
        raise SystemExit('未找到数据目录：%s' % DATA_DIR)
    all_rows = {}
    quarters = None
    for fp in sorted(DATA_DIR.glob('*.csv')):
        qs, rows = parse_file(fp)
        if not rows:
            continue
        if quarters is None or len(qs) > len(quarters):
            quarters = qs
        for k, v in rows.items():
            if k in all_rows and all_rows[k] != v:
                raise SystemExit('指标行冲突：%s' % k)
            all_rows[k] = v
    if quarters is None:
        raise SystemExit('data/ 下未找到有效数据表')
    quarters = list(reversed(quarters))  # 表头为逆序，转为时间正序

    n = len(quarters)
    S = {}
    for alias, prefix in MAIN_SPEC:
        key = next((k for k in all_rows if k.startswith(prefix)), None)
        if key is None:
            raise SystemExit('缺少指标：%s' % prefix)
        vals = list(reversed(all_rows[key]))
        if len(vals) != n or any(v is None for v in vals):
            raise SystemExit('指标 %s 长度/缺失异常：%d 项（需 %d）' % (alias, len(vals), n))
        S[alias] = vals

    industries = {}
    for short, prefix in INDUSTRIES:
        vkey = next((k for k in all_rows if k.startswith(prefix)), None)
        gprefix = prefix.replace('营业收入累计值', '营业收入累计增长')
        gkey = next((k for k in all_rows if k.startswith(gprefix)), None)
        if vkey is None or gkey is None:
            raise SystemExit('缺少大类指标：%s' % prefix)
        v = list(reversed(all_rows[vkey]))
        g = list(reversed(all_rows[gkey]))
        if len(v) != n or any(x is None for x in v):
            raise SystemExit('大类 %s 数据异常' % short)
        industries[short] = {'v': v, 'g': g}
    return quarters, S, industries


# =====================================================================
# 二、ECharts 图表库获取
# =====================================================================

ECHARTS_URLS = [
    'https://registry.npmmirror.com/echarts/5.5.1/files/dist/echarts.min.js',
    'https://cdn.bootcdn.net/ajax/libs/echarts/5.5.1/echarts.min.js',
    'https://cdn.staticfile.net/echarts/5.5.1/echarts.min.js',
    'https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js',
    'https://unpkg.com/echarts@5.5.1/dist/echarts.min.js',
]


def get_echarts_tag():
    if ECHARTS_CACHE.exists() and ECHARTS_CACHE.stat().st_size > 500000:
        print('[ECharts] 使用本地缓存 %s' % ECHARTS_CACHE.name)
        js = ECHARTS_CACHE.read_text(encoding='utf-8').replace('</script', '<\\/script')
        return '<script>\n' + js + '\n</script>'
    for url in ECHARTS_URLS:
        try:
            print('[ECharts] 尝试下载：%s' % url)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            if len(data) > 500000:
                ECHARTS_CACHE.write_bytes(data)
                print('[ECharts] 下载成功，已缓存到 %s（之后可完全离线运行）' % ECHARTS_CACHE.name)
                return '<script>\n' + data.decode('utf-8').replace('</script', '<\\/script') + '\n</script>'
            print('  文件大小异常（%d 字节），换下一个源' % len(data))
        except Exception as e:
            print('  失败：%s' % e)
    print('[ECharts] 所有下载源均失败，页面将改为联网加载 CDN（打开大屏时需要网络）')
    return '<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>'


# =====================================================================
# 三、页面资源：Bento 便当格样式 / 模板 / 交互脚本
# =====================================================================

# pylint: disable=line-too-long
CSS = r"""
#wh2-dashboard-root {
  --ink: #1d1d1f; --gray: #86868b; --faint: #aeaeb2;
  --blue: #0071e3; --green: #34c759; --orange: #ff9f0a; --pink: #ff375f; --purple: #bf5af2;
  --line: rgba(60,60,67,0.10);
  position: relative;
  color: var(--ink);
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  font-size: 14px; line-height: 1.5;
  padding: 22px 24px 16px; border-radius: 24px; min-width: 0;
  background: #f5f5f7;
}
#wh2-dashboard-root * { box-sizing: border-box; }

/* ---------- 头部 ---------- */
.wh2-header { display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 16px; }
.wh2-brand h1 { margin: 0; font-size: 26px; font-weight: 800; letter-spacing: 0.5px; color: var(--ink); }
.wh2-brand p { margin: 3px 0 0; font-size: 13px; color: var(--gray); }
.wh2-chip { font-size: 13px; font-weight: 700; color: var(--blue); background: rgba(0,113,227,0.08);
  border-radius: 999px; padding: 7px 18px; white-space: nowrap; font-variant-numeric: tabular-nums; }

/* ---------- 时间轴 ---------- */
.wh2-timeline { background: #fff; border-radius: 18px; padding: 12px 20px 24px; display: flex;
  align-items: center; gap: 12px; position: relative; margin-bottom: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.wh2-tl-label { font-size: 12.5px; font-weight: 600; color: var(--gray); flex: 0 0 auto; }
.wh2-arrow { width: 28px; height: 28px; border-radius: 50%; border: none; background: #f0f0f2;
  color: var(--gray); cursor: pointer; flex: 0 0 auto; font-size: 13px; line-height: 1;
  display: flex; align-items: center; justify-content: center; padding: 0; font-family: inherit; }
.wh2-arrow:hover { background: #e4e6ea; color: var(--ink); }
#wh2-range { flex: 1; -webkit-appearance: none; appearance: none; height: 6px; border-radius: 3px;
  background: #e8e8ed; outline: none; cursor: pointer; min-width: 120px; }
#wh2-range::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 18px; height: 18px;
  border-radius: 50%; background: var(--blue); border: 3px solid #fff;
  box-shadow: 0 1px 6px rgba(0,113,227,0.4); cursor: grab; }
#wh2-range::-moz-range-thumb { width: 13px; height: 13px; border-radius: 50%; background: var(--blue);
  border: 3px solid #fff; cursor: grab; }
.wh2-btn { border: none; background: #f0f0f2; color: var(--ink); border-radius: 999px;
  padding: 6px 16px; font-size: 12.5px; cursor: pointer; font-family: inherit; font-weight: 600; }
.wh2-btn:hover { background: #e4e6ea; }
.wh2-btn.primary { background: var(--blue); color: #fff; }
.wh2-hint { font-size: 11.5px; color: var(--faint); flex: 0 0 auto; max-width: 260px; text-align: right; line-height: 1.45; }
.wh2-years { position: absolute; left: 100px; right: 340px; bottom: 4px; height: 15px; pointer-events: none; }
.wh2-years span { position: absolute; transform: translateX(-50%); font-size: 10.5px; color: var(--faint); }

/* ---------- 详情钉住栏 ---------- */
.wh2-detail { background: #fff; border-radius: 14px; padding: 10px 18px; font-size: 13px;
  line-height: 1.7; margin-bottom: 16px; color: #3a3a3c; min-height: 42px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.wh2-detail b { color: var(--blue); font-weight: 700; }

/* ---------- Bento KPI ---------- */
.wh2-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 16px; margin-bottom: 16px; }
.wh2-kpi { background: #fff; border-radius: 22px; padding: 18px 18px 16px; min-width: 0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); position: relative; overflow: hidden; }
.wh2-kpi .dot { width: 30px; height: 30px; border-radius: 10px; margin-bottom: 12px;
  background: var(--ac, var(--blue)); opacity: 0.14; }
.wh2-kpi-top { font-size: 12.5px; color: var(--gray); font-weight: 600; }
.wh2-kpi-val { font-size: 30px; font-weight: 800; margin: 2px 0 3px; white-space: nowrap;
  color: var(--ink); font-variant-numeric: tabular-nums; letter-spacing: -0.5px; }
.wh2-kpi-val small { font-size: 13px; color: var(--gray); margin-left: 3px; font-weight: 600; }
.wh2-kpi-sub { font-size: 11.5px; color: var(--gray); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wh2-up { color: var(--green); font-weight: 700; }
.wh2-down { color: var(--pink); font-weight: 700; }

/* ---------- Bento 图表网格 ---------- */
.wh2-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
.wh2-card { background: #fff; border-radius: 22px; padding: 18px 20px 10px; min-width: 0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.wh2-s4 { grid-column: span 4; } .wh2-s6 { grid-column: span 6; } .wh2-s8 { grid-column: span 8; }
.wh2-card-h { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.wh2-card-h h3 { font-size: 15.5px; font-weight: 700; margin: 0; color: var(--ink); }
.wh2-hint-r { font-size: 11.5px; color: var(--faint); }
.wh2-sub { font-size: 12px; color: var(--gray); margin: 3px 0 2px; }
.wh2-chart { width: 100%; }
#wh2-ch-rev { height: 330px; }
#wh2-ch-quadrant { height: 330px; }
#wh2-ch-rank, #wh2-ch-growth, #wh2-ch-sector { height: 300px; }
#wh2-ch-profit, #wh2-ch-domain { height: 290px; }
.wh2-foot { font-size: 11.5px; color: var(--faint); margin-top: 14px; line-height: 1.7; }

@media (prefers-reduced-motion: reduce) {
  #wh2-dashboard-root *, #wh2-dashboard-root *::before { animation: none !important; transition: none !important; }
}
@media (max-width: 1280px) {
  .wh2-s4, .wh2-s6, .wh2-s8 { grid-column: span 12; }
  .wh2-kpis { grid-template-columns: repeat(3, 1fr); }
  .wh2-years { display: none; }
}
@media (max-width: 720px) {
  .wh2-kpis { grid-template-columns: 1fr; }
  #wh2-dashboard-root { padding: 14px; }
}
"""

TEMPLATE = """
<style>
/*__STYLE__*/
</style>

<div id="wh2-dashboard-root">
  <div class="wh2-header">
    <div class="wh2-brand">
      <h1>文化产业季度数据大屏</h1>
      <p>规模以上文化及相关产业 · 营收 / 利润 / 资产 / 九大产业结构 &nbsp;|&nbsp; 数据来源：国家统计局「季度数据」</p>
    </div>
    <span class="wh2-chip" id="wh2-chip">—</span>
  </div>

  <div class="wh2-timeline">
    <span class="wh2-tl-label">季度</span>
    <button type="button" class="wh2-arrow" id="btn-prev" aria-label="上一季度">‹</button>
    <input type="range" id="wh2-range" min="0" max="4" step="1" value="4" aria-label="选择季度" />
    <button type="button" class="wh2-arrow" id="btn-next" aria-label="下一季度">›</button>
    <button type="button" class="wh2-btn primary" id="btn-play">播放</button>
    <button type="button" class="wh2-btn" id="btn-reset">重置</button>
    <span class="wh2-hint">拖动时间轴或点击图 01/06 中的柱线即可联动全部图表 · 点击数据点钉住详情</span>
    <div class="wh2-years" aria-hidden="true">
      <span style="left:0%">2025Q2</span><span style="left:25%">2025Q3</span><span style="left:50%">2025Q4</span><span style="left:75%">2026Q1</span><span style="left:100%">2026Q2</span>
    </div>
  </div>

  <div class="wh2-detail" id="wh2-detail" aria-live="polite"></div>

  <div class="wh2-kpis" id="wh2-kpis"></div>

  <div class="wh2-grid">
    <div class="wh2-card wh2-s8">
      <div class="wh2-card-h"><h3>01 营业收入走势（累计）</h3><span class="wh2-hint-r">点击柱体切换季度</span></div>
      <div class="wh2-sub">柱：营业收入累计值（亿元）· 线：累计增长（%）</div>
      <div class="wh2-chart" id="wh2-ch-rev"></div>
    </div>
    <div class="wh2-card wh2-s4">
      <div class="wh2-card-h"><h3>02 增长 × 占比象限</h3><span class="wh2-hint-r">气泡 = 营收规模</span></div>
      <div class="wh2-sub" id="wh2-sub-quadrant">当前季度 · 横轴占比 · 纵轴累计增长</div>
      <div class="wh2-chart" id="wh2-ch-quadrant"></div>
    </div>
    <div class="wh2-card wh2-s4">
      <div class="wh2-card-h"><h3>03 九大产业结构排行</h3><span class="wh2-hint-r">按营收降序</span></div>
      <div class="wh2-sub" id="wh2-sub-rank">当前季度 · 亿元 · 括号内为累计增长</div>
      <div class="wh2-chart" id="wh2-ch-rank"></div>
    </div>
    <div class="wh2-card wh2-s4">
      <div class="wh2-card-h"><h3>04 九大类累计增长对比</h3><span class="wh2-hint-r">正 / 负增长</span></div>
      <div class="wh2-sub" id="wh2-sub-growth">当前季度 · 累计增长（%）· 按增速降序</div>
      <div class="wh2-chart" id="wh2-ch-growth"></div>
    </div>
    <div class="wh2-card wh2-s4">
      <div class="wh2-card-h"><h3>05 三大行业构成</h3><span class="wh2-hint-r">100% 堆叠</span></div>
      <div class="wh2-sub">文化制造 / 批发零售 / 文化服务业 占营收比重（%）</div>
      <div class="wh2-chart" id="wh2-ch-sector"></div>
    </div>
    <div class="wh2-card wh2-s6">
      <div class="wh2-card-h"><h3>06 利润与资产（累计/季末）</h3><span class="wh2-hint-r">点击切换季度</span></div>
      <div class="wh2-sub">柱：利润总额累计值（亿元）· 线：资产总计季末值（万亿元）</div>
      <div class="wh2-chart" id="wh2-ch-profit"></div>
    </div>
    <div class="wh2-card wh2-s6">
      <div class="wh2-card-h"><h3>07 核心领域 vs 相关领域</h3><span class="wh2-hint-r">营收占比环形</span></div>
      <div class="wh2-sub" id="wh2-sub-domain">当前季度 · 占营业收入比重（%）</div>
      <div class="wh2-chart" id="wh2-ch-domain"></div>
    </div>
  </div>

  <div class="wh2-foot">
    数据来源：国家统计局「数据库 — 季度数据」（规模以上文化及相关产业，2025Q2—2026Q2 共 5 期）。
    营业收入与利润为累计值口径，资产总计为季末存量口径（同比增长率由统计局发布）；
    累计增长由统计局发布，非本屏计算。九大类划分依据《文化及相关产业分类（2018）》。
  </div>
</div>

__ECHARTS__

<script>
window.WH2_DATA = /*__DATA__*/;
</script>

<script>
/*__APP__*/
</script>
"""

APP = r"""
(function () {
  'use strict';
  var root = document.getElementById('wh2-dashboard-root');
  if (!root) return;
  if (typeof echarts === 'undefined') {
    root.innerHTML = '<div style="padding:60px 20px;text-align:center;color:#86868b;font-size:14px;">ECharts 加载失败：请联网后刷新（首次运行脚本会自动下载并内联图表库）。</div>';
    return;
  }
  var RAW = window.WH2_DATA;
  var Q = RAW.quarters, N = Q.length, S = RAW.series, IND = RAW.industries;
  var IND_NAMES = RAW.industryNames;
  var state = { qi: N - 1, playing: false, timer: null };

  var C = {
    blue: '#0071e3', green: '#34c759', orange: '#ff9f0a', pink: '#ff375f', purple: '#bf5af2',
    ink: '#1d1d1f', gray: '#86868b', faint: '#aeaeb2',
    axis: 'rgba(60,60,67,0.45)', axisLine: 'rgba(60,60,67,0.15)', split: 'rgba(60,60,67,0.07)',
    tipBg: 'rgba(255,255,255,0.98)', tipBorder: 'rgba(0,0,0,0.06)'
  };
  var PALETTE = [C.blue, C.green, C.orange, C.pink, C.purple, '#8e8e93'];
  var TIP = {
    backgroundColor: C.tipBg, borderColor: C.tipBorder, borderWidth: 1,
    padding: [10, 14], textStyle: { color: C.ink, fontSize: 12.5 },
    extraCssText: 'box-shadow:0 8px 28px rgba(0,0,0,0.12);border-radius:14px;'
  };
  function tipTitle(q) { return '<div style="font-weight:700;font-size:13px;margin-bottom:4px;">' + q + '</div>'; }
  function tipRow(k, v, color) {
    return '<div style="display:flex;justify-content:space-between;gap:22px;line-height:1.9;">' +
      '<span style="opacity:.6;">' + k + '</span>' +
      '<span style="font-weight:600;' + (color ? 'color:' + color : '') + '">' + v + '</span></div>';
  }
  function el(id) { return document.getElementById(id); }
  function sgn(v) { return (v > 0 ? '+' : '') + v.toFixed(1); }
  function fmtYi(v) { return Math.round(v).toLocaleString('en-US'); }
  function wanYi(v) { return (v / 10000).toFixed(2); }
  function cls(v) { return v >= 0 ? 'wh2-up' : 'wh2-down'; }
  function wanFmt() {
    return function (v) { return v >= 10000 ? (v / 10000) + '万亿' : v; };
  }
  function r1(v) { return Math.round(v * 10) / 10; }

  var charts = {};
  function mk(id) { var c = echarts.init(el(id)); charts[id] = c; return c; }
  var chRev = mk('wh2-ch-rev'), chQuadrant = mk('wh2-ch-quadrant'), chRank = mk('wh2-ch-rank'),
      chGrowth = mk('wh2-ch-growth'), chSector = mk('wh2-ch-sector'), chProfit = mk('wh2-ch-profit'),
      chDomain = mk('wh2-ch-domain');
  var ALL = [chRev, chQuadrant, chRank, chGrowth, chSector, chProfit, chDomain];

  /* ---------- 图 01：营收走势 ---------- */
  function optRev() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 12, textStyle: { fontSize: 11, color: C.gray } },
      grid: { left: 58, right: 44, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('营业收入', fmtYi(S.rev[i]) + ' 亿元', C.blue) +
            tipRow('累计增长', sgn(S.revGrowth[i]) + '%', C.green);
        }
      }),
      xAxis: { type: 'category', data: Q,
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: [
        { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5, formatter: wanFmt() }, splitLine: { lineStyle: { color: C.split } } },
        { type: 'value', position: 'right', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { show: false } }
      ],
      series: [
        { name: '营业收入', type: 'bar', data: S.rev, barWidth: '44%',
          itemStyle: { borderRadius: [8, 8, 0, 0], color: C.blue } },
        { name: '累计增长', type: 'line', yAxisIndex: 1, data: S.revGrowth, symbol: 'circle', symbolSize: 7, z: 6,
          lineStyle: { width: 3, color: C.orange }, itemStyle: { color: C.orange } }
      ]
    };
  }

  /* ---------- 图 02：增长 × 占比象限 ---------- */
  function optQuadrant() {
    var total = S.rev[state.qi];
    var points = IND_NAMES.map(function (name, i) {
      var v = IND[name].v[state.qi], g = IND[name].g[state.qi];
      return { name: name, share: r1(v / total * 100), g: g, v: v };
    });
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 46, right: 30, top: 16, bottom: 40 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var it = points[p.dataIndex];
          return tipTitle(it.name) +
            tipRow('营业收入', fmtYi(it.v) + ' 亿元', C.blue) +
            tipRow('营收占比', it.share.toFixed(1) + '%') +
            tipRow('累计增长', sgn(it.g) + '%', it.g >= 0 ? C.green : C.pink);
        }
      }),
      xAxis: { type: 'value', name: '营收占比 %', nameTextStyle: { color: C.faint, fontSize: 10.5 },
        nameGap: 22, axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'value', name: '累计增长 %', nameTextStyle: { color: C.faint, fontSize: 10.5 },
        axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      series: [{
        name: '九大类', type: 'scatter',
        data: points.map(function (it, i) {
          return { value: [it.share, it.g],
            symbolSize: Math.max(10, Math.sqrt(it.v) * 0.55),
            itemStyle: { color: PALETTE[i % PALETTE.length], opacity: 0.9 },
            label: { show: true, position: 'right', distance: 6, fontSize: 10.5, color: C.gray, formatter: it.name } };
        })
      }]
    };
  }

  /* ---------- 图 03：九大类排行 ---------- */
  function optRank() {
    var items = IND_NAMES.map(function (name) {
      return { name: name, v: IND[name].v[state.qi], g: IND[name].g[state.qi] };
    }).sort(function (a, b) { return b.v - a.v; });
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 92, right: 78, top: 8, bottom: 20 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var it = items[p.dataIndex];
          return tipTitle(it.name) +
            tipRow('营业收入', fmtYi(it.v) + ' 亿元', C.blue) +
            tipRow('累计增长', sgn(it.g) + '%', it.g >= 0 ? C.green : C.pink);
        }
      }),
      xAxis: { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x.name; }),
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: C.gray, fontSize: 11 } },
      series: [{
        name: '营业收入', type: 'bar', barWidth: '58%',
        data: items.map(function (x, i) {
          return { value: x.v,
            itemStyle: { borderRadius: [0, 8, 8, 0], color: i === 0 ? C.blue : 'rgba(0,113,227,' + (0.75 - i * 0.055 > 0.25 ? 0.75 - i * 0.055 : 0.25) + ')' } };
        }),
        label: { show: true, position: 'right', fontSize: 10.5, color: C.ink, fontWeight: 600,
          formatter: function (p) {
            var it = items[p.dataIndex];
            return fmtYi(it.v) + '（' + sgn(it.g) + '%）';
          } }
      }]
    };
  }

  /* ---------- 图 04：增速对比 ---------- */
  function optGrowth() {
    var items = IND_NAMES.map(function (name) {
      return { name: name, g: IND[name].g[state.qi] };
    }).sort(function (a, b) { return b.g - a.g; });
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 92, right: 66, top: 8, bottom: 20 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var it = items[p.dataIndex];
          return tipTitle(it.name) + tipRow('累计增长', sgn(it.g) + '%', it.g >= 0 ? C.green : C.pink);
        }
      }),
      xAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x.name; }),
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: C.gray, fontSize: 11 } },
      series: [{
        name: '累计增长', type: 'bar', barWidth: '58%',
        data: items.map(function (x) {
          return { value: x.g,
            itemStyle: { borderRadius: x.g >= 0 ? [0, 8, 8, 0] : [8, 0, 0, 6], color: x.g >= 0 ? C.green : C.pink },
            label: { position: x.g >= 0 ? 'right' : 'left' } };
        }),
        label: { show: true, fontSize: 10.5, color: C.ink, fontWeight: 600,
          formatter: function (p) { return sgn(p.value) + '%'; } },
        markLine: { silent: true, symbol: 'none', animation: false, label: { show: false },
          lineStyle: { color: C.axisLine }, data: [{ xAxis: 0 }] }
      }]
    };
  }

  /* ---------- 图 05：三大行业构成 ---------- */
  function optSector() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.blue, C.orange, C.green],
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 8, textStyle: { fontSize: 10.5, color: C.gray } },
      grid: { left: 66, right: 26, top: 12, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('文化制造业', fmtYi(S.mfg[i]) + ' 亿元 (' + S.mfgShare[i].toFixed(1) + '%)', C.blue) +
            tipRow('批发和零售业', fmtYi(S.wholesale[i]) + ' 亿元 (' + S.wholesaleShare[i].toFixed(1) + '%)', C.orange) +
            tipRow('文化服务业', fmtYi(S.service[i]) + ' 亿元 (' + S.serviceShare[i].toFixed(1) + '%)', C.green);
        }
      }),
      xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', data: Q, inverse: true,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: C.gray, fontSize: 10.5 } },
      series: [
        { name: '文化制造业', type: 'bar', stack: 's', data: S.mfgShare, barWidth: '60%', itemStyle: { borderRadius: [8, 0, 0, 8] },
          label: { show: true, position: 'inside', fontSize: 10.5, color: '#fff', fontWeight: 600, formatter: function (p) { return p.value >= 8 ? p.value + '%' : ''; } } },
        { name: '批发和零售业', type: 'bar', stack: 's', data: S.wholesaleShare, itemStyle: {},
          label: { show: true, position: 'inside', fontSize: 10.5, color: '#fff', fontWeight: 600, formatter: function (p) { return p.value >= 8 ? p.value + '%' : ''; } } },
        { name: '文化服务业', type: 'bar', stack: 's', data: S.serviceShare, itemStyle: { borderRadius: [0, 8, 8, 0] },
          label: { show: true, position: 'inside', fontSize: 10.5, color: '#fff', fontWeight: 600, formatter: function (p) { return p.value >= 8 ? p.value + '%' : ''; } } }
      ]
    };
  }

  /* ---------- 图 06：利润与资产 ---------- */
  function optProfit() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 12, textStyle: { fontSize: 11, color: C.gray } },
      grid: { left: 56, right: 58, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('利润总额', fmtYi(S.profit[i]) + ' 亿元', C.pink) +
            tipRow('利润累计增长', sgn(S.profitGrowth[i]) + '%', C.orange) +
            tipRow('资产总计', wanYi(S.assets[i]) + ' 万亿元（季末）', C.blue) +
            tipRow('资产同比', sgn(S.assetsYoy[i]) + '%', C.blue);
        }
      }),
      xAxis: { type: 'category', data: Q,
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: [
        { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
        { type: 'value', position: 'right', axisLabel: { color: C.axis, fontSize: 10.5, formatter: function (v) { return v + '万亿'; } }, splitLine: { show: false }, max: function (v) { return v.max * 1.15; } }
      ],
      series: [
        { name: '利润总额', type: 'bar', data: S.profit, barWidth: '44%',
          itemStyle: { borderRadius: [8, 8, 0, 0], color: C.pink } },
        { name: '资产总计', type: 'line', yAxisIndex: 1, data: S.assets, symbol: 'circle', symbolSize: 7, z: 6,
          lineStyle: { width: 3, color: C.blue }, itemStyle: { color: C.blue } }
      ]
    };
  }

  /* ---------- 图 07：核心 vs 相关 ---------- */
  function optDomain() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.blue, '#c7c7cc'],
      legend: { bottom: 0, icon: 'circle', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11.5, color: C.gray } },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var i = p.dataIndex;
          var v = i === 0 ? S.core[state.qi] : S.related[state.qi];
          var g = i === 0 ? S.coreGrowth[state.qi] : S.relatedGrowth[state.qi];
          return tipTitle(p.name) +
            tipRow('营业收入', fmtYi(v) + ' 亿元', C.blue) +
            tipRow('占比', p.percent.toFixed(1) + '%') +
            tipRow('累计增长', sgn(g) + '%', g >= 0 ? C.green : C.pink);
        }
      }),
      series: [{
        name: '营收占比', type: 'pie', radius: ['52%', '74%'], center: ['50%', '44%'],
        data: [
          { name: '核心领域', value: S.core[state.qi] },
          { name: '相关领域', value: S.related[state.qi] }
        ],
        itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 6 },
        label: { color: C.ink, fontSize: 12, fontWeight: 600, formatter: '{d}%' },
        labelLine: { length: 10, length2: 8, lineStyle: { color: C.axisLine } }
      }]
    };
  }

  /* ---------- 详情钉住 ---------- */
  function pinDetail(html) { el('wh2-detail').innerHTML = html; }
  var DEFAULT_HINT = '<b>使用提示</b>&nbsp;&nbsp;拖动时间轴或点击图 01/06 中的柱线即可联动全部图表；点击数据点可将详情钉住显示在此栏。';
  function resetDetail() { el('wh2-detail').innerHTML = DEFAULT_HINT; }

  chRev.on('click', function (p) {
    if (typeof p.dataIndex !== 'number') return;
    setQuarter(p.dataIndex, true);
    if (p.seriesName === '累计增长') {
      pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · 营业收入累计增长') + '<b>' + sgn(S.revGrowth[p.dataIndex]) + '%</b>');
    }
  });
  chProfit.on('click', function (p) {
    if (typeof p.dataIndex !== 'number') return;
    setQuarter(p.dataIndex, true);
    if (p.seriesName === '资产总计') {
      pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · 资产总计（季末）') +
        '<b>' + wanYi(S.assets[p.dataIndex]) + ' 万亿元</b>&nbsp;&nbsp;同比 <b>' + sgn(S.assetsYoy[p.dataIndex]) + '%</b>');
    } else if (p.seriesName === '利润总额') {
      pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · 利润总额（累计）') +
        '<b>' + fmtYi(S.profit[p.dataIndex]) + ' 亿元</b>&nbsp;&nbsp;累计增长 <b>' + sgn(S.profitGrowth[p.dataIndex]) + '%</b>');
    }
  });

  /* ---------- KPI 与速读 ---------- */
  function kpiCard(ac, title, val, unit, sub) {
    return '<div class="wh2-kpi" style="--ac:' + ac + '"><div class="dot"></div>' +
      '<div class="wh2-kpi-top">' + title + '</div>' +
      '<div class="wh2-kpi-val">' + val + '<small>' + unit + '</small></div>' +
      '<div class="wh2-kpi-sub">' + sub + '</div></div>';
  }
  function renderKpis() {
    var i = state.qi;
    var best = null, worst = null;
    IND_NAMES.forEach(function (name) {
      var g = IND[name].g[i];
      if (!best || g > best.g) best = { n: name, g: g };
      if (!worst || g < worst.g) worst = { n: name, g: g };
    });
    el('wh2-kpis').innerHTML =
      kpiCard(C.blue, '营业收入', wanYi(S.rev[i]), '万亿元',
        '累计增长 <span class="' + cls(S.revGrowth[i]) + '">' + sgn(S.revGrowth[i]) + '%</span>') +
      kpiCard(C.pink, '利润总额', fmtYi(S.profit[i]), '亿元',
        '累计增长 <span class="' + cls(S.profitGrowth[i]) + '">' + sgn(S.profitGrowth[i]) + '%</span>') +
      kpiCard(C.green, '资产总计', wanYi(S.assets[i]), '万亿元',
        '季末值 · 同比 <span class="' + cls(S.assetsYoy[i]) + '">' + sgn(S.assetsYoy[i]) + '%</span>') +
      kpiCard(C.purple, '核心领域占比', S.coreShare[i].toFixed(1), '%',
        '相关领域 ' + S.relatedShare[i].toFixed(1) + '%') +
      kpiCard(C.orange, '文化服务业占比', S.serviceShare[i].toFixed(1), '%',
        '制造 ' + S.mfgShare[i].toFixed(1) + '% · 批零 ' + S.wholesaleShare[i].toFixed(1) + '%') +
      kpiCard(C.blue, '增长最快大类', sgn(best.g), '%',
        '<span class="wh2-up">' + best.n + '</span>' +
        (worst.n !== best.n ? ' · 最慢 <span class="wh2-down">' + worst.n + '</span>' : ''));
  }
  function renderBrief() {
    var i = state.qi;
    var sorted = IND_NAMES.map(function (name) { return { n: name, g: IND[name].g[i] }; })
      .sort(function (a, b) { return b.g - a.g; });
    el('wh2-detail').innerHTML =
      '<b>' + Q[i] + ' 速读</b>&nbsp;&nbsp;文化产业营业收入累计 <b>' + wanYi(S.rev[i]) + ' 万亿元</b>' +
      '（同比 <b>' + sgn(S.revGrowth[i]) + '%</b>）；利润总额 <b>' + fmtYi(S.profit[i]) + ' 亿元</b>' +
      '（<b>' + sgn(S.profitGrowth[i]) + '%</b>）；核心领域营收占 <b>' + S.coreShare[i].toFixed(1) + '%</b>，' +
      '文化服务业占 <b>' + S.serviceShare[i].toFixed(1) + '%</b>；' +
      '增长最快 <b>' + sorted[0].n + '（' + sgn(sorted[0].g) + '%）</b>，最慢 ' +
      sorted[sorted.length - 1].n + '（' + sgn(sorted[sorted.length - 1].g) + '%）。';
  }

  /* ---------- 渲染 ---------- */
  function renderSlider() {
    var r = el('wh2-range');
    r.value = state.qi;
    var p = state.qi / (N - 1) * 100;
    r.style.background = 'linear-gradient(to right,#0071e3 0%,#0071e3 ' + p + '%,#e8e8ed ' + p + '%)';
  }
  function apply() {
    var qi = state.qi;
    el('wh2-chip').textContent = Q[qi] + ' · 累计口径';
    renderSlider();
    renderKpis();
    renderBrief();
    chRev.setOption(optRev(), true);
    chQuadrant.setOption(optQuadrant(), true);
    chRank.setOption(optRank(), true);
    el('wh2-sub-rank').textContent = Q[qi] + ' · 亿元 · 括号内为累计增长';
    chGrowth.setOption(optGrowth(), true);
    el('wh2-sub-growth').textContent = Q[qi] + ' · 累计增长（%）· 按增速降序';
    chSector.setOption(optSector(), true);
    chProfit.setOption(optProfit(), true);
    chDomain.setOption(optDomain(), true);
    el('wh2-sub-domain').textContent = Q[qi] + ' · 占营业收入比重（%）';
  }
  function setQuarter(i, fromUser) {
    state.qi = Math.max(0, Math.min(N - 1, i));
    apply();
    resetDetail();
  }
  function stopPlay() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    state.playing = false;
    el('btn-play').textContent = '播放';
  }
  function togglePlay() {
    if (state.playing) { stopPlay(); return; }
    state.playing = true;
    el('btn-play').textContent = '暂停';
    state.timer = setInterval(function () { setQuarter((state.qi + 1) % N); }, 1500);
  }
  el('btn-play').addEventListener('click', togglePlay);
  el('btn-reset').addEventListener('click', function () {
    stopPlay(); state.qi = N - 1; apply(); resetDetail();
  });
  el('btn-prev').addEventListener('click', function () { setQuarter(state.qi - 1, true); });
  el('btn-next').addEventListener('click', function () { setQuarter(state.qi + 1, true); });
  el('wh2-range').addEventListener('input', function () { setQuarter(+this.value, true); });

  window.addEventListener('resize', function () {
    ALL.forEach(function (c) { c.resize(); });
  });
  window.addEventListener('load', function () {
    ALL.forEach(function (c) { c.resize(); });
  });

  apply();
  resetDetail();
})();
"""

# =====================================================================
# 四、校验与组装（与 Aurora 版相同的数据管线）
# =====================================================================

def build_data(quarters, S, industries):
    n = len(quarters)
    i = n - 1
    print('解析完成：%d 期（%s — %s）。抽样核对最新一期：' % (n, quarters[0], quarters[-1]))
    checks = [
        ('营业收入累计(亿元)', S['rev'][i], 72026),
        ('利润总额累计(亿元)', S['profit'][i], 5747),
        ('资产总计季末(亿元)', S['assets'][i], 232991),
        ('营收累计增长(%)', S['revGrowth'][i], 4.6),
        ('新闻信息服务(亿元)', industries['新闻信息服务']['v'][i], 10958),
        ('文化服务业占比(%)', S['serviceShare'][i], 60.0),
        ('核心领域占比(%)', S['coreShare'][i], 70.1),
    ]
    ok = True
    for name, got, want in checks:
        match = abs(got - want) < 0.05
        ok = ok and match
        print('  %-16s 取值 %-12s 期望 %-12s %s' % (name, got, want, 'OK' if match else '!!'))
    if not ok:
        raise SystemExit('抽样校验未通过，请确认 CSV 为国家统计局原始导出文件。')

    total_by_ind = sum(industries[name]['v'][i] for name, _ in INDUSTRIES)
    if abs(total_by_ind - S['rev'][i]) > S['rev'][i] * 0.01:
        raise SystemExit('九大类合计 %s ≠ 总营收 %s，请检查数据' % (total_by_ind, S['rev'][i]))
    return {
        'quarters': quarters,
        'series': S,
        'industries': industries,
        'industryNames': [name for name, _ in INDUSTRIES]
    }


def main():
    no_open = '--no-open' in sys.argv
    print('正在扫描 %s 下的数据表 …' % DATA_DIR)
    quarters, S, industries = load_data()
    data = build_data(quarters, S, industries)

    echarts_tag = get_echarts_tag()
    data_json = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    fragment = (TEMPLATE
                .replace('/*__STYLE__*/', CSS)
                .replace('__ECHARTS__', echarts_tag)
                .replace('/*__DATA__*/', data_json)
                .replace('/*__APP__*/', APP))
    html = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>文化产业 · 季度数据大屏（便当格版）</title>\n</head>\n<body>\n'
            + fragment + '\n</body>\n</html>\n')
    with open(OUTPUT_HTML, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)
    print('已生成：%s（%.0f KB）' % (OUTPUT_HTML, len(html.encode('utf-8')) / 1024))
    if not no_open:
        try:
            webbrowser.open(OUTPUT_HTML.resolve().as_uri())
            print('已在默认浏览器中打开大屏。')
        except Exception as e:
            print('自动打开浏览器失败（%s），请手动双击该 HTML 文件。' % e)
    print('完成。')


if __name__ == '__main__':
    main()

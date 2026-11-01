# -*- coding: utf-8 -*-
'''文化产业 · 季度数据 BI 大屏生成器（Aurora 极光渐变风）
================================================================

自包含的可视化项目：仅用 Python 标准库即可在本机（VS Code / PyCharm / 命令行）运行，
无需 pip 安装任何第三方包。风格：Aurora UI —— 深底青紫粉极光晕、半透明卡片、
柔和发光（风格选型依据见 ../风格库/README.md；用户偏好：不出现图签/制表信息元素）。

功能
----
1. 读取 data/ 目录下的 6 张国家统计局文化产业季度表（2025Q2—2026Q2，共 5 期，
   营收/利润为累计值口径，资产总计为季末存量口径）：
   · 规模以上文化及相关产业企业营业收入（总体 + 按产业分 9 大类，含累计增长）
   · 按行业分营业收入（文化制造 / 批发零售 / 服务业 / 核心领域 / 相关领域）
   · 按产业和领域分营业收入比重（三大行业与核心/相关领域的官方占比）
   · 规模以上文化及相关产业企业利润总额、资产总计
2. 解析、校验并派生指标（大类占比、增长最快/最慢行业等）；
3. 生成「Aurora 极光渐变风」交互式 BI 大屏 HTML 并自动在浏览器中打开。

使用方法
--------
在本文件夹内打开终端，执行：
    python generate_bi_dashboard.py            # 生成大屏并自动打开浏览器
    python generate_bi_dashboard.py --no-open  # 只生成文件，不打开浏览器

首次运行会自动下载 ECharts 图表库并缓存为本文件夹下的 echarts.min.js（此后完全离线可用）。

输出：文化BI大屏.html（双击也可随时打开）。
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
OUTPUT_HTML = BASE / '文化BI大屏.html'

QMAP = {'一': 1, '二': 2, '三': 3, '四': 4}

# =====================================================================
# 一、数据解析：按指标行前缀抽取（前缀全局唯一，文件名无关）
# =====================================================================

# 总体与派生维度指标（前缀 → 别名）
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

# 按产业分 9 大类（短名 → 指标前缀）。文化投资运营体量极小，保留但图中可能贴 0。
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
    """解析单张表：返回 (季度列表, {指标名(去空白): 数值列表})。"""
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
    quarters = list(reversed(quarters))  # 表头为逆序，转为时间正序（2025Q2 → 2026Q2）

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
# 二、ECharts 图表库获取：本地缓存 → 在线下载（并缓存） → CDN 兜底
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
# 三、页面资源：极光风样式 / 模板 / 交互脚本
# =====================================================================

# pylint: disable=line-too-long
CSS = r"""
#wh-dashboard-root {
  --line: rgba(148,163,255,0.22);
  --teal: #5eead4; --purple: #a78bfa; --pink: #f472b6; --blue: #60a5fa; --gold: #fbbf24;
  --text: #e6ecff; --muted: rgba(230,236,255,0.62); --faint: rgba(230,236,255,0.4);
  position: relative;
  color: var(--text);
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  font-size: 14px; line-height: 1.5;
  padding: 18px 22px 12px; border-radius: 18px; min-width: 0;
  border: 1px solid rgba(148,163,255,0.18);
  background:
    radial-gradient(900px 420px at 12% -6%, rgba(94,234,212,0.16), transparent 60%),
    radial-gradient(1000px 480px at 88% 0%, rgba(167,139,250,0.16), transparent 60%),
    radial-gradient(900px 500px at 50% 115%, rgba(244,114,182,0.12), transparent 62%),
    linear-gradient(180deg, #0b1020 0%, #0d1226 60%, #0a0e1e 100%);
}
#wh-dashboard-root * { box-sizing: border-box; }

/* ---------- 头部 ---------- */
.wh-header { display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 12px; }
.wh-brand { display: flex; align-items: center; gap: 13px; min-width: 0; }
.wh-mark { width: 46px; height: 46px; border-radius: 14px; flex: 0 0 auto;
  background: linear-gradient(135deg, rgba(94,234,212,0.22), rgba(167,139,250,0.18));
  border: 1px solid rgba(94,234,212,0.4); display: flex; align-items: center; justify-content: center;
  color: #5eead4; box-shadow: 0 0 20px rgba(94,234,212,0.2); }
.wh-brand h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 2px; white-space: nowrap;
  background: linear-gradient(90deg, #5eead4, #a78bfa 55%, #f472b6);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.wh-brand p { margin: 2px 0 0; font-size: 12px; color: var(--muted); }
.wh-chip { font-size: 12.5px; font-weight: 700; color: #5eead4; font-variant-numeric: tabular-nums;
  background: rgba(94,234,212,0.08); border: 1px solid rgba(94,234,212,0.35);
  border-radius: 999px; padding: 6px 16px; white-space: nowrap; }

/* ---------- 时间轴 ---------- */
.wh-timeline { background: rgba(17,24,46,0.55); border: 1px solid var(--line);
  border-radius: 14px; padding: 12px 18px 24px; display: flex; align-items: center; gap: 12px;
  position: relative; margin-bottom: 12px; backdrop-filter: blur(6px); }
.wh-tl-label { font-size: 12.5px; font-weight: 600; color: var(--muted); flex: 0 0 auto; }
.wh-arrow { width: 26px; height: 26px; border-radius: 50%; border: 1px solid var(--line);
  background: rgba(17,24,46,0.8); color: var(--muted); cursor: pointer; flex: 0 0 auto; font-size: 13px;
  line-height: 1; display: flex; align-items: center; justify-content: center; padding: 0; font-family: inherit; }
.wh-arrow:hover { border-color: var(--teal); color: var(--teal); }
#wh-range { flex: 1; -webkit-appearance: none; appearance: none; height: 6px; border-radius: 3px;
  background: rgba(148,163,255,0.18); outline: none; cursor: pointer; min-width: 120px; }
#wh-range::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 16px; height: 16px;
  border-radius: 50%; background: linear-gradient(135deg, #5eead4, #a78bfa); border: 2px solid #0b1020;
  box-shadow: 0 0 12px rgba(94,234,212,0.6); cursor: grab; }
#wh-range::-moz-range-thumb { width: 13px; height: 13px; border-radius: 50%;
  background: linear-gradient(135deg, #5eead4, #a78bfa); border: 2px solid #0b1020; cursor: grab; }
.wh-years { position: absolute; left: 96px; right: 330px; bottom: 4px; height: 15px; pointer-events: none; }
.wh-years span { position: absolute; transform: translateX(-50%); font-size: 10.5px; color: var(--faint); }
.wh-btn { border: 1px solid var(--line); background: rgba(17,24,46,0.8); color: var(--muted);
  border-radius: 999px; padding: 5px 15px; font-size: 12.5px; cursor: pointer; font-family: inherit; }
.wh-btn:hover { border-color: var(--teal); color: var(--teal); }
.wh-btn.primary { background: linear-gradient(135deg, #5eead4, #a78bfa); color: #0b1020;
  border: none; font-weight: 700; }
.wh-hint { font-size: 11.5px; color: var(--faint); flex: 0 0 auto; max-width: 280px; text-align: right; line-height: 1.45; }

/* ---------- 详情钉住栏 ---------- */
.wh-detail { background: rgba(94,234,212,0.06); border: 1px solid rgba(94,234,212,0.2);
  border-radius: 12px; padding: 9px 16px; font-size: 13px; line-height: 1.7;
  margin-bottom: 12px; color: #cfe0ff; min-height: 42px; }
.wh-detail b { color: var(--teal); font-weight: 700; }

/* ---------- KPI ---------- */
.wh-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 12px; }
.wh-kpi { background: linear-gradient(165deg, rgba(30,40,74,0.6), rgba(16,22,44,0.45));
  border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; position: relative;
  overflow: hidden; min-width: 0; backdrop-filter: blur(6px); }
.wh-kpi::before { content: ''; position: absolute; top: 0; left: 8%; right: 8%; height: 1px;
  background: linear-gradient(90deg, transparent, var(--ac, #5eead4), transparent); opacity: 0.7; }
.wh-kpi-top { display: flex; justify-content: space-between; gap: 6px; font-size: 12px; color: var(--muted); }
.wh-kpi-val { font-size: 24px; font-weight: 700; margin: 4px 0 2px; white-space: nowrap; color: #f7f9ff;
  letter-spacing: 0.3px; text-shadow: 0 0 16px var(--ac, #5eead4); font-variant-numeric: tabular-nums; }
.wh-kpi-val small { font-size: 12px; color: var(--muted); margin-left: 3px; }
.wh-kpi-sub { font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wh-up { color: var(--teal); font-weight: 700; }
.wh-down { color: var(--pink); font-weight: 700; }

/* ---------- 图表网格 ---------- */
.wh-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }
.wh-card { background: linear-gradient(165deg, rgba(30,40,74,0.55), rgba(15,20,40,0.4));
  border: 1px solid var(--line); border-radius: 16px; padding: 13px 15px 6px; min-width: 0;
  position: relative; overflow: hidden; backdrop-filter: blur(6px); }
.wh-card::before { content: ''; position: absolute; top: 0; left: 6%; right: 6%; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(148,163,255,0.45), transparent); }
.wh-s6 { grid-column: span 6; }
.wh-card-h { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.wh-card-h h3 { font-size: 14.5px; font-weight: 700; margin: 0; letter-spacing: 1px; color: #eef2ff; }
.wh-hint-r { font-size: 11px; color: var(--faint); }
.wh-sub { font-size: 11.5px; color: var(--faint); margin: 2px 0 2px; }
.wh-chart { width: 100%; height: 300px; }
.wh-foot { font-size: 11px; color: var(--faint); margin-top: 10px; line-height: 1.7; }

@media (prefers-reduced-motion: reduce) {
  #wh-dashboard-root *, #wh-dashboard-root *::before { animation: none !important; transition: none !important; }
}
@media (max-width: 1280px) {
  .wh-s6 { grid-column: span 12; }
  .wh-kpis { grid-template-columns: repeat(3, 1fr); }
  .wh-years { display: none; }
}
@media (max-width: 720px) {
  .wh-kpis { grid-template-columns: 1fr; }
  #wh-dashboard-root { padding: 12px; }
}
"""

TEMPLATE = """
<style>
/*__STYLE__*/
</style>

<div id="wh-dashboard-root">
  <div class="wh-header">
    <div class="wh-brand">
      <div class="wh-mark" aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
          <path d="M4 19c3-6 5-4 8-9 2.2-3.6 5-4 8-4" /><circle cx="9" cy="12" r="1.4" fill="currentColor" stroke="none" /><circle cx="15" cy="7" r="1.4" fill="currentColor" stroke="none" /><circle cx="19" cy="14" r="1.4" fill="currentColor" stroke="none" />
        </svg>
      </div>
      <div>
        <h1>文化产业季度数据大屏</h1>
        <p>规模以上文化及相关产业 · 营收 / 利润 / 资产 / 九大产业结构 &nbsp;|&nbsp; 数据来源：国家统计局「季度数据」</p>
      </div>
    </div>
    <span class="wh-chip" id="wh-chip">—</span>
  </div>

  <div class="wh-timeline">
    <span class="wh-tl-label">季度</span>
    <button type="button" class="wh-arrow" id="btn-prev" aria-label="上一季度">‹</button>
    <input type="range" id="wh-range" min="0" max="4" step="1" value="4" aria-label="选择季度" />
    <button type="button" class="wh-arrow" id="btn-next" aria-label="下一季度">›</button>
    <button type="button" class="wh-btn primary" id="btn-play">播放</button>
    <button type="button" class="wh-btn" id="btn-reset">重置</button>
    <span class="wh-hint">拖动时间轴或点击图 01/02 中的柱线即可联动全部图表 · 点击数据点钉住详情</span>
    <div class="wh-years" aria-hidden="true">
      <span style="left:0%">2025Q2</span><span style="left:25%">2025Q3</span><span style="left:50%">2025Q4</span><span style="left:75%">2026Q1</span><span style="left:100%">2026Q2</span>
    </div>
  </div>

  <div class="wh-detail" id="wh-detail" aria-live="polite"></div>

  <div class="wh-kpis" id="wh-kpis"></div>

  <div class="wh-grid">
    <div class="wh-card wh-s6">
      <div class="wh-card-h"><h3>01 营业收入走势（累计）</h3><span class="wh-hint-r">点击柱体切换季度</span></div>
      <div class="wh-sub">柱：营业收入累计值（亿元）· 线：累计增长（%）</div>
      <div class="wh-chart" id="ch-rev"></div>
    </div>
    <div class="wh-card wh-s6">
      <div class="wh-card-h"><h3>02 九大产业结构排行</h3><span class="wh-hint-r">按营业收入降序</span></div>
      <div class="wh-sub" id="sub-rank">当前季度 · 亿元 · 括号内为累计增长</div>
      <div class="wh-chart" id="ch-rank"></div>
    </div>
    <div class="wh-card wh-s6">
      <div class="wh-card-h"><h3>03 九大类累计增长对比</h3><span class="wh-hint-r">正增长 / 负增长</span></div>
      <div class="wh-sub" id="sub-growth">当前季度 · 累计增长（%）· 按增速降序</div>
      <div class="wh-chart" id="ch-growth"></div>
    </div>
    <div class="wh-card wh-s6">
      <div class="wh-card-h"><h3>04 增长 × 占比象限</h3><span class="wh-hint-r">气泡 = 营收规模</span></div>
      <div class="wh-sub" id="sub-quadrant">当前季度 · 横轴营收占比（%）· 纵轴累计增长（%）</div>
      <div class="wh-chart" id="ch-quadrant"></div>
    </div>
    <div class="wh-card wh-s6">
      <div class="wh-card-h"><h3>05 三大行业构成（累计）</h3><span class="wh-hint-r">100% 堆叠</span></div>
      <div class="wh-sub">文化制造 / 批发零售 / 文化服务业 占营业收入比重（%）</div>
      <div class="wh-chart" id="ch-sector"></div>
    </div>
    <div class="wh-card wh-s6">
      <div class="wh-card-h"><h3>06 利润与资产（累计/季末）</h3><span class="wh-hint-r">点击切换季度</span></div>
      <div class="wh-sub">柱：利润总额累计值（亿元）· 线：资产总计季末值（万亿元）</div>
      <div class="wh-chart" id="ch-profit"></div>
    </div>
  </div>

  <div class="wh-foot">
    数据来源：国家统计局「数据库 — 季度数据」（规模以上文化及相关产业，2025Q2—2026Q2 共 5 期）。
    营业收入与利润为累计值口径，资产总计为季末存量口径（同比增长率由统计局发布）；
    累计增长由统计局发布，非本屏计算。九大类划分依据《文化及相关产业分类（2018）》。
  </div>
</div>

__ECHARTS__

<script>
window.WH_DATA = /*__DATA__*/;
</script>

<script>
/*__APP__*/
</script>
"""

APP = r"""
(function () {
  'use strict';
  var root = document.getElementById('wh-dashboard-root');
  if (!root) return;
  if (typeof echarts === 'undefined') {
    root.innerHTML = '<div style="padding:60px 20px;text-align:center;color:#8fa3c8;font-size:14px;">ECharts 加载失败：请联网后刷新（首次运行脚本会自动下载并内联图表库）。</div>';
    return;
  }
  var RAW = window.WH_DATA;
  var Q = RAW.quarters, N = Q.length, S = RAW.series, IND = RAW.industries;
  var IND_NAMES = RAW.industryNames;
  var state = { qi: N - 1, playing: false, timer: null };

  var C = {
    teal: '#5eead4', purple: '#a78bfa', pink: '#f472b6', blue: '#60a5fa', gold: '#fbbf24',
    axis: 'rgba(200,210,255,0.55)', axisLine: 'rgba(200,210,255,0.3)', split: 'rgba(200,210,255,0.09)',
    text: '#e6ecff', muted: 'rgba(230,236,255,0.62)', faint: 'rgba(230,236,255,0.4)',
    tipBg: 'rgba(13,18,38,0.95)', tipBorder: 'rgba(148,163,255,0.3)'
  };
  var PALETTE = [C.teal, C.purple, C.pink, C.blue, C.gold, '#e2e8f0'];
  var TIP = {
    backgroundColor: C.tipBg, borderColor: C.tipBorder, borderWidth: 1,
    padding: [10, 14], textStyle: { color: C.text, fontSize: 12.5 },
    extraCssText: 'box-shadow:0 12px 32px rgba(0,0,0,0.5);border-radius:10px;'
  };
  function tipTitle(q) { return '<div style="font-weight:700;font-size:13px;margin-bottom:4px;">' + q + '</div>'; }
  function tipRow(k, v, color) {
    return '<div style="display:flex;justify-content:space-between;gap:22px;line-height:1.9;">' +
      '<span style="opacity:.72;">' + k + '</span>' +
      '<span style="font-weight:600;' + (color ? 'color:' + color : '') + '">' + v + '</span></div>';
  }
  function el(id) { return document.getElementById(id); }
  function sgn(v) { return (v > 0 ? '+' : '') + v.toFixed(1); }
  function fmtYi(v) { return Math.round(v).toLocaleString('en-US'); }
  function wanYi(v) { return (v / 10000).toFixed(2); }
  function cls(v) { return v >= 0 ? 'wh-up' : 'wh-down'; }
  function wanFmt() {
    return function (v) { return v >= 10000 ? (v / 10000) + '万亿' : v; };
  }

  var charts = {};
  function mk(id) { var c = echarts.init(el(id)); charts[id] = c; return c; }
  var chRev = mk('ch-rev'), chRank = mk('ch-rank'), chGrowth = mk('ch-growth'),
      chQuadrant = mk('ch-quadrant'), chSector = mk('ch-sector'), chProfit = mk('ch-profit');
  var ALL = [chRev, chRank, chGrowth, chQuadrant, chSector, chProfit];

  /* ---------- 图 01：营收走势 ---------- */
  function optRev() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 12, textStyle: { fontSize: 11, color: C.muted } },
      grid: { left: 58, right: 44, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('营业收入', fmtYi(S.rev[i]) + ' 亿元', C.teal) +
            tipRow('累计增长', sgn(S.revGrowth[i]) + '%', C.purple);
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
        { name: '营业收入', type: 'bar', data: S.rev, barWidth: '46%',
          itemStyle: { borderRadius: [6, 6, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(94,234,212,0.85)' }, { offset: 1, color: 'rgba(96,165,250,0.18)' }]) } },
        { name: '累计增长', type: 'line', yAxisIndex: 1, data: S.revGrowth, symbol: 'circle', symbolSize: 6.5, z: 6,
          lineStyle: { width: 2.5, color: C.pink, shadowColor: C.pink, shadowBlur: 8 }, itemStyle: { color: C.pink } }
      ]
    };
  }

  /* ---------- 图 02：九大类排行 ---------- */
  function optRank() {
    var items = IND_NAMES.map(function (name) {
      return { name: name, v: IND[name].v[state.qi], g: IND[name].g[state.qi] };
    }).sort(function (a, b) { return b.v - a.v; });
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 92, right: 74, top: 8, bottom: 20 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var it = items[p.dataIndex];
          return tipTitle(it.name) +
            tipRow('营业收入', fmtYi(it.v) + ' 亿元', C.teal) +
            tipRow('累计增长', sgn(it.g) + '%', it.g >= 0 ? C.teal : C.pink);
        }
      }),
      xAxis: { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x.name; }),
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.muted, fontSize: 11 } },
      series: [{
        name: '营业收入', type: 'bar', barWidth: '56%',
        data: items.map(function (x, i) {
          return { value: x.v,
            itemStyle: { borderRadius: [0, 6, 6, 0],
              color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: 'rgba(96,165,250,0.25)' }, { offset: 1, color: i === 0 ? 'rgba(94,234,212,0.9)' : 'rgba(167,139,250,0.75)' }]) } };
        }),
        label: { show: true, position: 'right', fontSize: 10.5, color: C.text, fontWeight: 600,
          formatter: function (p) {
            var it = items[p.dataIndex];
            return fmtYi(it.v) + '（' + sgn(it.g) + '%）';
          } }
      }]
    };
  }

  /* ---------- 图 03：增速对比 ---------- */
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
          return tipTitle(it.name) + tipRow('累计增长', sgn(it.g) + '%', it.g >= 0 ? C.teal : C.pink);
        }
      }),
      xAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x.name; }),
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.muted, fontSize: 11 } },
      series: [{
        name: '累计增长', type: 'bar', barWidth: '56%',
        data: items.map(function (x) {
          return { value: x.g,
            itemStyle: { borderRadius: x.g >= 0 ? [0, 6, 6, 0] : [6, 0, 0, 6],
              color: x.g >= 0 ? 'rgba(94,234,212,0.75)' : 'rgba(244,114,182,0.75)',
              borderColor: x.g >= 0 ? C.teal : C.pink, borderWidth: 1 },
            label: { position: x.g >= 0 ? 'right' : 'left' } };
        }),
        label: { show: true, fontSize: 10.5, color: C.text, fontWeight: 600,
          formatter: function (p) { return sgn(p.value) + '%'; } },
        markLine: { silent: true, symbol: 'none', animation: false, label: { show: false },
          lineStyle: { type: 'dashed', color: 'rgba(200,210,255,0.4)' }, data: [{ xAxis: 0 }] }
      }]
    };
  }

  /* ---------- 图 04：增长 × 占比象限 ---------- */
  function optQuadrant() {
    var total = S.rev[state.qi];
    var points = IND_NAMES.map(function (name, i) {
      var v = IND[name].v[state.qi], g = IND[name].g[state.qi];
      return { name: name, share: r1(v / total * 100), g: g, v: v };
    });
    function r1(v) { return Math.round(v * 10) / 10; }
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 48, right: 26, top: 18, bottom: 40 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var it = points[p.dataIndex];
          return tipTitle(it.name) +
            tipRow('营业收入', fmtYi(it.v) + ' 亿元', C.teal) +
            tipRow('营收占比', it.share.toFixed(1) + '%') +
            tipRow('累计增长', sgn(it.g) + '%', it.g >= 0 ? C.teal : C.pink);
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
            itemStyle: { color: PALETTE[i % PALETTE.length], opacity: 0.82,
              borderColor: '#0b1020', borderWidth: 1.5,
              shadowColor: PALETTE[i % PALETTE.length], shadowBlur: 10 },
            label: { show: true, position: 'right', distance: 6, fontSize: 10.5, color: C.muted, formatter: it.name } };
        })
      }]
    };
  }

  /* ---------- 图 05：三大行业构成 ---------- */
  function optSector() {
    function pct(v) { return r1(v / S.rev[state.qi] * 100); }
    function r1(v) { return Math.round(v * 10) / 10; }
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.blue, C.purple, C.teal],
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 10, textStyle: { fontSize: 11, color: C.muted } },
      grid: { left: 66, right: 30, top: 12, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('文化制造业', fmtYi(S.mfg[i]) + ' 亿元 (' + S.mfgShare[i].toFixed(1) + '%)', C.blue) +
            tipRow('批发和零售业', fmtYi(S.wholesale[i]) + ' 亿元 (' + S.wholesaleShare[i].toFixed(1) + '%)', C.purple) +
            tipRow('文化服务业', fmtYi(S.service[i]) + ' 亿元 (' + S.serviceShare[i].toFixed(1) + '%)', C.teal);
        }
      }),
      xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', data: Q, inverse: true,
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.muted, fontSize: 10.5 } },
      series: [
        { name: '文化制造业', type: 'bar', stack: 's', data: S.mfgShare, barWidth: '58%', itemStyle: { borderRadius: [6, 0, 0, 6] },
          label: { show: true, position: 'inside', fontSize: 10.5, color: '#0b1020', fontWeight: 600, formatter: function (p) { return p.value >= 8 ? p.value + '%' : ''; } } },
        { name: '批发和零售业', type: 'bar', stack: 's', data: S.wholesaleShare, itemStyle: {},
          label: { show: true, position: 'inside', fontSize: 10.5, color: '#0b1020', fontWeight: 600, formatter: function (p) { return p.value >= 8 ? p.value + '%' : ''; } } },
        { name: '文化服务业', type: 'bar', stack: 's', data: S.serviceShare, itemStyle: {},
          label: { show: true, position: 'inside', fontSize: 10.5, color: '#0b1020', fontWeight: 600, formatter: function (p) { return p.value >= 8 ? p.value + '%' : ''; } } }
      ]
    };
  }

  /* ---------- 图 06：利润与资产 ---------- */
  function optProfit() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 12, textStyle: { fontSize: 11, color: C.muted } },
      grid: { left: 56, right: 56, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('利润总额', fmtYi(S.profit[i]) + ' 亿元', C.pink) +
            tipRow('利润累计增长', sgn(S.profitGrowth[i]) + '%', C.gold) +
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
        { name: '利润总额', type: 'bar', data: S.profit, barWidth: '46%',
          itemStyle: { borderRadius: [6, 6, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(244,114,182,0.85)' }, { offset: 1, color: 'rgba(244,114,182,0.15)' }]) } },
        { name: '资产总计', type: 'line', yAxisIndex: 1, data: S.assets, symbol: 'circle', symbolSize: 6.5, z: 6,
          lineStyle: { width: 2.5, color: C.blue, shadowColor: C.blue, shadowBlur: 8 }, itemStyle: { color: C.blue } }
      ]
    };
  }

  /* ---------- 详情钉住 ---------- */
  function pinDetail(html) { el('wh-detail').innerHTML = html; }
  var DEFAULT_HINT = '<b>使用提示</b>&nbsp;&nbsp;拖动时间轴或点击图 01/06 中的柱线即可联动全部图表；点击数据点可将详情钉住显示在此栏。';
  function resetDetail() { el('wh-detail').innerHTML = DEFAULT_HINT; }

  chRev.on('click', function (p) {
    if (typeof p.dataIndex !== 'number') return;
    setQuarter(p.dataIndex, true);
  });
  chProfit.on('click', function (p) {
    if (typeof p.dataIndex !== 'number') return;
    setQuarter(p.dataIndex, true);
  });
  chRev.on('click', function (p) {
    if (typeof p.dataIndex !== 'number' || !p.seriesName) return;
    if (p.seriesName === '累计增长') {
      pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · 营业收入累计增长') + '<b>' + sgn(S.revGrowth[p.dataIndex]) + '%</b>');
    }
  });
  chProfit.on('click', function (p) {
    if (typeof p.dataIndex !== 'number' || !p.seriesName) return;
    if (p.seriesName === '资产总计') {
      pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · 资产总计（季末）') +
        '<b>' + wanYi(S.assets[p.dataIndex]) + ' 万亿元</b>&nbsp;&nbsp;同比 <b>' + sgn(S.assetsYoy[p.dataIndex]) + '%</b>');
    } else if (p.seriesName === '利润总额') {
      pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · 利润总额（累计）') +
        '<b>' + fmtYi(S.profit[p.dataIndex]) + ' 亿元</b>&nbsp;&nbsp;累计增长 <b>' + sgn(S.profitGrowth[p.dataIndex]) + '%</b>');
    }
  });
  chRank.on('click', function (p) {
    var name = IND_NAMES.filter(function (n) { return true; })[p.dataIndex];
    var items = IND_NAMES.map(function (n) { return { n: n, v: IND[n].v[state.qi] }; })
      .sort(function (a, b) { return b.v - a.v; });
    var it = items[p.dataIndex];
    if (!it) return;
    pinDetail(tipTitle('📌 ' + it.n) +
      '<b>' + fmtYi(it.v) + ' 亿元</b>&nbsp;&nbsp;累计增长 <b>' + sgn(IND[it.n].g[state.qi]) + '%</b>' +
      '&nbsp;&nbsp;占营收 <b>' + (it.v / S.rev[state.qi] * 100).toFixed(1) + '%</b>');
  });

  /* ---------- KPI 与速读 ---------- */
  function kpiCard(ac, title, val, unit, sub) {
    return '<div class="wh-kpi" style="--ac:' + ac + '">' +
      '<div class="wh-kpi-top"><span>' + title + '</span></div>' +
      '<div class="wh-kpi-val">' + val + '<small>' + unit + '</small></div>' +
      '<div class="wh-kpi-sub">' + sub + '</div></div>';
  }
  function renderKpis() {
    var i = state.qi;
    var best = null, worst = null;
    IND_NAMES.forEach(function (name) {
      var g = IND[name].g[i];
      if (!best || g > best.g) best = { n: name, g: g };
      if (!worst || g < worst.g) worst = { n: name, g: g };
    });
    el('wh-kpis').innerHTML =
      kpiCard(C.teal, '营业收入', wanYi(S.rev[i]), '万亿元',
        '累计增长 <span class="' + cls(S.revGrowth[i]) + '">' + sgn(S.revGrowth[i]) + '%</span>') +
      kpiCard(C.pink, '利润总额', fmtYi(S.profit[i]), '亿元',
        '累计增长 <span class="' + cls(S.profitGrowth[i]) + '">' + sgn(S.profitGrowth[i]) + '%</span>') +
      kpiCard(C.blue, '资产总计', wanYi(S.assets[i]), '万亿元',
        '季末值 · 同比 <span class="' + cls(S.assetsYoy[i]) + '">' + sgn(S.assetsYoy[i]) + '%</span>') +
      kpiCard(C.purple, '核心领域占比', S.coreShare[i].toFixed(1), '%',
        '相关领域 ' + S.relatedShare[i].toFixed(1) + '%') +
      kpiCard(C.gold, '文化服务业占比', S.serviceShare[i].toFixed(1), '%',
        '制造 ' + S.mfgShare[i].toFixed(1) + '% · 批零 ' + S.wholesaleShare[i].toFixed(1) + '%') +
      kpiCard(C.teal, '增长最快大类', sgn(best.g), '%',
        '<span class="wh-up">' + best.n + '</span>' +
        (worst.n !== best.n ? ' · 最慢 <span class="wh-down">' + worst.n + '</span>' : ''));
  }
  function renderBrief() {
    var i = state.qi;
    var sorted = IND_NAMES.map(function (name) { return { n: name, g: IND[name].g[i] }; })
      .sort(function (a, b) { return b.g - a.g; });
    el('wh-detail').innerHTML =
      '<b>' + Q[i] + ' 速读</b>&nbsp;&nbsp;文化产业营业收入累计 <b>' + wanYi(S.rev[i]) + ' 万亿元</b>' +
      '（同比 <b>' + sgn(S.revGrowth[i]) + '%</b>）；利润总额 <b>' + fmtYi(S.profit[i]) + ' 亿元</b>' +
      '（<b>' + sgn(S.profitGrowth[i]) + '%</b>）；核心领域营收占 <b>' + S.coreShare[i].toFixed(1) + '%</b>，' +
      '文化服务业占 <b>' + S.serviceShare[i].toFixed(1) + '%</b>；' +
      '增长最快 <b>' + sorted[0].n + '（' + sgn(sorted[0].g) + '%）</b>，最慢 ' +
      sorted[sorted.length - 1].n + '（' + sgn(sorted[sorted.length - 1].g) + '%）。';
  }

  /* ---------- 渲染 ---------- */
  function renderSlider() {
    var r = el('wh-range');
    r.value = state.qi;
    var p = state.qi / (N - 1) * 100;
    r.style.background = 'linear-gradient(to right,#5eead4 0%,#a78bfa ' + p + '%,rgba(148,163,255,0.18) ' + p + '%)';
  }
  function apply() {
    var qi = state.qi;
    el('wh-chip').textContent = Q[qi] + ' · 累计口径';
    renderSlider();
    renderKpis();
    renderBrief();
    chRev.setOption(optRev(), true);
    chRank.setOption(optRank(), true);
    el('sub-rank').textContent = Q[qi] + ' · 亿元 · 括号内为累计增长';
    chGrowth.setOption(optGrowth(), true);
    el('sub-growth').textContent = Q[qi] + ' · 累计增长（%）· 按增速降序';
    chQuadrant.setOption(optQuadrant(), true);
    el('sub-quadrant').textContent = Q[qi] + ' · 横轴营收占比（%）· 纵轴累计增长（%）';
    chSector.setOption(optSector(), true);
    chProfit.setOption(optProfit(), true);
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
  el('wh-range').addEventListener('input', function () { setQuarter(+this.value, true); });

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
# 四、校验与组装
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

    # 总体收入应约等于九大类之和（允许四舍五入误差）
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
            '<title>文化产业 · 季度数据大屏</title>\n</head>\n<body>\n'
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

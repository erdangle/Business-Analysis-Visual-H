# -*- coding: utf-8 -*-
'''建筑业 · 季度数据 BI 大屏生成器（工程蓝图风 Blueprint）
================================================================

自包含的可视化项目：仅用 Python 标准库即可在本机（VS Code / PyCharm / 命令行）运行，
无需 pip 安装任何第三方包。风格：工程蓝图 —— 深蓝图纸底、白色制图网格、
线框卡片与等宽数字（与建筑业主题呼应；风格选型依据见 ../风格库/README.md）。

功能
----
1. 读取 data/ 目录下的建筑业季度数据表（10 张 CSV，按【内容指纹】自动识别表格类型，
   文件名与内容错位也能正确解析）：
   · 时序表（2022Q2—2026Q3，18 个季度，累计值口径）：建筑业总产值、企业个数与用工、
     房屋建筑施工面积、房屋建筑竣工面积、签订合同情况、竣工房屋价值分类
   · 财务快照表（2017Q1 单期，统计局制度注明财务指标无四季度数据）：企业利润、
     企业总收入、资产负债情况（"费用情况"表与利润表内容重复，自动去重）
2. 解析、校验并派生指标（累计同比、结构占比、竣工率、新签占比、资产负债率等）；
3. 生成「工程蓝图风」交互式 BI 大屏 HTML 并自动在浏览器中打开。

使用方法
--------
在本文件夹内打开终端，执行：
    python generate_bi_dashboard.py            # 生成大屏并自动打开浏览器
    python generate_bi_dashboard.py --no-open  # 只生成文件，不打开浏览器

首次运行会自动下载 ECharts 图表库并缓存为本文件夹下的 echarts.min.js（此后完全离线可用）。

输出：建筑业BI大屏.html（双击也可随时打开）。
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
OUTPUT_HTML = BASE / '建筑业BI大屏.html'

QMAP = {'一': 1, '二': 2, '三': 3, '四': 4}

# =====================================================================
# 一、数据解析：按内容指纹识别表格类型（文件名无关，自动纠位）
# =====================================================================

# 各表格类型的指纹指标（出现即认为属于该类型）
FINGERPRINTS = {
    'gv':       '建筑业总产值累计值',
    'firms':    '建筑业企业单位数累计值',
    'area':     '房屋建筑施工面积累计值',
    'areaDone': '房屋建筑竣工面积累计值',
    'contract': '建筑业企业签订合同金额累计值',
    'valueDone':'建筑业竣工房屋价值累计值',
    'finRev':   '企业总收入累计值',
    'finProfit':'建筑业企业营业利润累计值',
    'finBalance':'建筑业企业流动资产累计值',
}

# 需要抽取的指标行（前缀匹配）
SERIES_SPEC = {
    'gv': [
        ('gv', '建筑业总产值累计值'),
        ('gvBuild', '建筑工程产值累计值'),
        ('gvInstall', '安装工程产值累计值'),
        ('gvDecor', '装饰装修产值累计值'),
        ('gvOther', '其他产值累计值'),
        ('gvDone', '建筑业竣工产值累计值'),
        ('gvOutProv', '在外省完成的产值累计值'),
    ],
    'firms': [
        ('firms', '建筑业企业单位数累计值'),
        ('workers', '直接从事生产经营活动的平均人数累计值'),
    ],
    'area': [
        ('areaUnder', '房屋建筑施工面积累计值'),
        ('areaNew', '新开工面积累计值'),
    ],
    'areaDone': [
        ('areaDone', '房屋建筑竣工面积累计值'),
        ('b_residential', '住宅房屋竣工面积累计值'),
        ('b_commercial', '商业及服务用房屋竣工面积累计值'),
        ('b_office', '办公用房屋竣工面积累计值'),
        ('b_edu', '科研、教育和医疗用房屋竣工面积累计值'),
        ('b_culture', '文化、体育和娱乐用房屋竣工面积累计值'),
        ('b_factory', '厂房及建筑物竣工面积累计值'),
        ('b_warehouse', '仓库竣工面积累计值'),
        ('b_misc', '其他未列明的房屋建筑物竣工面积累计值'),
    ],
    'contract': [
        ('contract', '建筑业企业签订合同金额累计值'),
        ('contractNew', '建筑业企业本年新签合同额累计值'),
        ('contractCarry', '建筑业企业上年结转合同额累计值'),
    ],
    'valueDone': [
        ('v_residential', '住宅房屋竣工价值累计值'),
        ('v_commercial', '商业及服务用房屋竣工价值累计值'),
        ('v_office', '办公用房屋竣工价值累计值'),
        ('v_edu', '科研、教育和医疗用房屋竣工价值累计值'),
        ('v_culture', '文化、体育和娱乐用房屋竣工价值累计值'),
        ('v_warehouse', '仓库竣工价值累计值'),
        ('v_misc', '其他未列明的房屋建筑物竣工价值累计值'),
    ],
    'finRev': [
        ('revTotal', '企业总收入累计值'),
        ('revMain', '建筑业企业主营业务收入累计值'),
        ('revOther', '建筑业企业其他业务收入累计值'),
        ('costMain', '建筑业企业主营业务成本累计值'),
    ],
    'finProfit': [
        ('operProfit', '建筑业企业营业利润累计值'),
        ('profitTotal', '建筑业企业利润总额累计值'),
        ('marginRate', '建筑业企业产值利润率累计值'),
    ],
    'finBalance': [
        ('liquid', '建筑业企业流动资产累计值'),
        ('receivable', '建筑业企业应收工程款累计值'),
        ('inventory', '建筑业企业存货累计值'),
        ('assets', '建筑业企业资产累计值'),
        ('liab', '建筑业企业负债累计值'),
    ],
}


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
    """扫描 data/ 全部 CSV，按内容指纹归类。返回 (quarters, S, fin)。"""
    if not DATA_DIR.exists():
        raise SystemExit('未找到数据目录：%s' % DATA_DIR)
    buckets = {}      # kind -> (quarters, {alias: values})
    skipped = []
    for fp in sorted(DATA_DIR.glob('*.csv')):
        quarters, rows = parse_file(fp)
        if not rows:
            skipped.append(fp.name)
            continue
        hit = None
        for kind, mark in FINGERPRINTS.items():
            if any(k.startswith(mark) for k in rows):
                hit = kind
                break
        if hit is None:
            skipped.append(fp.name)
            continue
        if hit in buckets:
            print('  [去重] %s 与先前文件内容重复（%s），跳过' % (fp.name, hit))
            continue
        buckets[hit] = (quarters, rows)

    missing = set(FINGERPRINTS) - set(buckets)
    if missing:
        raise SystemExit('以下类型的表未在 data/ 中找到：%s' % sorted(missing))

    # 时序轴：取时序表中最长的一份（18 季），并反转为时间正序（2022Q2 → 2026Q3）
    ts_kinds = ['gv', 'firms', 'area', 'areaDone', 'contract', 'valueDone']
    quarters = list(reversed(max((buckets[k][0] for k in ts_kinds), key=len)))
    n = len(quarters)

    def series(kind, alias, prefix, min_points=3):
        qs, rows = buckets[kind]
        key = next((k for k in rows if k.startswith(prefix)), None)
        if key is None:
            raise SystemExit('表 %s 缺少指标：%s' % (kind, prefix))
        vals = rows[key]
        if len(qs) == n:
            vals = list(reversed(vals))
            if sum(1 for v in vals if v is not None) < min_points:
                return None  # 数据点过少（如"厂房竣工价值"仅 1 期），丢弃
            return vals
        # 单点表：对齐到时序轴末端不合适，直接返回原始（供财务快照使用）
        return vals

    S = {}
    for kind, spec in SERIES_SPEC.items():
        if kind in ('finRev', 'finProfit', 'finBalance', 'valueDone'):
            continue
        for alias, prefix in spec:
            v = series(kind, alias, prefix)
            if v is not None:
                S[alias] = v
    for alias, vals in S.items():
        if len(vals) != n or any(v is None for v in vals):
            raise SystemExit('指标 %s 长度/缺失异常：%d 项' % (alias, len(vals)))

    # 竣工房屋价值表：缺 2026Q1（共 17 期），且无"厂房"分类行
    # → 按季度键映射存储（缺失季度视为无数据，排行图自动隐藏）
    qs_v, rows_v = buckets['valueDone']
    for alias, prefix in SERIES_SPEC['valueDone']:
        key = next((k for k in rows_v if k.startswith(prefix)), None)
        if key is None:
            raise SystemExit('表 valueDone 缺少指标：%s' % prefix)
        vals = list(rows_v[key])
        while vals and vals[-1] is None:
            vals.pop()
        S[alias] = dict(zip(qs_v, vals))

    # 财务快照（2017Q1 单期）
    def fin_one(kind, alias, prefix):
        qs, rows = buckets[kind]
        key = next((k for k in rows if k.startswith(prefix)), None)
        if key is None or not rows[key]:
            raise SystemExit('财务表缺少指标：%s' % prefix)
        v = rows[key][0]
        if v is None:
            raise SystemExit('财务指标 %s 首期为空' % prefix)
        return v

    fin = {'period': buckets['finProfit'][0][0] if buckets['finProfit'][0] else ''}
    for kind, spec in [('finProfit', SERIES_SPEC['finProfit']),
                       ('finRev', SERIES_SPEC['finRev']),
                       ('finBalance', SERIES_SPEC['finBalance'])]:
        for alias, prefix in spec:
            fin[alias] = fin_one(kind, alias, prefix)

    if skipped:
        print('  [跳过] 无有效指标行的文件：%s' % ', '.join(skipped))
    return quarters, S, fin


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
# 三、页面资源：蓝图风格样式 / 模板 / 交互脚本
# =====================================================================

# pylint: disable=line-too-long
CSS = r"""
#jz-dashboard-root {
  --line: rgba(226,240,255,0.55);
  --line-soft: rgba(226,240,255,0.22);
  --cyan: #8fd9ff; --gold: #ffd166; --green: #7be495; --orange: #ff9a76; --purple: #b8a6ff;
  --text: #eaf4ff; --muted: rgba(234,244,255,0.62); --faint: rgba(234,244,255,0.38);
  position: relative;
  color: var(--text);
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, -apple-system, sans-serif;
  font-size: 14px; line-height: 1.5;
  padding: 18px 22px 12px; border-radius: 4px; min-width: 0;
  border: 1px solid var(--line);
  background:
    repeating-linear-gradient(0deg, rgba(255,255,255,0.030) 0 1px, transparent 1px 28px),
    repeating-linear-gradient(90deg, rgba(255,255,255,0.030) 0 1px, transparent 1px 28px),
    repeating-linear-gradient(0deg, rgba(255,255,255,0.055) 0 1px, transparent 1px 140px),
    repeating-linear-gradient(90deg, rgba(255,255,255,0.055) 0 1px, transparent 1px 140px),
    radial-gradient(1100px 460px at 72% -12%, rgba(64,150,255,0.18), transparent 62%),
    linear-gradient(180deg, #0a1e3d 0%, #0b2144 55%, #081a35 100%);
}
#jz-dashboard-root * { box-sizing: border-box; }
#jz-dashboard-root .bp-frame {
  position: absolute; inset: 8px; border: 1px dashed rgba(226,240,255,0.16);
  pointer-events: none; border-radius: 2px;
}
.bp-mono { font-family: "Cascadia Mono", Consolas, "Courier New", monospace; }

/* ---------- 头部：标题区 + 工程图签 ---------- */
.bp-header { display: flex; justify-content: space-between; align-items: stretch; gap: 16px; margin-bottom: 12px; }
.bp-brand { display: flex; align-items: center; gap: 13px; min-width: 0; }
.bp-mark { width: 46px; height: 46px; flex: 0 0 auto; border: 1.5px solid var(--line);
  display: flex; align-items: center; justify-content: center; color: var(--cyan);
  background: rgba(143,217,255,0.06); }
.bp-brand h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 2px; white-space: nowrap; }
.bp-brand p { margin: 2px 0 0; font-size: 12px; color: var(--muted); }
.bp-brand .bp-sub-en { font-size: 10.5px; letter-spacing: 2.5px; color: var(--faint); }

/* ---------- 时间轴 ---------- */
.bp-timeline { border: 1px solid var(--line-soft); background: rgba(10,30,61,0.35);
  border-radius: 3px; padding: 12px 18px 26px; display: flex; align-items: center; gap: 12px;
  position: relative; margin-bottom: 12px; }
.bp-tl-label { font-size: 12px; font-weight: 600; color: var(--muted); flex: 0 0 auto; letter-spacing: 2px; }
.bp-arrow { width: 26px; height: 26px; border-radius: 0; border: 1px solid var(--line-soft);
  background: transparent; color: var(--muted); cursor: pointer; flex: 0 0 auto; font-size: 13px;
  line-height: 1; display: flex; align-items: center; justify-content: center; padding: 0; font-family: inherit; }
.bp-arrow:hover { border-color: var(--cyan); color: var(--cyan); }
#jz-range { flex: 1; -webkit-appearance: none; appearance: none; height: 4px; border-radius: 0;
  background: rgba(226,240,255,0.18); outline: none; cursor: pointer; min-width: 120px; }
#jz-range::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 14px; height: 14px;
  border-radius: 0; background: var(--cyan); border: 1px solid #fff; cursor: grab;
  box-shadow: 0 0 10px rgba(143,217,255,0.7); }
#jz-range::-moz-range-thumb { width: 12px; height: 12px; border-radius: 0; background: var(--cyan);
  border: 1px solid #fff; cursor: grab; }
.bp-years { position: absolute; left: 96px; right: 360px; bottom: 4px; height: 15px; pointer-events: none; }
.bp-years span { position: absolute; transform: translateX(-50%); font-size: 10.5px; color: var(--faint); }
.bp-years span:first-child { transform: none; }
.bp-btn { border: 1px solid var(--line-soft); background: transparent; color: var(--muted);
  padding: 5px 14px; font-size: 12.5px; cursor: pointer; font-family: inherit; letter-spacing: 2px; }
.bp-btn:hover { border-color: var(--cyan); color: var(--cyan); }
.bp-btn.primary { border-color: var(--cyan); color: #06121f; background: var(--cyan); font-weight: 700; }
.bp-hint { font-size: 11.5px; color: var(--faint); flex: 0 0 auto; max-width: 300px; text-align: right; line-height: 1.45; }

/* ---------- 详情钉住栏 ---------- */
.bp-detail { border: 1px solid var(--line-soft); border-left: 3px solid var(--cyan);
  background: rgba(143,217,255,0.05); padding: 9px 16px; font-size: 13px; line-height: 1.7;
  margin-bottom: 12px; color: #cfe4ff; min-height: 42px; }
.bp-detail b { color: var(--cyan); font-weight: 700; }

/* ---------- KPI ---------- */
.bp-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 12px; }
.bp-kpi { border: 1px solid var(--line-soft); background: rgba(255,255,255,0.025);
  padding: 11px 13px 10px 15px; position: relative; min-width: 0; }
.bp-kpi::before, .bp-kpi::after { content: '+'; position: absolute; font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11px; color: rgba(143,217,255,0.65); line-height: 1; }
.bp-kpi::before { top: -1px; left: -1px; }
.bp-kpi::after { bottom: -1px; right: -1px; }
.bp-kpi-top { display: flex; justify-content: space-between; gap: 6px; font-size: 12px; color: var(--muted); }
.bp-kpi-top .no { color: var(--faint); font-family: "Cascadia Mono", Consolas, monospace; }
.bp-kpi-val { font-size: 24px; font-weight: 700; margin: 4px 0 2px; white-space: nowrap;
  font-family: "Cascadia Mono", Consolas, "Microsoft YaHei", monospace; color: #ffffff;
  letter-spacing: 0.5px; text-shadow: 0 0 14px rgba(143,217,255,0.35); }
.bp-kpi-val small { font-size: 12px; color: var(--muted); margin-left: 3px; font-family: "Microsoft YaHei", sans-serif; }
.bp-kpi-sub { font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bp-up { color: var(--green); font-weight: 700; }
.bp-down { color: var(--orange); font-weight: 700; }

/* ---------- 图表网格 ---------- */
.bp-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }
.bp-card { border: 1px solid var(--line-soft); background: rgba(10,30,61,0.32);
  padding: 12px 15px 6px; min-width: 0; position: relative; }
.bp-card::before, .bp-card::after { content: '+'; position: absolute; font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11px; color: rgba(143,217,255,0.5); line-height: 1; }
.bp-card::before { top: -1px; left: -1px; }
.bp-card::after { bottom: -1px; right: -1px; }
.bp-s6 { grid-column: span 6; }
.bp-card-h { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.bp-card-h h3 { font-size: 14.5px; font-weight: 700; margin: 0; letter-spacing: 1px; color: #f2f8ff; }
.bp-card-h .no { font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px; color: var(--cyan);
  border: 1px solid var(--line-soft); padding: 0 6px; margin-right: 8px; }
.bp-hint-r { font-size: 11px; color: var(--faint); font-family: "Cascadia Mono", Consolas, monospace; letter-spacing: 0.5px; }
.bp-sub { font-size: 11.5px; color: var(--faint); margin: 2px 0 2px; }
.bp-chart { width: 100%; height: 300px; }
.bp-fin-note { font-size: 11.5px; color: var(--muted); line-height: 1.8; padding: 2px 4px 8px; border-top: 1px dashed var(--line-soft); margin-top: 4px; }
.bp-fin-note b { color: var(--gold); }
.bp-foot { font-size: 11px; color: var(--faint); margin-top: 10px; line-height: 1.7; }

@media (prefers-reduced-motion: reduce) {
  #jz-dashboard-root *, #jz-dashboard-root *::before, #jz-dashboard-root *::after {
    animation: none !important; transition: none !important;
  }
}
@media (max-width: 1280px) {
  .bp-s6 { grid-column: span 12; }
  .bp-kpis { grid-template-columns: repeat(3, 1fr); }
  .bp-years { display: none; }
  .bp-header { flex-direction: column; }
}
@media (max-width: 720px) {
  .bp-kpis { grid-template-columns: 1fr; }
  #jz-dashboard-root { padding: 12px; }
}
"""

TEMPLATE = """
<style>
/*__STYLE__*/
</style>

<div id="jz-dashboard-root">
  <div class="bp-frame" aria-hidden="true"></div>

  <div class="bp-header">
    <div class="bp-brand">
      <div class="bp-mark" aria-hidden="true">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <path d="M3 21L12 3l9 18z" /><circle cx="12" cy="15" r="3.2" /><path d="M12 21v-3.8" />
        </svg>
      </div>
      <div>
        <h1>建筑业季度数据监测屏</h1>
        <div class="bp-sub-en">CONSTRUCTION INDUSTRY QUARTERLY MONITOR</div>
        <p>总产值 · 合同 · 面积 · 用工 · 房屋建筑分类 &nbsp;|&nbsp; 数据来源：国家统计局「季度数据」</p>
      </div>
    </div>
  </div>

  <div class="bp-timeline">
    <span class="bp-tl-label">季度</span>
    <button type="button" class="bp-arrow" id="btn-prev" aria-label="上一季度">‹</button>
    <input type="range" id="jz-range" min="0" max="17" step="1" value="17" aria-label="选择季度" />
    <button type="button" class="bp-arrow" id="btn-next" aria-label="下一季度">›</button>
    <button type="button" class="bp-btn primary" id="btn-play">播放</button>
    <button type="button" class="bp-btn" id="btn-reset">重置</button>
    <span class="bp-hint">拖动时间轴或点击任意图表柱线即可联动全部图表 · 点击数据点钉住详情</span>
    <div class="bp-years" aria-hidden="true">
      <span style="left:0%">2022</span><span style="left:17.6%">2023</span><span style="left:41.2%">2024</span><span style="left:64.7%">2025</span><span style="left:88.2%">2026</span>
    </div>
  </div>

  <div class="bp-detail" id="jz-detail" aria-live="polite"></div>

  <div class="bp-kpis" id="jz-kpis"></div>

  <div class="bp-grid">
    <div class="bp-card bp-s6">
      <div class="bp-card-h"><h3><span class="no">01</span>建筑业总产值构成（累计）</h3><span class="bp-hint-r">CUM. GROSS OUTPUT</span></div>
      <div class="bp-sub">堆叠：建筑工程 / 安装工程 / 装饰装修 / 其他（亿元）· 线：总产值累计同比（%）</div>
      <div class="bp-chart" id="ch-gv"></div>
    </div>
    <div class="bp-card bp-s6">
      <div class="bp-card-h"><h3><span class="no">02</span>签订合同结构（累计）</h3><span class="bp-hint-r">CONTRACTS</span></div>
      <div class="bp-sub">堆叠：本年新签 / 上年结转（亿元）· 线：合同总额累计同比（%）</div>
      <div class="bp-chart" id="ch-contract"></div>
    </div>
    <div class="bp-card bp-s6">
      <div class="bp-card-h"><h3><span class="no">03</span>房屋建筑面积（累计）</h3><span class="bp-hint-r">FLOOR AREA, 10k ㎡</span></div>
      <div class="bp-sub">施工面积 / 新开工面积 / 竣工面积（万平方米）</div>
      <div class="bp-chart" id="ch-area"></div>
    </div>
    <div class="bp-card bp-s6">
      <div class="bp-card-h"><h3><span class="no">04</span>房屋竣工面积分类排行</h3><span class="bp-hint-r">BY BUILDING TYPE</span></div>
      <div class="bp-sub" id="sub-rank-area">当前季度 · 万平方米 · 按面积降序</div>
      <div class="bp-chart" id="ch-rank-area"></div>
    </div>
    <div class="bp-card bp-s6">
      <div class="bp-card-h"><h3><span class="no">05</span>竣工房屋价值分类排行</h3><span class="bp-hint-r">COMPLETION VALUE</span></div>
      <div class="bp-sub" id="sub-rank-value">当前季度 · 亿元 · 按价值降序</div>
      <div class="bp-chart" id="ch-rank-value"></div>
    </div>
    <div class="bp-card bp-s6">
      <div class="bp-card-h"><h3><span class="no">06</span>企业财务快照</h3><span class="bp-hint-r">FINANCIAL SNAPSHOT</span></div>
      <div class="bp-sub" id="sub-fin">最近一期财务数据时点 · 亿元</div>
      <div class="bp-chart" id="ch-fin" style="height:212px"></div>
      <div class="bp-fin-note" id="fin-note"></div>
    </div>
  </div>

  <div class="bp-foot">
    数据来源：国家统计局「数据库 — 季度数据」。产值、合同、面积、用工均为累计值口径；
    同比为累计口径（与上年同期累计值相比）。企业财务指标（利润 / 收入 / 资产负债）统计制度无四季度数据，
    最近一期为快照表所示时点，仅作结构参考。房屋建筑分类按 2021 年统计年报制度修订，
    「厂房竣工价值」因数据点不足未纳入。文件名与内容如有错位，生成器按内容指纹自动识别。
  </div>
</div>

__ECHARTS__

<script>
window.JZ_DATA = /*__DATA__*/;
</script>

<script>
/*__APP__*/
</script>
"""

APP = r"""
(function () {
  'use strict';
  var root = document.getElementById('jz-dashboard-root');
  if (!root) return;
  if (typeof echarts === 'undefined') {
    root.innerHTML = '<div style="padding:60px 20px;text-align:center;color:#8fa3c8;font-size:14px;">ECharts 加载失败：请联网后刷新（首次运行脚本会自动下载并内联图表库）。</div>';
    return;
  }
  var RAW = window.JZ_DATA;
  var Q = RAW.quarters, N = Q.length, S = RAW.series, F = RAW.fin;
  var state = { qi: N - 1, playing: false, timer: null };

  var C = {
    cyan: '#8fd9ff', gold: '#ffd166', green: '#7be495', orange: '#ff9a76', purple: '#b8a6ff', white: '#eaf4ff',
    axis: 'rgba(226,240,255,0.62)', axisLine: 'rgba(226,240,255,0.35)', split: 'rgba(226,240,255,0.08)',
    text: '#eaf4ff', muted: 'rgba(234,244,255,0.62)', faint: 'rgba(234,244,255,0.38)',
    tipBg: 'rgba(6,20,40,0.95)', tipBorder: 'rgba(143,217,255,0.5)'
  };
  var TIP = {
    backgroundColor: C.tipBg, borderColor: C.tipBorder, borderWidth: 1,
    padding: [10, 14], textStyle: { color: C.text, fontSize: 12.5 },
    extraCssText: 'box-shadow:0 12px 32px rgba(0,0,0,0.5);border-radius:2px;'
  };
  function tipTitle(q) { return '<div style="font-weight:700;font-size:13px;margin-bottom:4px;">' + q + '</div>'; }
  function tipRow(k, v, color) {
    return '<div style="display:flex;justify-content:space-between;gap:22px;line-height:1.9;">' +
      '<span style="opacity:.72;">' + k + '</span>' +
      '<span style="font-weight:600;' + (color ? 'color:' + color : '') + '">' + v + '</span></div>';
  }
  function el(id) { return document.getElementById(id); }
  function r1(v) { return Math.round(v * 10) / 10; }
  function sgn(v) { return (v > 0 ? '+' : '') + v.toFixed(1); }
  function fmtYi(v) { return Math.round(v).toLocaleString('en-US'); }
  function wanYi(v) { return (v / 10000).toFixed(2); }
  function cls(v) { return v >= 0 ? 'bp-up' : 'bp-down'; }
  function yoyOf(arr, i) {
    if (i < 4) return null;
    var base = arr[i - 4];
    return base ? r1((arr[i] / base - 1) * 100) : null;
  }
  function deltaHtml(label, d, unit) {
    return label + ' <span class="' + (d === null ? '' : cls(d)) + '">' +
      (d === null ? '—' : (d > 0 ? '+' : '') + d.toFixed(1) + (unit || '%')) + '</span>';
  }
  function yoyArr(arr) {
    return arr.map(function (v, i) { return yoyOf(arr, i); });
  }
  function fill(arr, color, border) {
    return { color: color, borderColor: border, borderWidth: 1 };
  }
  function catAxis(data, rotate) {
    return { type: 'category', data: data.map(function (q) { return q.slice(2); }),
      axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
      axisLabel: { color: C.axis, fontSize: 10.5, rotate: rotate || 0 } };
  }
  function valAxis() {
    return { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } };
  }

  var charts = {};
  function mk(id) { var c = echarts.init(el(id)); charts[id] = c; return c; }
  var chGv = mk('ch-gv'), chContract = mk('ch-contract'), chArea = mk('ch-area'),
      chRankArea = mk('ch-rank-area'), chRankValue = mk('ch-rank-value'), chFin = mk('ch-fin');
  var ALL = [chGv, chContract, chArea, chRankArea, chRankValue, chFin];

  /* ---------- 图 01：总产值构成 ---------- */
  function optGv() {
    var qi = state.qi;
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.cyan, C.gold, C.purple, C.green],
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 10, textStyle: { fontSize: 11, color: C.muted } },
      grid: { left: 60, right: 48, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('总产值', fmtYi(S.gv[i]) + ' 亿元', C.cyan) +
            tipRow('建筑工程', fmtYi(S.gvBuild[i]) + ' (' + (S.gvBuild[i] / S.gv[i] * 100).toFixed(1) + '%)') +
            tipRow('安装工程', fmtYi(S.gvInstall[i]) + ' (' + (S.gvInstall[i] / S.gv[i] * 100).toFixed(1) + '%)') +
            tipRow('装饰装修', fmtYi(S.gvDecor[i]) + ' (' + (S.gvDecor[i] / S.gv[i] * 100).toFixed(1) + '%)') +
            tipRow('其他', fmtYi(S.gvOther[i]) + ' (' + (S.gvOther[i] / S.gv[i] * 100).toFixed(1) + '%)');
        }
      }),
      xAxis: catAxis(Q),
      yAxis: [
        { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5, formatter: function (v) { return v >= 10000 ? (v / 10000) + '万亿' : v; } }, splitLine: { lineStyle: { color: C.split } } },
        { type: 'value', position: 'right', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { show: false } }
      ],
      series: [
        { name: '建筑工程', type: 'bar', stack: 'gv', data: S.gvBuild, barWidth: '52%', itemStyle: fill('rgba(143,217,255,0.30)', C.cyan) },
        { name: '安装工程', type: 'bar', stack: 'gv', data: S.gvInstall, itemStyle: fill('rgba(255,209,102,0.30)', C.gold) },
        { name: '装饰装修', type: 'bar', stack: 'gv', data: S.gvDecor, itemStyle: fill('rgba(184,166,255,0.30)', C.purple) },
        { name: '其他', type: 'bar', stack: 'gv', data: S.gvOther, itemStyle: fill('rgba(123,228,149,0.30)', C.green) },
        { name: '累计同比', type: 'line', yAxisIndex: 1, data: yoyArr(S.gv), symbol: 'circle', symbolSize: 5.5, z: 6,
          lineStyle: { width: 2, color: C.orange, shadowColor: C.orange, shadowBlur: 6 }, itemStyle: { color: C.orange } }
      ]
    };
  }

  /* ---------- 图 02：合同结构 ---------- */
  function optContract() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.cyan, C.purple],
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 12, textStyle: { fontSize: 11, color: C.muted } },
      grid: { left: 60, right: 48, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('签订合同总额', fmtYi(S.contract[i]) + ' 亿元', C.cyan) +
            tipRow('本年新签', fmtYi(S.contractNew[i]) + ' (' + (S.contractNew[i] / S.contract[i] * 100).toFixed(1) + '%)', C.gold) +
            tipRow('上年结转', fmtYi(S.contractCarry[i]) + ' (' + (S.contractCarry[i] / S.contract[i] * 100).toFixed(1) + '%)', C.purple);
        }
      }),
      xAxis: catAxis(Q),
      yAxis: [
        { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5, formatter: function (v) { return v >= 10000 ? (v / 10000) + '万亿' : v; } }, splitLine: { lineStyle: { color: C.split } } },
        { type: 'value', position: 'right', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { show: false } }
      ],
      series: [
        { name: '本年新签', type: 'bar', stack: 'c', data: S.contractNew, barWidth: '52%', itemStyle: fill('rgba(143,217,255,0.32)', C.cyan) },
        { name: '上年结转', type: 'bar', stack: 'c', data: S.contractCarry, itemStyle: fill('rgba(184,166,255,0.28)', C.purple) },
        { name: '总额同比', type: 'line', yAxisIndex: 1, data: yoyArr(S.contract), symbol: 'circle', symbolSize: 5.5, z: 6,
          lineStyle: { width: 2, color: C.orange, shadowColor: C.orange, shadowBlur: 6 }, itemStyle: { color: C.orange } }
      ]
    };
  }

  /* ---------- 图 03：面积三线 ---------- */
  function optArea() {
    function line(name, data, color) {
      return { name: name, type: 'line', data: data, symbol: 'circle', symbolSize: 5,
        lineStyle: { width: 2, color: color }, itemStyle: { color: color } };
    }
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.cyan, C.gold, C.green],
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 8, itemGap: 12, textStyle: { fontSize: 11, color: C.muted } },
      grid: { left: 62, right: 18, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'line' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('施工面积', fmtYi(S.areaUnder[i]) + ' 万㎡', C.cyan) +
            tipRow('新开工面积', fmtYi(S.areaNew[i]) + ' (' + (S.areaNew[i] / S.areaUnder[i] * 100).toFixed(1) + '%)', C.gold) +
            tipRow('竣工面积', fmtYi(S.areaDone[i]) + ' (' + (S.areaDone[i] / S.areaUnder[i] * 100).toFixed(1) + '%)', C.green);
        }
      }),
      xAxis: catAxis(Q),
      yAxis: { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      series: [
        line('施工面积', S.areaUnder, C.cyan),
        line('新开工面积', S.areaNew, C.gold),
        line('竣工面积', S.areaDone, C.green)
      ]
    };
  }

  /* ---------- 图 04/05：分类排行 ---------- */
  var AREA_CATS = [
    ['b_residential', '住宅'], ['b_commercial', '商业服务'], ['b_office', '办公'],
    ['b_edu', '科研教育医疗'], ['b_culture', '文体娱'], ['b_factory', '厂房及构筑物'],
    ['b_warehouse', '仓库'], ['b_misc', '其他']
  ];
  var VALUE_CATS = [
    ['v_residential', '住宅'], ['v_commercial', '商业服务'], ['v_office', '办公'],
    ['v_edu', '科研教育医疗'], ['v_culture', '文体娱'],
    ['v_warehouse', '仓库'], ['v_misc', '其他']
  ];
  function valOf(map, key) {
    var s = map[key];
    if (!s) return 0;
    return Array.isArray(s) ? (s[state.qi] || 0) : (s[Q[state.qi]] || 0);
  }
  function optRank(cats, map, unit, color) {
    var items = cats.map(function (c) {
      return { name: c[1], v: valOf(map, c[0]) };
    }).filter(function (x) { return x.v > 0; })
      .sort(function (a, b) { return b.v - a.v; });
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 96, right: 64, top: 8, bottom: 20 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) { return tipTitle(items[p.dataIndex].name) + tipRow(unit, fmtYi(p.value) + ' ' + unit, color); }
      }),
      xAxis: { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x.name; }),
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.muted, fontSize: 11 } },
      series: [{
        name: unit, type: 'bar', barWidth: '56%',
        data: items.map(function (x) { return x.v; }),
        itemStyle: { borderRadius: [0, 2, 2, 0], color: 'rgba(143,217,255,0.24)', borderColor: color, borderWidth: 1 },
        label: { show: true, position: 'right', fontSize: 10.5, color: C.text, fontWeight: 600,
          fontFamily: 'Cascadia Mono, Consolas, monospace',
          formatter: function (p) { return fmtYi(p.value); } }
      }]
    };
  }

  /* ---------- 图 06：财务快照 ---------- */
  function optFin() {
    var items = [
      ['资产总计', F.assets, C.cyan], ['负债合计', F.liab, C.orange],
      ['流动资产', F.liquid, C.gold], ['应收工程款', F.receivable, C.red || '#ff7b7b'],
      ['存货', F.inventory, C.green]
    ].sort(function (a, b) { return b[1] - a[1]; });
    return {
      animation: true, animationDuration: 0,
      grid: { left: 86, right: 66, top: 8, bottom: 18 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) { return tipTitle(items[p.dataIndex][0]) + tipRow('金额', fmtYi(p.value) + ' 亿元', C.cyan); }
      }),
      xAxis: { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5, formatter: function (v) { return v >= 10000 ? (v / 10000) + '万亿' : v; } }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x[0]; }),
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.muted, fontSize: 11 } },
      series: [{
        name: '亿元', type: 'bar', barWidth: '56%',
        data: items.map(function (x) {
          return { value: x[1], itemStyle: { borderRadius: [0, 2, 2, 0], color: 'rgba(143,217,255,0.20)', borderColor: x[2], borderWidth: 1 } };
        }),
        label: { show: true, position: 'right', fontSize: 10.5, color: C.text, fontWeight: 600,
          fontFamily: 'Cascadia Mono, Consolas, monospace', formatter: function (p) { return fmtYi(p.value); } }
      }]
    };
  }

  /* ---------- 详情钉住 ---------- */
  function pinDetail(html) { el('jz-detail').innerHTML = html; }
  var DEFAULT_HINT = '<b>使用提示</b>&nbsp;&nbsp;拖动时间轴或点击图 01—03 中的柱线即可联动全部图表；点击数据点可将详情钉住显示在此栏。';
  function resetDetail() { el('jz-detail').innerHTML = DEFAULT_HINT; }

  chGv.on('click', function (p) {
    var i = p.dataIndex;
    if (typeof i !== 'number') return;
    pinDetail(tipTitle('📌 ' + Q[i] + ' · 总产值构成') +
      '<b>' + p.seriesName + '</b>&nbsp;&nbsp;' + fmtYi(p.value) + ' 亿元' +
      '&nbsp;&nbsp;<span style="opacity:.7;">占总产值</span> <b>' + (p.value / S.gv[i] * 100).toFixed(1) + '%</b>');
  });
  chContract.on('click', function (p) {
    var i = p.dataIndex;
    if (typeof i !== 'number') return;
    var total = p.seriesName === '本年新签' ? S.contractNew[i] : S.contractCarry[i];
    pinDetail(tipTitle('📌 ' + Q[i] + ' · 签订合同') +
      '<b>' + p.seriesName + '</b>&nbsp;&nbsp;' + fmtYi(p.value) + ' 亿元' +
      '&nbsp;&nbsp;<span style="opacity:.7;">占合同总额</span> <b>' + (total / S.contract[i] * 100).toFixed(1) + '%</b>');
  });
  [chGv, chContract, chArea].forEach(function (c) {
    c.on('click', function (p) {
      if (typeof p.dataIndex === 'number') setQuarter(p.dataIndex, true);
    });
  });
  chArea.on('click', function (p) {
    if (typeof p.dataIndex !== 'number' || !p.seriesName) return;
    var i = p.dataIndex;
    var arr = p.seriesName === '施工面积' ? S.areaUnder : (p.seriesName === '新开工面积' ? S.areaNew : S.areaDone);
    pinDetail(tipTitle('📌 ' + Q[i] + ' · ' + p.seriesName) +
      '<b>' + fmtYi(arr[i]) + '</b> 万平方米');
  });

  /* ---------- KPI 与速读 ---------- */
  function kpiCard(no, title, val, unit, sub) {
    return '<div class="bp-kpi"><div class="bp-kpi-top"><span>' + title + '</span><span class="no">' + no + '</span></div>' +
      '<div class="bp-kpi-val">' + val + '<small>' + unit + '</small></div>' +
      '<div class="bp-kpi-sub">' + sub + '</div></div>';
  }
  function renderKpis() {
    var i = state.qi;
    var gvYoy = yoyOf(S.gv, i), cYoy = yoyOf(S.contract, i),
        fYoy = yoyOf(S.firms, i), wYoy = yoyOf(S.workers, i);
    var aYoy = yoyOf(S.areaUnder, i);
    var el1 = gvYoy === null ? null : r1(gvYoy - (yoyOf(S.gv, i - 1) || gvYoy));
    el('jz-kpis').innerHTML =
      kpiCard('K1', '建筑业总产值', wanYi(S.gv[i]), '万亿元',
        deltaHtml('累计同比', gvYoy) + (el1 === null ? '' : ' · ' + deltaHtml('增速环比', el1, 'pp'))) +
      kpiCard('K2', '签订合同总额', wanYi(S.contract[i]), '万亿元', deltaHtml('累计同比', cYoy)) +
      kpiCard('K3', '本年新签合同', wanYi(S.contractNew[i]), '万亿元',
        '占总额 <span class="bp-up">' + (S.contractNew[i] / S.contract[i] * 100).toFixed(1) + '%</span>') +
      kpiCard('K4', '房屋施工面积', fmtYi(S.areaUnder[i]), '万㎡',
        '新开工占 <span class="bp-up">' + (S.areaNew[i] / S.areaUnder[i] * 100).toFixed(1) + '%</span>' +
        (aYoy === null ? '' : ' · ' + deltaHtml('同比', aYoy))) +
      kpiCard('K5', '企业单位数', fmtYi(S.firms[i]), '个', deltaHtml('累计同比', fYoy)) +
      kpiCard('K6', '从业人员', fmtYi(S.workers[i]), '万人', deltaHtml('累计同比', wYoy));
  }
  function renderBrief() {
    var i = state.qi;
    el('jz-detail').innerHTML =
      '<b>' + Q[i] + ' 速读</b>&nbsp;&nbsp;建筑业总产值累计 <b>' + wanYi(S.gv[i]) + ' 万亿元</b>' +
      '（同比 <b>' + sgn(yoyOf(S.gv, i)) + '%</b>）；签订合同 <b>' + wanYi(S.contract[i]) + ' 万亿元</b>' +
      '（新签占 <b>' + (S.contractNew[i] / S.contract[i] * 100).toFixed(1) + '%</b>）；' +
      '竣工产值率 <b>' + (S.gvDone[i] / S.gv[i] * 100).toFixed(1) + '%</b>，' +
      '在外省完成产值占 <b>' + (S.gvOutProv[i] / S.gv[i] * 100).toFixed(1) + '%</b>；' +
      '房屋新开工面积占施工面积 <b>' + (S.areaNew[i] / S.areaUnder[i] * 100).toFixed(1) + '%</b>。';
  }
  function renderFinNote() {
    el('sub-fin').textContent = '最近一期：' + F.period + '（财务指标无四季度数据）· 亿元';
    el('fin-note').innerHTML =
      '资产负债率 <b>' + (F.liab / F.assets * 100).toFixed(1) + '%</b> · ' +
      '产值利润率 <b>' + F.marginRate + '%</b> · ' +
      '应收工程款占流动资产 <b>' + (F.receivable / F.liquid * 100).toFixed(1) + '%</b> · ' +
      '主营业务成本率 <b>' + (F.costMain / F.revMain * 100).toFixed(1) + '%</b>';
  }

  /* ---------- 渲染 ---------- */
  function renderSlider() {
    var r = el('jz-range');
    r.value = state.qi;
    var p = state.qi / (N - 1) * 100;
    r.style.background = 'linear-gradient(to right,#8fd9ff 0%,#8fd9ff ' + p + '%,rgba(226,240,255,0.18) ' + p + '%)';
  }
  function apply() {
    var qi = state.qi;
    renderSlider();
    renderKpis();
    renderBrief();
    chGv.setOption(optGv(), true);
    chContract.setOption(optContract(), true);
    chArea.setOption(optArea(), true);
    chRankArea.setOption(optRank(AREA_CATS, S, '万平方米', C.cyan), true);
    el('sub-rank-area').textContent = Q[qi] + ' · 万平方米 · 按面积降序';
    chRankValue.setOption(optRank(VALUE_CATS, S, '亿元', C.gold), true);
    el('sub-rank-value').textContent = Q[qi] + ' · 亿元 · 按价值降序';
    chFin.setOption(optFin(), true);
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
    state.timer = setInterval(function () { setQuarter((state.qi + 1) % N); }, 1200);
  }
  el('btn-play').addEventListener('click', togglePlay);
  el('btn-reset').addEventListener('click', function () {
    stopPlay(); state.qi = N - 1; apply(); resetDetail();
  });
  el('btn-prev').addEventListener('click', function () { setQuarter(state.qi - 1, true); });
  el('btn-next').addEventListener('click', function () { setQuarter(state.qi + 1, true); });
  el('jz-range').addEventListener('input', function () { setQuarter(+this.value, true); });

  window.addEventListener('resize', function () {
    ALL.forEach(function (c) { c.resize(); });
  });
  window.addEventListener('load', function () {
    ALL.forEach(function (c) { c.resize(); });
  });

  renderFinNote();
  apply();
  resetDetail();
})();
"""

# =====================================================================
# 四、派生校验与组装
# =====================================================================

def build_data(quarters, S, fin):
    n = len(quarters)
    for alias, vals in S.items():
        if isinstance(vals, dict):
            continue  # 竣工房屋价值按季度键映射，长度可不同于主时间轴
        if len(vals) != n:
            raise SystemExit('指标 %s 长度 %d ≠ %d' % (alias, len(vals), n))
    i = n - 1
    print('解析完成：%d 个季度（%s — %s）。抽样核对最后一期：' % (n, quarters[0], quarters[-1]))
    checks = [
        ('总产值累计(亿元)', S['gv'][i], 181227.42),
        ('建筑工程产值(亿元)', S['gvBuild'][i], 160168.06),
        ('签订合同总额(亿元)', S['contract'][i], 557673.11),
        ('施工面积(万㎡)', S['areaUnder'][i], 813287.61),
        ('企业单位数(个)', S['firms'][i], 158632),
        ('从业人员(万人)', S['workers'][i], 4093.37),
        ('竣工面积(万㎡)', S['areaDone'][i], 124236.50),
        ('住宅竣工价值(亿元)', S['v_residential'][quarters[i]], 13669.79),
    ]
    ok = True
    for name, got, want in checks:
        match = abs(got - want) < 0.05
        ok = ok and match
        print('  %-16s 取值 %-14s 期望 %-14s %s' % (name, got, want, 'OK' if match else '!!'))
    if not ok:
        raise SystemExit('抽样校验未通过，请确认 CSV 为国家统计局原始导出文件。')
    return {'quarters': quarters, 'series': S, 'fin': fin}


def main():
    no_open = '--no-open' in sys.argv
    print('正在扫描 %s 下的数据表 …' % DATA_DIR)
    quarters, S, fin = load_data()
    data = build_data(quarters, S, fin)

    echarts_tag = get_echarts_tag()
    data_json = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    fragment = (TEMPLATE
                .replace('/*__STYLE__*/', CSS)
                .replace('__ECHARTS__', echarts_tag)
                .replace('/*__DATA__*/', data_json)
                .replace('/*__APP__*/', APP))
    html = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>建筑业 · 季度数据监测屏</title>\n</head>\n<body>\n'
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

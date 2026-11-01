# -*- coding: utf-8 -*-
'''价值指数 · 季度数据 BI 大屏生成器（Swiss Typographic 瑞士国际主义风）
================================================================

自包含的可视化项目：仅用 Python 标准库即可在本机（VS Code / PyCharm / 命令行）运行，
无需 pip 安装任何第三方包。风格：瑞士国际主义 —— 白底黑字、红色强调、严格网格、
左对齐粗标题、几乎零装饰（风格选型依据见 ../风格库/README.md；
用户偏好：不出现图签/制表信息元素）。

功能
----
1. 读取 data/ 目录下的 5 张国家统计局价值指数季度表：
   · 农产品生产者价格指数（上年同期=100，2025Q2—2026Q3 当季值，部分品类存在缺报）
   · 固定资产投资价格指数（当季 / 累计，2017Q4—2019Q4 历史数据；
     2020 年起该统计制度取消，故 2018 及以前与 2019 年采用两套分类口径，本屏自动拼接）
2. 解析、校验并派生指标（指数−100 的涨跌幅、涨跌最大品类等）；
3. 生成「瑞士国际主义风」交互式 BI 大屏 HTML 并自动在浏览器中打开。

使用方法
--------
在本文件夹内打开终端，执行：
    python generate_bi_dashboard.py            # 生成大屏并自动打开浏览器
    python generate_bi_dashboard.py --no-open  # 只生成文件，不打开浏览器

首次运行会自动下载 ECharts 图表库并缓存为本文件夹下的 echarts.min.js（此后完全离线可用）。

输出：价值指数BI大屏.html（双击也可随时打开）。
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
OUTPUT_HTML = BASE / '价值指数BI大屏.html'

QMAP = {'一': 1, '二': 2, '三': 3, '四': 4}

# =====================================================================
# 一、数据解析
# =====================================================================

# 农产品表：排除"总指数"后的分类展示顺序（短名 → 指标前缀）
AGRI_CATS = [
    ('农业产品', '农业产品生产者价格指数当季值'),
    ('谷物', '谷物生产价格指数当季值'),
    ('小麦', '小麦生产价格指数当季值'),
    ('稻谷', '稻谷生产价格指数当季值'),
    ('玉米', '玉米生产价格指数当季值'),
    ('豆类', '豆类生产价格指数当季值'),
    ('薯类', '薯类生产价格指数当季值'),
    ('油料', '油料生产价格指数当季值'),
    ('棉花', '棉花生产价格指数当季值'),
    ('糖料', '糖料生产价格指数当季值'),
    ('烟叶', '烟叶生产价格指数当季值'),
    ('蔬菜', '蔬菜生产价格指数当季值'),
    ('水果', '水果生产价格指数当季值'),
    ('茶叶', '茶叶生产价格指数当季值'),
    ('林业产品', '林业产品生产价格指数当季值'),
    ('木材', '木材生产价格指数当季值'),
    ('竹材', '竹材生产价格指数当季值'),
]
# 多线走势图重点展示的主要品类
AGRI_MAIN = ['农业产品', '谷物', '玉米', '豆类', '蔬菜', '水果']

# 固定资产投资价格指数：新(2019-) / 旧(-2018) 两套口径的分类
FA_NEW_CATS = [
    ('建筑安装工程', '建筑安装工程价格指数当季值'),
    ('人工费', '人工费价格指数当季值'),
    ('材料费', '材料费价格指数当季值'),
    ('金属材料', '金属材料价格指数当季值'),
    ('非金属材料', '非金属材料价格指数当季值'),
    ('机械费', '机械费价格指数当季值'),
    ('设备工器具', '设备、工器具购置价格指数当季值'),
    ('其他费用', '其他费用价格指数当季值'),
]
FA_OLD_CATS = [
    ('建筑安装装饰工程', '建筑、安装、装饰工程价格指数当季值'),
    ('人工费', '人工费价格指数当季值'),
    ('材料费', '材料费价格指数当季值'),
    ('钢材', '钢材价格指数当季值'),
    ('水泥', '水泥价格指数当季值'),
    ('地方建筑材料', '地方建筑材料价格指数当季值'),
    ('机械使用费', '机械使用费价格指数当季值'),
    ('设备工器具', '设备、工器具购置价格指数当季值'),
]


def parse_file(fp):
    """解析单张表：返回 (季度列表[时间正序], {指标名(去空白): 数值列表})。缺失值保留 None。"""
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
        # 关键：按季度轴对齐（中间/尾部缺报一律补 None），避免"去尾"导致错位
        vals = (vals + [None] * len(quarters))[:len(quarters)]
        rows[first] = vals
    if quarters is None:
        raise SystemExit('数据表格式异常（未找到表头季度行）：%s' % fp.name)
    quarters = list(reversed(quarters))
    rows = {k: list(reversed(v)) for k, v in rows.items()}
    return quarters, rows


def grab(rows, prefix, label):
    key = next((k for k in rows if k.startswith(prefix)), None)
    if key is None:
        raise SystemExit('缺少指标：%s（%s）' % (prefix, label))
    return rows[key]


def load_data():
    if not DATA_DIR.exists():
        raise SystemExit('未找到数据目录：%s' % DATA_DIR)

    # ---- 农产品生产者价格指数（当季，6 期；允许缺失值，ECharts 折线自动断点）----
    qs_a, rows_a = parse_file(DATA_DIR / '农产品生产者价格指数（上年同期=100）.csv')
    agri = {
        'total': grab(rows_a, '农产品生产者价格指数当季值', '农产品总指数'),
    }
    dropped = []
    for short, prefix in AGRI_CATS:
        vals = grab(rows_a, prefix, short)
        if sum(1 for v in vals if v is not None) < 2:
            dropped.append(short)
            continue
        agri[short] = vals
    if dropped:
        print('  [农产品] 缺报过多被略去的品类：%s' % '、'.join(dropped))

    # ---- 固定资产投资价格指数（2017Q4—2019Q4 历史数据，新旧口径拼接）----
    qs_o_q, rows_o_q = parse_file(DATA_DIR / '固定资产投资价格指数_当季（上年同季=100） (-2018).csv')
    qs_n_q, rows_n_q = parse_file(DATA_DIR / '固定资产投资价格指数_当季（上年同季=100） (2019-).csv')
    qs_o_c, rows_o_c = parse_file(DATA_DIR / '固定资产投资价格指数_累计值（上年同期=100） (-2018).csv')
    qs_n_c, rows_n_c = parse_file(DATA_DIR / '固定资产投资价格指数_累计（上年同期=100） (2019-).csv')

    # 当季总指数：旧口径(2017Q4—2018Q4) + 新口径(2019Q1—Q4) 拼接
    fa_q_quarters = qs_o_q + qs_n_q
    fa_total_q = grab(rows_o_q, '固定资产投资价格指数当季值', '固投当季-旧') + \
        grab(rows_n_q, '固定资产投资价格指数当季值', '固投当季-新')
    # 累计总指数：旧口径 5 期 + 新口径 3 期（2019Q1 累计未发布）
    fa_c_quarters = qs_o_c + qs_n_c
    fa_total_c = grab(rows_o_c, '固定资产投资价格指数累计值', '固投累计-旧') + \
        grab(rows_n_c, '固定资产投资价格指数累计值', '固投累计-新')

    def cat_series(rows, cats, qs_check):
        out = {}
        for short, prefix in cats:
            out[short] = grab(rows, prefix, short)
            if len(out[short]) != len(qs_check):
                raise SystemExit('固投分类 %s 长度异常' % short)
        return out

    return {
        'agri': {'quarters': qs_a, 'series': agri, 'dropped': dropped},
        'fa': {
            'quarterly': {'quarters': fa_q_quarters, 'total': fa_total_q,
                          'old': cat_series(rows_o_q, FA_OLD_CATS, qs_o_q),
                          'new': cat_series(rows_n_q, FA_NEW_CATS, qs_n_q)},
            'cumulative': {'quarters': fa_c_quarters, 'total': fa_total_c},
        },
    }


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
# 三、页面资源：瑞士国际主义样式 / 模板 / 交互脚本
# =====================================================================

# pylint: disable=line-too-long
CSS = r"""
#vi-dashboard-root {
  --ink: #111111; --gray: #8c8c8c; --faint: #b3b3b3;
  --red: #e63312; --blue: #0057ff; --hairline: #e5e5e5;
  position: relative;
  color: var(--ink);
  font-family: "Helvetica Neue", "Microsoft YaHei", Arial, sans-serif;
  font-size: 14px; line-height: 1.5;
  padding: 22px 26px 16px; border-radius: 2px; min-width: 0;
  background: #ffffff; border-top: 6px solid #111111;
}
#vi-dashboard-root * { box-sizing: border-box; }

/* ---------- 头部 ---------- */
.vi-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 14px;
  flex-wrap: wrap; margin-bottom: 16px; padding-bottom: 14px; border-bottom: 1px solid #111111; }
.vi-brand h1 { margin: 0; font-size: 26px; font-weight: 800; letter-spacing: 0.5px; text-align: left; }
.vi-brand h1 em { font-style: normal; color: var(--red); }
.vi-brand p { margin: 4px 0 0; font-size: 12.5px; color: var(--gray); }
.vi-brand .en { font-size: 10.5px; letter-spacing: 3px; color: var(--faint); text-transform: uppercase; }
.vi-meta { font-size: 11px; color: var(--gray); text-align: right; line-height: 1.8; }
.vi-meta b { color: var(--ink); }

/* ---------- 时间轴 ---------- */
.vi-timeline { display: flex; align-items: center; gap: 12px; position: relative;
  margin-bottom: 16px; padding: 10px 4px 22px; border-bottom: 1px solid var(--hairline); }
.vi-tl-label { font-size: 12px; font-weight: 700; color: var(--ink); flex: 0 0 auto; }
.vi-arrow { width: 26px; height: 26px; border: 1px solid #111111; background: #fff; color: #111;
  cursor: pointer; flex: 0 0 auto; font-size: 13px; line-height: 1; display: flex;
  align-items: center; justify-content: center; padding: 0; font-family: inherit; border-radius: 0; }
.vi-arrow:hover { background: #111111; color: #fff; }
#vi-range { flex: 1; -webkit-appearance: none; appearance: none; height: 3px; border-radius: 0;
  background: #111111; outline: none; cursor: pointer; min-width: 120px; }
#vi-range::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 16px; height: 16px;
  border-radius: 0; background: var(--red); border: none; cursor: grab; }
#vi-range::-moz-range-thumb { width: 14px; height: 14px; border-radius: 0; background: var(--red);
  border: none; cursor: grab; }
.vi-btn { border: 1px solid #111111; background: #fff; color: #111; border-radius: 0;
  padding: 5px 15px; font-size: 12px; cursor: pointer; font-family: inherit; font-weight: 700; }
.vi-btn:hover { background: #111111; color: #fff; }
.vi-btn.primary { background: var(--red); border-color: var(--red); color: #fff; }
.vi-btn.primary:hover { background: #c22a0e; }
.vi-years { position: absolute; left: 92px; right: 330px; bottom: 3px; height: 15px; pointer-events: none; }
.vi-years span { position: absolute; transform: translateX(-50%); font-size: 10.5px; color: var(--gray); }
.vi-hint { font-size: 11px; color: var(--gray); flex: 0 0 auto; max-width: 250px; text-align: right; line-height: 1.45; }

/* ---------- 详情钉住栏 ---------- */
.vi-detail { border-top: 2px solid #111111; border-bottom: 1px solid var(--hairline);
  padding: 9px 2px; font-size: 13px; line-height: 1.7; margin-bottom: 16px; color: #333333; min-height: 42px; }
.vi-detail b { color: var(--red); font-weight: 700; }

/* ---------- KPI ---------- */
.vi-kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; margin-bottom: 18px;
  border-top: 2px solid #111111; border-bottom: 1px solid var(--hairline); }
.vi-kpi { padding: 14px 16px 12px; min-width: 0; border-right: 1px solid var(--hairline); }
.vi-kpi:last-child { border-right: none; }
.vi-kpi-top { font-size: 11.5px; color: var(--gray); font-weight: 700; letter-spacing: 1px; }
.vi-kpi-val { font-size: 32px; font-weight: 800; margin: 4px 0 2px; white-space: nowrap;
  color: var(--ink); font-variant-numeric: tabular-nums; letter-spacing: -0.5px; }
.vi-kpi-val small { font-size: 13px; color: var(--gray); font-weight: 600; }
.vi-kpi-val .neg { color: var(--red); }
.vi-kpi-sub { font-size: 11.5px; color: var(--gray); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vi-up { color: var(--red); font-weight: 700; }
.vi-down { color: var(--blue); font-weight: 700; }

/* ---------- 图表网格 ---------- */
.vi-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 0; }
.vi-card { border-top: 2px solid #111111; padding: 12px 18px 8px 0; min-width: 0; }
.vi-s4 { grid-column: span 4; padding-right: 18px; }
.vi-s6 { grid-column: span 6; }
.vi-s6 + .vi-s6 { padding-left: 18px; border-left: 1px solid var(--hairline); }
.vi-s8 { grid-column: span 8; padding-right: 18px; }
.vi-s4 + .vi-s8, .vi-s8 + .vi-s4 { }
.vi-card-h h3 { font-size: 14.5px; font-weight: 800; margin: 0; text-align: left; }
.vi-card-h h3 .no { color: var(--red); margin-right: 8px; font-family: "Helvetica Neue", Arial, sans-serif; }
.vi-hint-r { font-size: 11px; color: var(--gray); }
.vi-sub { font-size: 11.5px; color: var(--gray); margin: 2px 0 2px; }
.vi-chart { width: 100%; height: 296px; }
.vi-foot { font-size: 11px; color: var(--gray); margin-top: 16px; line-height: 1.7;
  border-top: 1px solid var(--hairline); padding-top: 10px; }

@media (prefers-reduced-motion: reduce) {
  #vi-dashboard-root * { animation: none !important; transition: none !important; }
}
@media (max-width: 1280px) {
  .vi-s4, .vi-s6, .vi-s8 { grid-column: span 12; padding-left: 0; padding-right: 0; border-left: none; }
  .vi-kpis { grid-template-columns: repeat(2, 1fr); }
  .vi-kpi { border-bottom: 1px solid var(--hairline); }
  .vi-years { display: none; }
}
@media (max-width: 720px) {
  .vi-kpis { grid-template-columns: 1fr; }
  #vi-dashboard-root { padding: 14px; }
}
"""

TEMPLATE = """
<style>
/*__STYLE__*/
</style>

<div id="vi-dashboard-root">
  <div class="vi-header">
    <div class="vi-brand">
      <h1>价值指数季度数据大屏 <em>/</em> 农产品与固定资产投资价格</h1>
      <div class="en">PRICE INDEX QUARTERLY MONITOR — AGRICULTURAL &amp; FIXED ASSET INVESTMENT</div>
      <p>农产品生产者价格指数（上年同期=100）· 固定资产投资价格指数（2017Q4—2019Q4，2020 年起制度取消）&nbsp;|&nbsp; 数据来源：国家统计局「季度数据」</p>
    </div>
    <div class="vi-meta">
      指数基准：<b>上年同期 = 100</b><br>
      &gt; 100 表示价格上涨，&lt; 100 表示下降<br>
      红色 <b style="color:#e63312;">■</b> 为强调色
    </div>
  </div>

  <div class="vi-timeline">
    <span class="vi-tl-label">季度</span>
    <button type="button" class="vi-arrow" id="btn-prev" aria-label="上一季度">‹</button>
    <input type="range" id="vi-range" min="0" max="5" step="1" value="5" aria-label="选择季度（农产品指数）" />
    <button type="button" class="vi-arrow" id="btn-next" aria-label="下一季度">›</button>
    <button type="button" class="vi-btn primary" id="btn-play">播放</button>
    <button type="button" class="vi-btn" id="btn-reset">重置</button>
    <span class="vi-hint">时间轴联动农产品指数三张图 · 点击图 01/03 柱线可切换季度</span>
    <div class="vi-years" aria-hidden="true">
      <span style="left:0%">2025Q2</span><span style="left:20%">2025Q3</span><span style="left:40%">2025Q4</span><span style="left:60%">2026Q1</span><span style="left:80%">2026Q2</span><span style="left:100%">2026Q3</span>
    </div>
  </div>

  <div class="vi-detail" id="vi-detail" aria-live="polite"></div>

  <div class="vi-kpis" id="vi-kpis"></div>

  <div class="vi-grid">
    <div class="vi-card vi-s8">
      <div class="vi-card-h"><h3><span class="no">01</span>农产品生产者价格总指数（当季）</h3><span class="vi-hint-r">点击柱体切换季度</span></div>
      <div class="vi-sub">上年同期 = 100；红色虚线为 100 基准（&gt;100 涨价，&lt;100 降价）</div>
      <div class="vi-chart" id="vi-ch-total"></div>
    </div>
    <div class="vi-card vi-s4">
      <div class="vi-card-h"><h3><span class="no">02</span>分类指数涨跌（当季）</h3><span class="vi-hint-r">指数 − 100</span></div>
      <div class="vi-sub" id="sub-rank">红色 = 上涨 · 蓝色 = 下降</div>
      <div class="vi-chart" id="vi-ch-rank"></div>
    </div>
    <div class="vi-card vi-s6">
      <div class="vi-card-h"><h3><span class="no">03</span>主要品类指数走势（当季）</h3><span class="vi-hint-r">含缺报断点</span></div>
      <div class="vi-sub">总指数与六大主要品类 · 100 基准线</div>
      <div class="vi-chart" id="vi-ch-multi"></div>
    </div>
    <div class="vi-card vi-s6">
      <div class="vi-card-h"><h3><span class="no">04</span>固定资产投资价格总指数（当季）</h3><span class="vi-hint-r">2017Q4—2019Q4</span></div>
      <div class="vi-sub">新旧口径拼接 · 灰色区域为口径切换点（2020 年起制度取消）</div>
      <div class="vi-chart" id="vi-ch-fa"></div>
    </div>
    <div class="vi-card vi-s6">
      <div class="vi-card-h"><h3><span class="no">05</span>固投分类指数涨跌（2019Q4 当季）</h3><span class="vi-hint-r">新口径 · 指数 − 100</span></div>
      <div class="vi-sub">红色 = 上涨 · 蓝色 = 下降</div>
      <div class="vi-chart" id="vi-ch-farank"></div>
    </div>
    <div class="vi-card vi-s6">
      <div class="vi-card-h"><h3><span class="no">06</span>固定资产投资价格总指数（累计）</h3><span class="vi-hint-r">2017Q4—2019Q4</span></div>
      <div class="vi-sub">面积图 · 100 基准线</div>
      <div class="vi-chart" id="vi-ch-facum"></div>
    </div>
  </div>

  <div class="vi-foot">
    数据来源：国家统计局「数据库 — 季度数据」。农产品生产者价格指数为当季同比指数（上年同期=100），
    棉花、糖料、烟叶等品类存在季度缺报，图中以断点呈现；固定资产投资价格指数统计至 2019 年
    （2020 年起取消该统计调查制度），2018 年及以前与 2019 年分类口径不同，总指数序列为两套口径拼接，
    分类别涨跌仅在同一口径内比较。涨跌幅度 = 指数 − 100，正值为上涨、负值为下降。
  </div>
</div>

__ECHARTS__

<script>
window.VI_DATA = /*__DATA__*/;
</script>

<script>
/*__APP__*/
</script>
"""

APP = r"""
(function () {
  'use strict';
  var root = document.getElementById('vi-dashboard-root');
  if (!root) return;
  if (typeof echarts === 'undefined') {
    root.innerHTML = '<div style="padding:60px 20px;text-align:center;color:#8c8c8c;font-size:14px;">ECharts 加载失败：请联网后刷新（首次运行脚本会自动下载并内联图表库）。</div>';
    return;
  }
  var RAW = window.VI_DATA;
  var A = RAW.agri, FA = RAW.fa;
  var Q = A.quarters, N = Q.length;
  var state = { qi: N - 1, playing: false, timer: null };

  var C = { ink: '#111111', gray: '#8c8c8c', faint: '#b3b3b3', red: '#e63312', blue: '#0057ff',
    hairline: '#e5e5e5', axis: 'rgba(17,17,17,0.55)', split: 'rgba(17,17,17,0.07)' };
  var SERIES_COLORS = [C.ink, C.red, C.blue, C.gray, '#c22a0e', '#5a5a5a'];
  var TIP = {
    backgroundColor: '#ffffff', borderColor: '#111111', borderWidth: 1.5,
    padding: [10, 14], textStyle: { color: C.ink, fontSize: 12.5 },
    extraCssText: 'box-shadow:4px 4px 0 rgba(17,17,17,0.9);border-radius:0;'
  };
  function tipTitle(q) { return '<div style="font-weight:800;font-size:13px;margin-bottom:4px;">' + q + '</div>'; }
  function tipRow(k, v, color) {
    return '<div style="display:flex;justify-content:space-between;gap:22px;line-height:1.9;">' +
      '<span style="opacity:.6;">' + k + '</span>' +
      '<span style="font-weight:700;' + (color ? 'color:' + color : '') + '">' + v + '</span></div>';
  }
  function el(id) { return document.getElementById(id); }
  function dev(v) { return v - 100; }
  function sgn(v) { return (v > 0 ? '+' : '') + v.toFixed(1); }
  function idxFmt(v) { return v.toFixed(1); }
  function baseline(color) {
    return { silent: true, symbol: 'none', animation: false, label: { show: false },
      lineStyle: { type: 'dashed', color: color || C.red, width: 1.2 }, data: [{ yAxis: 100 }] };
  }
  function baseAxis() {
    return { type: 'category', data: Q.map(function (q) { return q.slice(2); }),
      axisLine: { lineStyle: { color: '#111111' } }, axisTick: { show: false },
      axisLabel: { color: C.axis, fontSize: 10.5 } };
  }
  function pctAxis(minPad, maxPad) {
    return { type: 'value', min: function (v) { return Math.floor((v.min - (minPad || 1)) * 2) / 2; },
      max: function (v) { return Math.ceil((v.max + (maxPad || 1)) * 2) / 2; },
      axisLabel: { color: C.axis, fontSize: 10.5, formatter: '{value}' }, splitLine: { lineStyle: { color: C.split } } };
  }

  var charts = {};
  function mk(id) { var c = echarts.init(el(id)); charts[id] = c; return c; }
  var chTotal = mk('vi-ch-total'), chRank = mk('vi-ch-rank'), chMulti = mk('vi-ch-multi'),
      chFa = mk('vi-ch-fa'), chFaRank = mk('vi-ch-farank'), chFaCum = mk('vi-ch-facum');

  /* ---------- 图 01：农产品总指数柱状 + 100 基准 ---------- */
  function optTotal() {
    var i = state.qi;
    var v = A.series.total[i];
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 46, right: 14, top: 22, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var k = ps[0].dataIndex;
          var val = A.series.total[k];
          return tipTitle(Q[k]) +
            tipRow('总指数', val.toFixed(1), val >= 100 ? C.red : C.blue) +
            tipRow('较上年同期', (val >= 100 ? '+' : '') + dev(val).toFixed(1) + '%');
        }
      }),
      xAxis: baseAxis(),
      yAxis: pctAxis(),
      series: [{
        name: '总指数', type: 'bar', barWidth: '52%',
        data: A.series.total.map(function (val, k) {
          return { value: val,
            itemStyle: { color: k === i ? '#111111' : 'rgba(17,17,17,0.16)' } };
        }),
        markLine: baseline(),
        label: { show: true, position: 'top', fontSize: 10.5, color: C.ink, fontWeight: 700,
          formatter: function (p) { return idxFmt(p.value); } }
      }]
    };
  }

  /* ---------- 图 02：分类涨跌发散条形（当季） ---------- */
  function optRank() {
    var i = state.qi;
    var items = RAW.agriCats.map(function (c) {
      var raw = A.series[c[0]] ? A.series[c[0]][i] : null;
      return { name: c[0], v: raw === null || raw === undefined ? null : dev(raw) };
    }).filter(function (x) { return x.v !== null; })
      .sort(function (a, b) { return b.v - a.v; });
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 76, right: 56, top: 8, bottom: 20 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var it = items[p.dataIndex];
          return tipTitle(it.name) +
            tipRow('指数', (100 + it.v).toFixed(1), it.v >= 0 ? C.red : C.blue) +
            tipRow('较上年同期', sgn(it.v) + '%', it.v >= 0 ? C.red : C.blue);
        }
      }),
      xAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x.name; }),
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: '#333333', fontSize: 11 } },
      series: [{
        name: '涨跌', type: 'bar', barWidth: '58%',
        data: items.map(function (x) {
          return { value: x.v,
            itemStyle: { color: x.v >= 0 ? C.red : C.blue, borderRadius: 0 },
            label: { position: x.v >= 0 ? 'right' : 'left' } };
        }),
        label: { show: true, fontSize: 10.5, color: C.ink, fontWeight: 700,
          formatter: function (p) { return sgn(p.value) + '%'; } },
        markLine: { silent: true, symbol: 'none', animation: false, label: { show: false },
          lineStyle: { color: '#111111', width: 1.2 }, data: [{ xAxis: 0 }] }
      }]
    };
  }

  /* ---------- 图 03：主要品类多线走势 ---------- */
  function optMulti() {
    var names = ['total'].concat(RAW.agriMain.filter(function (n) { return A.series[n]; }));
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: SERIES_COLORS,
      legend: { top: 0, right: 4, itemWidth: 16, itemHeight: 2, itemGap: 10,
        textStyle: { fontSize: 10.5, color: '#333333' },
        data: names.map(function (n) { return n === 'total' ? '总指数' : n; }) },
      grid: { left: 44, right: 16, top: 34, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'line' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          var html = tipTitle(Q[i]);
          ps.forEach(function (p) {
            if (p.value === null || p.value === undefined) return;
            html += tipRow(p.seriesName, p.value.toFixed(1), p.color);
          });
          return html;
        }
      }),
      xAxis: baseAxis(),
      yAxis: { type: 'value', min: 88, max: 112, axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      series: names.map(function (n, i) {
        var display = n === 'total' ? '总指数' : n;
        return { name: display, type: 'line', data: A.series[n], symbol: 'circle', symbolSize: 5,
          connectNulls: false, z: i === 0 ? 6 : 3,
          lineStyle: { width: n === 'total' ? 3 : 1.8, color: SERIES_COLORS[i % SERIES_COLORS.length] },
          itemStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
          markLine: i === 0 ? baseline() : undefined };
      })
    };
  }

  /* ---------- 图 04：固投总指数历史（当季拼接） ---------- */
  function optFa() {
    var qs = FA.quarterly.quarters.map(function (q) { return q.slice(2); });
    var breakIdx = qs_o_break();
    function qs_o_break() { return 5; } // 旧口径 5 期（2017Q4—2018Q4），此后为新口径
    return {
      animation: true, animationDuration: 0,
      grid: { left: 44, right: 16, top: 26, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'line' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(FA.quarterly.quarters[i]) +
            tipRow('总指数', FA.quarterly.total[i].toFixed(1), FA.quarterly.total[i] >= 100 ? C.red : C.blue) +
            tipRow('较上年同季', sgn(dev(FA.quarterly.total[i])) + '%');
        }
      }),
      xAxis: { type: 'category', data: qs,
        axisLine: { lineStyle: { color: '#111111' } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: { type: 'value', min: 98, max: 110, axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      series: [{
        name: '总指数', type: 'line', data: FA.quarterly.total, symbol: 'rect', symbolSize: 7,
        lineStyle: { width: 2.5, color: '#111111' }, itemStyle: { color: '#111111' },
        areaStyle: { color: 'rgba(17,17,17,0.05)' },
        markLine: baseline(),
        markArea: { silent: true, itemStyle: { color: 'rgba(230,51,18,0.05)' },
          label: { show: true, position: 'insideTop', fontSize: 10, color: C.red,
            formatter: '2019 年起为新口径' },
          data: [[{ xAxis: qs[breakIdx] }, { xAxis: qs[qs.length - 1] }]] }
      }]
    };
  }

  /* ---------- 图 05：固投分类涨跌发散条形（2019Q4 新口径） ---------- */
  function optFaRank() {
    var items = RAW.faNewCats.map(function (c) {
      var arr = FA.quarterly.new[c[0]];
      var v = arr[arr.length - 1];  // 新口径数组自对齐 2019 年四季，最后一期即 2019Q4
      return { name: c[0], v: dev(v) };
    }).sort(function (a, b) { return b.v - a.v; });
    return {
      animation: true, animationDuration: 0,
      grid: { left: 110, right: 56, top: 8, bottom: 20 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var it = items[p.dataIndex];
          return tipTitle(it.name) +
            tipRow('指数', (100 + it.v).toFixed(1), it.v >= 0 ? C.red : C.blue) +
            tipRow('较上年同季', sgn(it.v) + '%', it.v >= 0 ? C.red : C.blue);
        }
      }),
      xAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x.name; }),
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: '#333333', fontSize: 10.5 } },
      series: [{
        name: '涨跌', type: 'bar', barWidth: '56%',
        data: items.map(function (x) {
          return { value: x.v, itemStyle: { color: x.v >= 0 ? C.red : C.blue },
            label: { position: x.v >= 0 ? 'right' : 'left' } };
        }),
        label: { show: true, fontSize: 10.5, color: C.ink, fontWeight: 700,
          formatter: function (p) { return sgn(p.value) + '%'; } },
        markLine: { silent: true, symbol: 'none', animation: false, label: { show: false },
          lineStyle: { color: '#111111', width: 1.2 }, data: [{ xAxis: 0 }] }
      }]
    };
  }

  /* ---------- 图 06：固投累计指数面积图 ---------- */
  function optFaCum() {
    var qs = FA.cumulative.quarters.map(function (q) { return q.slice(2); });
    return {
      animation: true, animationDuration: 0,
      grid: { left: 44, right: 16, top: 26, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'line' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(FA.cumulative.quarters[i]) +
            tipRow('累计指数', FA.cumulative.total[i].toFixed(1), FA.cumulative.total[i] >= 100 ? C.red : C.blue) +
            tipRow('较上年同期', sgn(dev(FA.cumulative.total[i])) + '%');
        }
      }),
      xAxis: { type: 'category', data: qs,
        axisLine: { lineStyle: { color: '#111111' } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: { type: 'value', min: 100, max: 108, axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      series: [{
        name: '累计指数', type: 'line', data: FA.cumulative.total, symbol: 'rect', symbolSize: 7,
        lineStyle: { width: 2.5, color: C.red }, itemStyle: { color: C.red },
        areaStyle: { color: 'rgba(230,51,18,0.08)' },
        markLine: baseline()
      }]
    };
  }

  /* ---------- 详情钉住 ---------- */
  function pinDetail(html) { el('vi-detail').innerHTML = html; }
  var DEFAULT_HINT = '<b>使用提示</b>&nbsp;&nbsp;时间轴联动图 01—03（农产品指数，当季）；点击图 01 柱体或图 03 拐点可切换季度，点击数据点钉住详情。指数 &gt; 100 为上涨、&lt; 100 为下降。';
  function resetDetail() { el('vi-detail').innerHTML = DEFAULT_HINT; }

  chTotal.on('click', function (p) {
    if (typeof p.dataIndex !== 'number') return;
    setQuarter(p.dataIndex, true);
  });
  chMulti.on('click', function (p) {
    if (typeof p.dataIndex !== 'number') return;
    setQuarter(p.dataIndex, true);
  });
  chTotal.on('click', function (p) {
    if (typeof p.dataIndex !== 'number' || p.seriesName !== '总指数') return;
    pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · 农产品生产者价格总指数') +
      '<b>' + p.value.toFixed(1) + '</b>&nbsp;&nbsp;较上年同期 <b>' + sgn(dev(p.value)) + '%</b>');
  });

  /* ---------- KPI ---------- */
  function kpiTile(no, title, val, unit, sub) {
    return '<div class="vi-kpi"><div class="vi-kpi-top">' + no + ' · ' + title + '</div>' +
      '<div class="vi-kpi-val">' + val + '<small>' + unit + '</small></div>' +
      '<div class="vi-kpi-sub">' + sub + '</div></div>';
  }
  function renderKpis() {
    var i = state.qi;
    var total = A.series.total[i];
    var items = RAW.agriCats.map(function (c) {
      var v = A.series[c[0]] ? A.series[c[0]][i] : null;
      return { n: c[0], v: v };
    }).filter(function (x) { return x.v !== null; });
    var best = items.reduce(function (a, b) { return b.v > a.v ? b : a; });
    var worst = items.reduce(function (a, b) { return b.v < a.v ? b : a; });
    var faQ = FA.quarterly.total[FA.quarterly.total.length - 1];
    var faC = FA.cumulative.total[FA.cumulative.total.length - 1];
    var tDev = dev(total);
    el('vi-kpis').innerHTML =
      kpiTile('K1', '农产品价格总指数', '<span class="' + (tDev >= 0 ? '' : 'neg') + '">' + total.toFixed(1) + '</span>', '',
        '较上年同期 ' + sgn(tDev) + '%') +
      kpiTile('K2', '上涨最高品类', '<span class="vi-up">' + best.v.toFixed(1) + '</span>', '',
        best.n + '（' + sgn(dev(best.v)) + '%）') +
      kpiTile('K3', '下跌最深品类', '<span class="vi-down">' + worst.v.toFixed(1) + '</span>', '',
        worst.n + '（' + sgn(dev(worst.v)) + '%）') +
      kpiTile('K4', '固投价格总指数', faQ.toFixed(1), '',
        '2019Q4 当季 · ' + sgn(dev(faQ)) + '%') +
      kpiTile('K5', '固投累计指数', faC.toFixed(1), '',
        '2019Q4 累计 · ' + sgn(dev(faC)) + '%');
  }
  function renderBrief() {
    var i = state.qi;
    var total = A.series.total[i];
    var items = RAW.agriCats.map(function (c) {
      var v = A.series[c[0]] ? A.series[c[0]][i] : null;
      return { n: c[0], v: v };
    }).filter(function (x) { return x.v !== null; })
      .sort(function (a, b) { return b.v - a.v; });
    var rising = items.filter(function (x) { return x.v >= 100; }).length;
    el('vi-detail').innerHTML =
      '<b>' + Q[i] + ' 速读</b>&nbsp;&nbsp;农产品生产者价格总指数 <b>' + total.toFixed(1) + '</b>' +
      '（较上年同期 <b>' + sgn(dev(total)) + '%</b>）；' + rising + ' 个品类同比上涨、' +
      (items.length - rising) + ' 个下降；' +
      '最高 <b>' + items[0].n + '（' + items[0].v.toFixed(1) + '）</b>，最低 ' +
      items[items.length - 1].n + '（' + items[items.length - 1].v.toFixed(1) + '）。' +
      '固定资产投资价格指数已停更于 2019Q4（当季 ' + FA.quarterly.total[FA.quarterly.total.length - 1].toFixed(1) + '）。';
  }

  /* ---------- 渲染 ---------- */
  function renderSlider() {
    var r = el('vi-range');
    r.value = state.qi;
    var p = state.qi / (N - 1) * 100;
    r.style.background = 'linear-gradient(to right,#e63312 0%,#e63312 ' + p + '%,#e5e5e5 ' + p + '%)';
  }
  function apply() {
    renderSlider();
    renderKpis();
    renderBrief();
    chTotal.setOption(optTotal(), true);
    chRank.setOption(optRank(), true);
    el('sub-rank').textContent = Q[state.qi] + ' 当季 · 红色 = 上涨 · 蓝色 = 下降';
    chMulti.setOption(optMulti(), true);
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
  el('vi-range').addEventListener('input', function () { setQuarter(+this.value, true); });

  window.addEventListener('resize', function () {
    Object.keys(charts).forEach(function (k) { charts[k].resize(); });
  });
  window.addEventListener('load', function () {
    Object.keys(charts).forEach(function (k) { charts[k].resize(); });
  });

  apply();
  chFa.setOption(optFa(), true);
  chFaRank.setOption(optFaRank(), true);
  chFaCum.setOption(optFaCum(), true);
  resetDetail();
})();
"""

# =====================================================================
# 四、校验与组装
# =====================================================================

def build_data(data):
    qs = data['agri']['quarters']
    i = len(qs) - 1
    total = data['agri']['series']['total']
    print('解析完成：农产品 %d 期（%s — %s）；固投当季 %d 期（%s — %s）。抽样核对：' % (
        len(qs), qs[0], qs[-1],
        len(data['fa']['quarterly']['quarters']),
        data['fa']['quarterly']['quarters'][0], data['fa']['quarterly']['quarters'][-1]))
    checks = [
        ('农产品总指数(2026Q3)', total[i], 97.9),
        ('农产品总指数(2026Q2)', total[i - 1], 97.0),
        ('玉米指数(2026Q3)', data['agri']['series']['玉米'][i], 103.3),
        ('蔬菜指数(2026Q3)', data['agri']['series']['蔬菜'][i], 97.1),
        ('固投当季(2019Q4)', data['fa']['quarterly']['total'][-1], 101.2),
        ('固投当季(2018Q4)', data['fa']['quarterly']['total'][4], 104.7),
        ('固投累计(2019Q4)', data['fa']['cumulative']['total'][-1], 102.6),
        ('固投累计(2018Q4)', data['fa']['cumulative']['total'][4], 105.4),
    ]
    ok = True
    for name, got, want in checks:
        match = abs(got - want) < 0.05
        ok = ok and match
        print('  %-18s 取值 %-10s 期望 %-10s %s' % (name, got, want, 'OK' if match else '!!'))
    if not ok:
        raise SystemExit('抽样校验未通过，请确认 CSV 为国家统计局原始导出文件。')

    # 供 JS 使用的分类清单（剔除缺报过多的品类）
    data['agriCats'] = [[s, p] for s, p in AGRI_CATS if s in data['agri']['series']]
    data['agriMain'] = [n for n in AGRI_MAIN if n in data['agri']['series']]
    data['faNewCats'] = [[s, p] for s, p in FA_NEW_CATS]
    return data


def main():
    no_open = '--no-open' in sys.argv
    print('正在扫描 %s 下的数据表 …' % DATA_DIR)
    data = load_data()
    data = build_data(data)

    echarts_tag = get_echarts_tag()
    data_json = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    fragment = (TEMPLATE
                .replace('/*__STYLE__*/', CSS)
                .replace('__ECHARTS__', echarts_tag)
                .replace('/*__DATA__*/', data_json)
                .replace('/*__APP__*/', APP))
    html = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>价值指数 · 季度数据大屏</title>\n</head>\n<body>\n'
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

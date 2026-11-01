# -*- coding: utf-8 -*-
'''人民生活 · 季度数据 BI 大屏生成器（Glassmorphism 玻璃拟态风）
================================================================

自包含的可视化项目：仅用 Python 标准库即可在本机（VS Code / PyCharm / 命令行）运行，
无需 pip 安装任何第三方包。风格：玻璃拟态 —— 浅色暖渐变底、磨砂半透明卡片、
柔和投影（风格选型依据见 ../风格库/README.md；用户偏好：不出现图签/制表信息元素）。

功能
----
1. 读取 data/ 目录下的 7 张国家统计局人民生活季度表（2025Q2—2026Q3，共 6 个季度）：
   · 全国 / 城镇 / 农村居民人均收入情况（可支配收入、中位数、四项收入，累计值口径）
   · 全国 / 城镇 / 农村居民人均支出情况（消费支出 + 八大类，累计值口径）
   · 外出务工情况（单季度数据，2025Q4 未发布）
2. 解析、校验并派生指标（恩格尔系数、城乡收入比、增长最快收入来源 / 消费大类等）；
3. 生成「玻璃拟态风」交互式 BI 大屏 HTML 并自动在浏览器中打开。

使用方法
--------
在本文件夹内打开终端，执行：
    python generate_bi_dashboard.py            # 生成大屏并自动打开浏览器
    python generate_bi_dashboard.py --no-open  # 只生成文件，不打开浏览器

首次运行会自动下载 ECharts 图表库并缓存为本文件夹下的 echarts.min.js（此后完全离线可用）。

输出：人民生活BI大屏.html（双击也可随时打开）。
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
OUTPUT_HTML = BASE / '人民生活BI大屏.html'

QMAP = {'一': 1, '二': 2, '三': 3, '四': 4}

# =====================================================================
# 一、数据解析
# =====================================================================

# 三个口径：文件名前缀 + 指标名前缀（全国表的指标不带"全国"前缀）
GROUPS = {
    '全国': {'file': '全国居民人均收入情况.csv', 'exp_file': '全国居民人均支出情况.csv', 'p': '居民'},
    '城镇': {'file': '城镇居民人均收入情况.csv', 'exp_file': '城镇居民人均支出情况.csv', 'p': '城镇居民'},
    '农村': {'file': '农村居民人均收入情况.csv', 'exp_file': '农村居民人均支出情况.csv', 'p': '农村居民'},
}

INC_CATS = ['工资性', '经营净', '财产净', '转移净']
EXP_CATS = ['食品烟酒', '衣着', '居住', '生活用品及服务', '交通通信', '教育文化娱乐', '医疗保健', '其他用品及服务']


def parse_file(fp):
    """解析单张表：返回 (季度列表[时间正序], {指标名(去空白): 数值列表})。"""
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
    if quarters is None:
        raise SystemExit('数据表格式异常（未找到表头季度行）：%s' % fp.name)
    quarters = list(reversed(quarters))            # 表头逆序 → 时间正序
    rows = {k: list(reversed(v)) for k, v in rows.items()}
    return quarters, rows


def load_data():
    if not DATA_DIR.exists():
        raise SystemExit('未找到数据目录：%s' % DATA_DIR)

    def grab(rows, prefix, label):
        key = next((k for k in rows if k.startswith(prefix)), None)
        if key is None:
            raise SystemExit('缺少指标：%s（%s）' % (prefix, label))
        return rows[key]

    groups = {}
    quarters = None
    for g, conf in GROUPS.items():
        p = conf['p']
        qs_i, rows_i = parse_file(DATA_DIR / conf['file'])
        qs_e, rows_e = parse_file(DATA_DIR / conf['exp_file'])
        if qs_i != qs_e:
            raise SystemExit('%s：收入表与支出表季度轴不一致' % g)
        if quarters is None:
            quarters = qs_i
        elif quarters != qs_i:
            raise SystemExit('%s：季度轴与全国不一致' % g)
        n = len(quarters)

        def check(vals, label):
            if len(vals) != n or any(v is None for v in vals):
                raise SystemExit('%s：%s 长度/缺失异常' % (g, label))

        income = {
            'inc': grab(rows_i, p + '人均可支配收入累计值', '可支配收入'),
            'incGrowth': grab(rows_i, p + '人均可支配收入累计增长', '可支配收入增长'),
            'median': grab(rows_i, p + '人均可支配收入中位数累计值', '收入中位数'),
            'incGrowthMedian': grab(rows_i, p + '人均可支配收入中位数累计增长', '中位数增长'),
        }
        for c in INC_CATS:
            income['inc_' + c] = grab(rows_i, p + '人均可支配' + c + '收入累计值', c + '收入')
            income['incG_' + c] = grab(rows_i, p + '人均可支配' + c + '收入累计增长', c + '收入增长')
        expenditure = {
            'exp': grab(rows_e, p + '人均消费支出累计值', '消费支出'),
            'expGrowth': grab(rows_e, p + '人均消费支出累计增长', '消费支出增长'),
        }
        for c in EXP_CATS:
            expenditure['cat_' + c] = grab(rows_e, p + '人均' + c + '支出累计值', c + '支出')
            expenditure['catG_' + c] = grab(rows_e, p + '人均' + c + '支出累计增长', c + '支出增长')
        for d in (income, expenditure):
            for k, v in d.items():
                check(v, k)
        groups[g] = {'income': income, 'expenditure': expenditure}

    # 外出务工（单季度数据；2025Q4 未发布，季度轴与主轴不同属正常）
    qs_l, rows_l = parse_file(DATA_DIR / '外出务工情况.csv')
    labor = {
        'quarters': qs_l,
        'workers': grab(rows_l, '农村外出务工劳动力', '务工劳动力'),
        'wage': grab(rows_l, '外出务工农村劳动力月均收入', '务工月均收入'),
    }
    return quarters, groups, labor


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
# 三、页面资源：玻璃拟态样式 / 模板 / 交互脚本
# =====================================================================

# pylint: disable=line-too-long
CSS = r"""
#rm-dashboard-root {
  --ink: #2a3555; --gray: #5c6b8a; --faint: rgba(42,53,85,0.5);
  --blue: #4f7cff; --purple: #a06bff; --pink: #ff7eb3; --teal: #33c9b0; --gold: #ffb648;
  --line: rgba(255,255,255,0.75);
  position: relative;
  color: var(--ink);
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  font-size: 14px; line-height: 1.5;
  padding: 20px 22px 14px; border-radius: 24px; min-width: 0;
  border: 1px solid rgba(255,255,255,0.9);
  background:
    radial-gradient(900px 420px at 8% 0%, rgba(255,126,179,0.16), transparent 60%),
    radial-gradient(1000px 460px at 92% 4%, rgba(79,124,255,0.16), transparent 60%),
    radial-gradient(900px 480px at 50% 112%, rgba(160,107,255,0.14), transparent 62%),
    linear-gradient(135deg, #dcecfe 0%, #ece4fb 45%, #ffe9f2 100%);
}
#rm-dashboard-root * { box-sizing: border-box; }
.gm-card { background: rgba(255,255,255,0.55); backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  border: 1px solid var(--line); border-radius: 20px; box-shadow: 0 8px 32px rgba(80,100,180,0.10); }

/* ---------- 头部 ---------- */
.rm-header { display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 14px; }
.rm-brand { display: flex; align-items: center; gap: 13px; min-width: 0; }
.rm-mark { width: 46px; height: 46px; border-radius: 15px; flex: 0 0 auto;
  background: rgba(255,255,255,0.6); border: 1px solid var(--line);
  display: flex; align-items: center; justify-content: center; color: var(--blue);
  box-shadow: 0 4px 16px rgba(79,124,255,0.18); }
.rm-brand h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 1px; white-space: nowrap; }
.rm-brand p { margin: 2px 0 0; font-size: 12px; color: var(--gray); }
.rm-seg { display: flex; background: rgba(255,255,255,0.55); border: 1px solid var(--line);
  border-radius: 12px; padding: 3px; backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); }
.rm-seg button { border: 0; background: transparent; padding: 6px 18px; border-radius: 10px;
  font-size: 13px; color: var(--gray); cursor: pointer; font-family: inherit; font-weight: 600; }
.rm-seg button.on { background: linear-gradient(135deg, #4f7cff, #a06bff); color: #fff;
  box-shadow: 0 4px 14px rgba(79,124,255,0.35); }

/* ---------- 时间轴 ---------- */
.rm-timeline { padding: 12px 18px 24px; display: flex; align-items: center; gap: 12px;
  position: relative; margin-bottom: 14px; }
.rm-tl-label { font-size: 12.5px; font-weight: 600; color: var(--gray); flex: 0 0 auto; }
.rm-arrow { width: 26px; height: 26px; border-radius: 50%; border: 1px solid var(--line);
  background: rgba(255,255,255,0.6); color: var(--gray); cursor: pointer; flex: 0 0 auto; font-size: 13px;
  line-height: 1; display: flex; align-items: center; justify-content: center; padding: 0; font-family: inherit; }
.rm-arrow:hover { border-color: var(--blue); color: var(--blue); }
#rm-range { flex: 1; -webkit-appearance: none; appearance: none; height: 6px; border-radius: 3px;
  background: rgba(255,255,255,0.75); outline: none; cursor: pointer; min-width: 120px; }
#rm-range::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 17px; height: 17px;
  border-radius: 50%; background: linear-gradient(135deg, #4f7cff, #a06bff); border: 2.5px solid #fff;
  box-shadow: 0 2px 10px rgba(79,124,255,0.45); cursor: grab; }
#rm-range::-moz-range-thumb { width: 13px; height: 13px; border-radius: 50%;
  background: linear-gradient(135deg, #4f7cff, #a06bff); border: 2.5px solid #fff; cursor: grab; }
.rm-btn { border: 1px solid var(--line); background: rgba(255,255,255,0.6); color: var(--ink);
  border-radius: 999px; padding: 5px 15px; font-size: 12.5px; cursor: pointer; font-family: inherit; font-weight: 600; }
.rm-btn:hover { border-color: var(--blue); color: var(--blue); }
.rm-btn.primary { background: linear-gradient(135deg, #4f7cff, #a06bff); color: #fff;
  border: none; box-shadow: 0 4px 14px rgba(79,124,255,0.35); }
.rm-years { position: absolute; left: 96px; right: 330px; bottom: 4px; height: 15px; pointer-events: none; }
.rm-years span { position: absolute; transform: translateX(-50%); font-size: 10.5px; color: var(--faint); }
.rm-hint { font-size: 11.5px; color: var(--faint); flex: 0 0 auto; max-width: 250px; text-align: right; line-height: 1.45; }

/* ---------- 详情钉住栏 ---------- */
.rm-detail { padding: 10px 18px; font-size: 13px; line-height: 1.7; margin-bottom: 14px;
  color: #3a4666; min-height: 42px; }
.rm-detail b { color: var(--blue); font-weight: 700; }

/* ---------- KPI ---------- */
.rm-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; margin-bottom: 14px; }
.rm-kpi { padding: 14px 16px 12px; min-width: 0; position: relative; overflow: hidden; }
.rm-kpi .dot { width: 30px; height: 30px; border-radius: 10px; margin-bottom: 10px;
  background: linear-gradient(135deg, var(--ac, var(--blue)), rgba(160,107,255,0.55)); opacity: 0.8; }
.rm-kpi-top { font-size: 12px; color: var(--gray); font-weight: 600; }
.rm-kpi-val { font-size: 26px; font-weight: 800; margin: 2px 0 3px; white-space: nowrap; color: #22315c;
  font-variant-numeric: tabular-nums; letter-spacing: -0.3px; }
.rm-kpi-val small { font-size: 12.5px; color: var(--gray); margin-left: 3px; font-weight: 600; }
.rm-kpi-sub { font-size: 11.5px; color: var(--gray); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rm-up { color: #1ea97c; font-weight: 700; }
.rm-down { color: #e5588a; font-weight: 700; }

/* ---------- 图表网格 ---------- */
.rm-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
.rm-s4 { grid-column: span 4; } .rm-s6 { grid-column: span 6; }
.rm-card { padding: 16px 18px 8px; min-width: 0; }
.rm-card-h { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.rm-card-h h3 { font-size: 15px; font-weight: 700; margin: 0; color: #22315c; }
.rm-hint-r { font-size: 11.5px; color: var(--faint); }
.rm-sub { font-size: 12px; color: var(--gray); margin: 3px 0 2px; }
.rm-chart { width: 100%; height: 300px; }
.rm-foot { font-size: 11.5px; color: var(--faint); margin-top: 14px; line-height: 1.7; }

@media (prefers-reduced-motion: reduce) {
  #rm-dashboard-root *, #rm-dashboard-root *::before { animation: none !important; transition: none !important; }
}
@media (max-width: 1280px) {
  .rm-s4, .rm-s6 { grid-column: span 12; }
  .rm-kpis { grid-template-columns: repeat(3, 1fr); }
  .rm-years { display: none; }
}
@media (max-width: 720px) {
  .rm-kpis { grid-template-columns: 1fr; }
  #rm-dashboard-root { padding: 14px; }
}
"""

TEMPLATE = """
<style>
/*__STYLE__*/
</style>

<div id="rm-dashboard-root">
  <div class="rm-header">
    <div class="rm-brand">
      <div class="rm-mark" aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 10.5L12 3l9 7.5" /><path d="M5.5 9.5V20h13V9.5" /><path d="M10 20v-5.5h4V20" />
        </svg>
      </div>
      <div>
        <h1>人民生活季度数据大屏</h1>
        <p>居民人均收入 / 消费支出 / 恩格尔系数 / 城乡对比 / 外出务工 &nbsp;|&nbsp; 数据来源：国家统计局「季度数据」</p>
      </div>
    </div>
    <div class="rm-seg" role="group" aria-label="统计口径">
      <button type="button" class="on" data-g="全国">全国</button>
      <button type="button" data-g="城镇">城镇</button>
      <button type="button" data-g="农村">农村</button>
    </div>
  </div>

  <div class="gm-card rm-timeline">
    <span class="rm-tl-label">季度</span>
    <button type="button" class="rm-arrow" id="btn-prev" aria-label="上一季度">‹</button>
    <input type="range" id="rm-range" min="0" max="5" step="1" value="5" aria-label="选择季度" />
    <button type="button" class="rm-arrow" id="btn-next" aria-label="下一季度">›</button>
    <button type="button" class="rm-btn primary" id="btn-play">播放</button>
    <button type="button" class="rm-btn" id="btn-reset">重置</button>
    <span class="rm-hint">拖动时间轴或点击图 01/02 中的柱线即可联动全部图表 · 点击数据点钉住详情</span>
    <div class="rm-years" aria-hidden="true">
      <span style="left:0%">2025Q2</span><span style="left:20%">2025Q3</span><span style="left:40%">2025Q4</span><span style="left:60%">2026Q1</span><span style="left:80%">2026Q2</span><span style="left:100%">2026Q3</span>
    </div>
  </div>

  <div class="gm-card rm-detail" id="rm-detail" aria-live="polite"></div>

  <div class="rm-kpis" id="rm-kpis"></div>

  <div class="rm-grid">
    <div class="gm-card rm-card rm-s6">
      <div class="rm-card-h"><h3>01 人均可支配收入走势（累计）</h3><span class="rm-hint-r">点击柱体切换季度</span></div>
      <div class="rm-sub" id="sub-inc">当前口径 · 柱：可支配收入累计值（元）· 线：累计增长（%）</div>
      <div class="rm-chart" id="ch-inc"></div>
    </div>
    <div class="gm-card rm-card rm-s6">
      <div class="rm-card-h"><h3>02 收入构成（四项收入，累计）</h3><span class="rm-hint-r">堆积柱状图</span></div>
      <div class="rm-sub">工资性 / 经营净 / 财产净 / 转移净收入（元）</div>
      <div class="rm-chart" id="ch-comp"></div>
    </div>
    <div class="gm-card rm-card rm-s6">
      <div class="rm-card-h"><h3>03 消费支出八大类结构（累计）</h3><span class="rm-hint-r">堆积柱状图</span></div>
      <div class="rm-sub">八大类人均支出（元），柱顶为消费支出合计</div>
      <div class="rm-chart" id="ch-exp"></div>
    </div>
    <div class="gm-card rm-card rm-s6">
      <div class="rm-card-h"><h3>04 支出占比环形（最新季度）</h3><span class="rm-hint-r">中心为恩格尔系数</span></div>
      <div class="rm-sub" id="sub-donut">当前口径 · 八大类占消费支出比重（%）</div>
      <div class="rm-chart" id="ch-donut"></div>
    </div>
    <div class="gm-card rm-card rm-s6">
      <div class="rm-card-h"><h3>05 城乡收入对比（累计）</h3><span class="rm-hint-r">右轴为城乡收入比</span></div>
      <div class="rm-sub">全国 / 城镇 / 农村人均可支配收入（元）· 城乡收入比 = 城镇 ÷ 农村</div>
      <div class="rm-chart" id="ch-urban"></div>
    </div>
    <div class="gm-card rm-card rm-s6">
      <div class="rm-card-h"><h3>06 城乡八大类支出雷达（最新季度）</h3><span class="rm-hint-r">单位：元</span></div>
      <div class="rm-sub">城镇 vs 农村，直观对比各类别绝对水平</div>
      <div class="rm-chart" id="ch-radar"></div>
    </div>
    <div class="gm-card rm-card rm-s6">
      <div class="rm-card-h"><h3>07 外出务工（单季度）</h3><span class="rm-hint-r">2025Q4 未发布</span></div>
      <div class="rm-sub">柱：外出务工劳动力（万人）· 线：月均收入（元）</div>
      <div class="rm-chart" id="ch-labor"></div>
    </div>
    <div class="gm-card rm-card rm-s6">
      <div class="rm-card-h"><h3>08 恩格尔系数与消费增速（累计）</h3><span class="rm-hint-r">全国口径</span></div>
      <div class="rm-sub">线：恩格尔系数 = 食品烟酒 ÷ 消费支出（%）· 柱：消费支出累计增长（%）</div>
      <div class="rm-chart" id="ch-engel"></div>
    </div>
  </div>

  <div class="rm-foot">
    数据来源：国家统计局「数据库 — 季度数据」（2025Q2—2026Q3 共 6 个季度）。
    收入与消费支出均为**人均累计值**口径；人均可支配收入增速为扣除价格因素的**实际增速**，其余增速为名义增速（均由统计局发布）。
    恩格尔系数 = 食品烟酒支出 ÷ 消费支出；城乡收入比 = 城镇 ÷ 农村。外出务工为单季度数据（2025Q4 未发布）。
  </div>
</div>

__ECHARTS__

<script>
window.RM_DATA = /*__DATA__*/;
</script>

<script>
/*__APP__*/
</script>
"""

APP = r"""
(function () {
  'use strict';
  var root = document.getElementById('rm-dashboard-root');
  if (!root) return;
  if (typeof echarts === 'undefined') {
    root.innerHTML = '<div style="padding:60px 20px;text-align:center;color:#5c6b8a;font-size:14px;">ECharts 加载失败：请联网后刷新（首次运行脚本会自动下载并内联图表库）。</div>';
    return;
  }
  var RAW = window.RM_DATA;
  var Q = RAW.quarters, N = Q.length, G = RAW.groups, LABOR = RAW.labor;
  var INC_CATS = ['工资性', '经营净', '财产净', '转移净'];
  var EXP_CATS = ['食品烟酒', '衣着', '居住', '生活用品及服务', '交通通信', '教育文化娱乐', '医疗保健', '其他用品及服务'];
  var state = { qi: N - 1, group: '全国', playing: false, timer: null };

  var C = {
    blue: '#4f7cff', purple: '#a06bff', pink: '#ff7eb3', teal: '#33c9b0', gold: '#ffb648', indigo: '#6b8cff',
    axis: 'rgba(60,80,140,0.55)', axisLine: 'rgba(60,80,140,0.25)', split: 'rgba(60,80,140,0.10)',
    text: '#2a3555', muted: 'rgba(42,53,85,0.62)', faint: 'rgba(42,53,85,0.4)',
    tipBg: 'rgba(255,255,255,0.92)', tipBorder: 'rgba(255,255,255,0.95)'
  };
  var PALETTE = [C.blue, C.purple, C.pink, C.teal, C.gold, C.indigo];
  var TIP = {
    backgroundColor: C.tipBg, borderColor: C.tipBorder, borderWidth: 1,
    padding: [10, 14], textStyle: { color: '#2a3555', fontSize: 12.5 },
    extraCssText: 'box-shadow:0 12px 32px rgba(80,100,180,0.18);border-radius:14px;'
  };
  function tipTitle(q) { return '<div style="font-weight:700;font-size:13px;margin-bottom:4px;">' + q + '</div>'; }
  function tipRow(k, v, color) {
    return '<div style="display:flex;justify-content:space-between;gap:22px;line-height:1.9;">' +
      '<span style="opacity:.65;">' + k + '</span>' +
      '<span style="font-weight:600;' + (color ? 'color:' + color : '') + '">' + v + '</span></div>';
  }
  function el(id) { return document.getElementById(id); }
  function sgn(v) { return (v > 0 ? '+' : '') + v.toFixed(1); }
  function fmtYuan(v) { return Math.round(v).toLocaleString('en-US'); }
  function wanYuan(v) { return (v / 10000).toFixed(2); }
  function cls(v) { return v >= 0 ? 'rm-up' : 'rm-down'; }
  function gsel() { return G[state.group]; }

  var charts = {};
  function mk(id) { var c = echarts.init(el(id)); charts[id] = c; return c; }
  var chInc = mk('ch-inc'), chComp = mk('ch-comp'), chExp = mk('ch-exp'), chDonut = mk('ch-donut'),
      chUrban = mk('ch-urban'), chRadar = mk('ch-radar'), chLabor = mk('ch-labor'), chEngel = mk('ch-engel');
  var ALL = [chInc, chComp, chExp, chDonut, chUrban, chRadar, chLabor, chEngel];

  /* ---------- 图 01：收入走势（口径联动） ---------- */
  function optInc() {
    var d = gsel().income;
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 12, textStyle: { fontSize: 11, color: C.gray } },
      grid: { left: 56, right: 44, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('人均可支配收入', fmtYuan(d.inc[i]) + ' 元', C.blue) +
            tipRow('收入中位数', fmtYuan(d.median[i]) + ' 元', C.purple) +
            tipRow('累计增长', sgn(d.incGrowth[i]) + '%', C.teal);
        }
      }),
      xAxis: { type: 'category', data: Q,
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: [
        { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
        { type: 'value', position: 'right', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { show: false } }
      ],
      series: [
        { name: '可支配收入', type: 'bar', data: d.inc, barWidth: '46%',
          itemStyle: { borderRadius: [8, 8, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(79,124,255,0.9)' }, { offset: 1, color: 'rgba(160,107,255,0.35)' }]) } },
        { name: '累计增长', type: 'line', yAxisIndex: 1, data: d.incGrowth, symbol: 'circle', symbolSize: 7, z: 6,
          lineStyle: { width: 3, color: C.teal }, itemStyle: { color: C.teal } }
      ]
    };
  }

  /* ---------- 图 02：收入构成堆积（口径联动） ---------- */
  function optComp() {
    var d = gsel().income;
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.blue, C.purple, C.pink, C.teal],
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 10, textStyle: { fontSize: 11, color: C.gray } },
      grid: { left: 56, right: 18, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          var total = d.inc[i];
          var html = tipTitle(Q[i]);
          INC_CATS.forEach(function (c) {
            var v = d['inc_' + c][i];
            html += tipRow(c + '收入', fmtYuan(v) + ' 元 (' + (v / total * 100).toFixed(1) + '%)');
          });
          return html;
        }
      }),
      xAxis: { type: 'category', data: Q,
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      series: INC_CATS.map(function (c) {
        return { name: c + '收入', type: 'bar', stack: 'inc', data: d['inc_' + c], barWidth: '46%',
          itemStyle: { borderRadius: c === INC_CATS[INC_CATS.length - 1] ? [7, 7, 0, 0] : 0 } };
      })
    };
  }

  /* ---------- 图 03：支出八大类堆积（口径联动） ---------- */
  function optExp() {
    var d = gsel().expenditure;
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.blue, C.teal, C.purple, C.gold, C.pink, C.indigo, '#8fa8ff', C.orange],
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 8, textStyle: { fontSize: 10.5, color: C.gray } },
      grid: { left: 56, right: 18, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          var total = d.exp[i];
          var html = tipTitle(Q[i]) + tipRow('消费支出合计', fmtYuan(total) + ' 元', C.blue);
          EXP_CATS.forEach(function (c) {
            var v = d['cat_' + c][i];
            html += tipRow(c, fmtYuan(v) + ' 元 (' + (v / total * 100).toFixed(1) + '%)');
          });
          return html;
        }
      }),
      xAxis: { type: 'category', data: Q,
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
      series: EXP_CATS.map(function (c, idx) {
        return { name: c, type: 'bar', stack: 'exp', data: d['cat_' + c], barWidth: '46%',
          itemStyle: { borderRadius: idx === EXP_CATS.length - 1 ? [7, 7, 0, 0] : 0 } };
      })
    };
  }

  /* ---------- 图 04：支出占比环形（口径联动） ---------- */
  function optDonut() {
    var d = gsel().expenditure;
    var i = state.qi;
    var engel = d['cat_食品烟酒'][i] / d.exp[i] * 100;
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.blue, C.teal, C.purple, C.gold, C.pink, C.indigo, '#8fa8ff', C.orange],
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var v = d['cat_' + EXP_CATS[p.dataIndex]][i];
          var g = d['catG_' + EXP_CATS[p.dataIndex]][i];
          return tipTitle(p.name) +
            tipRow('人均支出', fmtYuan(v) + ' 元', C.blue) +
            tipRow('占比', p.percent.toFixed(1) + '%') +
            tipRow('累计增长', sgn(g) + '%', g >= 0 ? '#1ea97c' : '#e5588a');
        }
      }),
      series: [{
        name: '支出占比', type: 'pie', radius: ['46%', '70%'], center: ['50%', '46%'],
        data: EXP_CATS.map(function (c) { return { name: c, value: d['cat_' + c][i] }; }),
        itemStyle: { borderColor: 'rgba(255,255,255,0.95)', borderWidth: 2.5, borderRadius: 5 },
        label: { color: C.muted, fontSize: 10.5, formatter: '{b}\n{d}%' },
        labelLine: { length: 8, length2: 8, lineStyle: { color: 'rgba(60,80,140,0.35)' } }
      },
      { name: '恩格尔系数', type: 'pie', silent: true, radius: [0, 0], data: [{ value: 0 }],
        label: { show: true, position: 'center', formatter: function () {
          return '{a|恩格尔系数}\n{b|' + engel.toFixed(1) + '%}';
        }, rich: {
          a: { color: C.gray, fontSize: 11, lineHeight: 20 },
          b: { color: C.blue, fontSize: 21, fontWeight: 700, lineHeight: 28 }
        } }
      }]
    };
  }

  /* ---------- 图 05：城乡收入对比（固定三口径） ---------- */
  function optUrban() {
    function r1(v) { return Math.round(v * 10) / 10; }
    var ratio = G['城镇'].income.inc.map(function (v, i) { return r1(v / G['农村'].income.inc[i]); });
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 8, itemGap: 10, textStyle: { fontSize: 11, color: C.gray } },
      grid: { left: 60, right: 52, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'line' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('城镇居民', fmtYuan(G['城镇'].income.inc[i]) + ' 元', C.blue) +
            tipRow('全国居民', fmtYuan(G['全国'].income.inc[i]) + ' 元', C.purple) +
            tipRow('农村居民', fmtYuan(G['农村'].income.inc[i]) + ' 元', C.teal) +
            tipRow('城乡收入比', ratio[i].toFixed(2) + ' 倍', C.pink);
        }
      }),
      xAxis: { type: 'category', data: Q,
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: [
        { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
        { type: 'value', position: 'right', min: 2, max: 3, axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { show: false } }
      ],
      series: [
        { name: '城镇居民', type: 'line', data: G['城镇'].income.inc, symbol: 'circle', symbolSize: 6.5,
          lineStyle: { width: 3, color: C.blue }, itemStyle: { color: C.blue } },
        { name: '全国居民', type: 'line', data: G['全国'].income.inc, symbol: 'circle', symbolSize: 6,
          lineStyle: { width: 2, color: C.purple, type: 'dashed' }, itemStyle: { color: C.purple } },
        { name: '农村居民', type: 'line', data: G['农村'].income.inc, symbol: 'circle', symbolSize: 6,
          lineStyle: { width: 2, color: C.teal, type: 'dashed' }, itemStyle: { color: C.teal } },
        { name: '城乡收入比', type: 'line', yAxisIndex: 1, data: ratio, symbol: 'diamond', symbolSize: 7, z: 6,
          lineStyle: { width: 2, color: C.pink }, itemStyle: { color: C.pink } }
      ]
    };
  }

  /* ---------- 图 06：城乡八大类雷达（固定） ---------- */
  function optRadar() {
    var latest = N - 1;
    var maxv = 0;
    EXP_CATS.forEach(function (c) {
      maxv = Math.max(maxv, G['城镇'].expenditure['cat_' + c][latest], G['农村'].expenditure['cat_' + c][latest]);
    });
    return {
      animation: true, animationDuration: 0,
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 8, itemGap: 10, textStyle: { fontSize: 11, color: C.gray } },
      radar: {
        indicator: EXP_CATS.map(function (c) { return { name: c, max: maxv * 1.1 }; }),
        radius: '64%', center: ['50%', '52%'],
        axisName: { color: C.muted, fontSize: 10.5 },
        splitLine: { lineStyle: { color: C.split } },
        splitArea: { areaStyle: { color: ['rgba(255,255,255,0.25)', 'rgba(255,255,255,0.45)'] } },
        axisLine: { lineStyle: { color: C.axisLine } }
      },
      series: [{
        name: '支出对比', type: 'radar',
        data: [
          { name: '城镇居民', value: EXP_CATS.map(function (c) { return G['城镇'].expenditure['cat_' + c][latest]; }),
            lineStyle: { width: 2.5, color: C.blue }, itemStyle: { color: C.blue },
            areaStyle: { color: 'rgba(79,124,255,0.14)' } },
          { name: '农村居民', value: EXP_CATS.map(function (c) { return G['农村'].expenditure['cat_' + c][latest]; }),
            lineStyle: { width: 2.5, color: C.pink }, itemStyle: { color: C.pink },
            areaStyle: { color: 'rgba(255,126,179,0.14)' } }
        ]
      }]
    };
  }

  /* ---------- 图 07：外出务工（固定） ---------- */
  function optLabor() {
    return {
      animation: true, animationDuration: 0,
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 10, textStyle: { fontSize: 11, color: C.gray } },
      grid: { left: 50, right: 52, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(LABOR.quarters[i] + '（单季度）') +
            tipRow('外出务工劳动力', fmtYuan(LABOR.workers[i]) + ' 万人', C.purple) +
            tipRow('月均收入', fmtYuan(LABOR.wage[i]) + ' 元', C.teal);
        }
      }),
      xAxis: { type: 'category', data: LABOR.quarters.map(function (q) { return q.slice(2); }),
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: [
        { type: 'value', axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
        { type: 'value', position: 'right', min: function (v) { return v.min * 0.97; }, max: function (v) { return v.max * 1.03; },
          axisLabel: { color: C.axis, fontSize: 10.5 }, splitLine: { show: false } }
      ],
      series: [
        { name: '务工劳动力', type: 'bar', data: LABOR.workers, barWidth: '46%',
          itemStyle: { borderRadius: [8, 8, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(160,107,255,0.9)' }, { offset: 1, color: 'rgba(255,126,179,0.35)' }]) } },
        { name: '月均收入', type: 'line', yAxisIndex: 1, data: LABOR.wage, symbol: 'circle', symbolSize: 7, z: 6,
          lineStyle: { width: 3, color: C.teal }, itemStyle: { color: C.teal } }
      ]
    };
  }

  /* ---------- 图 08：恩格尔系数与消费增速（全国口径） ---------- */
  function optEngel() {
    var d = G['全国'].expenditure;
    var engel = d.exp.map(function (v, i) { return r1(d['cat_食品烟酒'][i] / v * 100); });
    function r1(v) { return Math.round(v * 10) / 10; }
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      legend: { top: 0, right: 4, itemWidth: 12, itemHeight: 8, itemGap: 12, textStyle: { fontSize: 11, color: C.gray } },
      grid: { left: 46, right: 46, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('恩格尔系数', engel[i].toFixed(1) + '%', C.gold) +
            tipRow('消费支出累计增长', sgn(d.expGrowth[i]) + '%', C.blue) +
            tipRow('人均消费支出', fmtYuan(d.exp[i]) + ' 元');
        }
      }),
      xAxis: { type: 'category', data: Q,
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.axis, fontSize: 10.5 } },
      yAxis: [
        { type: 'value', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } },
        { type: 'value', position: 'right', axisLabel: { formatter: '{value}%', color: C.axis, fontSize: 10.5 }, splitLine: { show: false } }
      ],
      series: [
        { name: '消费支出累计增长', type: 'bar', data: d.expGrowth, barWidth: '44%',
          itemStyle: { borderRadius: [8, 8, 0, 0], color: 'rgba(79,124,255,0.75)' } },
        { name: '恩格尔系数', type: 'line', yAxisIndex: 1, data: engel, symbol: 'circle', symbolSize: 7, z: 6,
          lineStyle: { width: 3, color: C.gold, shadowColor: C.gold, shadowBlur: 6 }, itemStyle: { color: C.gold } }
      ]
    };
  }

  /* ---------- 详情钉住 ---------- */
  function pinDetail(html) { el('rm-detail').innerHTML = html; }
  var DEFAULT_HINT = '<b>使用提示</b>&nbsp;&nbsp;顶部可切换全国 / 城镇 / 农村口径（联动 KPI 与图 01—04）；拖动时间轴或点击图 01/03 中的柱线即可联动全部图表，点击数据点钉住详情。';
  function resetDetail() { el('rm-detail').innerHTML = DEFAULT_HINT; }

  chInc.on('click', function (p) {
    if (typeof p.dataIndex !== 'number') return;
    setQuarter(p.dataIndex, true);
    if (p.seriesName === '累计增长') {
      var d = gsel().income;
      pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · ' + state.group + '居民收入累计增长') + '<b>' + sgn(d.incGrowth[p.dataIndex]) + '%</b>');
    }
  });
  chExp.on('click', function (p) {
    if (typeof p.dataIndex !== 'number') return;
    setQuarter(p.dataIndex, true);
    var d = gsel().expenditure;
    pinDetail(tipTitle('📌 ' + Q[p.dataIndex] + ' · ' + state.group + '居民消费支出八大类') +
      '<b>' + p.seriesName + '</b>&nbsp;&nbsp;' + fmtYuan(d['cat_' + p.seriesName][p.dataIndex]) + ' 元' +
      '&nbsp;&nbsp;累计增长 <b>' + sgn(d['catG_' + p.seriesName][p.dataIndex]) + '%</b>');
  });

  /* ---------- KPI 与速读 ---------- */
  function kpiCard(ac, title, val, unit, sub) {
    return '<div class="gm-card rm-kpi" style="--ac:' + ac + '"><div class="dot"></div>' +
      '<div class="rm-kpi-top">' + title + '</div>' +
      '<div class="rm-kpi-val">' + val + '<small>' + unit + '</small></div>' +
      '<div class="rm-kpi-sub">' + sub + '</div></div>';
  }
  function renderKpis() {
    var i = state.qi;
    var d = gsel();
    var bestInc = null, worstInc = null;
    INC_CATS.forEach(function (c) {
      var g = d.income['incG_' + c][i];
      if (!bestInc || g > bestInc.g) bestInc = { n: c + '收入', g: g };
      if (!worstInc || g < worstInc.g) worstInc = { n: c + '收入', g: g };
    });
    var bestExp = null, worstExp = null;
    EXP_CATS.forEach(function (c) {
      var g = d.expenditure['catG_' + c][i];
      if (!bestExp || g > bestExp.g) bestExp = { n: c, g: g };
      if (!worstExp || g < worstExp.g) worstExp = { n: c, g: g };
    });
    var engel = d.expenditure['cat_食品烟酒'][i] / d.expenditure.exp[i] * 100;
    el('rm-kpis').innerHTML =
      kpiCard(C.blue, '人均可支配收入', wanYuan(d.income.inc[i]), '万元',
        '累计增长 <span class="' + cls(d.income.incGrowth[i]) + '">' + sgn(d.income.incGrowth[i]) + '%</span>') +
      kpiCard(C.purple, '收入中位数', fmtYuan(d.income.median[i]), '元',
        '累计增长 <span class="' + cls(d.income.incGrowthMedian[i]) + '">' + sgn(d.income.incGrowthMedian[i]) + '%</span>') +
      kpiCard(C.pink, '人均消费支出', fmtYuan(d.expenditure.exp[i]), '元',
        '累计增长 <span class="' + cls(d.expenditure.expGrowth[i]) + '">' + sgn(d.expenditure.expGrowth[i]) + '%</span>') +
      kpiCard(C.gold, '恩格尔系数', engel.toFixed(1), '%',
        '食品烟酒 ÷ 消费支出') +
      kpiCard(C.teal, '增长最快收入', sgn(bestInc.g), '%',
        '<span class="rm-up">' + bestInc.n + '</span>') +
      kpiCard(C.indigo, '增长最快支出', sgn(bestExp.g), '%',
        '<span class="rm-up">' + bestExp.n + '</span>' +
        (worstExp.n !== bestExp.n ? ' · 最慢 <span class="rm-down">' + worstExp.n + '</span>' : ''));
  }
  function renderBrief() {
    var i = state.qi;
    var d = G[state.group];
    var engel = d.expenditure['cat_食品烟酒'][i] / d.expenditure.exp[i] * 100;
    var sorted = EXP_CATS.map(function (c) { return { n: c, g: d.expenditure['catG_' + c][i] }; })
      .sort(function (a, b) { return b.g - a.g; });
    var ratio = r1(G['城镇'].income.inc[i] / G['农村'].income.inc[i]);
    function r1(v) { return Math.round(v * 10) / 10; }
    function sortedInc() {
      var arr = INC_CATS.map(function (c) { return { n: c, g: d.income['incG_' + c][i] }; })
        .sort(function (a, b) { return b.g - a.g; });
      return arr[0].n + '（' + sgn(arr[0].g) + '%）';
    }
    el('rm-detail').innerHTML =
      '<b>' + Q[i] + ' 速读（' + state.group + '口径）</b>&nbsp;&nbsp;人均可支配收入累计 <b>' +
      wanYuan(d.income.inc[i]) + ' 万元</b>（' + sgn(d.income.incGrowth[i]) + '%），' +
      '人均消费支出 <b>' + fmtYuan(d.expenditure.exp[i]) + ' 元</b>（' + sgn(d.expenditure.expGrowth[i]) + '%），' +
      '恩格尔系数 <b>' + engel.toFixed(1) + '%</b>；' +
      '增长最快收入来源 <b>' + sortedInc() + '</b>，增长最快支出大类 <b>' + sorted[0].n + '（' + sgn(sorted[0].g) + '%）</b>；' +
      '城乡收入比 <b>' + ratio.toFixed(2) + ' 倍</b>（城镇 ' + fmtYuan(G['城镇'].income.inc[i]) + ' 元 / 农村 ' + fmtYuan(G['农村'].income.inc[i]) + ' 元）。';
  }

  /* ---------- 渲染 ---------- */
  function renderSlider() {
    var r = el('rm-range');
    r.value = state.qi;
    var p = state.qi / (N - 1) * 100;
    r.style.background = 'linear-gradient(to right,#4f7cff 0%,#a06bff ' + p + '%,rgba(255,255,255,0.8) ' + p + '%)';
  }
  function apply() {
    renderSlider();
    renderKpis();
    renderBrief();
    chInc.setOption(optInc(), true);
    el('sub-inc').textContent = '当前口径：' + state.group + '居民 · 柱：可支配收入累计值（元）· 线：累计增长（%）';
    chComp.setOption(optComp(), true);
    chExp.setOption(optExp(), true);
    chDonut.setOption(optDonut(), true);
    el('sub-donut').textContent = '当前口径：' + state.group + '居民 · ' + Q[state.qi] + ' 八大类占消费支出比重（%）';
  }
  function applyFixed() {
    chUrban.setOption(optUrban(), true);
    chRadar.setOption(optRadar(), true);
    chLabor.setOption(optLabor(), true);
    chEngel.setOption(optEngel(), true);
  }
  function setQuarter(i, fromUser) {
    state.qi = Math.max(0, Math.min(N - 1, i));
    apply();
    resetDetail();
  }
  function setGroup(g) {
    state.group = g;
    document.querySelectorAll('.rm-seg button').forEach(function (b) {
      b.className = b.getAttribute('data-g') === g ? 'on' : '';
    });
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
    state.timer = setInterval(function () { setQuarter((state.qi + 1) % N); }, 1400);
  }
  el('btn-play').addEventListener('click', togglePlay);
  el('btn-reset').addEventListener('click', function () {
    stopPlay(); state.qi = N - 1; state.group = '全国'; setGroup('全国');
  });
  el('btn-prev').addEventListener('click', function () { setQuarter(state.qi - 1, true); });
  el('btn-next').addEventListener('click', function () { setQuarter(state.qi + 1, true); });
  el('rm-range').addEventListener('input', function () { setQuarter(+this.value, true); });
  document.querySelectorAll('.rm-seg button').forEach(function (b) {
    b.addEventListener('click', function () { setGroup(b.getAttribute('data-g')); });
  });

  window.addEventListener('resize', function () {
    ALL.forEach(function (c) { c.resize(); });
  });
  window.addEventListener('load', function () {
    ALL.forEach(function (c) { c.resize(); });
  });

  applyFixed();
  apply();
  resetDetail();
})();
"""

# =====================================================================
# 四、校验与组装
# =====================================================================

def build_data(quarters, groups, labor):
    n = len(quarters)
    i = n - 1
    print('解析完成：%d 个季度（%s — %s）。抽样核对最新一期：' % (n, quarters[0], quarters[-1]))
    checks = [
        ('全国可支配收入(元)', groups['全国']['income']['inc'][i], 34230),
        ('全国收入中位数(元)', groups['全国']['income']['median'][i], 28388),
        ('全国消费支出(元)', groups['全国']['expenditure']['exp'][i], 22354),
        ('全国食品烟酒(元)', groups['全国']['expenditure']['cat_食品烟酒'][i], 6643),
        ('城镇可支配收入(元)', groups['城镇']['income']['inc'][i], 44945),
        ('农村可支配收入(元)', groups['农村']['income']['inc'][i], 18809),
        ('农村消费支出(元)', groups['农村']['expenditure']['exp'][i], 15218),
        ('务工劳动力(万人)', labor['workers'][-1], 19270),
        ('务工月均收入(元)', labor['wage'][-1], 5155),
    ]
    ok = True
    for name, got, want in checks:
        match = abs(got - want) < 0.05
        ok = ok and match
        print('  %-16s 取值 %-12s 期望 %-12s %s' % (name, got, want, 'OK' if match else '!!'))
    if not ok:
        raise SystemExit('抽样校验未通过，请确认 CSV 为国家统计局原始导出文件。')
    return {'quarters': quarters, 'groups': groups, 'labor': labor}


def main():
    no_open = '--no-open' in sys.argv
    print('正在扫描 %s 下的数据表 …' % DATA_DIR)
    quarters, groups, labor = load_data()
    data = build_data(quarters, groups, labor)

    echarts_tag = get_echarts_tag()
    data_json = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    fragment = (TEMPLATE
                .replace('/*__STYLE__*/', CSS)
                .replace('__ECHARTS__', echarts_tag)
                .replace('/*__DATA__*/', data_json)
                .replace('/*__APP__*/', APP))
    html = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>人民生活 · 季度数据大屏</title>\n</head>\n<body>\n'
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

# -*- coding: utf-8 -*-
'''国民经济核算 · 季度数据 BI 大屏生成器（深色科技版）
================================================================

自包含的可视化项目：仅用 Python 标准库即可在本机（VS Code / PyCharm / 命令行）运行，
无需 pip 安装任何第三方包。

功能
----
1. 读取 data/ 目录下的 6 张国家统计局季度数据表：
   国内生产总值 (现价).csv / 国内生产总值 (不变价).csv / 国内生产总值指数.csv /
   国内生产总值环比增长速度.csv / 三大需求对国内生产总值增长的贡献率.csv /
   三次产业贡献率.csv
2. 解析、校验并派生全部指标（2022Q2—2026Q3，共 18 个季度）；
3. 生成「深色科技风」交互式 BI 大屏 HTML（三栏布局、当季/累计切换、
   时间轴拖拽、播放轮播、点击图表全局联动），并自动在浏览器中打开。

使用方法
--------
在本文件夹内打开终端，执行：
    python generate_bi_dashboard.py            # 生成大屏并自动打开浏览器
    python generate_bi_dashboard.py --no-open  # 只生成文件，不打开浏览器

首次运行会自动下载 ECharts 图表库并缓存到本目录的 echarts.min.js（此后完全离线可用）；
若下载失败，生成的页面将改用联网 CDN 加载。

输出：国民经济核算BI大屏.html（双击也可随时打开）。
数据来源：国家统计局「数据库 — 季度数据」（2022Q2—2026Q3）。
'''

import json
import re
import sys
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / 'data'
# 缓存与产物不再建子目录，直接与 data/ 同级
ECHARTS_CACHE = BASE / 'echarts.min.js'
OUTPUT_HTML = BASE / '国民经济核算BI大屏.html'
LEGACY_DIRS = (BASE / 'cache', BASE / 'outputs')
# =====================================================================
# 一、数据解析：六张表 → 结构化数据（与页面 data.json 完全一致）
# =====================================================================

QMAP = {'一': 1, '二': 2, '三': 3, '四': 4}

FILES = {
    'cur':    '国内生产总值 (现价).csv',              # 现价 GDP 与行业增加值
    'real':   '国内生产总值 (不变价).csv',            # 不变价
    'idx':    '国内生产总值指数.csv',                # 指数（上年同期=100）
    'qoq':    '国内生产总值环比增长速度.csv',        # 环比增长速度
    'demand': '三大需求对国内生产总值增长的贡献率.csv',  # 三大需求贡献率
    'contrib':'三次产业贡献率.csv',                  # 三次产业贡献率
}

INDUSTRIES = ['农林牧渔业', '工业', '制造业', '建筑业', '批发和零售业',
              '交通运输、仓储和邮政业', '住宿和餐饮业', '金融业', '房地产业',
              '信息传输、软件和信息技术服务业', '租赁和商务服务业', '其他行业']


def parse_file(fp):
    """解析单张表：返回 (季度列表, {指标名(去空白): 数值列表})，列顺序与表头一致。"""
    text = fp.read_text(encoding='utf-8-sig')
    quarters, rows = None, {}
    for line in text.splitlines():
        if '\t' not in line:
            continue                      # 注释行、来源行等无制表符，跳过
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
        while vals and vals[-1] is None:   # 去掉行尾空单元格
            vals.pop()
        rows[first] = vals
    if not quarters:
        raise SystemExit('数据表格式异常（未找到表头季度行）：%s' % fp.name)
    return quarters, rows


def load_data(folder):
    P = {}
    for key, fname in FILES.items():
        fp = folder / fname
        if not fp.exists():
            raise SystemExit('缺少数据文件：%s' % fp)
        P[key] = parse_file(fp)

    quarters = P['cur'][0]
    for key, (qs, _) in P.items():
        if qs != quarters:
            raise SystemExit('六张表的季度列不一致，请检查文件：%s' % FILES[key])
    quarters = list(reversed(quarters))    # 转为时间正序（2022Q2 → 2026Q3）

    def grab(rows, pred, label):
        key = next((k for k in rows if pred(k)), None)
        if key is None:
            raise SystemExit('未找到指标：%s' % label)
        vals = list(reversed(rows[key]))
        if len(vals) != len(quarters):
            raise SystemExit('%s 数据长度 %d ≠ %d' % (label, len(vals), len(quarters)))
        if any(v is None for v in vals):
            raise SystemExit('%s 存在缺失值' % label)
        return vals

    S = {}
    # 现价 / 不变价：GDP 与三次产业
    S['gdpCur']  = grab(P['cur'][1],  lambda r: r.startswith('国内生产总值当季值'), 'GDP现价当季')
    S['gdpCum']  = grab(P['cur'][1],  lambda r: r.startswith('国内生产总值累计值'), 'GDP现价累计')
    S['gdpRealCur'] = grab(P['real'][1], lambda r: r.startswith('国内生产总值(不变价)当季值'), 'GDP不变价当季')
    S['gdpRealCum'] = grab(P['real'][1], lambda r: r.startswith('国内生产总值(不变价)累计值'), 'GDP不变价累计')
    for p, cn in (('p1', '第一'), ('p2', '第二'), ('p3', '第三')):
        S[p + 'Cur'] = grab(P['cur'][1],  lambda r, cn=cn: r.startswith(cn + '产业增加值当季值'), cn + '产现价当季')
        S[p + 'Cum'] = grab(P['cur'][1],  lambda r, cn=cn: r.startswith(cn + '产业增加值累计值'), cn + '产现价累计')
        S[p + 'RealCur'] = grab(P['real'][1], lambda r, cn=cn: r.startswith(cn + '产业增加值(不变价)当季值'), cn + '产不变价当季')
        S[p + 'RealCum'] = grab(P['real'][1], lambda r, cn=cn: r.startswith(cn + '产业增加值(不变价)累计值'), cn + '产不变价累计')
        S[p + 'IdxCur'] = grab(P['idx'][1], lambda r, cn=cn: r.startswith(cn + '产业增加值指数') and r.find('当季值') > 0, cn + '产指数当季')
        S[p + 'IdxCum'] = grab(P['idx'][1], lambda r, cn=cn: r.startswith(cn + '产业增加值指数') and r.find('累计值') > 0, cn + '产指数累计')
        S['pc' + p[1] + 'Cur'] = grab(P['contrib'][1], lambda r, cn=cn: r.startswith(cn + '产业贡献率') and r.find('当季值') > 0, cn + '产贡献率当季')
        S['pc' + p[1] + 'Cum'] = grab(P['contrib'][1], lambda r, cn=cn: r.startswith(cn + '产业贡献率') and r.find('累计值') > 0, cn + '产贡献率累计')
    # GDP 指数与环比
    S['gdpIdxCur'] = grab(P['idx'][1], lambda r: r.startswith('国内生产总值指数') and r.find('当季值') > 0, 'GDP指数当季')
    S['gdpIdxCum'] = grab(P['idx'][1], lambda r: r.startswith('国内生产总值指数') and r.find('累计值') > 0, 'GDP指数累计')
    S['qoq'] = grab(P['qoq'][1], lambda r: r.startswith('国内生产总值环比增长速度'), 'GDP环比')
    # 三大需求贡献率
    S['consCur'] = grab(P['demand'][1], lambda r: r.startswith('最终消费支出') and r.find('当季值') > 0, '消费贡献当季')
    S['consCum'] = grab(P['demand'][1], lambda r: r.startswith('最终消费支出') and r.find('累计值') > 0, '消费贡献累计')
    S['capCur']  = grab(P['demand'][1], lambda r: r.startswith('资本形成总额') and r.find('当季值') > 0, '资本形成贡献当季')
    S['capCum']  = grab(P['demand'][1], lambda r: r.startswith('资本形成总额') and r.find('累计值') > 0, '资本形成贡献累计')
    S['nexCur']  = grab(P['demand'][1], lambda r: r.startswith('货物和服务净出口') and r.find('当季值') > 0, '净出口贡献当季')
    S['nexCum']  = grab(P['demand'][1], lambda r: r.startswith('货物和服务净出口') and r.find('累计值') > 0, '净出口贡献累计')
    # 行业：增加值（现价）与指数
    industries = {}
    for name in INDUSTRIES:
        industries[name] = {
            'cur':    grab(P['cur'][1], lambda r, n=name: r.startswith(n + '增加值当季值'), name + '当季'),
            'cum':    grab(P['cur'][1], lambda r, n=name: r.startswith(n + '增加值累计值'), name + '累计'),
            'idxCur': grab(P['idx'][1], lambda r, n=name: r.startswith(n + '增加值指数') and r.find('当季值') > 0, name + '指数当季'),
            'idxCum': grab(P['idx'][1], lambda r, n=name: r.startswith(n + '增加值指数') and r.find('累计值') > 0, name + '指数累计'),
        }
    # 自检：前端脚本引用的全部序列键必须存在（防止字段名不匹配导致页面空白）
    REQUIRED = {'gdpCur', 'gdpCum', 'gdpRealCur', 'gdpRealCum',
                'p1Cur', 'p1Cum', 'p2Cur', 'p2Cum', 'p3Cur', 'p3Cum',
                'p1IdxCur', 'p1IdxCum', 'p2IdxCur', 'p2IdxCum', 'p3IdxCur', 'p3IdxCum',
                'pc1Cur', 'pc1Cum', 'pc2Cur', 'pc2Cum', 'pc3Cur', 'pc3Cum',
                'consCur', 'consCum', 'capCur', 'capCum', 'nexCur', 'nexCum',
                'gdpIdxCur', 'gdpIdxCum', 'qoq'}
    missing = REQUIRED - set(S)
    if missing:
        raise SystemExit('内部序列键缺失：%s' % sorted(missing))
    return {'quarters': quarters, 'series': S, 'industries': industries}


def find_data_folder():
    """数据表位于本脚本同级的 data/ 目录。"""
    if (DATA_DIR / FILES['cur']).exists():
        return DATA_DIR
    raise SystemExit(
        '未找到数据目录：%s\n请确认 6 张季度数据表（含 %s）都在该目录下。'
        % (DATA_DIR, FILES['cur']))


# =====================================================================
# 二、ECharts 图表库获取：本地缓存 → 在线下载（并缓存） → CDN 兜底
# =====================================================================

ECHARTS_URLS = [
    'https://registry.npmmirror.com/echarts/5.5.1/files/dist/echarts.min.js',
    'https://cdn.bootcdn.net/ajax/libs/echarts/5.5.1/echarts.min.js',
    'https://cdn.staticfile.net/echarts/5.5.1/echarts.min.js',
    'https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js',
    'https://unpkg.com/echarts@5.5.1/dist/echarts.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.1/echarts.min.js',
]


def get_echarts_tag():
    local = ECHARTS_CACHE
    js = None
    if local.exists() and local.stat().st_size > 500000:
        js = local.read_text(encoding='utf-8')
        print('[ECharts] 使用本地缓存 %s' % local.name)
    else:
        for url in ECHARTS_URLS:
            try:
                print('[ECharts] 尝试下载：%s' % url)
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                if len(data) > 500000:
                    local.write_bytes(data)
                    js = data.decode('utf-8')
                    print('[ECharts] 下载成功，已缓存到 %s（之后可完全离线运行）' % local.name)
                    break
                print('  文件大小异常（%d 字节），换下一个源' % len(data))
            except Exception as e:
                print('  失败：%s' % e)
    if js:
        return '<script>\n' + js.replace('</script', '<\\/script') + '\n</script>'
    print('[ECharts] 所有下载源均失败，页面将改为联网加载 CDN（打开大屏时需要网络）')
    return '<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>'


# =====================================================================
# 三、页面资源：样式 / 结构模板 / 交互脚本（与已验收版本逐字一致）
# =====================================================================

CSS = r"""#na-bi-dashboard-root {
  --na-text: #e6efff;
  --na-muted: #8fa3c8;
  --na-faint: #64789e;
  --na-line: rgba(59, 130, 246, 0.16);
  --na-card-a: rgba(17, 30, 56, 0.72);
  --na-card-b: rgba(12, 21, 40, 0.5);
  --na-cyan: #22d3ee;
  color: var(--na-text);
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  padding: 18px 22px 14px;
  border-radius: 14px;
  min-width: 0;
  background:
    radial-gradient(1100px 480px at 50% -8%, rgba(56, 189, 248, 0.14), transparent 62%),
    radial-gradient(900px 420px at 8% 108%, rgba(124, 58, 237, 0.08), transparent 60%),
    linear-gradient(180deg, #0c1830 0%, #0a1426 55%, #091120 100%);
}
#na-bi-dashboard-root * { box-sizing: border-box; }

/* ---------- 头部（三区：左信息 / 中大标题 / 右控制） ---------- */
.na-header2 { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 14px; margin-bottom: 14px; }
.h2-left { display: flex; align-items: center; gap: 11px; min-width: 0; }
.na-logo { width: 44px; height: 44px; border-radius: 12px; flex: 0 0 auto;
  background: linear-gradient(135deg, rgba(34, 211, 238, 0.25), rgba(59, 130, 246, 0.12));
  border: 1px solid rgba(34, 211, 238, 0.45);
  display: flex; align-items: center; justify-content: center; color: #67e8f9;
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.25), inset 0 0 12px rgba(34, 211, 238, 0.12); }
.h2-meta { min-width: 0; }
.h2-meta .src { font-size: 12.5px; color: var(--na-muted); white-space: nowrap; }
.h2-meta .upt { font-size: 11.5px; color: var(--na-faint); white-space: nowrap; }
.h2-center { text-align: center; }
.h2-title-row { display: flex; align-items: center; justify-content: center; gap: 16px; }
.h2-deco { height: 2px; width: 110px; background: linear-gradient(90deg, transparent, #22d3ee); border-radius: 2px; }
.h2-deco.r { transform: scaleX(-1); }
.h2-center h1 { margin: 0; font-size: 25px; font-weight: 700; letter-spacing: 3px; white-space: nowrap;
  background: linear-gradient(180deg, #ffffff 30%, #7dd3fc 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  text-shadow: 0 0 26px rgba(56, 189, 248, 0.35); }
.h2-center p { margin: 3px 0 0; font-size: 12px; color: var(--na-faint); letter-spacing: 1px; white-space: nowrap; }
.h2-right { display: flex; justify-content: flex-end; }
.na-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.na-seg { display: flex; background: rgba(10, 20, 38, 0.9); border: 1px solid var(--na-line); border-radius: 10px; padding: 3px; }
.na-seg button { border: 0; background: transparent; padding: 6px 16px; border-radius: 8px;
  font-size: 13px; color: var(--na-muted); cursor: pointer; font-family: inherit; font-weight: 500; }
.na-seg button.on { background: linear-gradient(135deg, #22d3ee, #0ea5e9); color: #06121f; font-weight: 700;
  box-shadow: 0 0 14px rgba(34, 211, 238, 0.45); }
.na-chip { font-size: 13px; font-weight: 700; color: #67e8f9; font-variant-numeric: tabular-nums;
  background: rgba(34, 211, 238, 0.08); border: 1px solid rgba(34, 211, 238, 0.4);
  border-radius: 9px; padding: 6px 14px; min-width: 84px; text-align: center;
  text-shadow: 0 0 12px rgba(34, 211, 238, 0.5); }
.na-btn { border: 1px solid transparent; border-radius: 9px; padding: 6px 16px; font-size: 13px;
  cursor: pointer; font-family: inherit; font-weight: 600; }
.na-btn.primary { background: linear-gradient(135deg, #22d3ee, #0ea5e9); color: #06121f;
  box-shadow: 0 0 16px rgba(34, 211, 238, 0.35); }
.na-btn.primary:hover { filter: brightness(1.1); }
.na-btn.ghost { background: rgba(10, 20, 38, 0.7); border-color: rgba(94, 130, 190, 0.35); color: #aebfe0; }
.na-btn.ghost:hover { border-color: rgba(34, 211, 238, 0.6); color: #67e8f9; }

/* ---------- 时间轴 ---------- */
.na-timeline { background: linear-gradient(180deg, var(--na-card-a), var(--na-card-b)); border: 1px solid var(--na-line);
  border-radius: 12px; padding: 12px 18px 26px; display: flex; align-items: center; gap: 12px; position: relative;
  margin-bottom: 14px; }
.na-tl-label { font-size: 13px; font-weight: 600; color: #aebfe0; flex: 0 0 auto; }
.na-arrow { width: 26px; height: 26px; border-radius: 50%; border: 1px solid rgba(94, 130, 190, 0.4);
  background: rgba(10, 20, 38, 0.8); color: #aebfe0; cursor: pointer; flex: 0 0 auto; font-size: 13px;
  line-height: 1; display: flex; align-items: center; justify-content: center; padding: 0; font-family: inherit; }
.na-arrow:hover { border-color: var(--na-cyan); color: #67e8f9; }
#na-range { flex: 1; -webkit-appearance: none; appearance: none; height: 6px; border-radius: 3px;
  background: #1b2a47; outline: none; cursor: pointer; min-width: 120px; }
#na-range::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 18px; height: 18px;
  border-radius: 50%; background: #22d3ee; border: 3px solid #0a1426;
  box-shadow: 0 0 14px rgba(34, 211, 238, 0.8); cursor: grab; }
#na-range::-moz-range-thumb { width: 14px; height: 14px; border-radius: 50%; background: #22d3ee;
  border: 3px solid #0a1426; box-shadow: 0 0 14px rgba(34, 211, 238, 0.8); cursor: grab; }
.na-years { position: absolute; left: 96px; right: 330px; bottom: 5px; height: 15px; pointer-events: none; }
.na-years span { position: absolute; transform: translateX(-50%); font-size: 11px; color: var(--na-faint); }
.na-years span:first-child { transform: none; }
.na-hint { font-size: 12px; color: var(--na-faint); flex: 0 0 auto; max-width: 330px; text-align: right; line-height: 1.45; }

/* ---------- KPI ---------- */
.na-kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 12px; }
.na-kpi { background: linear-gradient(180deg, var(--na-card-a), var(--na-card-b));
  border: 1px solid var(--na-line); border-radius: 12px; padding: 12px 14px 12px 18px; position: relative;
  overflow: hidden; min-width: 0; }
.na-kpi::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--ac, #22d3ee); box-shadow: 0 0 12px var(--ac, #22d3ee); }
.na-kpi-top { display: flex; justify-content: space-between; gap: 6px; font-size: 12.5px; color: #aebfe0; font-weight: 600; }
.na-kpi-tag { color: var(--na-faint); font-weight: 400; white-space: nowrap; }
.na-kpi-val { font-size: 27px; font-weight: 700; margin: 3px 0 1px; letter-spacing: .5px; white-space: nowrap;
  color: #f4f9ff; font-variant-numeric: tabular-nums; text-shadow: 0 0 18px var(--ac, #22d3ee); }
.na-kpi-val small { font-size: 13.5px; font-weight: 600; color: var(--na-muted); margin-left: 3px; }
.na-kpi-sub { font-size: 12px; color: var(--na-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.na-up { color: #34d399; font-weight: 700; }
.na-down { color: #fb7185; font-weight: 700; }

/* ---------- 速读 ---------- */
.na-brief { background: linear-gradient(90deg, rgba(34, 211, 238, 0.10), rgba(17, 30, 56, 0.55) 45%);
  border: 1px solid rgba(34, 211, 238, 0.22); border-left: 3px solid #22d3ee;
  border-radius: 12px; padding: 11px 18px; font-size: 13.5px; line-height: 1.75; margin-bottom: 14px;
  color: #c9d8f5; box-shadow: 0 0 22px rgba(34, 211, 238, 0.07) inset; }
.na-brief b { font-weight: 700; }
.na-brief .hl { color: #fcd34d; }
.na-brief .num { color: #67e8f9; }

/* ---------- 图表网格：左 / 中 / 右三栏 + 底部通栏 ---------- */
.na-grid2 { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }
.na-col { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.na-col.left, .na-col.right { grid-column: span 3; }
.na-col.center { grid-column: span 6; }
.na-col.bottom { grid-column: span 12; }

.na-card { background: linear-gradient(180deg, var(--na-card-a), var(--na-card-b));
  border: 1px solid var(--na-line); border-radius: 10px; padding: 13px 15px 6px;
  display: flex; flex-direction: column; min-width: 0; position: relative; }
.na-card::before, .na-card::after { content: ''; position: absolute; width: 9px; height: 9px;
  border: 0 solid rgba(56, 189, 248, 0.65); pointer-events: none; }
.na-card::before { top: -1px; left: -1px; border-top-width: 2px; border-left-width: 2px; }
.na-card::after { bottom: -1px; right: -1px; border-bottom-width: 2px; border-right-width: 2px; }
.na-card-h { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.na-card-h h3 { font-size: 15px; font-weight: 700; margin: 0; white-space: nowrap; color: #dcebff; letter-spacing: .5px; }
.na-hint-r { font-size: 12px; color: var(--na-faint); white-space: nowrap; }
.na-hint-r i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin: 0 3px 0 8px; }
.na-sub { font-size: 12px; color: var(--na-faint); margin: 1px 0 2px; }
.na-chart { width: 100%; }
.na-col.left #ch3, .na-col.left #ch4, .na-col.right #ch5, .na-col.right #ch6 { height: 344px; }
.na-col.center #ch1 { height: 428px; }
.na-col.center #ch2 { height: 296px; }
.na-col.bottom #ch7 { height: 316px; }
.na-foot { font-size: 11.5px; color: #55688c; margin-top: 10px; line-height: 1.7; }

@media (prefers-reduced-motion: reduce) {
  #na-bi-dashboard-root *, #na-bi-dashboard-root *::before, #na-bi-dashboard-root *::after {
    animation: none !important; transition: none !important;
  }
}
@media (max-width: 1360px) {
  .na-col.left, .na-col.center, .na-col.right, .na-col.bottom { grid-column: span 12; }
  .na-col.center { order: -1; }
  .na-years { display: none; }
}
@media (max-width: 1080px) {
  .na-header2 { grid-template-columns: 1fr; text-align: center; }
  .h2-left { justify-content: center; }
  .h2-right { justify-content: center; }
  .na-kpis { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 720px) {
  .na-kpis { grid-template-columns: 1fr; }
  #na-bi-dashboard-root { padding: 12px; }
  .h2-deco { width: 40px; }
}
"""

TEMPLATE = r"""<style>
/*__STYLE__*/
</style>

<div id="na-bi-dashboard-root">
  <div class="na-header2">
    <div class="h2-left">
      <div class="na-logo" aria-hidden="true">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
          <path d="M5 20V13" /><path d="M12 20V5" /><path d="M19 20v-9" />
        </svg>
      </div>
      <div class="h2-meta">
        <div class="src">国家统计局 · 季度数据库</div>
        <div class="upt">更新至 2026Q3 · 六表联动</div>
      </div>
    </div>
    <div class="h2-center">
      <div class="h2-title-row">
        <span class="h2-deco" aria-hidden="true"></span>
        <h1>国民经济核算数据大屏</h1>
        <span class="h2-deco r" aria-hidden="true"></span>
      </div>
      <p>GDP · 三次产业 · 三大需求 · 行业增速 &nbsp;|&nbsp; 2022Q2 — 2026Q3 · 18 个季度</p>
    </div>
    <div class="h2-right">
      <div class="na-controls">
        <div class="na-seg" role="group" aria-label="统计口径">
          <button type="button" id="mode-cur" class="on">当季值</button>
          <button type="button" id="mode-cum">累计值</button>
        </div>
        <span class="na-chip" id="q-chip">—</span>
        <button type="button" class="na-btn primary" id="btn-play">播放</button>
        <button type="button" class="na-btn ghost" id="btn-reset">重置</button>
      </div>
    </div>
  </div>

  <div class="na-timeline">
    <span class="na-tl-label">季度</span>
    <button type="button" class="na-arrow" id="btn-prev" aria-label="上一季度">‹</button>
    <input type="range" id="na-range" min="0" max="17" step="1" value="17" aria-label="选择季度" />
    <button type="button" class="na-arrow" id="btn-next" aria-label="下一季度">›</button>
    <span class="na-hint">拖动时间轴 / 点击任意图表中的柱、线、格子即可联动全部图表</span>
    <div class="na-years" aria-hidden="true">
      <span style="left:0%">2022</span><span style="left:17.6%">2023</span><span style="left:41.2%">2024</span><span style="left:64.7%">2025</span><span style="left:88.2%">2026</span>
    </div>
  </div>

  <div class="na-kpis" id="na-kpis"></div>
  <div class="na-brief" id="na-brief" aria-live="polite"></div>

  <div class="na-grid2">
    <div class="na-col left">
      <div class="na-card">
        <div class="na-card-h"><h3 id="t3">三次产业结构（当季值）</h3><span class="na-hint-r">占比线看服务业</span></div>
        <div class="na-sub" id="s3">堆叠：增加值（亿元）· 线：三产占比（%）</div>
        <div class="na-chart" id="ch3"></div>
      </div>
      <div class="na-card">
        <div class="na-card-h"><h3 id="t4">三次产业同比增速（当季值）</h3><span class="na-hint-r">0 线为分界</span></div>
        <div class="na-sub">指数（上年同期=100）− 100（%）</div>
        <div class="na-chart" id="ch4"></div>
      </div>
    </div>

    <div class="na-col center">
      <div class="na-card">
        <div class="na-card-h"><h3 id="t1">GDP 当季值（现价）与同比增速</h3><span class="na-hint-r">点击柱体切换季度</span></div>
        <div class="na-sub" id="s1">柱：当季值规模（亿元）· 线：当季同比（%）</div>
        <div class="na-chart" id="ch1"></div>
      </div>
      <div class="na-card">
        <div class="na-card-h"><h3>环比增长动能</h3><span class="na-hint-r">柱高即增速</span></div>
        <div class="na-sub">经季节调整的季度环比（%）</div>
        <div class="na-chart" id="ch2"></div>
      </div>
    </div>

    <div class="na-col right">
      <div class="na-card">
        <div class="na-card-h"><h3 id="t5">三次产业贡献率（当季值）</h3><span class="na-hint-r">谁在拉动增长</span></div>
        <div class="na-sub">对 GDP 增长的贡献，合计 100%</div>
        <div class="na-chart" id="ch5"></div>
      </div>
      <div class="na-card">
        <div class="na-card-h"><h3 id="t6">三大需求贡献率（当季值）</h3><span class="na-hint-r">消费 · 投资 · 净出口</span></div>
        <div class="na-sub" id="s6">三大需求贡献率走势（%），可为负</div>
        <div class="na-chart" id="ch6"></div>
      </div>
    </div>

    <div class="na-col bottom">
      <div class="na-card">
        <div class="na-card-h">
          <h3 id="t7">行业增加值同比增速（当季值）</h3>
          <span class="na-hint-r">颜色按三次产业
            <i style="background:#34d399"></i>一产
            <i style="background:#38bdf8"></i>二产
            <i style="background:#c084fc"></i>三产
          </span>
        </div>
        <div class="na-sub" id="s7">12 个行业 · 按当季增速排序 · 悬停查看规模</div>
        <div class="na-chart" id="ch7"></div>
      </div>
    </div>
  </div>

  <div class="na-foot">
    数据来源：国家统计局「数据库 — 季度数据」（2022Q2—2026Q3）。联动报表：国内生产总值（现价）／国内生产总值（不变价）／国内生产总值指数（上年同期=100）／环比增长速度／三大需求贡献率／三次产业贡献率。
    同比增速 = 指数 − 100（不变价口径）；第三产业占比按现价计算；贡献率之和因四舍五入可能不完全等于 100%。
  </div>
</div>

__ECHARTS__

<script>
window.NA_DATA = /*__DATA__*/;
</script>

<script>
window.NA_THEME = {
  barPale: '#1d4ed8', barSel: '#22d3ee', barNeg: '#f43f5e',
  line1: '#34d399', line2: '#38bdf8', line3: '#c084fc',
  s1: '#34d399', s2: '#38bdf8', s3: '#c084fc',
  pastel1: '#3ddc97', pastel2: '#45b6f5', pastel3: '#b57df7',
  orange: '#fbbf24', teal: '#2dd4bf', purple: '#f472b6',
  axisText: '#7e93bd', axisLine: 'rgba(126,147,189,0.35)', split: 'rgba(148,163,184,0.09)',
  mark: 'rgba(148,163,184,0.45)', legendText: '#8fa3c8', valLabel: '#dbe7ff',
  yLabel: '#9fb2d8', segLabel: '#eaf2ff', orangeText: '#fbbf24',
  tipBg: 'rgba(8,15,31,0.95)', tipBorder: 'rgba(56,189,248,0.35)', tipText: '#e6efff',
  tipShadow: '0 12px 32px rgba(0,0,0,0.5)',
  sliderFill: '#22d3ee', sliderTrack: '#1b2a47',
  accents: ['#22d3ee', '#c084fc', '#34d399', '#fbbf24', '#fb7185'],
  glowSel: true
};
</script>

<script>
/*__APP__*/
</script>
"""

APP_JS = r"""(function () {
  'use strict';
  var root = document.getElementById('na-bi-dashboard-root');
  if (!root) return;
  if (typeof echarts === 'undefined') {
    root.innerHTML = '<div style="padding:60px 20px;text-align:center;color:#64748b;font-size:14px;">ECharts 加载失败：本页面依赖 ECharts 库，请联网后刷新，或使用随附的离线完整版 HTML。</div>';
    return;
  }
  var RAW = window.NA_DATA;
  var Q = RAW.quarters, N = Q.length, S = RAW.series, IND = RAW.industries;

  /* ---------- 主题（默认浅色，可经 window.NA_THEME 覆盖为深色等） ---------- */
  var THEME = Object.assign({
    barPale: '#bfe3e0', barSel: '#0d9488', barNeg: '#f5a9a9',
    line1: '#10b981', line2: '#3b82f6', line3: '#8b5cf6',
    s1: '#34d399', s2: '#60a5fa', s3: '#a78bfa',
    pastel1: '#7dedc0', pastel2: '#a7cbfd', pastel3: '#bcc7fd',
    orange: '#f59e0b', teal: '#14b8a6', purple: '#8b5cf6',
    axisText: '#7c8aa0', axisLine: '#d7dfe8', split: '#eef2f6',
    mark: '#c3ccd8', legendText: '#64748b', valLabel: '#475569',
    yLabel: '#475569', segLabel: '#1e293b', orangeText: '#b45309',
    tipBg: 'rgba(255,255,255,.97)', tipBorder: '#e2e8f0', tipText: '#0f172a',
    tipShadow: '0 10px 28px rgba(15,23,42,.14)',
    sliderFill: '#0d9488', sliderTrack: '#e2e8f0',
    accents: ['#14b8a6', '#8b5cf6', '#10b981', '#f59e0b', '#f43f5e'],
    glowSel: false
  }, window.NA_THEME || {});
  var C = THEME;

  var REDUCE = false;
  try { REDUCE = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}
  var ANIM = REDUCE ? 0 : 320;

  var SECTOR_COLOR = { 1: C.s1, 2: C.s2, 3: C.s3 };

  var INDUSTRIES = [
    { name: '农林牧渔业', short: '农林牧渔', sector: 1 },
    { name: '工业', short: '工业', sector: 2 },
    { name: '制造业', short: '制造业', sector: 2 },
    { name: '建筑业', short: '建筑业', sector: 2 },
    { name: '批发和零售业', short: '批发零售', sector: 3 },
    { name: '交通运输、仓储和邮政业', short: '交通仓储邮政', sector: 3 },
    { name: '住宿和餐饮业', short: '住宿餐饮', sector: 3 },
    { name: '金融业', short: '金融业', sector: 3 },
    { name: '房地产业', short: '房地产业', sector: 3 },
    { name: '信息传输、软件和信息技术服务业', short: '信息传输软件', sector: 3 },
    { name: '租赁和商务服务业', short: '租赁商务', sector: 3 },
    { name: '其他行业', short: '其他行业', sector: 3 }
  ];

  var state = { mode: 'cur', qi: N - 1, playing: false, timer: null };

  /* ---------- 恢复会话内交互状态（仅可视化宿主提供） ---------- */
  try {
    var saved = window.zcode && window.zcode.widgetState && window.zcode.widgetState.privateContent;
    if (saved && typeof saved.qi === 'number' && saved.qi >= 0 && saved.qi < N) state.qi = saved.qi;
    if (saved && saved.mode === 'cum') state.mode = 'cum';
  } catch (e) {}
  function saveState() {
    try {
      if (window.zcode && typeof window.zcode.setWidgetState === 'function') {
        window.zcode.setWidgetState({ privateContent: { qi: state.qi, mode: state.mode } }).catch(function () {});
      }
    } catch (e) {}
  }

  /* ---------- 工具 ---------- */
  function el(id) { return document.getElementById(id); }
  function shortQ(q) { return q.slice(2); }
  function r1(v) { return Math.round(v * 10) / 10; }
  function sgn(v, d) { return (v > 0 ? '+' : '') + v.toFixed(d === undefined ? 1 : d); }
  function fmtYi(v) { return Math.round(v).toLocaleString('en-US'); }
  function fmtWan(v) { return (v / 10000).toFixed(2); }
  function wFmt(v) { return v >= 10000 ? (v / 10000) + '万亿' : v; }
  function cls(v) { return v >= 0 ? 'na-up' : 'na-down'; }
  function rgba(hex, a) {
    var h = hex.replace('#', '');
    return 'rgba(' + parseInt(h.slice(0, 2), 16) + ',' + parseInt(h.slice(2, 4), 16) + ',' + parseInt(h.slice(4, 6), 16) + ',' + a + ')';
  }
  function glow(color) { return THEME.glowSel ? { shadowColor: color, shadowBlur: 8 } : {}; }
  function barItems(values, colorOf) {
    // 逐柱着色；选中柱在深色主题下附加辉光
    return values.map(function (v, i) {
      var col = colorOf(v, i);
      var it = { value: v, itemStyle: { color: col } };
      if (THEME.glowSel && i === state.qi) {
        it.itemStyle.shadowColor = col;
        it.itemStyle.shadowBlur = 14;
      }
      return it;
    });
  }
  function dimFn(solid) { return function (p) { return p.dataIndex === state.qi ? solid : rgba(solid, 0.38); }; }
  function m1(k) { return state.mode === 'cur' ? S[k + 'Cur'] : S[k + 'Cum']; }
  function idx100(arr) { return arr.map(function (v) { return r1(v - 100); }); }
  function shareOf(p) {
    var gdp = m1('gdp'), v = m1(p);
    return v.map(function (x, i) { return r1(x / gdp[i] * 100); });
  }
  function delta(arr, i, back) {
    var j = i - (back || 1);
    return j < 0 ? null : r1(arr[i] - arr[j]);
  }
  function deltaHtml(label, d) {
    return label + ' <span class="' + (d === null ? '' : cls(d)) + '">' + (d === null ? '—' : sgn(d) + 'pp') + '</span>';
  }

  var D = {}; // 当季/累计派生数据
  function computeDerived() {
    var gdp = m1('gdp');
    D.gdp = gdp;
    D.p1 = m1('p1'); D.p2 = m1('p2'); D.p3 = m1('p3');
    D.gdpReal = m1('gdpReal');
    D.yoyG = idx100(state.mode === 'cur' ? S.gdpIdxCur : S.gdpIdxCum);
    D.yoy1 = idx100(state.mode === 'cur' ? S.p1IdxCur : S.p1IdxCum);
    D.yoy2 = idx100(state.mode === 'cur' ? S.p2IdxCur : S.p2IdxCum);
    D.yoy3 = idx100(state.mode === 'cur' ? S.p3IdxCur : S.p3IdxCum);
    D.s1 = shareOf('p1'); D.s2 = shareOf('p2'); D.s3 = shareOf('p3');
    D.pc1 = m1('pc1'); D.pc2 = m1('pc2'); D.pc3 = m1('pc3');
    D.cons = m1('cons'); D.cap = m1('cap'); D.nex = m1('nex');
    D.qoq = S.qoq;
  }

  /* ---------- 图表公共样式 ---------- */
  var TIP = {
    backgroundColor: THEME.tipBg, borderColor: THEME.tipBorder, borderWidth: 1,
    padding: [10, 14], textStyle: { color: THEME.tipText, fontSize: 12.5 },
    extraCssText: 'box-shadow:' + THEME.tipShadow + ';border-radius:10px;'
  };
  function tipTitle(q) { return '<div style="font-weight:700;font-size:13px;margin-bottom:4px;">' + q + '</div>'; }
  function tipRow(k, v, color) {
    return '<div style="display:flex;justify-content:space-between;gap:22px;line-height:1.9;">' +
      '<span style="opacity:.75;">' + k + '</span>' +
      '<span style="font-weight:600;' + (color ? 'color:' + color : '') + '">' + v + '</span></div>';
  }
  var AX = { color: THEME.axisText, fontSize: 11.5 };
  var SPLIT = { lineStyle: { color: THEME.split } };
  var CAT_X = {
    type: 'category', data: Q.map(shortQ),
    axisLine: { lineStyle: { color: THEME.axisLine } }, axisTick: { show: false },
    axisLabel: { color: AX.color, fontSize: AX.fontSize }
  };
  var PCT_Y = {
    type: 'value', position: 'right', axisLabel: { formatter: '{value}%', color: AX.color, fontSize: AX.fontSize },
    splitLine: { show: false }, axisLine: { show: false }
  };
  function selMark() {
    return { silent: true, symbol: 'none', animation: false, label: { show: false },
      lineStyle: { type: 'dashed', color: THEME.mark }, data: [{ xAxis: state.qi }] };
  }

  var charts = {};
  function mk(id) {
    var c = echarts.init(el(id));
    charts[id] = c;
    return c;
  }

  /* ---------- 图 1：GDP 规模与同比 ---------- */
  function opt1() {
    var name = state.mode === 'cur' ? 'GDP 当季值' : 'GDP 累计值';
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: ANIM,
      color: [C.barSel, C.orange],
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 9, itemGap: 18, textStyle: { fontSize: 12, color: THEME.legendText }, data: [name, '同比增速'] },
      grid: { left: 62, right: 52, top: 32, bottom: 24 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow(name, fmtYi(D.gdp[i]) + ' 亿元') +
            tipRow('同比增速', sgn(D.yoyG[i]) + '%', THEME.orangeText) +
            tipRow('环比增速（季调）', sgn(D.qoq[i]) + '%');
        }
      }),
      xAxis: CAT_X,
      yAxis: [
        { type: 'value', axisLabel: { formatter: wFmt, color: AX.color, fontSize: AX.fontSize }, splitLine: SPLIT },
        PCT_Y
      ],
      series: [
        { name: name, type: 'bar', data: barItems(D.gdp, function (v, i) { return i === state.qi ? C.barSel : C.barPale; }),
          barWidth: '52%', itemStyle: { borderRadius: [3, 3, 0, 0] } },
        { name: '同比增速', type: 'line', yAxisIndex: 1, data: D.yoyG, z: 6,
          symbol: 'circle', symbolSize: 6,
          lineStyle: Object.assign({ width: 2.5, color: C.orange }, glow(C.orange)),
          itemStyle: { color: C.orange } }
      ]
    };
  }

  /* ---------- 图 2：环比 ---------- */
  function opt2() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: ANIM,
      grid: { left: 44, right: 14, top: 26, bottom: 24 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) + tipRow('环比增速（季调）', sgn(D.qoq[i]) + '%', THEME.teal);
        }
      }),
      xAxis: CAT_X,
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: AX.color, fontSize: AX.fontSize }, splitLine: SPLIT },
      series: [{
        name: '环比增速', type: 'bar', barWidth: '55%',
        data: barItems(D.qoq, function (v, i) {
          if (i === state.qi) return C.barSel;
          return v < 0 ? C.barNeg : C.barPale;
        }),
        itemStyle: { borderRadius: 2 },
        markLine: { silent: true, symbol: 'none', animation: false, label: { show: false },
          lineStyle: { type: 'dashed', color: THEME.mark }, data: [{ yAxis: 0 }] }
      }]
    };
  }

  /* ---------- 图 3：三次产业结构 ---------- */
  function opt3() {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: ANIM,
      color: [C.s1, C.s2, C.s3, C.orange],
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 9, itemGap: 12, textStyle: { fontSize: 12, color: THEME.legendText } },
      grid: { left: 62, right: 50, top: 32, bottom: 24 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('第一产业', fmtYi(D.p1[i]) + ' 亿元 · ' + D.s1[i].toFixed(1) + '%') +
            tipRow('第二产业', fmtYi(D.p2[i]) + ' 亿元 · ' + D.s2[i].toFixed(1) + '%') +
            tipRow('第三产业', fmtYi(D.p3[i]) + ' 亿元 · ' + D.s3[i].toFixed(1) + '%');
        }
      }),
      xAxis: CAT_X,
      yAxis: [
        { type: 'value', axisLabel: { formatter: wFmt, color: AX.color, fontSize: AX.fontSize }, splitLine: SPLIT },
        { type: 'value', scale: true, position: 'right', axisLabel: { formatter: '{value}%', color: AX.color, fontSize: AX.fontSize }, splitLine: { show: false } }
      ],
      series: [
        { name: '第一产业', type: 'bar', stack: 'gdp', data: D.p1, barWidth: '52%', itemStyle: { color: dimFn(C.s1) } },
        { name: '第二产业', type: 'bar', stack: 'gdp', data: D.p2, itemStyle: { color: dimFn(C.s2) } },
        { name: '第三产业', type: 'bar', stack: 'gdp', data: D.p3, itemStyle: { color: dimFn(C.s3) } },
        { name: '三产占比', type: 'line', yAxisIndex: 1, data: D.s3, z: 6, symbol: 'circle', symbolSize: 5.5,
          lineStyle: Object.assign({ width: 2.5, color: C.orange }, glow(C.orange)),
          itemStyle: { color: C.orange } }
      ]
    };
  }

  /* ---------- 图 4：三次产业同比 ---------- */
  function opt4() {
    function line(name, data, color) {
      return { name: name, type: 'line', data: data, symbol: 'circle', symbolSize: 5,
        lineStyle: Object.assign({ width: 2, color: color }, glow(color)), itemStyle: { color: color } };
    }
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: ANIM,
      color: [C.line1, C.line2, C.line3],
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 9, itemGap: 12, textStyle: { fontSize: 12, color: THEME.legendText } },
      grid: { left: 40, right: 14, top: 32, bottom: 24 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'line' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('第一产业', sgn(D.yoy1[i]) + '%', C.line1) +
            tipRow('第二产业', sgn(D.yoy2[i]) + '%', C.line2) +
            tipRow('第三产业', sgn(D.yoy3[i]) + '%', C.line3);
        }
      }),
      xAxis: CAT_X,
      yAxis: { type: 'value', scale: true, axisLabel: { formatter: '{value}%', color: AX.color, fontSize: AX.fontSize }, splitLine: SPLIT },
      series: [
        Object.assign(line('第一产业', D.yoy1, C.line1), { markLine: selMark() }),
        line('第二产业', D.yoy2, C.line2),
        line('第三产业', D.yoy3, C.line3)
      ]
    };
  }

  /* ---------- 图 5：三次产业贡献率 ---------- */
  function opt5() {
    function seg(name, data, color) {
      var label = { show: true, position: 'inside', fontSize: 11, color: THEME.segLabel, fontWeight: 600,
        formatter: function (p) { return p.value >= 6 ? Math.round(p.value) : ''; } };
      if (THEME.glowSel) { label.textShadowColor = 'rgba(2,8,20,0.65)'; label.textShadowBlur = 4; }
      return { name: name, type: 'bar', stack: 'c', data: data, barWidth: '55%',
        itemStyle: { color: dimFn(color) }, label: label };
    }
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: ANIM,
      color: [C.pastel1, C.pastel2, C.pastel3],
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 9, itemGap: 10, textStyle: { fontSize: 12, color: THEME.legendText } },
      grid: { left: 40, right: 12, top: 32, bottom: 24 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('第一产业', D.pc1[i].toFixed(1) + '%') +
            tipRow('第二产业', D.pc2[i].toFixed(1) + '%') +
            tipRow('第三产业', D.pc3[i].toFixed(1) + '%');
        }
      }),
      xAxis: CAT_X,
      yAxis: { type: 'value', min: 0, max: 100, interval: 25, axisLabel: { formatter: '{value}%', color: AX.color, fontSize: AX.fontSize }, splitLine: SPLIT },
      series: [seg('第一产业', D.pc1, C.pastel1), seg('第二产业', D.pc2, C.pastel2), seg('第三产业', D.pc3, C.pastel3)]
    };
  }

  /* ---------- 图 6：三大需求贡献率 ---------- */
  function opt6() {
    function line(name, data, color) {
      return { name: name, type: 'line', data: data, symbol: 'circle', symbolSize: 5,
        lineStyle: Object.assign({ width: 2, color: color }, glow(color)), itemStyle: { color: color } };
    }
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: ANIM,
      color: [C.teal, C.orange, C.purple],
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 9, itemGap: 14, textStyle: { fontSize: 12, color: THEME.legendText } },
      grid: { left: 44, right: 16, top: 32, bottom: 24 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'line' },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return tipTitle(Q[i]) +
            tipRow('最终消费支出', sgn(D.cons[i]) + '%', C.teal) +
            tipRow('资本形成总额', sgn(D.cap[i]) + '%', C.orange) +
            tipRow('货物和服务净出口', sgn(D.nex[i]) + '%', C.purple);
        }
      }),
      xAxis: CAT_X,
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: AX.color, fontSize: AX.fontSize }, splitLine: SPLIT },
      series: [
        Object.assign(line('最终消费支出', D.cons, C.teal), { markLine: { silent: true, symbol: 'none', animation: false,
          label: { show: false }, lineStyle: { type: 'dashed', color: THEME.mark }, data: [{ yAxis: 0 }] } }),
        line('资本形成总额', D.cap, C.orange),
        line('货物和服务净出口', D.nex, C.purple)
      ]
    };
  }

  /* ---------- 图 7：行业增速排行 ---------- */
  function opt7() {
    var idxKey = state.mode === 'cur' ? 'idxCur' : 'idxCum';
    var valKey = state.mode === 'cur' ? 'cur' : 'cum';
    var items = INDUSTRIES.map(function (d) {
      return {
        name: d.name, short: d.short, sector: d.sector,
        g: r1(IND[d.name][idxKey][state.qi] - 100),
        val: IND[d.name][valKey][state.qi]
      };
    }).sort(function (a, b) { return b.g - a.g; });
    var gs = items.map(function (x) { return x.g; });
    var min = Math.min.apply(null, gs), max = Math.max.apply(null, gs);
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: ANIM,
      grid: { left: 106, right: 62, top: 12, bottom: 22 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) {
          var it = items[p.dataIndex];
          return tipTitle(it.name) +
            tipRow('增加值' + (state.mode === 'cur' ? '当季值' : '累计值'), fmtYi(it.val) + ' 亿元') +
            tipRow('同比增速', sgn(it.g) + '%', THEME.teal);
        }
      }),
      xAxis: { type: 'value', min: Math.floor(min) - 1, max: Math.ceil(max) + 1,
        axisLabel: { formatter: '{value}%', color: AX.color, fontSize: AX.fontSize }, splitLine: SPLIT },
      yAxis: { type: 'category', inverse: true, data: items.map(function (x) { return x.short; }),
        axisLine: { lineStyle: { color: THEME.axisLine } }, axisTick: { show: false },
        axisLabel: { color: THEME.yLabel, fontSize: 11.5 } },
      series: [{
        name: '同比增速', type: 'bar', barWidth: '58%',
        data: items.map(function (x) {
          return {
            value: x.g,
            itemStyle: { borderRadius: x.g >= 0 ? [0, 3, 3, 0] : [3, 0, 0, 3], color: rgba(SECTOR_COLOR[x.sector], 0.92) },
            label: { position: x.g >= 0 ? 'right' : 'left' }
          };
        }),
        label: { show: true, fontSize: 11, color: THEME.valLabel, fontWeight: 600,
          formatter: function (p) { return sgn(p.value) + '%'; } }
      }]
    };
  }

  /* ---------- KPI 与速读 ---------- */
  function kpiHtml(ac, title, tag, val, unit, sub) {
    return '<div class="na-kpi" style="--ac:' + ac + '">' +
      '<div class="na-kpi-top"><span>' + title + '</span><span class="na-kpi-tag">' + tag + '</span></div>' +
      '<div class="na-kpi-val">' + val + (unit ? '<small>' + unit + '</small>' : '') + '</div>' +
      '<div class="na-kpi-sub">' + sub + '</div></div>';
  }
  function renderKpis() {
    var cur = state.mode === 'cur';
    var A = THEME.accents;
    var y = D.yoyG[state.qi];
    var gdpSub = '同比 <span class="' + cls(y) + '">' + sgn(y) + '%</span> · ' + deltaHtml('较上季', delta(D.yoyG, state.qi));
    var shareYoy = delta(D.s3, state.qi, 4);
    var html =
      kpiHtml(A[0], 'GDP ' + (cur ? '当季值' : '累计值'), '现价', fmtWan(D.gdp[state.qi]), '万亿元', gdpSub) +
      kpiHtml(A[1], '第三产业占比', '结构', D.s3[state.qi].toFixed(1), '%',
        deltaHtml('同比', shareYoy) + ' · 贡献 ' + D.pc3[state.qi].toFixed(1) + '%') +
      kpiHtml(A[2], '最终消费贡献率', '需求', D.cons[state.qi].toFixed(1), '%',
        deltaHtml('较上季', delta(D.cons, state.qi))) +
      kpiHtml(A[3], '资本形成贡献率', '需求', D.cap[state.qi].toFixed(1), '%',
        deltaHtml('较上季', delta(D.cap, state.qi))) +
      kpiHtml(A[4], '净出口贡献率', '需求', D.nex[state.qi].toFixed(1), '%',
        deltaHtml('较上季', delta(D.nex, state.qi)));
    el('na-kpis').innerHTML = html;
  }
  function renderBrief() {
    var cur = state.mode === 'cur', qi = state.qi;
    var best = null, worst = null;
    var idxKey = cur ? 'idxCur' : 'idxCum';
    INDUSTRIES.forEach(function (d) {
      var g = r1(IND[d.name][idxKey][qi] - 100);
      if (!best || g > best.g) best = { n: d.name, g: g };
      if (!worst || g < worst.g) worst = { n: d.name, g: g };
    });
    var b = cur
      ? '<b>' + Q[qi] + ' 速读</b>&nbsp;&nbsp;GDP 当季 <b class="num">' + fmtWan(D.gdp[qi]) + ' 万亿元</b>，同比 <b class="num">' + sgn(D.yoyG[qi]) + '%</b>，环比 <b class="num">' + sgn(D.qoq[qi]) + '%</b>；' +
        '第三产业占比 <b class="num">' + D.s3[qi].toFixed(1) + '%</b>、贡献 <b class="num">' + D.pc3[qi].toFixed(1) + '%</b>；消费 / 资本形成 / 净出口贡献分别为 <b class="num">' +
        D.cons[qi].toFixed(1) + '% / ' + D.cap[qi].toFixed(1) + '% / ' + D.nex[qi].toFixed(1) + '%</b>。' +
        '行业层面，<b class="hl">' + best.n + '</b> 增长最快（<b>' + sgn(best.g) + '%</b>），<b class="hl">' + worst.n + '</b> 最弱（<b>' + sgn(worst.g) + '%</b>）。'
      : '<b>' + Q[qi] + ' 速读（累计）</b>&nbsp;&nbsp;GDP 累计 <b class="num">' + fmtWan(D.gdp[qi]) + ' 万亿元</b>，累计同比 <b class="num">' + sgn(D.yoyG[qi]) + '%</b>；' +
        '第三产业占比 <b class="num">' + D.s3[qi].toFixed(1) + '%</b>、贡献 <b class="num">' + D.pc3[qi].toFixed(1) + '%</b>；消费 / 资本形成 / 净出口累计贡献分别为 <b class="num">' +
        D.cons[qi].toFixed(1) + '% / ' + D.cap[qi].toFixed(1) + '% / ' + D.nex[qi].toFixed(1) + '%</b>。' +
        '行业层面按累计增速，<b class="hl">' + best.n + '</b> 最快（<b>' + sgn(best.g) + '%</b>），<b class="hl">' + worst.n + '</b> 最弱（<b>' + sgn(worst.g) + '%</b>）。';
    el('na-brief').innerHTML = b;
  }
  function renderTitles() {
    var cur = state.mode === 'cur', suffix = cur ? '当季值' : '累计值';
    el('t1').textContent = 'GDP ' + suffix + '（现价）与同比增速';
    el('s1').textContent = '柱：' + suffix + '规模（亿元）· 线：' + (cur ? '当季' : '累计') + '同比（%）';
    el('t3').textContent = '三次产业结构（' + suffix + '）';
    el('s3').textContent = '堆叠：增加值（亿元）· 线：三产占比（%）';
    el('t4').textContent = '三次产业同比增速（' + suffix + '）';
    el('t5').textContent = '三次产业贡献率（' + suffix + '）';
    el('t6').textContent = '三大需求对 GDP 增长的贡献率（' + suffix + '）';
    el('s6').textContent = '三大需求贡献率走势（%），可为负';
    el('t7').textContent = '行业增加值同比增速（' + suffix + '）';
    el('s7').textContent = '12 个行业 · 按' + (cur ? '当季' : '累计') + '增速排序 · 悬停查看规模';
  }

  /* ---------- 渲染 ---------- */
  var ch1 = mk('ch1'), ch2 = mk('ch2'), ch3 = mk('ch3'),
      ch4 = mk('ch4'), ch5 = mk('ch5'), ch6 = mk('ch6'), ch7 = mk('ch7');

  function pinTips() {
    window.requestAnimationFrame(function () {
      try {
        ch1.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: state.qi });
        ch3.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: state.qi });
        ch5.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: state.qi });
      } catch (e) {}
    });
  }
  function renderSlider() {
    var r = el('na-range');
    r.value = state.qi;
    var p = state.qi / (N - 1) * 100;
    r.style.background = 'linear-gradient(to right,' + THEME.sliderFill + ' 0%,' + THEME.sliderFill + ' ' + p + '%,' + THEME.sliderTrack + ' ' + p + '%)';
  }
  function render() {
    computeDerived();
    el('q-chip').textContent = Q[state.qi];
    el('mode-cur').className = state.mode === 'cur' ? 'on' : '';
    el('mode-cum').className = state.mode === 'cum' ? 'on' : '';
    renderSlider();
    renderKpis();
    renderBrief();
    renderTitles();
    ch1.setOption(opt1(), true);
    ch2.setOption(opt2(), true);
    ch3.setOption(opt3(), true);
    ch4.setOption(opt4(), true);
    ch5.setOption(opt5(), true);
    ch6.setOption(opt6(), true);
    ch7.setOption(opt7(), true);
    pinTips();
  }

  /* ---------- 交互 ---------- */
  function setQuarter(i, fromUser) {
    state.qi = Math.max(0, Math.min(N - 1, i));
    render();
    if (fromUser) saveState();
  }
  function setMode(m) {
    if (state.mode === m) return;
    state.mode = m;
    render();
    saveState();
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
  el('mode-cur').addEventListener('click', function () { setMode('cur'); });
  el('mode-cum').addEventListener('click', function () { setMode('cum'); });
  el('btn-play').addEventListener('click', togglePlay);
  el('btn-reset').addEventListener('click', function () {
    stopPlay(); state.mode = 'cur'; state.qi = N - 1; render(); saveState();
  });
  el('btn-prev').addEventListener('click', function () { setQuarter(state.qi - 1, true); });
  el('btn-next').addEventListener('click', function () { setQuarter(state.qi + 1, true); });
  el('na-range').addEventListener('input', function () { setQuarter(+this.value, true); });

  [ch1, ch2, ch3, ch4, ch5, ch6].forEach(function (c) {
    c.on('click', function (p) {
      if (typeof p.dataIndex === 'number') setQuarter(p.dataIndex, true);
    });
  });

  window.addEventListener('zcode:set_globals', function (ev) {
    try {
      var pc = ev.detail && ev.detail.globals && ev.detail.globals.widgetState && ev.detail.globals.widgetState.privateContent;
      if (pc && typeof pc.qi === 'number') { state.qi = pc.qi; state.mode = pc.mode === 'cum' ? 'cum' : 'cur'; render(); }
    } catch (e) {}
  });

  window.addEventListener('resize', function () {
    Object.keys(charts).forEach(function (k) { charts[k].resize(); });
  });
  window.addEventListener('load', function () {
    Object.keys(charts).forEach(function (k) { charts[k].resize(); });
  });

  render();
})();
"""


# =====================================================================
# 四、组装与输出
# =====================================================================

def build_html(data, echarts_tag):
    data_json = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    fragment = (TEMPLATE
                .replace('/*__STYLE__*/', CSS)
                .replace('__ECHARTS__', echarts_tag)
                .replace('/*__DATA__*/', data_json)
                .replace('/*__APP__*/', APP_JS))
    return ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>国民经济核算 · 数据大屏</title>\n</head>\n<body>\n'
            + fragment + '\n</body>\n</html>\n')


def main():
    no_open = '--no-open' in sys.argv
    folder = find_data_folder()
    print('数据文件夹：%s' % folder)
    print('正在解析六张季度数据表 …')
    data = load_data(folder)

    quarters = data['quarters']
    S = data['series']
    i = quarters.index('2025Q3')
    print('解析完成：%d 个季度（%s — %s）。抽样核对 2025Q3：' % (len(quarters), quarters[0], quarters[-1]))
    checks = [
        ('GDP 现价当季', S['gdpCur'][i], 354106.2),
        ('GDP 不变价当季', S['gdpRealCur'][i], 341216.5),
        ('GDP 同比指数', S['gdpIdxCur'][i], 104.8),
        ('GDP 环比', S['qoq'][i], 1.1),
        ('消费/资本/净出口贡献', (S['consCur'][i], S['capCur'][i], S['nexCur'][i]), (54.1, 15.9, 30.0)),
        ('第三产业贡献率', S['pc3Cur'][i], 61.8),
        ('信息传输业指数', data['industries']['信息传输、软件和信息技术服务业']['idxCur'][i], 111.7),
    ]
    ok = True
    for name, got, want in checks:
        match = abs(got - want) < 0.05 if isinstance(got, float) else got == want
        ok = ok and match
        print('  %-14s 取值 %-24s 期望 %-14s %s' % (name, got, want, 'OK' if match else '!!'))
    if not ok:
        raise SystemExit('抽样校验未通过，请确认六张 CSV 为国家统计局原始导出文件。')

    echarts_tag = get_echarts_tag()
    html = build_html(data, echarts_tag)

    with open(OUTPUT_HTML, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)
    print('已生成：%s（%.0f KB）' % (OUTPUT_HTML, len(html.encode("utf-8")) / 1024))
    if not no_open:
        try:
            webbrowser.open(OUTPUT_HTML.resolve().as_uri())
            print('已在默认浏览器中打开大屏。')
        except Exception as e:
            print('自动打开浏览器失败（%s），请手动双击该 HTML 文件。' % e)
    print('完成。')


if __name__ == '__main__':
    main()

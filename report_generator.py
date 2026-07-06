"""
报告生成模块
============
1. 控制台格式化输出（清晰结构化）
2. HTML 报告文件生成（YYYYMMDD-股票分析报告.html）
3. CSV 归档保存（每日数据本地存档）
"""

import os
import csv
import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from config import OUTPUT_DIR, CSV_ARCHIVE_DIR, DISCLAIMER

logger = logging.getLogger(__name__)


# ================================================================
# 一、控制台报告
# ================================================================
def print_console_report(watch_results: dict, hot_results: list, run_time: str,
                        daily_summary: str = ""):
    """
    在控制台打印清晰结构化分析报告。
    """
    sep = "=" * 72
    sub = "-" * 48

    print("\n" + sep)
    print("  📈 股票自动分析日报")
    print(f"  生成时间: {run_time}")
    print(sep)

    # ---- 自选股分析 ----
    print(f"\n  【一、自选股跟踪分析】")
    for name, data in watch_results.items():
        analysis = data.get("analysis", {})
        quote = data.get("quote") or {}
        tech = analysis.get("technical", {})

        print(f"\n  {sub}")
        print(f"  ▸ {name}（{data.get('code', '')}）")

        if quote:
            print(f"    最新价: ¥{quote.get('price', 'N/A')}  "
                  f"涨跌幅: {_color_pct(quote.get('pct_change', 0))}  "
                  f"成交额: {_fmt_amount(quote.get('amount', 0))}  "
                  f"换手率: {quote.get('turnover', 'N/A')}%")

        # 技术指标
        ma = tech.get("ma_trend", {})
        macd = tech.get("macd_trend", {})
        returns = tech.get("returns", {})
        sr = tech.get("sr_levels", {})

        if ma:
            print(f"    MA5: {ma.get('ma5', 'N/A')}  "
                  f"MA10: {ma.get('ma10', 'N/A')}  "
                  f"MA20: {ma.get('ma20', 'N/A')}")
            print(f"    均线状态: {ma.get('alignment', 'N/A')}  "
                  f"价格 vs MA20: {ma.get('price_vs_ma20', 'N/A')}")
            print(f"    MA5-MA10: {ma.get('ma5_cross_ma10', 'N/A')}  "
                  f"MA5-MA20: {ma.get('ma5_cross_ma20', 'N/A')}")

        if macd:
            print(f"    MACD: DIF={macd.get('dif', 'N/A')}  "
                  f"DEA={macd.get('dea', 'N/A')}  "
                  f"柱={macd.get('macd_bar', 'N/A')}  "
                  f"{macd.get('dif_position', '')}  {macd.get('dif_direction', '')}")
            if macd.get("golden_cross"):
                print(f"    ✚ 近3日金叉信号")
            if macd.get("death_cross"):
                print(f"    ✖ 近3日死叉信号")

        if returns:
            ret_str = "  ".join(
                f"{k}: {_color_pct(v)}" if v is not None else f"{k}: N/A"
                for k, v in returns.items()
            )
            print(f"    近期涨跌幅: {ret_str}")

        if sr:
            print(f"    短期支撑: ¥{sr.get('support', 'N/A')}  "
                  f"短期压力: ¥{sr.get('resistance', 'N/A')}")

        # 操作参考
        suggestion = analysis.get("suggestion", "—")
        risk = analysis.get("risk_note", "")
        print(f"\n    📋 参考建议: {suggestion}")
        if risk:
            print(f"    信号摘要: {risk}")

    # ---- 热门涨幅个股 ----
    print(f"\n\n  【二、当日热门涨幅个股】")
    if not hot_results:
        print("    暂无符合条件的涨幅靠前个股")
    else:
        print(f"\n  {'序号':<5} {'名称':<10} {'代码':<8} {'涨幅':<8} {'成交额':<12} {'市值':<10} {'板块'}")
        print(f"  {'—'*5} {'—'*10} {'—'*8} {'—'*8} {'—'*12} {'—'*10} {'—'*18}")
        for i, stock in enumerate(hot_results, 1):
            mc = stock.get('market_cap', 0)
            mc_str = f"{mc:.0f}亿" if mc > 0 else "—"
            pe = stock.get('pe', 0)
            pe_str = f" PE{pe:.0f}" if pe > 0 else ""
            print(f"  {i:<5} {stock['name']:<10} {stock['code']:<8} "
                  f"{_color_pct(stock['pct_change']):<8} "
                  f"{_fmt_amount(stock['amount']):<12} "
                  f"{mc_str:<10} "
                  f"{stock.get('sector', '')}")
            print(f"         ↳ {stock.get('driver_note', '')}{pe_str}")

    # ---- 今日投资建议 ----
    if daily_summary:
        print(f"\n\n  【三、今日投资建议】")
        print(f"  {sub}")
        for line in daily_summary.split("\n"):
            print(f"  {line.strip()}")
        print(f"  {sub}")

    # ---- 免责声明 ----
    print(f"\n  {sep}")
    print(f"  {DISCLAIMER}")
    print(f"  {sep}\n")


# ================================================================
# 二、HTML 报告
# ================================================================
def generate_html_report(watch_results: dict, hot_results: list,
                         run_time: str, daily_summary: str = "") -> str:
    """
    生成 HTML 格式分析报告，保存到 D:/GUPIAO。

    返回:
        生成的文件路径
    """
    today_str = datetime.now().strftime("%Y%m%d")
    filename = f"{today_str}-股票分析报告.html"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)

    html = _build_html(watch_results, hot_results, run_time, daily_summary)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("HTML 报告已保存: %s", filepath)
    return filepath


def _build_html(watch_results: dict, hot_results: list, run_time: str,
                daily_summary: str = "") -> str:
    """构建 HTML 页面内容"""

    # --- 自选股表格行 ---
    watch_rows = ""
    for name, data in watch_results.items():
        analysis = data.get("analysis", {})
        quote = data.get("quote") or {}
        tech = analysis.get("technical", {})
        ma = tech.get("ma_trend", {})
        macd = tech.get("macd_trend", {})
        returns = tech.get("returns", {})
        sr = tech.get("sr_levels", {})

        pct = quote.get("pct_change", 0)
        pct_class = "up" if pct >= 0 else "down"
        pct_str = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"

        ret_1d = returns.get("1d")
        ret_3d = returns.get("3d")
        ret_1d_str = f"+{ret_1d:.2f}%" if ret_1d and ret_1d >= 0 else f"{ret_1d:.2f}%" if ret_1d else "N/A"
        ret_3d_str = f"+{ret_3d:.2f}%" if ret_3d and ret_3d >= 0 else f"{ret_3d:.2f}%" if ret_3d else "N/A"

        macd_signal = ""
        if macd.get("golden_cross"):
            macd_signal += " ✚金叉"
        if macd.get("death_cross"):
            macd_signal += " ✖死叉"

        suggestion = analysis.get("suggestion", "—")
        risk = analysis.get("risk_note", "—")

        # 均线状态颜色
        al = ma.get('alignment','')
        al_class = 'signal-bull' if '多头' in al else ('signal-bear' if '空头' in al else 'signal-neut')
        # MACD方向颜色
        md_dir = macd.get('dif_direction','')
        md_class = 'signal-bull' if '向上' in md_dir else ('signal-bear' if '向下' in md_dir else '')
        # 建议色块
        sug = analysis.get('suggestion','')
        sug_class = 'sug-bull' if '偏多' in sug or '🟢' in sug else ('sug-bear' if '偏空' in sug or '🔴' in sug else 'sug-neut')
        watch_rows += f"""
        <tr>
            <td class="left"><strong>{name}</strong><br><span class="code">{data.get('code', '')}</span></td>
            <td class="right bold">¥{quote.get('price', 'N/A')}</td>
            <td class="{pct_class}">{pct_str}</td>
            <td class="right">{quote.get('open', 'N/A')}/{quote.get('high', 'N/A')}/{quote.get('low', 'N/A')}</td>
            <td class="right">{_fmt_amount(quote.get('amount', 0))}</td>
            <td class="right">{quote.get('turnover', 'N/A')}%</td>
            <td class="right">{ret_1d_str}/{ret_3d_str}</td>
            <td class="right">MA5:{ma.get('ma5', 'N/A')}<br>MA10:{ma.get('ma10', 'N/A')}<br>MA20:{ma.get('ma20', 'N/A')}</td>
            <td class="{al_class}">{al}<br>{ma.get('ma5_cross_ma10', '')} {ma.get('ma5_cross_ma20', '')}</td>
            <td class="{md_class}">DIF:{macd.get('dif', 'N/A')}<br>{macd.get('dif_position', '')}<br>{md_dir}{macd_signal}</td>
            <td class="right bold">支撑 ¥{sr.get('support', 'N/A')}<br>压力 ¥{sr.get('resistance', 'N/A')}</td>
            <td class="left"><div class="sug-box {sug_class}">{suggestion}<br><span class="risk-note">{risk}</span></div></td>
        </tr>"""

    # --- 热门个股表格行 ---
    hot_rows = ""
    for i, stock in enumerate(hot_results, 1):
        pct = stock.get("pct_change", 0)
        pct_class = "up" if pct >= 0 else "down"
        pct_str = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"

        mc = stock.get("market_cap", 0)
        mc_str = f"{mc:.0f}亿" if mc > 0 else "—"
        pe = stock.get("pe", 0)
        pe_warn = "pe-warn" if pe > 200 else ""
        pe_str = f"<span class='{pe_warn}'>PE(TTM){pe:.0f}</span>" if pe > 0 else "—"
        turnover = stock.get('turnover', 0)
        to_warn = " <span class='to-warn'>⚠高换手{:.0f}%</span>".format(turnover) if turnover > 20 else ""
        hot_rows += f"""
        <tr>
            <td>{i}</td>
            <td class="left"><strong>{stock['name']}</strong><br><span class="code">{stock['code']}</span></td>
            <td class="{pct_class}">{pct_str}</td>
            <td class="right">{_fmt_amount(stock.get('amount', 0))}</td>
            <td class="right">{mc_str}</td>
            <td>{pe_str}</td>
            <td class="right">{stock.get('turnover', 'N/A')}%{to_warn}</td>
            <td>{stock.get('sector', '')}</td>
            <td class="left driver">{stock.get('driver_note', '')}</td>
        </tr>"""

    # --- 完整 HTML（三色分区+卡片布局+表格可视化+目录跳转）---
    today = datetime.now().strftime('%Y%m%d')
    # 处理 summary 中的 HTML 标记
    summary_html = daily_summary if daily_summary else '暂无'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{today}-股票分析报告</title>
<style>
    :root {{
        --bg: #f5f6f8; --card: #ffffff; --border: #e2e8f0;
        --text: #2d3748; --muted: #718096;
        --blue: #2b6cb0; --blue-light: #ebf4ff; --blue-dark: #1a365d;
        --green: #38a169; --green-light: #f0fff4;
        --red: #e53e3e; --red-light: #fff5f5;
        --orange: #dd6b20; --orange-light: #fffaf0;
        --yellow-warn: #fefcbf;
        --gray: #4a5568; --gray-light: #f7fafc;
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{
        font-family:"Microsoft YaHei","PingFang SC",-apple-system,sans-serif;
        background:var(--bg); color:var(--text); line-height:1.6;
        font-size:14px; padding:0 5%;
    }}
    @media (max-width:800px) {{ body {{ padding:0 8px; }} }}
    .container {{ max-width:1500px; margin:0 auto; }}

    /* ═══ 导航 ═══ */
    .toc {{
        position:sticky; top:0; z-index:200;
        background:rgba(255,255,255,0.97); border-bottom:2px solid var(--blue);
        padding:10px 5%; margin:0 -5% 20px -5%;
        display:flex; align-items:center; gap:28px; flex-wrap:wrap;
        backdrop-filter:blur(10px); box-shadow:0 2px 8px rgba(0,0,0,0.06);
    }}
    .toc-logo {{ font-weight:800; font-size:15px; color:var(--blue-dark); white-space:nowrap; }}
    .toc a {{
        color:var(--muted); text-decoration:none; font-size:13px;
        padding:4px 12px; border-radius:14px; transition:all 0.2s; white-space:nowrap;
    }}
    .toc a:hover, .toc a.active {{ background:var(--blue); color:#fff; }}

    /* ═══ Header ═══ */
    .header {{
        background:linear-gradient(135deg, #1a365d 0%, #2b6cb0 50%, #3182ce 100%);
        border-radius:14px; padding:28px 40px; margin:0 0 24px 0;
        color:#fff; position:relative; overflow:hidden;
    }}
    .header h1 {{ font-size:24px; font-weight:800; position:relative; }}
    .header .time {{ opacity:0.7; font-size:13px; margin-top:4px; position:relative; }}

    /* ═══ 分区标题 ═══ */
    .sec-h1 {{
        font-size:17px; font-weight:700; color:#fff; background:var(--blue-dark);
        padding:8px 18px; border-radius:6px; margin:28px 0 12px;
        display:inline-block;
    }}
    .sec-h2 {{
        font-size:15px; font-weight:700; color:var(--blue); background:var(--blue-light);
        padding:6px 14px; border-radius:4px; margin:16px 0 8px;
    }}
    .sec-card {{
        background:var(--card); border:1px solid var(--border);
        border-radius:10px; padding:20px 24px; margin-bottom:16px;
        box-shadow:0 2px 8px rgba(0,0,0,0.04);
    }}
    .sec-card.blue {{ border-left:4px solid var(--blue); }}
    .sec-card.green {{ border-left:4px solid var(--green); }}
    .sec-card.orange {{ border-left:4px solid var(--orange); }}
    .sec-card.gray {{ border-left:4px solid var(--gray); }}

    /* ═══ 表格 ═══ */
    .tbl-wrap {{ overflow-x:auto; }}
    table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    th {{
        background:var(--blue-dark); color:#fff; font-weight:600;
        padding:10px 8px; text-align:center; border-right:1px solid rgba(255,255,255,0.1);
        white-space:nowrap; font-size:11px; position:sticky; top:0;
    }}
    td {{
        padding:8px; border-bottom:1px solid #f0f2f5; text-align:center;
    }}
    tr:nth-child(even) td {{ background:#fafbfc; }}
    tr:nth-child(odd) td {{ background:#fff; }}
    tr:hover td {{ background:#ebf4ff !important; }}
    td.left {{ text-align:left; }}
    td.right {{ text-align:right; }}

    /* ═══ 颜色标注 ═══ */
    .up {{ color:var(--red); font-weight:700; }}
    .down {{ color:var(--green); font-weight:700; }}
    .bold {{ font-weight:700; }}
    .code {{ color:var(--muted); font-size:10px; font-family:Consolas,monospace; }}
    .pe-warn {{ background:var(--yellow-warn); color:#975a16; padding:1px 6px; border-radius:3px; font-weight:700; font-size:11px; }}
    .to-warn {{ color:var(--red); font-weight:700; font-size:11px; }}
    .signal-bull {{ color:var(--blue); font-weight:700; }}
    .signal-bear {{ color:var(--red); font-weight:700; }}
    .signal-neut {{ color:var(--orange); font-weight:700; }}

    /* ═══ 消息面 ═══ */
    .news-bull {{
        background:var(--green-light); border-left:4px solid var(--green);
        padding:10px 16px; margin:8px 0; border-radius:0 6px 6px 0; font-size:12px;
    }}
    .news-bear {{
        background:var(--red-light); border-left:4px solid var(--red);
        padding:10px 16px; margin:8px 0; border-radius:0 6px 6px 0; font-size:12px;
    }}
    .news-other {{
        background:var(--blue-light); border-left:4px solid var(--blue);
        padding:10px 16px; margin:8px 0; border-radius:0 6px 6px 0; font-size:12px;
    }}

    /* ═══ 预警 ═══ */
    .alert {{
        background:var(--red-light); border:1px solid #fc8181;
        border-left:4px solid var(--red); border-radius:6px;
        padding:10px 16px; margin:8px 0; font-size:12px;
    }}
    .warn-box {{
        background:var(--orange-light); border:1px solid #f6ad55;
        border-left:4px solid var(--orange); border-radius:6px;
        padding:8px 14px; margin:6px 0; font-size:12px;
    }}

    /* ═══ 建议色块 ═══ */
    .sug-box {{
        display:inline-block; background:var(--blue-light); border:1px solid #bee3f8;
        border-radius:6px; padding:8px 14px; margin:4px 0; font-size:12px;
        max-width:360px;
    }}
    .sug-bull {{ border-color:#38a169; background:var(--green-light); }}
    .sug-bear {{ border-color:#e53e3e; background:var(--red-light); }}
    .sug-neut {{ border-color:#dd6b20; background:var(--orange-light); }}

    /* ═══ 仓位数字 ═══ */
    .pos-num {{ font-size:20px; font-weight:800; color:var(--blue); }}

    /* ═══ 免责 ═══ */
    .disclaimer {{
        background:#fffff0; border:1px solid #f6e05e; border-radius:8px;
        padding:14px 22px; margin-top:24px; font-size:12px; color:#b7791f; text-align:center;
    }}
    .footer {{
        text-align:center; color:var(--muted); font-size:11px; margin:24px 0; opacity:0.5;
    }}

    @media (max-width:1100px) {{ .toc {{ gap:12px; font-size:11px; }} }}
    @media print {{
        body {{ background:#fff; padding:0; }} .toc {{ display:none; }}
    }}
</style>
</head>
<body>

<nav class="toc" id="toc">
    <span class="toc-logo">📈 股票日报</span>
    <a href="#sec1">自选股分析</a>
    <a href="#sec2">热门涨幅个股</a>
    <a href="#sec3">投资建议</a>
    <a href="#sec4">半导体深度</a>
</nav>

<div class="container">

<div class="header">
    <h1>📈 股票自动分析日报</h1>
    <div class="time">{run_time} &nbsp;|&nbsp; 数据源: 腾讯/新浪公开接口 &nbsp;|&nbsp; 仅供参考</div>
</div>

<section id="sec1">
    <div class="sec-h1">01 · 自选股跟踪分析</div>
    <div class="sec-card gray">
        <div class="tbl-wrap"><table>
        <thead><tr>
            <th>名称/代码</th><th>最新价</th><th>涨跌幅</th>
            <th>今开/最高/最低</th><th>成交额</th><th>换手</th>
            <th>近1/3日</th><th>MA5/10/20</th><th>均线状态</th><th>MACD</th><th>支撑/压力</th><th>参考建议</th>
        </tr></thead>
        <tbody>{watch_rows}</tbody>
        </table></div>
    </div>
</section>

<section id="sec2">
    <div class="sec-h1">02 · 当日热门涨幅个股</div>
    <div class="sec-card blue">
        <div class="tbl-wrap"><table>
        <thead><tr>
            <th>#</th><th>名称/代码</th><th>涨幅</th><th>成交额</th>
            <th>总市值</th><th>PE(TTM)</th><th>换手</th><th>板块</th><th>驱动逻辑</th>
        </tr></thead>
        <tbody>{hot_rows}</tbody>
        </table></div>
        {f'<p style="margin-top:14px;color:var(--muted);font-size:12px;">◆ 共筛选 {len(hot_results)} 只值得关注的热门标的</p>' if hot_results else '<p style="margin-top:14px;color:var(--muted);">今日暂无符合条件的个股</p>'}
    </div>
</section>

<section id="sec3">
    <div class="sec-h1">03 · 今日投资建议</div>
    <div class="sec-card blue" style="font-size:14px;line-height:2.2;white-space:pre-wrap;padding:24px 30px;">{summary_html}</div>
</section>

<section id="sec4" style="display:none;"></section>

<div class="disclaimer">⚠️ <strong>免责声明：</strong>{DISCLAIMER}</div>
<div class="footer">本报告由股票自动分析程序生成 &nbsp;|&nbsp; 数据来源: 腾讯/新浪公开行情接口</div>

</div>

<script>
document.querySelectorAll('.toc a').forEach(a=>{{
    a.addEventListener('click',e=>{{e.preventDefault();const t=document.querySelector(a.getAttribute('href'));if(t)window.scrollTo({{top:t.offsetTop-60,behavior:'smooth'}});}});
}});
window.addEventListener('scroll',()=>{{
    let c='';document.querySelectorAll('section').forEach(s=>{{if(window.scrollY>=s.offsetTop-120)c=s.id;}});
    document.querySelectorAll('.toc a').forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+c));
}});
</script>
</body>
</html>"""


# ================================================================
# 三、CSV 存档
# ================================================================
def save_csv_archive(watch_results: dict, hot_results: list):
    """
    将当日数据保存到本地 CSV 存档，方便回溯历史 K 线数据。

    生成两个文件:
      1. watch_archive.csv —— 自选股每日快照（追加模式）
      2. hot_stocks_YYYYMMDD.csv —— 当日热门个股明细
    """
    os.makedirs(CSV_ARCHIVE_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")

    # ---- 自选股快照 ----
    watch_file = os.path.join(CSV_ARCHIVE_DIR, "watch_archive.csv")
    file_exists = os.path.exists(watch_file)

    with open(watch_file, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "日期", "名称", "代码",
                "开盘", "最高", "最低", "收盘",
                "涨跌幅%", "成交量(手)", "成交额(元)", "换手率%",
                "MA5", "MA10", "MA20",
                "均线状态", "MACD_DIF", "MACD_DEA", "MACD_BAR",
                "支撑位", "压力位", "操作参考",
            ])

        for name, data in watch_results.items():
            analysis = data.get("analysis", {})
            quote = data.get("quote") or {}
            tech = analysis.get("technical", {})
            ma = tech.get("ma_trend", {})
            macd = tech.get("macd_trend", {})
            sr = tech.get("sr_levels", {})

            writer.writerow([
                today_str,
                name,
                data.get("code", ""),
                quote.get("open", ""),
                quote.get("high", ""),
                quote.get("low", ""),
                quote.get("price", ""),
                quote.get("pct_change", ""),
                quote.get("volume", ""),
                quote.get("amount", ""),
                quote.get("turnover", ""),
                ma.get("ma5", ""),
                ma.get("ma10", ""),
                ma.get("ma20", ""),
                ma.get("alignment", ""),
                macd.get("dif", ""),
                macd.get("dea", ""),
                macd.get("macd_bar", ""),
                sr.get("support", ""),
                sr.get("resistance", ""),
                analysis.get("suggestion", ""),
            ])

    logger.info("自选股 CSV 存档已更新: %s", watch_file)

    # ---- 热门个股明细 ----
    hot_file = os.path.join(CSV_ARCHIVE_DIR, f"hot_stocks_{today_str}.csv")
    with open(hot_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "序号", "名称", "代码", "最新价", "涨跌幅%",
            "成交额(元)", "换手率%", "所属板块", "上涨驱动逻辑",
        ])
        for i, stock in enumerate(hot_results, 1):
            writer.writerow([
                i,
                stock.get("name", ""),
                stock.get("code", ""),
                stock.get("price", ""),
                stock.get("pct_change", ""),
                stock.get("amount", ""),
                stock.get("turnover", ""),
                stock.get("sector", ""),
                stock.get("driver_note", ""),
            ])

    logger.info("热门个股 CSV 已保存: %s", hot_file)


# ================================================================
# 四、K 线历史存档（保存原始日 K 线数据）
# ================================================================
def save_kline_archive(name: str, code: str, history: Optional[pd.DataFrame]):
    """
    将每只自选股的原始日 K 线数据追加保存到独立 CSV，
    方便后续回溯完整 K 线历史。
    """
    if history is None or history.empty:
        return

    os.makedirs(CSV_ARCHIVE_DIR, exist_ok=True)
    filepath = os.path.join(CSV_ARCHIVE_DIR, f"kline_{code}_{name}.csv")

    # 如果已有存档，去重合并
    if os.path.exists(filepath):
        existing = pd.read_csv(filepath, encoding="utf-8-sig")
        if "date" in existing.columns:
            existing["date"] = pd.to_datetime(existing["date"])
            existing_dates = set(existing["date"].dt.strftime("%Y-%m-%d"))
            new_rows = history[~history["date"].dt.strftime("%Y-%m-%d").isin(existing_dates)]
            if not new_rows.empty:
                combined = pd.concat([existing, new_rows], ignore_index=True)
                combined = combined.sort_values("date").drop_duplicates(subset=["date"])
                combined.to_csv(filepath, index=False, encoding="utf-8-sig")
                logger.info("K线存档更新 %s: +%d 条", name, len(new_rows))
            return

    history.to_csv(filepath, index=False, encoding="utf-8-sig")
    logger.info("K线存档初始化 %s: %d 条记录", name, len(history))


# ================================================================
# 辅助格式化函数
# ================================================================
def _color_pct(val) -> str:
    """带颜色标记的涨跌幅"""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if v > 0:
            return f"🔴 +{v:.2f}%"
        elif v < 0:
            return f"🟢 {v:.2f}%"
        else:
            return f"  0.00%"
    except (ValueError, TypeError):
        return str(val)


def _fmt_amount(val) -> str:
    """格式化成交额（自动转换亿/万）"""
    try:
        v = float(val)
        if v >= 1e8:
            return f"{v / 1e8:.2f} 亿"
        elif v >= 1e4:
            return f"{v / 1e4:.2f} 万"
        else:
            return f"{v:.0f} 元"
    except (ValueError, TypeError):
        return str(val)

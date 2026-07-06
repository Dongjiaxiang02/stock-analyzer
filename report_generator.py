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

        watch_rows += f"""
        <tr>
            <td><strong>{name}</strong><br><span class="code">{data.get('code', '')}</span></td>
            <td>¥{quote.get('price', 'N/A')}</td>
            <td class="{pct_class}">{pct_str}</td>
            <td>{quote.get('open', 'N/A')} / {quote.get('high', 'N/A')} / {quote.get('low', 'N/A')}</td>
            <td>{_fmt_amount(quote.get('amount', 0))}</td>
            <td>{quote.get('turnover', 'N/A')}%</td>
            <td>{ret_1d_str} / {ret_3d_str}</td>
            <td>MA5:{ma.get('ma5', 'N/A')}<br>MA10:{ma.get('ma10', 'N/A')}<br>MA20:{ma.get('ma20', 'N/A')}</td>
            <td>{ma.get('alignment', 'N/A')}<br>{ma.get('ma5_cross_ma10', '')} {ma.get('ma5_cross_ma20', '')}</td>
            <td>DIF:{macd.get('dif', 'N/A')}<br>{macd.get('dif_position', '')}<br>{macd.get('dif_direction', '')}{macd_signal}</td>
            <td>支撑:¥{sr.get('support', 'N/A')}<br>压力:¥{sr.get('resistance', 'N/A')}</td>
            <td class="suggestion">{suggestion}<br><span class="risk-note">{risk}</span><br><span style="font-size:9px;color:#3182ce;">{analysis.get('fundamental','')[:60]}...</span></td>
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
            <td><strong>{stock['name']}</strong><br><span class="code">{stock['code']}</span></td>
            <td class="{pct_class}">{pct_str}</td>
            <td>{_fmt_amount(stock.get('amount', 0))}</td>
            <td>{mc_str}</td>
            <td>{pe_str}</td>
            <td>{stock.get('turnover', 'N/A')}%{to_warn}</td>
            <td>{stock.get('sector', '')}</td>
            <td class="driver">{stock.get('driver_note', '')}</td>
        </tr>"""

    # --- 完整 HTML（科技感深色主题 + 目录导航）---
    today = datetime.now().strftime('%Y%m%d')
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{today}-股票分析报告</title>
<style>
    :root {{
        --bg: #f0f4f8; --surface: #f8fafc; --card: #ffffff;
        --border: #e2e8f0; --text: #1a202c; --muted: #718096;
        --accent: #3182ce; --accent-light: #ebf4ff;
        --up: #e53e3e; --down: #38a169;
        --gold: #b7791f; --purple: #805ad5;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", "Segoe UI", sans-serif;
        background: var(--bg); color: var(--text); line-height: 1.6;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 0 24px; }}

    /* ── 顶部横向目录 ── */
    .toc {{
        position: sticky; top: 0; z-index: 100;
        background: rgba(255,255,255,0.95); border-bottom: 1px solid var(--border);
        padding: 10px 28px; margin-bottom: 20px;
        backdrop-filter: blur(10px);
        display: flex; align-items: center; gap: 24px;
    }}
    .toc-title {{
        font-size: 11px; letter-spacing: 1.5px; color: var(--muted);
        font-weight: 600; white-space: nowrap;
    }}
    .toc a {{
        color: var(--muted); text-decoration: none;
        font-size: 13px; transition: color 0.15s; white-space: nowrap;
    }}
    .toc a:hover, .toc a.active {{ color: var(--accent); font-weight: 600; }}
    .toc-dot {{ display: none; }}

    /* ── Header ── */
    .header {{
        background: linear-gradient(135deg, #1a365d 0%, #2b6cb0 50%, #3182ce 100%);
        border-radius: 14px; padding: 32px 44px; margin: 24px 0 30px;
        color: #fff; position: relative; overflow: hidden;
    }}
    .header::before {{
        content: ''; position: absolute; top: -60%; right: -5%;
        width: 350px; height: 350px;
        background: radial-gradient(circle, rgba(255,255,255,0.06) 0%, transparent 70%);
        border-radius: 50%;
    }}
    .header h1 {{
        font-size: 26px; font-weight: 800; letter-spacing: -0.5px;
        color: #fff; margin-bottom: 4px; position: relative;
    }}
    .header .time {{ opacity: 0.75; font-size: 13px; position: relative; }}
    .header .badge {{
        display: inline-block; background: rgba(255,255,255,0.15);
        border: 1px solid rgba(255,255,255,0.25); border-radius: 20px;
        padding: 3px 12px; font-size: 11px; margin-left: 10px; vertical-align: middle;
    }}

    /* ── Sections ── */
    section {{ scroll-margin-top: 40px; margin-bottom: 28px; }}
    .section-title {{
        font-size: 18px; font-weight: 700; color: #2d3748;
        margin-bottom: 14px; padding-left: 12px;
        border-left: 3px solid var(--accent);
        display: flex; align-items: center; gap: 10px;
    }}
    .section-title .num {{
        font-size: 11px; color: var(--accent); background: var(--accent-light);
        padding: 2px 10px; border-radius: 12px; font-weight: 600;
    }}

    /* ── Cards ── */
    .card {{
        background: var(--card); border: 1px solid var(--border);
        border-radius: 10px; padding: 22px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.04);
        overflow-x: auto;
    }}

    /* ── Tables ── */
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th {{
        background: #f7fafc; color: var(--muted); font-weight: 600;
        padding: 11px 10px; text-align: left; border-bottom: 2px solid #e2e8f0;
        white-space: nowrap; font-size: 11px; letter-spacing: 0.3px;
    }}
    td {{
        padding: 10px; border-bottom: 1px solid #f0f2f5; vertical-align: middle;
    }}
    tr:hover td {{ background: #f7fafc; }}
    .code {{ color: var(--muted); font-size: 10px; font-family: 'SF Mono','Consolas',monospace; }}
    .up {{ color: var(--up); font-weight: 700; }}
    .down {{ color: var(--down); font-weight: 700; }}
    .suggestion {{ font-size: 12px; max-width: 340px; line-height: 1.5; }}
    .risk-note {{ color: var(--muted); font-size: 10px; }}
    .driver {{ font-size: 11px; color: var(--muted); max-width: 340px; }}
    .pe-warn {{ background: #fefcbf; color: #975a16; padding: 1px 6px; border-radius: 3px; font-weight: 700; }}
    .to-warn {{ color: #e53e3e; font-weight: 700; font-size: 10px; }}
    .alert-box {{ background: #fff5f5; border: 1px solid #fc8181; border-left: 4px solid #e53e3e;
        border-radius: 6px; padding: 10px 16px; margin: 8px 0; font-size: 12px; }}
    .news-bull {{ background: #f0fff4; border-left: 3px solid #38a169; padding: 8px 14px; margin: 6px 0; border-radius: 4px; }}
    .news-bear {{ background: #fff5f5; border-left: 3px solid #e53e3e; padding: 8px 14px; margin: 6px 0; border-radius: 4px; }}

    /* ── Summary card ── */
    .summary-card {{
        background: linear-gradient(135deg, #ebf8ff 0%, #f0fff4 100%);
        border: 1px solid #bee3f8; border-radius: 10px;
        padding: 26px 30px; line-height: 2; font-size: 14px;
    }}
    .summary-card .label {{
        display: inline-block; background: var(--accent-light);
        color: var(--accent); padding: 1px 10px; border-radius: 10px;
        font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-right: 4px;
    }}

    /* ── Disclaimer ── */
    .disclaimer {{
        background: #fffff0; border: 1px solid #f6e05e; border-radius: 8px;
        padding: 14px 22px; margin-top: 24px; font-size: 12px;
        color: var(--gold); text-align: center;
    }}

    /* ── Footer ── */
    .footer {{
        text-align: center; color: var(--muted); font-size: 11px;
        margin: 28px 0 20px; padding: 14px; opacity: 0.6;
    }}

    /* ── Responsive ── */
    @media (max-width: 1100px) {{ .toc {{ display: none; }} }}
    @media print {{
        .toc {{ display: none; }}
        body {{ background: #fff; }}
    }}
</style>
</head>
<body>

<!-- 目录导航 -->
<nav class="toc" id="toc">
    <div class="toc-title">◆ 目 录</div>
    <a href="#sec1"><span class="toc-dot"></span>自选股分析</a>
    <a href="#sec2"><span class="toc-dot"></span>热门涨幅个股</a>
    <a href="#sec3"><span class="toc-dot"></span>今日投资建议</a>
</nav>

<div class="container">

<div class="header">
    <h1>📈 股票自动分析日报</h1>
    <div class="time">{run_time}<span class="badge">● 实时数据</span></div>
</div>

<!-- 一、自选股 -->
<section id="sec1">
    <div class="section-title"><span class="num">01</span> 自选股跟踪分析</div>
    <div class="card card-glow">
        <table>
        <thead><tr>
            <th>名称/代码</th><th>最新价</th><th>涨跌幅</th>
            <th>今开/最高/最低</th><th>成交额</th><th>换手</th>
            <th>近1/3日</th><th>MA5/10/20</th>
            <th>均线状态</th><th>MACD</th>
            <th>支撑/压力</th><th>参考建议</th>
        </tr></thead>
        <tbody>{watch_rows}</tbody>
        </table>
    </div>
</section>

<!-- 二、热门个股 -->
<section id="sec2">
    <div class="section-title"><span class="num">02</span> 当日热门涨幅个股</div>
    <div class="card">
        <table>
        <thead><tr>
            <th>#</th><th>名称/代码</th><th>涨幅</th>
            <th>成交额</th><th>总市值</th><th>换手</th>
            <th>板块</th><th>驱动逻辑</th>
        </tr></thead>
        <tbody>{hot_rows}</tbody>
        </table>
        {f'<p style="margin-top:16px;color:var(--muted);font-size:12px;">◆ 共筛选出 {len(hot_results)} 只值得关注的热门标的</p>' if hot_results else '<p style="margin-top:16px;color:var(--muted);">今日暂无符合条件的个股</p>'}
    </div>
</section>

<!-- 三、投资建议 -->
<section id="sec3">
    <div class="section-title"><span class="num">03</span> 今日投资建议</div>
    <div class="summary-card">
        <div style="font-size:14px; white-space:pre-wrap;">{daily_summary if daily_summary else '暂无'}</div>
        <p style="margin-top:16px;color:var(--muted);font-size:11px;">以上分析仅基于公开行情数据的技术面推演，不构成投资建议。</p>
    </div>
</section>

<div class="disclaimer">
    ⚠️ <strong>免责声明：</strong>{DISCLAIMER}
</div>

<div class="footer">
    本报告由股票自动分析程序生成 &nbsp;|&nbsp; 数据来源: 腾讯/新浪公开行情接口 &nbsp;|&nbsp; 仅供参考
</div>

</div>

<script>
// 目录高亮当前滚动位置
const sections = document.querySelectorAll('section');
const links = document.querySelectorAll('.toc a');
window.addEventListener('scroll', () => {{
    let current = '';
    sections.forEach(s => {{ if(window.scrollY >= s.offsetTop - 120) current = s.id; }});
    links.forEach(a => {{
        a.classList.toggle('active', a.getAttribute('href') === '#' + current);
    }});
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

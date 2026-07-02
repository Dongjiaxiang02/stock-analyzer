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
def print_console_report(watch_results: dict, hot_results: list, run_time: str):
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
        print(f"\n  {'序号':<5} {'名称':<10} {'代码':<8} {'涨幅':<8} {'成交额':<14} {'板块'}")
        print(f"  {'—'*5} {'—'*10} {'—'*8} {'—'*8} {'—'*14} {'—'*20}")
        for i, stock in enumerate(hot_results, 1):
            print(f"  {i:<5} {stock['name']:<10} {stock['code']:<8} "
                  f"{_color_pct(stock['pct_change']):<8} "
                  f"{_fmt_amount(stock['amount']):<14} "
                  f"{stock.get('sector', '')}")
            print(f"         ↳ {stock.get('driver_note', '')}")

    # ---- 免责声明 ----
    print(f"\n  {sep}")
    print(f"  {DISCLAIMER}")
    print(f"  {sep}\n")


# ================================================================
# 二、HTML 报告
# ================================================================
def generate_html_report(watch_results: dict, hot_results: list,
                         run_time: str) -> str:
    """
    生成 HTML 格式分析报告，保存到 D:/GUPIAO。

    返回:
        生成的文件路径
    """
    today_str = datetime.now().strftime("%Y%m%d")
    filename = f"{today_str}-股票分析报告.html"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)

    html = _build_html(watch_results, hot_results, run_time)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("HTML 报告已保存: %s", filepath)
    return filepath


def _build_html(watch_results: dict, hot_results: list, run_time: str) -> str:
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
            <td class="suggestion">📋 {suggestion}<br><span class="risk-note">{risk}</span></td>
        </tr>"""

    # --- 热门个股表格行 ---
    hot_rows = ""
    for i, stock in enumerate(hot_results, 1):
        pct = stock.get("pct_change", 0)
        pct_class = "up" if pct >= 0 else "down"
        pct_str = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"

        hot_rows += f"""
        <tr>
            <td>{i}</td>
            <td><strong>{stock['name']}</strong><br><span class="code">{stock['code']}</span></td>
            <td class="{pct_class}">{pct_str}</td>
            <td>{_fmt_amount(stock.get('amount', 0))}</td>
            <td>{stock.get('turnover', 'N/A')}%</td>
            <td>{stock.get('sector', '')}</td>
            <td class="driver">{stock.get('driver_note', '')}</td>
        </tr>"""

    # --- 完整 HTML ---
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{datetime.now().strftime('%Y%m%d')}-股票分析报告</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", "Segoe UI", sans-serif;
        background: #f5f6fa; color: #2d3436; padding: 20px; line-height: 1.6;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    .header {{
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        color: white; padding: 30px 40px; border-radius: 12px; margin-bottom: 24px;
    }}
    .header h1 {{ font-size: 26px; margin-bottom: 8px; }}
    .header .time {{ opacity: 0.8; font-size: 14px; }}
    .section-title {{
        font-size: 20px; font-weight: 700; color: #1a1a2e;
        margin: 28px 0 16px; padding-left: 12px;
        border-left: 4px solid #e17055;
    }}
    .card {{
        background: white; border-radius: 10px; padding: 24px;
        margin-bottom: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }}
    table {{
        width: 100%; border-collapse: collapse; font-size: 13px;
    }}
    th {{
        background: #f8f9fa; color: #636e72; font-weight: 600;
        padding: 10px 8px; text-align: left; border-bottom: 2px solid #dfe6e9;
        white-space: nowrap;
    }}
    td {{
        padding: 10px 8px; border-bottom: 1px solid #f1f2f6;
        vertical-align: top;
    }}
    tr:hover {{ background: #fafbfc; }}
    .code {{ color: #636e72; font-size: 11px; }}
    .up {{ color: #d63031; font-weight: 700; }}
    .down {{ color: #00b894; font-weight: 700; }}
    .suggestion {{ font-size: 13px; max-width: 360px; }}
    .risk-note {{ color: #636e72; font-size: 11px; }}
    .driver {{ font-size: 12px; color: #636e72; max-width: 320px; }}
    .disclaimer {{
        background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px;
        padding: 16px 24px; margin-top: 24px; font-size: 13px;
        color: #856404; text-align: center;
    }}
    .tag {{
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 11px; font-weight: 600;
    }}
    .tag-bull {{ background: #ffeaa7; color: #d63031; }}
    .tag-bear {{ background: #dfe6e9; color: #00b894; }}
    .footer {{
        text-align: center; color: #b2bec3; font-size: 12px;
        margin-top: 32px; padding: 16px;
    }}
    @media print {{
        body {{ background: white; }}
        .card {{ box-shadow: none; border: 1px solid #ddd; }}
    }}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>📈 股票自动分析日报</h1>
    <div class="time">生成时间: {run_time} &nbsp;|&nbsp; 数据来源: 公开行情接口（东方财富）</div>
</div>

<h2 class="section-title">一、自选股跟踪分析</h2>
<div class="card">
    <div style="overflow-x: auto;">
    <table>
        <thead>
        <tr>
            <th>名称 / 代码</th>
            <th>最新价</th>
            <th>涨跌幅</th>
            <th>今开/最高/最低</th>
            <th>成交额</th>
            <th>换手率</th>
            <th>近1/3日涨跌</th>
            <th>均线(5/10/20)</th>
            <th>均线状态</th>
            <th>MACD</th>
            <th>支撑/压力</th>
            <th>参考建议</th>
        </tr>
        </thead>
        <tbody>
        {watch_rows}
        </tbody>
    </table>
    </div>
</div>

<h2 class="section-title">二、当日热门涨幅个股</h2>
<div class="card">
    <div style="overflow-x: auto;">
    <table>
        <thead>
        <tr>
            <th>#</th>
            <th>名称 / 代码</th>
            <th>涨幅</th>
            <th>成交额</th>
            <th>换手率</th>
            <th>所属板块</th>
            <th>上涨驱动逻辑（推测）</th>
        </tr>
        </thead>
        <tbody>
        {hot_rows}
        </tbody>
    </table>
    </div>
    {f'<p style="margin-top:16px;color:#636e72;font-size:13px;">共筛选出 {len(hot_results)} 只值得关注的热门标的</p>' if hot_results else '<p style="margin-top:16px;color:#636e72;">今日暂无符合条件的个股</p>'}
</div>

<div class="disclaimer">
    ⚠️ <strong>免责声明：</strong>{DISCLAIMER}
</div>

<div class="footer">
    本报告由股票自动分析程序生成 &nbsp;|&nbsp; 数据来源: akshare / 东方财富公开行情接口 &nbsp;|&nbsp; 仅供参考
</div>

</div>
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

"""
股票自动分析程序 —— 主入口
============================
一键运行：python main.py

功能：
  1. 自动抓取自选股（石头科技、科沃斯、嘉美包装）实时行情 + 历史K线
  2. 筛选全市场/半导体/光模块当日涨幅靠前个股
  3. 计算 5/10/20 日均线、MACD、K线趋势判断
  4. 输出操作参考建议（观望/持有/轻仓加仓/减仓提示）
  5. 控制台打印结构化报告 + 生成 HTML 报告 + CSV 存档

依赖：
  pip install akshare pandas numpy

运行方式：
  python main.py             # 正常模式（需要网络）
  python main.py --demo      # 演示模式（使用仿真数据，无网络也行）
"""

import logging
import sys
from datetime import datetime

from config import (
    WATCH_STOCKS,
    HOT_SECTORS,
    MARKET_HOT_TOP_N,
    DISCLAIMER,
)
from data_fetcher import (
    fetch_watch_quotes,
    fetch_all_history_kline,
    get_all_watch_stocks_data,
    fetch_market_top_gainers,
    fetch_sector_stocks,
    generate_demo_quote,
    generate_demo_history,
    generate_demo_market_data,
    generate_demo_sector_data,
)
from analyzer import (
    analyze_watch_stock,
    analyze_hot_stocks,
)
from report_generator import (
    print_console_report,
    generate_html_report,
    save_csv_archive,
    save_kline_archive,
)

# ------------------------------------------------------------
# 日志配置
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("StockAnalyzer")


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------
def main(demo_mode: bool = False):
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_label = "🔶 演示模式（仿真数据）" if demo_mode else "🟢 正常模式"

    logger.info("=" * 60)
    logger.info("  股票自动分析程序 启动 — %s", mode_label)
    logger.info("  运行时间: %s", run_time)
    logger.info("=" * 60)

    # ================================================
    # STEP 1: 获取自选股数据（行情缓存一次 + K 线逐只拉取）
    # ================================================
    logger.info("[Step 1/5] 获取自选股行情 + 历史K线数据...")

    if demo_mode:
        watch_data = _load_demo_watch_data()
    else:
        # 行情：全市场只拉一次，然后从缓存秒取
        watch_quotes = fetch_watch_quotes()
        # K线：每只独立请求（API 不支持批量）
        history_data = fetch_all_history_kline()
        # 组装
        watch_data = get_all_watch_stocks_data(watch_quotes, history_data)

    # ================================================
    # STEP 2: 逐只分析自选股
    # ================================================
    logger.info("[Step 2/5] 分析自选股技术指标...")
    watch_results = {}
    for name, data in watch_data.items():
        code = data["code"]
        quote = data["quote"]
        history = data["history"]

        if quote is None:
            logger.warning("  ⚠ %s (%s) 实时行情获取失败", name, code)
        if history is None or history.empty:
            logger.warning("  ⚠ %s (%s) 历史K线获取失败", name, code)

        analysis = analyze_watch_stock(name, code, quote, history)
        watch_results[name] = {
            "code": code,
            "quote": quote,
            "history": history,
            "analysis": analysis,
        }

    # ================================================
    # STEP 3: 获取热门涨幅个股
    # ================================================
    logger.info("[Step 3/5] 获取全市场 + 板块热门涨幅个股...")

    if demo_mode:
        market_df = generate_demo_market_data(n=MARKET_HOT_TOP_N * 3)
        sector_data = {}
        for sector_name, cfg in HOT_SECTORS.items():
            sdf = generate_demo_sector_data(cfg["keywords"])
            sector_data[sector_name] = sdf
    else:
        # 3a. 全市场涨幅排名
        market_df = fetch_market_top_gainers(top_n=MARKET_HOT_TOP_N * 3)
        # 3b. 重点板块（半导体 / 光模块）
        sector_data = {}
        for sector_name, cfg in HOT_SECTORS.items():
            logger.info("  正在筛选 %s 板块...", sector_name)
            sdf = fetch_sector_stocks(cfg["keywords"])
            sector_data[sector_name] = sdf

    # 3c. 综合分析
    hot_results = analyze_hot_stocks(market_df, sector_data)
    logger.info("  共筛选出 %d 只热门关注标的", len(hot_results))

    # ================================================
    # STEP 4: 生成报告
    # ================================================
    logger.info("[Step 4/5] 生成分析报告...")

    # 4a. 控制台输出
    print_console_report(watch_results, hot_results, run_time)

    # 4b. HTML 报告
    html_path = generate_html_report(watch_results, hot_results, run_time)

    # ================================================
    # STEP 5: CSV 存档
    # ================================================
    logger.info("[Step 5/5] 保存 CSV 数据存档...")

    save_csv_archive(watch_results, hot_results)

    # K 线历史存档
    for name, data in watch_data.items():
        save_kline_archive(name, data["code"], data["history"])

    # ================================================
    # 完成
    # ================================================
    logger.info("=" * 60)
    logger.info("  ✅ 分析完成！（%s）", mode_label)
    logger.info("  HTML 报告: %s", html_path)
    logger.info("  CSV 存档: %s", r"D:\GUPIAO\csv_archive")
    logger.info("  %s", DISCLAIMER)
    logger.info("=" * 60)


# ------------------------------------------------------------
# 演示模式数据加载
# ------------------------------------------------------------
def _load_demo_watch_data() -> dict:
    """加载仿真自选股数据"""
    result = {}
    for name, code in WATCH_STOCKS.items():
        logger.info("  [演示] 生成 %s (%s) 仿真数据...", name, code)
        result[name] = {
            "code": code,
            "quote": generate_demo_quote(name, code),
            "history": generate_demo_history(name, code),
        }
    return result


# ------------------------------------------------------------
# 入口
# ------------------------------------------------------------
if __name__ == "__main__":
    try:
        demo = "--demo" in sys.argv
        main(demo_mode=demo)
    except KeyboardInterrupt:
        logger.info("\n用户中断运行")
        sys.exit(0)
    except Exception as e:
        logger.exception("程序运行异常: %s", e)
        print(f"\n{'='*60}")
        print(f"  ❌ 程序异常退出: {e}")
        print(f"  请检查网络连接或 akshare 是否已正确安装。")
        print(f"  使用 'python main.py --demo' 可离线演示。")
        print(f"{'='*60}")
        sys.exit(1)

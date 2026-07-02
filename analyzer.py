"""
分析策略模块
============
1. 对自选股：综合 K 线趋势 + 均线 + MACD + 近3日涨跌幅 → 输出参考建议
2. 对热门涨幅个股：归因行业，推测上涨驱动逻辑
"""

import logging
from typing import Optional

import pandas as pd

from config import (
    HOT_SECTORS,
    MARKET_HOT_TOP_N,
    MARKET_MIN_PCT_CHANGE,
    MARKET_MIN_AMOUNT,
    DISCLAIMER,
)
from indicators import build_technical_summary

logger = logging.getLogger(__name__)


# ================================================================
# 一、自选股分析
# ================================================================
def analyze_watch_stock(name: str, code: str,
                        quote: Optional[dict],
                        history: Optional[pd.DataFrame]) -> dict:
    """
    对单只自选股进行综合分析。

    参数:
        name: 股票名称
        code: 股票代码
        quote: 当日实时行情 dict
        history: 历史 K 线 DataFrame

    返回:
        {
            "name": str,
            "code": str,
            "quote": dict,
            "technical": dict,        # 技术指标汇总
            "suggestion": str,        # 文字操作参考
            "risk_note": str,         # 风险提示
        }
    """
    result = {
        "name": name,
        "code": code,
        "quote": quote or {},
        "technical": {},
        "suggestion": "—",
        "risk_note": "",
    }

    if quote is None:
        result["suggestion"] = "⚠️ 无法获取实时行情，暂不分析"
        return result

    if history is None or history.empty:
        result["suggestion"] = "⚠️ 无法获取历史K线，参考数据不足"
        return result

    # 技术指标
    tech = build_technical_summary(history)
    result["technical"] = tech

    ma = tech.get("ma_trend", {})
    macd = tech.get("macd_trend", {})
    returns = tech.get("returns", {})
    sr = tech.get("sr_levels", {})

    # ---------- 综合判断逻辑 ----------
    signals_bull = 0   # 多头信号计数
    signals_bear = 0   # 空头信号计数
    notes = []

    # 1. 均线排列
    alignment = ma.get("alignment", "")
    if "多头" in alignment:
        signals_bull += 2
        notes.append("均线多头排列")
    elif "空头" in alignment:
        signals_bear += 2
        notes.append("均线空头排列")
    else:
        notes.append("均线粘合震荡")

    # 2. 价格 vs MA20
    if sr.get("ma20_support"):
        signals_bull += 1
    else:
        signals_bear += 1

    # 3. 近 3 日涨跌幅
    ret_3d = returns.get("3d")
    if ret_3d is not None:
        if ret_3d > 5:
            signals_bull += 1
            notes.append(f"近3日涨幅{ret_3d}%，短线强势")
        elif ret_3d < -5:
            signals_bear += 2
            notes.append(f"近3日跌幅{ret_3d}%，短线超跌")
        elif ret_3d > 0:
            signals_bull += 0.5
        else:
            signals_bear += 0.5

    # 4. MACD 信号
    if macd.get("golden_cross"):
        signals_bull += 2
        notes.append("MACD 近日金叉")
    if macd.get("death_cross"):
        signals_bear += 2
        notes.append("MACD 近日死叉")

    dif_pos = macd.get("dif_position", "")
    if "上方" in dif_pos:
        signals_bull += 1
    else:
        signals_bear += 0.5

    # 5. 今日涨跌
    pct = quote.get("pct_change", 0)
    if pct > 5:
        signals_bull += 1
        notes.append(f"今日大涨 {pct}%")
    elif pct < -5:
        signals_bear += 2
        notes.append(f"今日大跌 {pct}%")

    # ---------- 生成操作参考建议 ----------
    suggestion = _generate_suggestion(signals_bull, signals_bear, pct, ma, sr)
    result["suggestion"] = suggestion
    result["risk_note"] = " | ".join(notes) if notes else "无明显信号"

    return result


def _generate_suggestion(bull: float, bear: float, pct: float,
                         ma: dict, sr: dict) -> str:
    """
    根据多空信号强度生成文字参考建议。

    仅作数据参考，不构成投资建议！
    """
    total = bull + bear
    if total == 0:
        return "📊 数据不足，暂无法分析"

    bull_ratio = bull / total

    # 支撑/压力参考
    support = sr.get("support", 0)
    resistance = sr.get("resistance", 0)

    if bull_ratio >= 0.70:
        suggestion = (
            f"🟢 偏多信号（多头强度 {bull_ratio:.0%}）。"
            f"短期支撑参考 ¥{support:.2f}，压力参考 ¥{resistance:.2f}。"
            f"短线趋势偏强，已有仓位可继续持有观察；"
            f"轻仓者可关注回调至 MA20 附近的机会。"
        )
    elif bull_ratio >= 0.55:
        suggestion = (
            f"🟡 偏多震荡（多头强度 {bull_ratio:.0%}）。"
            f"短期支撑参考 ¥{support:.2f}，压力参考 ¥{resistance:.2f}。"
            f"信号偏多但不强烈，建议持有观望，"
            f"等待均线进一步确认方向后再操作。"
        )
    elif bull_ratio >= 0.40:
        suggestion = (
            f"🟠 方向不明（多空均衡 {bull_ratio:.0%}）。"
            f"短期支撑 ¥{support:.2f} / 压力 ¥{resistance:.2f}。"
            f"均线粘合、趋势未明，建议观望为主，"
            f"不宜追涨杀跌，等待方向选择信号。"
        )
    elif bull_ratio >= 0.25:
        suggestion = (
            f"🟡 偏空震荡（空头强度 {(1 - bull_ratio):.0%}）。"
            f"短期支撑参考 ¥{support:.2f}，压力参考 ¥{resistance:.2f}。"
            f"空头信号有所抬头，重仓者可关注反弹减仓机会，"
            f"轻仓或空仓者暂观望。"
        )
    else:
        suggestion = (
            f"🔴 偏空信号（空头强度 {(1 - bull_ratio):.0%}）。"
            f"短期支撑参考 ¥{support:.2f}（关注是否有效跌破），"
            f"压力参考 ¥{resistance:.2f}。"
            f"趋势偏弱，建议控制仓位、注意风险，"
            f"耐心等待止跌企稳信号出现。"
        )

    return suggestion


# ================================================================
# 二、热门涨幅个股分析
# ================================================================
def analyze_hot_stocks(market_df: pd.DataFrame,
                       sector_data: dict) -> list:
    """
    分析当日热门个股。

    参数:
        market_df: 全市场行情 DataFrame
        sector_data: {"半导体": df, "光模块": df}

    返回:
        [{"name": "...", "code": "...", "pct_change": ..., "amount": ...,
           "sector": "半导体", "driver_note": "..."}, ...]
    """
    results = []

    # ---- 2a. 全市场综合热门 ----
    if market_df is not None and not market_df.empty:
        mk = market_df.copy()
        for col in ["涨跌幅", "成交额"]:
            if col in mk.columns:
                mk[col] = pd.to_numeric(mk[col], errors="coerce")

        mk = mk[mk["涨跌幅"] >= MARKET_MIN_PCT_CHANGE]
        mk = mk[mk["成交额"] >= MARKET_MIN_AMOUNT]
        mk = mk.sort_values("涨跌幅", ascending=False).head(MARKET_HOT_TOP_N)

        for _, row in mk.iterrows():
            results.append({
                "name": str(row.get("名称", "")),
                "code": str(row.get("代码", "")),
                "price": _safe_float(row.get("最新价")),
                "pct_change": _safe_float(row.get("涨跌幅")),
                "amount": _safe_float(row.get("成交额")),
                "turnover": _safe_float(row.get("换手率")),
                "sector": "全市场热门",
                "driver_note": _guess_driver(str(row.get("名称", "")),
                                             str(row.get("代码", "")),
                                             _safe_float(row.get("涨跌幅"))),
            })

    # ---- 2b. 重点板块（半导体、光模块）----
    for sector_name, sdf in sector_data.items():
        if sdf is None or sdf.empty:
            continue

        cfg = HOT_SECTORS.get(sector_name, {})
        min_pct = cfg.get("min_pct_change", 3.0)
        min_amt = cfg.get("min_amount", 2e8)
        top_n = cfg.get("top_n", 5)

        sd = sdf.copy()
        for col in ["涨跌幅", "成交额"]:
            if col in sd.columns:
                sd[col] = pd.to_numeric(sd[col], errors="coerce")

        sd = sd[sd["涨跌幅"] >= min_pct]
        sd = sd[sd["成交额"] >= min_amt]
        sd = sd.sort_values("涨跌幅", ascending=False).head(top_n)

        for _, row in sd.iterrows():
            # 避免与全市场重复
            code = str(row.get("代码", ""))
            if any(r["code"] == code for r in results):
                continue

            results.append({
                "name": str(row.get("名称", "")),
                "code": code,
                "price": _safe_float(row.get("最新价")),
                "pct_change": _safe_float(row.get("涨跌幅")),
                "amount": _safe_float(row.get("成交额")),
                "turnover": _safe_float(row.get("换手率")),
                "sector": sector_name,
                "driver_note": _guess_sector_driver(sector_name,
                                                    _safe_float(row.get("涨跌幅"))),
            })

    # 按涨幅排序
    results.sort(key=lambda x: x["pct_change"], reverse=True)
    return results


def _guess_driver(name: str, code: str, pct: float) -> str:
    """
    根据名称/代码粗粒度推测上涨驱动逻辑（仅作参考标注）。
    """
    name_code = name + code
    drivers = []

    if any(kw in name_code for kw in ["半导体", "芯片", "集成", "晶圆", "封测", "光刻"]):
        drivers.append("半导体产业链活跃")
    if any(kw in name_code for kw in ["光模块", "光通信", "CPO", "光器件", "硅光"]):
        drivers.append("光通信/AI 算力需求驱动")
    if any(kw in name_code for kw in ["AI", "人工智能", "算力", "大模型"]):
        drivers.append("AI 概念炒作")
    if any(kw in name_code for kw in ["机器人", "智能", "自动"]):
        drivers.append("机器人/自动化概念")
    if any(kw in name_code for kw in ["新能", "锂电", "光伏", "储能", "风电"]):
        drivers.append("新能源产业链")
    if any(kw in name_code for kw in ["医药", "生物", "制药", "医疗"]):
        drivers.append("医药/生物概念")
    if any(kw in name_code for kw in ["汽车", "整车", "零部件"]):
        drivers.append("汽车产业链")
    if any(kw in name_code for kw in ["军工", "航天", "航空"]):
        drivers.append("军工/航空航天")
    if any(kw in name_code for kw in ["消费", "食品", "饮料", "白酒"]):
        drivers.append("大消费概念")

    if not drivers:
        if pct >= 9.5:
            drivers.append("涨停封板，市场情绪推动")
        elif pct >= 5:
            drivers.append("主力资金介入，短线强势")
        else:
            drivers.append("跟随板块或市场反弹")

    return "；".join(drivers)


def _guess_sector_driver(sector_name: str, pct: float) -> str:
    """板块级驱动逻辑推测"""
    mapping = {
        "半导体": "受益于国产替代 + AI 算力芯片需求增长，半导体板块持续活跃",
        "光模块": "AI 数据中心大规模建设推动高速光模块需求爆发，CPO 技术路线受关注",
    }
    return mapping.get(sector_name, f"{sector_name}板块资金关注度提升")


def _safe_float(val) -> float:
    try:
        if pd.isna(val):
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

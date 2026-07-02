"""
技术指标计算模块
=================
基于历史 K 线数据，计算：
  - 5/10/20 日简单移动平均线（MA）
  - MACD 指标（DIF / DEA / 柱）
  - K 线简单趋势判断（多头排列 / 空头排列 / 震荡）
  - 近 N 日涨跌幅
  - 近期支撑 / 压力位（基于近期高低点 + 均线）
"""

import logging
from typing import Optional

import pandas as pd
import numpy as np

from config import MA_PERIODS, MACD_FAST, MACD_SLOW, MACD_SIGNAL

logger = logging.getLogger(__name__)


def calc_ma(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    """
    计算移动平均线。

    参数:
        df: 含 close 列的 DataFrame，按日期升序
        periods: 均线周期列表，默认 [5, 10, 20]

    返回:
        原 df 追加 MA5, MA10, MA20 等列
    """
    if periods is None:
        periods = MA_PERIODS

    df = df.copy()
    for p in periods:
        col_name = f"MA{p}"
        if len(df) >= p:
            df[col_name] = df["close"].rolling(window=p).mean()
        else:
            df[col_name] = np.nan
    return df


def calc_macd(df: pd.DataFrame,
              fast: int = None, slow: int = None, signal: int = None) -> pd.DataFrame:
    """
    计算 MACD 指标。

    返回:
        df 追加 DIF, DEA, MACD（柱）三列
    """
    if fast is None:
        fast = MACD_FAST
    if slow is None:
        slow = MACD_SLOW
    if signal is None:
        signal = MACD_SIGNAL

    df = df.copy()
    if len(df) < slow:
        df["DIF"] = np.nan
        df["DEA"] = np.nan
        df["MACD"] = np.nan
        return df

    # EMA 计算
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()

    df["DIF"] = ema_fast - ema_slow
    df["DEA"] = df["DIF"].ewm(span=signal, adjust=False).mean()
    df["MACD"] = 2 * (df["DIF"] - df["DEA"])  # 柱状值 (通常柱 = DIF-DEA， ×2 是标准做法)

    return df


def judge_ma_trend(df: pd.DataFrame) -> dict:
    """
    判断均线多头 / 空头 / 交叉状态。

    返回:
        {
            "ma5": float, "ma10": float, "ma20": float,
            "current_price": float,
            "alignment": "多头排列" | "空头排列" | "粘合震荡",
            "ma5_cross_ma10": "金叉" | "死叉" | "无",
            "ma5_cross_ma20": "金叉" | "死叉" | "无",
            "price_vs_ma5": "上方" | "下方",
            "price_vs_ma20": "上方" | "下方",
        }
    """
    if df is None or df.empty or len(df) < 20:
        return {"alignment": "数据不足", "current_price": 0}

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    ma5 = _safe_val(last.get("MA5"))
    ma10 = _safe_val(last.get("MA10"))
    ma20 = _safe_val(last.get("MA20"))
    price = _safe_val(last.get("close"))

    prev_ma5 = _safe_val(prev.get("MA5"))
    prev_ma10 = _safe_val(prev.get("MA10"))
    prev_ma20 = _safe_val(prev.get("MA20"))

    # 多头/空头排列判断
    if ma5 > ma10 > ma20 and all(v > 0 for v in [ma5, ma10, ma20]):
        alignment = "多头排列 ↑"
    elif ma5 < ma10 < ma20 and all(v > 0 for v in [ma5, ma10, ma20]):
        alignment = "空头排列 ↓"
    else:
        alignment = "粘合震荡 ↔"

    # 均线交叉
    if prev_ma5 <= prev_ma10 and ma5 > ma10:
        cross_5_10 = "金叉 ✚"
    elif prev_ma5 >= prev_ma10 and ma5 < ma10:
        cross_5_10 = "死叉 ✖"
    else:
        cross_5_10 = "—"

    if prev_ma5 <= prev_ma20 and ma5 > ma20:
        cross_5_20 = "金叉 ✚"
    elif prev_ma5 >= prev_ma20 and ma5 < ma20:
        cross_5_20 = "死叉 ✖"
    else:
        cross_5_20 = "—"

    return {
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "current_price": round(price, 2),
        "alignment": alignment,
        "ma5_cross_ma10": cross_5_10,
        "ma5_cross_ma20": cross_5_20,
        "price_vs_ma5": "上方 ▲" if price > ma5 else "下方 ▼",
        "price_vs_ma20": "上方 ▲" if price > ma20 else "下方 ▼",
    }


def judge_macd_trend(df: pd.DataFrame) -> dict:
    """
    判断 MACD 当前状态。

    返回:
        {
            "dif": float, "dea": float, "macd_bar": float,
            "dif_position": "零轴上方" | "零轴下方",
            "dif_direction": "向上" | "向下" | "走平",
            "golden_cross": bool,    # 近 3 日内金叉
            "death_cross": bool,     # 近 3 日内死叉
        }
    """
    if df is None or df.empty or "DIF" not in df.columns:
        return {"dif": 0, "dea": 0, "macd_bar": 0,
                "dif_position": "数据不足", "dif_direction": "—"}

    last = df.iloc[-1]
    dif = _safe_val(last.get("DIF"))
    dea = _safe_val(last.get("DEA"))
    bar = _safe_val(last.get("MACD"))

    # DIF 方向（对比前 3 日均值）
    recent_dif = df["DIF"].dropna().tail(3)
    if len(recent_dif) >= 2:
        if recent_dif.iloc[-1] > recent_dif.iloc[0] * 1.02:
            direction = "向上 ↗"
        elif recent_dif.iloc[-1] < recent_dif.iloc[0] * 0.98:
            direction = "向下 ↘"
        else:
            direction = "走平 →"
    else:
        direction = "—"

    # 近 3 日金叉/死叉 检测
    golden = False
    death = False
    if len(df) >= 3:
        for i in range(-3, 0):
            if abs(i) > len(df):
                break
            cur_dif = _safe_val(df.iloc[i].get("DIF"))
            cur_dea = _safe_val(df.iloc[i].get("DEA"))
            prev_dif = _safe_val(df.iloc[i - 1].get("DIF")) if i - 1 >= -len(df) else 0
            prev_dea = _safe_val(df.iloc[i - 1].get("DEA")) if i - 1 >= -len(df) else 0
            if prev_dif <= prev_dea and cur_dif > cur_dea:
                golden = True
            if prev_dif >= prev_dea and cur_dif < cur_dea:
                death = True

    return {
        "dif": round(dif, 3),
        "dea": round(dea, 3),
        "macd_bar": round(bar, 3),
        "dif_position": "零轴上方 ▲" if dif > 0 else "零轴下方 ▼",
        "dif_direction": direction,
        "golden_cross": golden,
        "death_cross": death,
    }


def calc_recent_returns(df: pd.DataFrame, days_list: list = None) -> dict:
    """
    计算近 N 日涨跌幅。

    返回:
        {"1d": 1.5, "3d": 2.3, "5d": -0.5, ...}
    """
    if days_list is None:
        days_list = [1, 3, 5]

    if df is None or df.empty:
        return {f"{d}d": None for d in days_list}

    result = {}
    for d in days_list:
        if len(df) >= d + 1:
            today_close = _safe_val(df.iloc[-1]["close"])
            past_close = _safe_val(df.iloc[-(d + 1)]["close"])
            if past_close > 0:
                result[f"{d}d"] = round((today_close - past_close) / past_close * 100, 2)
            else:
                result[f"{d}d"] = None
        else:
            result[f"{d}d"] = None
    return result


def calc_support_resistance(df: pd.DataFrame) -> dict:
    """
    基于近期高/低点 + 均线估算支撑/压力位（非常粗略参考）。

    返回:
        {
            "support": float,   # 最近 20 日最低价附近
            "resistance": float, # 最近 20 日最高价附近
            "ma20_support": bool, # 价格是否在 MA20 上方
        }
    """
    if df is None or df.empty or len(df) < 10:
        return {"support": 0, "resistance": 0, "ma20_support": False}

    recent = df.tail(20)
    support = _safe_val(recent["low"].min())
    resistance = _safe_val(recent["high"].max())
    current = _safe_val(df.iloc[-1]["close"])

    ma20 = _safe_val(df.iloc[-1].get("MA20")) if "MA20" in df.columns else 0

    return {
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "ma20_support": current > ma20 if ma20 > 0 else None,
    }


def build_technical_summary(df: pd.DataFrame) -> dict:
    """
    一站式计算所有技术指标，返回综合分析字典。
    """
    if df is None or df.empty:
        return {"error": "无 K 线数据"}

    df = calc_ma(df)
    df = calc_macd(df)

    return {
        "ma_trend": judge_ma_trend(df),
        "macd_trend": judge_macd_trend(df),
        "returns": calc_recent_returns(df),
        "sr_levels": calc_support_resistance(df),
        "latest_close": _safe_val(df.iloc[-1]["close"]),
        "latest_date": str(df.iloc[-1]["date"])[:10] if "date" in df.columns else "",
    }


def _safe_val(val) -> float:
    """安全转为 float，失败返回 0.0"""
    try:
        if pd.isna(val) or val is None:
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

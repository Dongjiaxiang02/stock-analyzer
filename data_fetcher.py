"""
数据获取模块 —— 多数据源自动切换
=================================
优先使用腾讯 HTTP API（国内/海外均可访问），
eastmoney 不可用时自动降级，确保在任何网络环境都能获取数据。
"""

import time
import json
import logging
from typing import Optional

import requests
import pandas as pd

from config import (
    WATCH_STOCKS,
    LOOKBACK_DAYS,
    REQUEST_DELAY,
    MAX_RETRIES,
    RETRY_DELAY,
    HOT_SECTORS,
    MARKET_HOT_TOP_N,
)

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ================================================================
# 热门关注股票池（半导体 + 光模块 + AI + 机器人 + 新能源等活跃板块）
# 用于全市场筛选时批量查询，避免拉全市场 5000+ 条数据
# ================================================================
_HOT_STOCK_POOL = [
    # ---- 半导体 ----
    "688981","002049","300782","603986","688012","688396","300661","002916",
    "002185","688256","688187","300604","688728","300373","688368","605111",
    "688123","688595","300458","688536","600703","300623","002463","688525",
    "688608","688352","688047","688041","688107","688126","688385","688521",
    "300672","300327","688037","603290","688153","002409","300077","002156",
    # ---- 光模块 / AI 算力 ----
    "300308","300394","300502","688498","300570","688313","002281","688205",
    "300620","688195","300548","301191","688662","300602","300476","688800",
    "002837","300499","688228","300659","002230",
    # ---- 机器人 / 自动化 ----
    "300024","688017","002747","300124","688160","002527","300508","688686",
    "300496","300567","002979","688400","300607","688003","002444",
    # ---- 新能源 / 锂电 / 光伏 ----
    "300750","002594","601012","688599","300274","300763","002459","688223",
    "600438","300316","300724","688779","002129","300751","688390",
    # ---- 消费电子 / 汽车 ----
    "002475","601138","300433","002241","600745","688036","002920","300115",
    "600104","002074","300207","688567","300438",
    # ---- 医药生物 ----
    "300760","300759","603259","688276","300122","600196","688180",
    # ---- 软件 / 信创 ----
    "688111","688561","300454","002439","688188","300369","688568",
]

# 去重
_HOT_STOCK_POOL = list(dict.fromkeys(_HOT_STOCK_POOL))


# ================================================================
# 工具函数
# ================================================================
def _code_with_market(code: str) -> str:
    """纯数字代码 → 'sh688169' / 'sz002969' 格式"""
    return ("sh" if code.startswith(("6", "68")) else "sz") + code


def _safe_float(val) -> float:
    try:
        return 0.0 if pd.isna(val) else float(val)
    except (ValueError, TypeError):
        return 0.0


# ================================================================
# 1. 腾讯实时行情 API（批量查询，一次请求搞定所有股票）
# ================================================================
def _fetch_tencent_quotes(codes: list) -> dict:
    """
    通过腾讯 HTTP 接口批量获取实时行情。

    参数:
        codes: ["688169", "603486", ...] 纯数字代码列表

    返回:
        {code: {name, price, open, high, low, pre_close, pct_change, volume, amount, turnover}, ...}
    """
    if not codes:
        return {}

    # 组合请求：http://qt.gtimg.cn/q=sh688169,sh603486,sz002969
    symbols = [_code_with_market(c) for c in codes]
    url = "http://qt.gtimg.cn/q=" + ",".join(symbols)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY * 0.3)
            r = requests.get(url, headers={"User-Agent": _UA}, timeout=15)
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")

            result = {}
            for line in r.text.strip().split(";"):
                line = line.strip()
                if not line or "pv_none_match" in line:
                    continue
                # 格式: v_sh688169="1~石头科技~688169~95.35~..."
                # 去掉 v_shXXXXXX=" 前缀和尾部 "
                idx = line.find('"')
                if idx == -1:
                    continue
                payload = line[idx + 1 : line.rfind('"')]
                parts = payload.split("~")
                if len(parts) < 40:
                    continue

                code = parts[2]
                # 腾讯格式字段位置（已验证）:
                # [1]名称 [2]代码 [3]最新价 [4]昨收 [5]今开
                # [6]成交量(手) [32]涨跌幅% [33]最高 [34]最低 [38]换手率%
                # [37]成交额(万元) [57]成交额(万元,更精确)
                amount_wan = _safe_float(parts[57]) if len(parts) > 57 and parts[57] else (
                    _safe_float(parts[37]) if len(parts) > 37 else 0)
                amount = amount_wan * 10000  # 万元 → 元

                result[code] = {
                    "code": code,
                    "name": parts[1],
                    "price": _safe_float(parts[3]),
                    "pre_close": _safe_float(parts[4]),
                    "open": _safe_float(parts[5]),
                    "high": _safe_float(parts[33]) if len(parts) > 33 else 0,
                    "low": _safe_float(parts[34]) if len(parts) > 34 else 0,
                    "pct_change": _safe_float(parts[32]) if len(parts) > 32 else 0,
                    "volume": _safe_float(parts[6]),
                    "amount": amount,
                    "turnover": _safe_float(parts[38]) if len(parts) > 38 else 0,
                }
            return result

        except Exception as e:
            logger.warning("腾讯行情请求 第 %d/%d 次失败: %s", attempt, MAX_RETRIES, str(e)[:80])
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.error("腾讯行情全部失败")
    return {}


# ================================================================
# 2. 腾讯历史 K 线 API
# ================================================================
def fetch_history_kline(code: str, days: int = LOOKBACK_DAYS) -> Optional[pd.DataFrame]:
    """
    通过腾讯接口获取个股历史日K线（前复权）。

    返回: pd.DataFrame，列 date/open/high/low/close/volume/amount
    """
    symbol = _code_with_market(code)
    url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{symbol},day,,,{days + 30},qfq"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY * 0.3)
            r = requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=15)
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")

            data = r.json()
            if data.get("code") != 0:
                raise Exception(f"API error: {data.get('msg', 'unknown')}")

            stock_data = data.get("data", {}).get(symbol, {})
            rows = stock_data.get("qfqday") or stock_data.get("day") or []

            if not rows:
                logger.warning("股票 %s 历史K线为空", code)
                return None

            # 腾讯 K 线格式: [date, open, close, high, low, volume]
            records = []
            for row in rows:
                if len(row) < 6:
                    continue
                records.append({
                    "date": row[0],
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": float(row[5]),
                    "amount": float(row[2]) * float(row[5]) * 100,  # 估算：均价×量
                })

            df = pd.DataFrame(records)
            df["date"] = pd.to_datetime(df["date"])
            for c in ["open", "high", "low", "close", "volume", "amount"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
            return df.tail(days)

        except Exception as e:
            logger.warning("获取 %s 历史K线 第 %d/%d 次失败: %s", code, attempt, MAX_RETRIES, str(e)[:80])
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.error("获取 %s 历史K线全部失败", code)
    return None


# ================================================================
# 3. 自选股数据（一次批量拉取行情 + 逐只拉取 K 线）
# ================================================================
def fetch_watch_quotes() -> dict:
    """
    批量获取所有自选股实时行情（单次 HTTP 请求）。

    返回:
        {"石头科技": dict, "科沃斯": dict, "嘉美包装": dict}
    """
    codes = list(WATCH_STOCKS.values())
    quotes = _fetch_tencent_quotes(codes)
    # 按名称映射
    result = {}
    for name, code in WATCH_STOCKS.items():
        result[name] = quotes.get(code)
    return result


def fetch_all_history_kline() -> dict:
    """批量获取所有自选股历史K线"""
    result = {}
    for name, code in WATCH_STOCKS.items():
        logger.info("  获取历史K线: %s (%s)", name, code)
        result[name] = fetch_history_kline(code)
    return result


def get_all_watch_stocks_data(quotes: dict, history: dict) -> dict:
    """组装自选股完整数据"""
    result = {}
    for name, code in WATCH_STOCKS.items():
        result[name] = {
            "code": code,
            "quote": quotes.get(name),
            "history": history.get(name),
        }
    return result


# ================================================================
# 4. 热门个股筛选（从预定义股票池批量拉取，再筛选）
# ================================================================
def fetch_market_top_gainers(top_n: int = MARKET_HOT_TOP_N) -> Optional[pd.DataFrame]:
    """
    从热门股票池中批量拉取行情，按涨幅排序取前 N。
    不再拉全市场 5000+ 条，只拉 ~150 只活跃标的。
    """
    quotes = _fetch_tencent_quotes(_HOT_STOCK_POOL)
    if not quotes:
        return None

    rows = []
    for code, q in quotes.items():
        rows.append({
            "代码": code, "名称": q["name"], "最新价": q["price"],
            "涨跌幅": q["pct_change"], "成交额": q["amount"],
            "成交量": q["volume"], "换手率": q["turnover"],
        })

    df = pd.DataFrame(rows)
    # 数值化
    for col in ["涨跌幅", "成交额", "成交量", "换手率"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["涨跌幅"]).sort_values("涨跌幅", ascending=False)
    return df.head(top_n)


def fetch_sector_stocks(keywords: list, sector_label: str = "") -> Optional[pd.DataFrame]:
    """
    从热门股票池中根据关键词匹配板块成分股，再拉取行情筛选。

    参数:
        keywords: ["半导体", "芯片"]
        sector_label: 板块标签
    """
    # 关键词 → 匹配的股票代码子集
    # 直接用预定义映射
    sector_map = {
        "半导体": [
            "688981","002049","300782","603986","688012","688396","300661","002916",
            "002185","688256","688187","300604","688728","300373","688368","605111",
            "688123","688595","300458","688536","600703","300623","002463","688525",
            "688608","688352","688047","688041","688107","688126","688385","688521",
            "300672","300327","688037","603290","688153","002409","300077","002156",
        ],
        "光模块": [
            "300308","300394","300502","688498","300570","688313","002281","688205",
            "300620","688195","300548","301191","688662","300602","300476","688800",
            "002837","300499","688228","300659",
        ],
        "光通信": [
            "300308","300394","300502","688498","300570","688313","002281","688205",
            "300620","688195","300548",
        ],
    }

    # 匹配关键词
    target_codes = set()
    matched_label = sector_label
    for kw in keywords:
        for sector_name, codes in sector_map.items():
            if kw in sector_name or sector_name in kw:
                target_codes.update(codes)
                if not matched_label:
                    matched_label = sector_name

    if not target_codes:
        # 从总池子中模糊匹配名称
        target_codes = set(_HOT_STOCK_POOL)

    # 批量拉取行情
    quotes = _fetch_tencent_quotes(list(target_codes))
    if not quotes:
        return None

    rows = []
    for code, q in quotes.items():
        rows.append({
            "代码": code, "名称": q["name"], "最新价": q["price"],
            "涨跌幅": q["pct_change"], "成交额": q["amount"],
            "成交量": q["volume"], "换手率": q["turnover"],
            "所属板块": matched_label or "热门板块",
        })

    df = pd.DataFrame(rows)
    for col in ["涨跌幅", "成交额", "成交量", "换手率"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("涨跌幅", ascending=False)


# ================================================================
# 5. 市场指数（通过新浪接口，用于判断大盘环境）
# ================================================================
def fetch_market_indices() -> dict:
    """获取上证/深证/创业板指数"""
    try:
        url = "https://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sz399006"
        r = requests.get(url, headers={
            "User-Agent": _UA,
            "Referer": "https://finance.sina.com.cn/",
        }, timeout=10)
        if r.status_code != 200:
            return {}
        result = {}
        for line in r.text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            idx = line.find('"')
            if idx == -1:
                continue
            parts = line[idx + 1 : line.rfind('"')].split(",")
            if len(parts) < 4:
                continue
            name_map = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}
            code = line[line.find("_s_") + 3 : line.find("=")]
            result[code] = {
                "name": name_map.get(code, code),
                "price": _safe_float(parts[0]),
                "change": _safe_float(parts[1]),
                "pct_change": _safe_float(parts[2]),
            }
        return result
    except Exception as e:
        logger.warning("获取大盘指数失败: %s", e)
        return {}


# ================================================================
# 6. akshare 备用通道（当腾讯不可用时尝试）
# ================================================================
def _try_akshare_spot() -> Optional[pd.DataFrame]:
    """尝试通过 akshare 获取全市场行情（可能被墙）"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            logger.info("  ✅ akshare 通道可用")
            return df
    except Exception:
        pass
    return None


# ================================================================
# 7. 演示模式
# ================================================================
def generate_demo_quote(name: str, code: str) -> dict:
    import random
    random.seed(hash(code) % (2**31))
    base_prices = {"石头科技": 265.0, "科沃斯": 48.0, "嘉美包装": 6.5}
    base = base_prices.get(name, 20.0)
    pct = round(random.uniform(-4.5, 5.5), 2)
    price = round(base * (1 + pct / 100), 2)
    pre_close = round(base, 2)
    open_p = round(pre_close * (1 + random.uniform(-1, 1) / 100), 2)
    high = round(max(open_p, price) * (1 + abs(random.uniform(0, 2)) / 100), 2)
    low = round(min(open_p, price) * (1 - abs(random.uniform(0, 2)) / 100), 2)
    volume = random.randint(50000, 500000)
    return {
        "code": code, "name": name,
        "open": open_p, "high": high, "low": low,
        "price": price, "pre_close": pre_close,
        "pct_change": pct, "volume": volume,
        "amount": volume * price * 100,
        "turnover": round(random.uniform(0.5, 8.0), 2),
    }


def generate_demo_history(name: str, code: str, days: int = 60) -> pd.DataFrame:
    import random
    import numpy as np
    random.seed(hash(code) % (2**31))
    np.random.seed(hash(code) % (2**31))
    base_prices = {"石头科技": 260.0, "科沃斯": 50.0, "嘉美包装": 6.8}
    base = base_prices.get(name, 20.0)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="B")
    rets = np.random.normal(0.0002, 0.025, len(dates))
    closes = base * np.cumprod(1 + rets)
    data = []
    for d, c in zip(dates, closes):
        o = c * (1 + random.uniform(-0.01, 0.01))
        h = max(o, c) * (1 + abs(random.uniform(0, 0.02)))
        l = min(o, c) * (1 - abs(random.uniform(0, 0.02)))
        vol = random.randint(30000, 400000)
        data.append({"date": d, "open": round(o, 2), "high": round(h, 2),
                     "low": round(l, 2), "close": round(c, 2),
                     "volume": vol, "amount": round(vol * c * 100, 0)})
    return pd.DataFrame(data)


def generate_demo_market_data(n: int = 30) -> pd.DataFrame:
    import random
    random.seed(42)
    demo_stocks = [
        ("002049","紫光国微"),("688981","中芯国际"),("300782","卓胜微"),
        ("603986","兆易创新"),("688012","中微公司"),("688396","华润微"),
        ("300661","圣邦股份"),("002916","深南电路"),("300502","新易盛"),
        ("688187","时代电气"),("300308","中际旭创"),("300394","天孚通信"),
        ("688498","源杰科技"),("300570","太辰光"),("688313","仕佳光子"),
        ("002281","光迅科技"),("600703","三安光电"),("300604","长川科技"),
        ("688256","寒武纪"),("002463","沪电股份"),
    ]
    rows = []
    for code, name in demo_stocks[:n]:
        base = random.uniform(8, 300)
        pct = round(random.uniform(-2, 12), 2)
        price = round(base * (1 + pct / 100), 2)
        rows.append({
            "代码": code, "名称": name, "最新价": price,
            "涨跌幅": pct, "成交额": random.uniform(5e7, 5e9),
            "成交量": random.randint(10000, 800000),
            "换手率": round(random.uniform(1, 15), 2),
        })
    return pd.DataFrame(rows)


def generate_demo_sector_data(keywords: list) -> pd.DataFrame:
    import random
    random.seed(123)
    sector_map = {
        "半导体": [
            ("688981","中芯国际"),("002049","紫光国微"),("300782","卓胜微"),
            ("603986","兆易创新"),("688012","中微公司"),("688396","华润微"),
            ("300661","圣邦股份"),("002916","深南电路"),("002185","华天科技"),
            ("688256","寒武纪"),("688187","时代电气"),("300604","长川科技"),
        ],
        "光模块": [
            ("300308","中际旭创"),("300394","天孚通信"),("300502","新易盛"),
            ("688498","源杰科技"),("300570","太辰光"),("688313","仕佳光子"),
            ("002281","光迅科技"),
        ],
    }
    rows = []
    for sector_key, stocks in sector_map.items():
        if not any(kw in sector_key for kw in keywords):
            continue
        for code, name in stocks:
            base = random.uniform(10, 200)
            pct = round(random.uniform(-1, 10), 2)
            price = round(base * (1 + pct / 100), 2)
            rows.append({
                "代码": code, "名称": name, "最新价": price,
                "涨跌幅": pct, "成交额": random.uniform(1e7, 4e9),
                "成交量": random.randint(10000, 500000),
                "换手率": round(random.uniform(1, 12), 2),
                "所属板块": sector_key,
            })
    return pd.DataFrame(rows)

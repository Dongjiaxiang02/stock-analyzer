"""
分析策略模块
1. 自选股技术分析（均线+MACD+支撑压力+多空评分+基本面备注）
2. 热门个股筛选归因（真实赛道催化驱动）
3. 六段市场全貌分析（含北向资金、明日推演、半导体/光模块深度）
"""
import logging
from typing import Optional
import pandas as pd
from config import HOT_SECTORS, MARKET_HOT_TOP_N, MARKET_MIN_PCT_CHANGE, MARKET_MIN_AMOUNT, DISCLAIMER
from indicators import build_technical_summary

logger = logging.getLogger(__name__)

# 自选股基本面备注
FUNDAMENTALS = {
    "石头科技": "全球扫地机器人龙头，海外营收占比高，AI导航技术壁垒，消费复苏+出海双驱动",
    "科沃斯": "扫地机器人+小家电双轮驱动，国内品牌力强，关注新品周期和海外拓展进度",
    "嘉美包装": "食品饮料金属包装龙头，绑定大客户（农夫山泉等），周期性较弱，跟随消费品景气",
    "影石创新": "全景运动相机全球第一(81.7%份额)，AI+影像，上市后业绩高增67%，高成长赛道",
    "小米集团-W": "手机×AIoT×汽车三线并进，SU7交付超预期，港股科技龙头，关注汽车毛利率爬坡",
}


def analyze_watch_stock(name, code, quote, history):
    result = {"name": name, "code": code, "quote": quote or {}, "technical": {}, "suggestion": "—", "risk_note": "", "fundamental": FUNDAMENTALS.get(name, "")}
    if quote is None: result["suggestion"] = "⚠️ 无法获取实时行情，暂不分析"; return result
    if history is None or history.empty: result["suggestion"] = "⚠️ 无法获取历史K线，参考数据不足"; return result
    tech = build_technical_summary(history)
    result["technical"] = tech
    ma, macd, returns, sr = tech.get("ma_trend", {}), tech.get("macd_trend", {}), tech.get("returns", {}), tech.get("sr_levels", {})
    bull = bear = 0; notes = []
    a = ma.get("alignment", "")
    if "多头" in a: bull += 2; notes.append("均线多头排列")
    elif "空头" in a: bear += 2; notes.append("均线空头排列")
    else: notes.append("均线粘合震荡")
    if sr.get("ma20_support"): bull += 1
    else: bear += 1
    r3 = returns.get("3d")
    if r3 is not None:
        if r3 > 5: bull += 1; notes.append(f"近3日涨幅{r3}%短线强势")
        elif r3 < -5: bear += 2; notes.append(f"近3日跌幅{r3}%短线超跌")
        elif r3 > 0: bull += 0.5
        else: bear += 0.5
    if macd.get("golden_cross"): bull += 2; notes.append("MACD金叉")
    if macd.get("death_cross"): bear += 2; notes.append("MACD死叉")
    if "上方" in macd.get("dif_position", ""): bull += 1
    else: bear += 0.5
    pct = quote.get("pct_change", 0)
    if pct > 5: bull += 1; notes.append(f"今日大涨{pct}%")
    elif pct < -5: bear += 2; notes.append(f"今日大跌{pct}%")
    result["suggestion"] = _sug(bull, bear, sr)
    result["risk_note"] = " | ".join(notes) if notes else "无明显信号"
    result["bull_score"] = bull
    result["bear_score"] = bear
    return result


def _sug(bull, bear, sr):
    t = bull + bear
    if t == 0: return "数据不足"
    r = bull / t; s = sr.get("support", 0); p = sr.get("resistance", 0)
    if r >= 0.70: return f"🟢 偏多({r:.0%})支撑¥{s:.0f}压力¥{p:.0f}，持有观察"
    elif r >= 0.55: return f"🟡 偏多震荡({r:.0%})支撑¥{s:.0f}压力¥{p:.0f}，持有观望"
    elif r >= 0.40: return f"🟠 方向不明 支撑¥{s:.0f}压力¥{p:.0f}，观望为主"
    elif r >= 0.25: return f"🟡 偏空震荡(空头{1-r:.0%})支撑¥{s:.0f}，重仓关注减仓"
    else: return f"🔴 偏空(空头{1-r:.0%})支撑¥{s:.0f}压力¥{p:.0f}，控制仓位"


# ================================================================
# 热门个股分析（真实赛道催化）
# ================================================================
def analyze_hot_stocks(market_df, sector_data):
    results = []
    if market_df is not None and not market_df.empty:
        mk = market_df.copy()
        for col in ["涨跌幅", "成交额"]:
            if col in mk.columns: mk[col] = pd.to_numeric(mk[col], errors="coerce")
        mk = mk[mk["涨跌幅"] >= MARKET_MIN_PCT_CHANGE]
        mk = mk[mk["成交额"] >= MARKET_MIN_AMOUNT]
        mk = mk.sort_values("涨跌幅", ascending=False).head(MARKET_HOT_TOP_N)
        for _, row in mk.iterrows():
            results.append(_hot(row, "全市场热门"))
    for sector_name, sdf in sector_data.items():
        if sdf is None or sdf.empty: continue
        cfg = HOT_SECTORS.get(sector_name, {})
        sd = sdf.copy()
        for col in ["涨跌幅", "成交额"]:
            if col in sd.columns: sd[col] = pd.to_numeric(sd[col], errors="coerce")
        sd = sd[sd["涨跌幅"] >= cfg.get("min_pct_change", 1.0)]
        sd = sd[sd["成交额"] >= cfg.get("min_amount", 5e7)]
        sd = sd.sort_values("涨跌幅", ascending=False).head(cfg.get("top_n", 10))
        for _, row in sd.iterrows():
            code = str(row.get("代码", ""))
            if any(r["code"] == code for r in results): continue
            results.append(_hot(row, sector_name))
    results.sort(key=lambda x: x["pct_change"], reverse=True)
    return results


def _hot(row, sector):
    name = str(row.get("名称", "")); code = str(row.get("代码", "")); pct = _sf(row.get("涨跌幅"))
    return {
        "name": name, "code": code, "price": _sf(row.get("最新价")), "pct_change": pct,
        "amount": _sf(row.get("成交额")), "turnover": _sf(row.get("换手率")),
        "market_cap": _sf(row.get("总市值")), "pe": _sf(row.get("市盈率")),
        "sector": sector, "driver_note": _driver(name, code, pct),
    }


def _driver(name, code, pct):
    nc = name + code; drivers = []
    semis = ["半导体","芯片","集成","晶圆","封测","光刻","存储","设备","材料"]
    ai_cp = ["光模块","光通信","CPO","光器件","硅光","液冷","算力","服务器","IDC","数据中心"]
    robo = ["机器人","自动","伺服","减速","传动","控制"]
    ne = ["新能","锂电","光伏","储能","风电","固态","钠离子"]
    med = ["医药","生物","制药","医疗","器械","创新药","CXO","疫苗"]
    auto = ["汽车","整车","零部件","智能驾驶","座舱","激光雷达"]
    mil = ["军工","航天","航空","导弹","雷达","舰船"]
    cons = ["消费","食品","饮料","白酒","家电","旅游","免税","医美"]
    ai_software = ["AI","人工智能","大模型","软件","信创","SaaS","数据"]

    if any(k in nc for k in semis): drivers.append("半导体产业链：国产替代+AI芯片需求双轮驱动，关注设备/材料国产化率提升")
    if any(k in nc for k in ai_cp): drivers.append("AI算力基建：海外云厂商资本开支高增，800G/1.6T光模块放量，液冷渗透率提升")
    if any(k in nc for k in robo): drivers.append("机器人产业：特斯拉Optimus迭代+国内政策支持，减速器/伺服系统先行受益")
    if any(k in nc for k in ne): drivers.append("新能源：光伏装机超预期+锂电排产回暖，关注新技术路线（固态/钠电）")
    if any(k in nc for k in med): drivers.append("医药生物：创新药出海加速+CXO订单回暖，估值修复行情")
    if any(k in nc for k in auto): drivers.append("汽车产业链：智能驾驶渗透率提升+零部件国产替代，关注机器人跨界标的")
    if any(k in nc for k in mil): drivers.append("军工：订单恢复+资产整合预期，关注航空航天核心标的")
    if any(k in nc for k in cons): drivers.append("大消费：消费复苏+政策刺激，关注业绩确定性强的龙头")
    if any(k in nc for k in ai_software): drivers.append("AI应用：大模型商用落地+信创替代，关注有真实收入转化的标的")
    if not drivers:
        if pct >= 9.5: drivers.append("涨停封板，短线情绪推动，关注次日溢价和换手率变化")
        elif pct >= 5: drivers.append("主力资金介入，量价配合，关注板块联动和持续性")
        else: drivers.append("跟随市场节奏，需观察量能确认趋势")
    return "；".join(drivers)


# ================================================================
# 六段+市场全貌报告
# ================================================================
def generate_full_summary(watch_results, hot_results, indices, breadth, news, quotes_pool):
    parts = []
    bd = breadth or {}; nd = news or {}
    pcts_all = [v.get("pct", 0) for v in (indices or {}).values() if v]
    all_down = indices and all(p < -0.5 for p in pcts_all)
    up_n = bd.get("涨家数"); dn_n = bd.get("跌家数")

    # ═══ 一、大盘定性 ═══
    idx_lines = []
    for _, info in (indices or {}).items():
        p = info.get("pct", 0); a = "↑" if p > 0 else "↓"
        idx_lines.append(f"{info['name']} {info.get('price',0):.0f} {a}{abs(p):.2f}%")
    parts.append(f"【一、大盘定性】{' | '.join(idx_lines)}")
    amt = bd.get("两市成交额", 0)
    if amt > 0:
        vs = bd.get("放量缩量", ""); ys = bd.get("昨日成交额", 0)
        note = f"（{vs}" + (f"，昨日{ys/1e8:.0f}亿" if ys > 0 else "") + "）" if vs else ""
        parts.append(f"两市成交 {amt/1e8:.0f}亿{note}")
    if pcts_all:
        up = sum(1 for p in pcts_all if p > 0)
        if up >= len(pcts_all)-1 and all(p > 0.3 for p in pcts_all): env = "普涨格局，操作环境积极"
        elif up == 0 and all(p < -1 for p in pcts_all): env = "情绪退潮，防守为主"
        elif max(pcts_all)-min(pcts_all) > 2: env = "结构性分化，重结构轻指数"
        elif all(abs(p) < 0.5 for p in pcts_all): env = "窄幅震荡，观望等方向"
        else: env = "震荡分化，控制仓位高抛低吸"
        parts.append(f"定性：{env}")

    # ═══ 二、市场情绪 ═══
    sp = []
    if up_n and dn_n and up_n+dn_n > 0:
        sp.append(f"上涨{up_n}家/下跌{dn_n}家 赚钱效应{up_n/(up_n+dn_n)*100:.0f}%")
    zt = bd.get("涨停数"); dt = bd.get("跌停数")
    if zt and dt: sp.append(f"涨停≈{zt}家/跌停≈{dt}家")
    if sp:
        em = "偏暖" if (up_n and dn_n and up_n>dn_n*1.5) else ("冰点" if (up_n and dn_n and dn_n>up_n*3) else "中性")
        sp.append(f"短线情绪：{em}")
        parts.append(f"【二、市场情绪】{' | '.join(sp)}")

    # ═══ 三、北向+主力资金 ═══
    parts.append(_build_capital_section(bd, hot_results, quotes_pool))

    # ═══ 四、消息面 ═══
    parts.append(_build_news_section(nd, hot_results, watch_results, all_down))

    # ═══ 五、核心主线板块（半导体/光模块深度）═══
    parts.append(_build_sector_deep_dive(hot_results, quotes_pool))

    # ═══ 六、跌幅板块&风险 ═══
    parts.append(_build_risk_section(watch_results, hot_results, all_down, quotes_pool))

    # ═══ 七、明日推演 ═══
    parts.append(_build_tomorrow_section(indices, pcts_all, hot_results, all_down))

    # ═══ 八、仓位策略 ═══
    bull = sum(1 for _, d in watch_results.items() if "偏多" in d.get("analysis", {}).get("suggestion", ""))
    bear = sum(1 for _, d in watch_results.items() if "偏空" in d.get("analysis", {}).get("suggestion", ""))
    parts.append(_build_position_section(bull, bear, hot_results, watch_results, all_down))

    return "\n\n".join(parts)


# ── 北向资金 ──
def _build_capital_section(bd, hot_results, quotes):
    lines = []
    nf = bd.get("北向净流入")
    if nf is not None:
        d = "净流入" if nf > 0 else "净流出"
        lines.append(f"北向资金：{d} {abs(nf):.1f}亿" + ("（偏多信号）" if nf > 30 else "（小幅波动）" if abs(nf) < 10 else "（偏空信号）"))
    else:
        lines.append("北向资金：数据暂不可用（eastmoney接口波动）")

    # 从盘面估算资金偏好
    if quotes:
        total_in = {}
        for code, q in quotes.items():
            pct = q.get("pct_change", 0); amt = q.get("amount", 0)
            if pct > 2 and amt > 1e8:
                # 简单归类
                name = q.get("name", "")
                sector = _classify_sector(name, code)
                total_in[sector] = total_in.get(sector, 0) + amt
        if total_in:
            sorted_sec = sorted(total_in.items(), key=lambda x: x[1], reverse=True)
            top_in = ", ".join(f"{s}({v/1e8:.0f}亿)" for s, v in sorted_sec[:4])
            lines.append(f"资金偏好（估算）：{top_in}")

    # 风格总结
    if hot_results:
        tech_count = sum(1 for h in hot_results[:20] if any(k in h.get("driver_note","") for k in ["半导体","AI","光模块","算力","机器人"]))
        med_count = sum(1 for h in hot_results[:20] if "医药" in h.get("driver_note",""))
        if tech_count > med_count * 2: style = "资金聚焦科技成长，短线游资抱团AI/半导体"
        elif med_count > tech_count: style = "资金偏向防御，医药消费获关注"
        else: style = "资金分散，板块轮动加速"
        lines.append(f"风格总结：{style}")

    return f"【三、资金面】\n  " + "\n  ".join(lines)


def _classify_sector(name, code):
    nc = name + code
    if any(k in nc for k in ["半导体","芯片","集成","晶圆","封测","光刻"]): return "半导体"
    if any(k in nc for k in ["光模块","光通信","CPO","液冷","算力","服务器"]): return "AI算力"
    if any(k in nc for k in ["机器人","自动","伺服","减速"]): return "机器人"
    if any(k in nc for k in ["新能","锂电","光伏","储能","风电"]): return "新能源"
    if any(k in nc for k in ["医药","生物","制药","医疗"]): return "医药"
    if any(k in nc for k in ["汽车","整车","零部件","智驾"]): return "汽车"
    if any(k in nc for k in ["军工","航天","导弹"]): return "军工"
    return "其他"


# ── 消息面 ──
def _build_news_section(nd, hot_results, watch_results, all_down):
    lines = []
    # 过滤无关新闻
    skip_kw = ["海外个股","场外基金","ETF华宝","ETF（","小炮APP","观影团","微博","足球","冰岛","比利时",
               "易捷航空","洛克希德","黑石","TeraWulf","游艇","Zuber","哈萨克","五角大楼"]
    real_bull = [n for n in nd.get("利好", []) if not any(k in n.get("title","") for k in skip_kw)]
    real_bear = [n for n in nd.get("利空", []) if not any(k in n.get("title","") for k in skip_kw)]
    real_other = [n for n in nd.get("其他", []) if not any(k in n.get("title","") for k in skip_kw)]

    if real_bull:
        titles = " | ".join(n["title"][:60] for n in real_bull[:6])
        lines.append(f"利好({len(real_bull)}条)：{titles}")
    if real_bear:
        titles = " | ".join(n["title"][:60] for n in real_bear[:4])
        lines.append(f"利空({len(real_bear)}条)：{titles}")
    if real_other:
        titles = " | ".join(n["title"][:60] for n in real_other[:2])
        lines.append(f"其他：{titles}")

    # 盘面推演
    inf_bull = []; inf_bear = []
    has_ai = any("AI" in h.get("driver_note","") or "半导体" in h.get("driver_note","") or "光模块" in h.get("driver_note","") for h in hot_results[:15])
    if has_ai: inf_bull.append("AI算力/半导体产业链资金持续介入，中线逻辑明确")
    has_robot = any("机器人" in h.get("driver_note","") for h in hot_results[:15])
    if has_robot: inf_bull.append("机器人概念维持活跃，产业催化持续")
    if all_down: inf_bear.append("三大指数全线收跌，注意系统性风险")
    weak = [n for n, d in watch_results.items() if (d.get("quote") or {}).get("pct_change", 0) < -4]
    if weak: inf_bear.append(f"自选{'、'.join(weak)}跌超4%，关注资金动向")

    if inf_bull: lines.append(f"盘面利好：{'；'.join(inf_bull)}")
    if inf_bear: lines.append(f"盘面利空：{'；'.join(inf_bear)}")
    if not lines: lines.append("今日暂无重大消息面驱动")
    return f"【四、消息面汇总】\n  " + "\n  ".join(lines)


# ── 半导体+光模块深度 ──
SEMI_DETAIL = {
    "设备": ["688012","002371","688200","688082"],
    "材料": ["688126","688019","300346","688233"],
    "封测": ["002156","002185","600584","688362"],
    "存储": ["688525","603986","688110","002049"],
    "设计": ["688256","688041","688107","688536","688047","688123"],
    "制造": ["688981","688396"],
}

def _build_sector_deep_dive(hot_results, quotes):
    lines = []
    # 半导体细分
    semi_codes = set()
    for sub, codes in SEMI_DETAIL.items():
        semi_codes.update(codes)

    if quotes:
        semi_stocks = [(code, quotes[code]) for code in semi_codes if code in quotes]
        sub_analysis = {}
        for sub, codes in SEMI_DETAIL.items():
            items = [(c, quotes[c]) for c in codes if c in quotes]
            if items:
                avg = sum(q["pct_change"] for _, q in items) / len(items)
                sub_analysis[sub] = {"avg": avg, "count": len(items)}

        if sub_analysis:
            sub_lines = []
            for sub, info in sorted(sub_analysis.items(), key=lambda x: x[1]["avg"], reverse=True):
                arrow = "↑" if info["avg"] > 0 else "↓"
                sub_lines.append(f"{sub}({info['count']}只){arrow}{info['avg']:+.1f}%")
            lines.append(f"【五、半导体+光模块深度】")
            lines.append(f"半导体细分强弱：{' | '.join(sub_lines)}")

    # 光模块+液冷
    optical_codes = ["300308","300394","300502","688498","300570","688313","002281","688205","301191","300499"]
    if quotes:
        opt_stocks = [(c, quotes[c]) for c in optical_codes if c in quotes]
        if opt_stocks:
            avg = sum(q["pct_change"] for _, q in opt_stocks) / len(opt_stocks)
            tops = sorted(opt_stocks, key=lambda x: x[1]["pct_change"], reverse=True)[:3]
            names = ", ".join(f"{quotes[c]['name']}({quotes[c]['pct_change']:+.1f}%)" for c, _ in tops)
            lines.append(f"光模块/液冷均涨幅{avg:+.1f}% 龙头：{names}")
            if avg > 3: lines.append("海外AI服务器资本开支高增，800G/1.6T光模块放量逻辑持续验证，液冷渗透率提升趋势明确。关注龙头订单兑现。")
            elif avg > 0: lines.append("板块温和修复，关注北美云厂商Q3资本开支指引。中线景气度不变，短期需消化估值。")
            else: lines.append("板块回调，高估值压力释放。中线AI算力需求确定性高，关注超跌龙头布局机会。")

    # 高PE估值提示
    high_pe = [h for h in hot_results[:10] if h.get("pe", 0) > 200]
    if high_pe:
        lines.append("⚠️ 高PE标的估值提示：部分科技股PE较高，依赖行业景气兑现和业绩高增消化估值，警惕增速不及预期导致的戴维斯双杀。")

    if not lines: lines.append("【五、半导体+光模块深度】数据收集中")
    return "\n  ".join(lines)


# ── 风险 ──
def _build_risk_section(watch_results, hot_results, all_down, quotes):
    lines = ["【六、跌幅板块&市场风险】"]
    # 从行情池找弱势板块
    if quotes:
        weak_by_sec = {}
        for code, q in quotes.items():
            pct = q.get("pct_change", 0)
            if pct < -2:
                sec = _classify_sector(q.get("name",""), code)
                weak_by_sec.setdefault(sec, []).append(pct)
        if weak_by_sec:
            worst = sorted(weak_by_sec.items(), key=lambda x: sum(x[1])/len(x[1]))[:4]
            worst_str = " | ".join(f"{s}(均{sum(p)/len(p):+.1f}%)" for s, p in worst)
            lines.append(f"弱势板块：{worst_str}")

    weak_names = [n for n, d in watch_results.items() if (d.get("quote") or {}).get("pct_change", 0) < -3]
    if weak_names: lines.append(f"自选弱势：{'、'.join(weak_names)}")

    high_risk = [h for h in hot_results if h.get("pct_change", 0) > 9 and h.get("turnover", 0) > 10]
    if high_risk: lines.append(f"高位放量防回落：{'、'.join(h['name'] for h in high_risk)}")

    lines.append("避雷：纯题材无业绩支撑、高位放量滞涨、ST/问题股、大股东减持中标的")
    return "\n  ".join(lines)


# ── 明日推演 ──
def _build_tomorrow_section(indices, pcts, hot_results, all_down):
    lines = ["【七、明日行情推演】"]
    # 支撑压力
    if indices:
        sh = indices.get("上证", {})
        if sh:
            lines.append(f"上证关键支撑 {sh.get('low',0):.0f} / 压力 {sh.get('high',0):.0f}")
            lines.append(f"创业板支撑 {indices.get('创业板',{}).get('low',0):.0f} / 压力 {indices.get('创业板',{}).get('high',0):.0f}")

    # 资金轮动预判
    tech_strong = sum(1 for h in hot_results[:15] if any(k in h.get("driver_note","") for k in ["AI","半导体","光模块","算力"]))
    if tech_strong >= 5: lines.append("科技方向资金认可度高，明日有望延续活跃，关注龙头溢价")
    elif tech_strong >= 2: lines.append("科技方向局部活跃，明日关注量能是否持续，若缩量则轮动概率大")
    else: lines.append("科技方向休整，明日关注新能源/医药是否承接轮动资金")

    # 情景预判
    lines.append("情景①（偏多）：早盘放量+科技延续 → 可适当提升仓位至5-7成")
    lines.append("情景②（震荡）：量能持平+板块轮动 → 维持4-6成，高抛低吸")
    lines.append("情景③（偏空）：低开低走+缩量 → 减仓至3成以下，等企稳信号")
    lines.append("关注晚间美股科技股走势和北向资金明早盘前数据")

    return "\n  ".join(lines)


# ── 仓位策略 ──
def _build_position_section(bull, bear, hot_results, watch_results, all_down):
    lines = ["【八、仓位策略】"]
    total = len(watch_results)
    if all_down: pt, pm = "3成以下", "3成以下"
    elif bull >= bear + 2: pt, pm = "5-7成", "5-7成"
    elif bear >= bull + 2: pt, pm = "3-5成", "3-4成"
    else: pt, pm = "4-6成", "4-5成"
    lines.append(f"今日仓位：{pt} | 明日建议：{pm}")

    # 主打、潜伏、规避
    mains = []
    if hot_results:
        by_sec = {}
        for h in hot_results:
            if h["sector"] != "全市场热门":
                by_sec.setdefault(h["sector"], []).append(h["pct_change"])
        mains = [s for s, p in sorted(by_sec.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True) if sum(p)/len(p) > 1.5]
    latent = []
    for n, d in watch_results.items():
        tech = d.get("analysis", {}).get("technical", {})
        macd = tech.get("macd_trend", {})
        ma = tech.get("ma_trend", {})
        if macd.get("golden_cross") and "下方" in ma.get("price_vs_ma20", ""):
            latent.append(f"{n}(金叉+低位)")
    av = ["纯题材无业绩", "ST/问题股", "大股东减持中", "高位放量滞涨"]
    lines.append(f"主打：{'、'.join(mains) if mains else '跟随资金选择强势板块'}")
    lines.append(f"潜伏：{'、'.join(latent) if latent else '等回调企稳信号'}")
    lines.append(f"规避：{'、'.join(av)}")

    notable = [h for h in hot_results[:12] if h["pct_change"] >= 2]
    short = f"短线（1-3日）：{'关注' + '、'.join(h['name'] for h in notable[:4]) if notable else '减少操作'}，快进快出±5%止损"
    med = f"中线（1-4周）：{'持有' if bull >= bear else '观望'}均线多头标的，MA20附近分批建仓，目标10-20%波段"
    lines.append(f"短线：{short}")
    lines.append(f"中线：{med}")

    return "\n  ".join(lines)


def _sf(v):
    try:
        if pd.isna(v): return 0.0
        return float(v)
    except: return 0.0

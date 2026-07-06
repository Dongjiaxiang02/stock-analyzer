"""
分析策略模块 v2
- 自选股技术分析(均线+MACD+支撑压力+多空评分+基本面)
- 热门个股筛选(真实赛道催化驱动)
- 八段市场全貌报告(情绪量化/资金面/半导体深度/明日推演)
"""
import logging
from typing import Optional
import pandas as pd
from config import HOT_SECTORS, MARKET_HOT_TOP_N, MARKET_MIN_PCT_CHANGE, MARKET_MIN_AMOUNT, DISCLAIMER
from indicators import build_technical_summary

logger = logging.getLogger(__name__)

FUNDAMENTALS = {
    "石头科技": "全球扫地机器人龙头，海外营收占比高，AI导航技术壁垒，消费复苏+出海双驱动",
    "科沃斯": "扫地机器人+小家电双轮驱动，国内品牌力强，关注新品周期和海外拓展进度",
    "嘉美包装": "食品饮料金属包装龙头，绑定大客户(农夫山泉等)，周期性较弱，跟随消费品景气",
    "影石创新": "全景运动相机全球第一(81.7%份额)，AI+影像，上市后业绩高增67%，高成长赛道",
    "小米集团-W": "手机×AIoT×汽车三线并进，SU7交付超预期，港股科技龙头，关注汽车毛利率爬坡",
}

LATENT_CATALYSTS = {
    "科沃斯": "新品T50系列发布+海外渠道扩张+扫地机器人渗透率提升",
    "影石创新": "AI影像芯片自研+运动相机消费复苏+海外营收占比超70%受益汇率",
    "小米集团-W": "SU7持续放量+汽车毛利率改善+手机高端化+AIoT生态变现",
    "石头科技": "海外Prime Day大促+扫地机器人换机周期+AI导航技术领先",
    "嘉美包装": "夏季饮料旺季+新客户拓展+马口铁成本下行",
}


def analyze_watch_stock(name, code, quote, history):
    result = {"name": name, "code": code, "quote": quote or {}, "technical": {},
              "suggestion": "—", "risk_note": "", "fundamental": FUNDAMENTALS.get(name, ""),
              "latent_catalyst": LATENT_CATALYSTS.get(name, "")}
    if quote is None: result["suggestion"] = "⚠️ 无法获取实时行情"; return result
    if history is None or history.empty: result["suggestion"] = "⚠️ 历史K线不足"; return result
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
        if r3 > 5: bull += 1; notes.append(f"近3日+{r3}%短线强势")
        elif r3 < -5: bear += 2; notes.append(f"近3日{r3}%超跌")
        elif r3 > 0: bull += 0.5
        else: bear += 0.5
    if macd.get("golden_cross"): bull += 2; notes.append("MACD金叉")
    if macd.get("death_cross"): bear += 2; notes.append("MACD死叉")
    if "上方" in macd.get("dif_position", ""): bull += 1
    else: bear += 0.5
    pct = quote.get("pct_change", 0)
    if pct > 5: bull += 1; notes.append(f"大涨{pct}%")
    elif pct < -5: bear += 2; notes.append(f"大跌{pct}%")
    result["suggestion"] = _sug(bull, bear, sr)
    result["risk_note"] = " | ".join(notes) if notes else "无明显信号"
    result["bull_score"] = bull; result["bear_score"] = bear
    return result

def _sug(bull, bear, sr):
    t = bull + bear
    if t == 0: return "数据不足"
    r = bull / t; s = sr.get("support", 0); p = sr.get("resistance", 0)
    if r >= 0.70: return f"🟢 偏多({r:.0%}) 支撑¥{s:.0f} 压力¥{p:.0f}，持有观察"
    elif r >= 0.55: return f"🟡 偏多震荡({r:.0%}) 支撑¥{s:.0f} 压力¥{p:.0f}，持有观望"
    elif r >= 0.40: return f"🟠 方向不明 支撑¥{s:.0f} 压力¥{p:.0f}，观望为主"
    elif r >= 0.25: return f"🟡 偏空震荡(空头{1-r:.0%}) 支撑¥{s:.0f}，重仓关注减仓"
    else: return f"🔴 偏空(空头{1-r:.0%}) 支撑¥{s:.0f} 压力¥{p:.0f}，控制仓位"


# ── 热门个股 ──
def analyze_hot_stocks(market_df, sector_data):
    results = []
    if market_df is not None and not market_df.empty:
        mk = market_df.copy()
        for col in ["涨跌幅", "成交额"]:
            if col in mk.columns: mk[col] = pd.to_numeric(mk[col], errors="coerce")
        mk = mk[mk["涨跌幅"] >= MARKET_MIN_PCT_CHANGE]
        mk = mk[mk["成交额"] >= MARKET_MIN_AMOUNT]
        mk = mk.sort_values("涨跌幅", ascending=False).head(MARKET_HOT_TOP_N)
        for _, row in mk.iterrows(): results.append(_hot(row, "全市场热门"))
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
            if any(r["code"] == str(row.get("代码", "")) for r in results): continue
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
    nc = name + code
    m = {
        "半导体": (["半导体","芯片","集成","晶圆","封测","光刻","存储","设备","材料"],
                   "半导体产业链：国产替代+AI芯片双轮驱动，关注设备/材料国产化率提升"),
        "AI算力": (["光模块","光通信","CPO","光器件","硅光","液冷","算力","服务器","IDC","数据中心"],
                   "AI算力基建：海外云厂商资本开支高增，800G/1.6T光模块放量，液冷渗透率提升"),
        "机器人": (["机器人","自动","伺服","减速","传动","控制"],
                   "机器人产业：特斯拉Optimus迭代+国内政策支持，减速器/伺服系统先行受益"),
        "新能源": (["新能","锂电","光伏","储能","风电","固态","钠离子"],
                   "新能源：光伏装机超预期+锂电排产回暖，关注新技术路线(固态/钠电)"),
        "医药": (["医药","生物","制药","医疗","器械","创新药","CXO","疫苗"],
                 "医药生物：创新药出海加速+CXO订单回暖，估值修复行情"),
        "汽车": (["汽车","整车","零部件","智能驾驶","座舱","激光雷达"],
                 "汽车产业链：智能驾驶渗透率提升+零部件国产替代，关注机器人跨界标的"),
        "军工": (["军工","航天","航空","导弹","雷达","舰船"],
                 "军工：订单恢复+资产整合预期，关注航空航天核心标的"),
        "消费": (["消费","食品","饮料","白酒","家电","旅游","免税","医美"],
                 "大消费：消费复苏+政策刺激，关注业绩确定性强的龙头"),
        "AI应用": (["AI","人工智能","大模型","软件","信创","SaaS","数据"],
                   "AI应用：大模型商用落地+信创替代，关注有真实收入转化的标的"),
    }
    dr = []
    for label, (kws, desc) in m.items():
        if any(k in nc for k in kws): dr.append(desc)
    if not dr:
        if pct >= 9.5: dr.append("涨停封板，短线情绪推动，关注次日溢价和换手率变化")
        elif pct >= 5: dr.append("主力资金介入，量价配合，关注板块联动和持续性")
        else: dr.append("跟随市场节奏，需观察量能确认趋势")
    return "；".join(dr)


# ═══════════════════════════════════════════════
# 八段市场全貌报告 V2
# ═══════════════════════════════════════════════
def generate_full_summary(watch_results, hot_results, indices, breadth, news, quotes_pool):
    parts = []
    bd = breadth or {}; nd = news or {}
    pcts_all = [v.get("pct_change", v.get("pct_change", 0)) for v in (indices or {}).values() if v]
    all_down = indices and all(p < -0.5 for p in pcts_all)
    up_n = bd.get("涨家数"); dn_n = bd.get("跌家数"); zt = bd.get("涨停数"); dt = bd.get("跌停数")
    total_amt = bd.get("两市成交额", 0); ys_amt = bd.get("昨日成交额", 0)

    # ═══ 一、大盘定性 ═══
    idx_lines = []
    for _, info in (indices or {}).items():
        p = info.get("pct_change", 0); a = "↑" if p > 0 else "↓"
        idx_lines.append(f"{info['name']} {info.get('price',0):.0f} {a}{abs(p):.2f}%")
    parts.append(f"【一、大盘定性】{' | '.join(idx_lines)}")

    if total_amt > 0:
        amt_str = f"两市成交 {total_amt/1e8:.0f}亿"
        if ys_amt > 0:
            chg = (total_amt/ys_amt - 1) * 100
            amt_str += f"（环比{chg:+.1f}%，{'放量' if chg>5 else '缩量' if chg<-5 else '持平'}）"
        parts.append(amt_str)

    # 支撑压力（从K线数据或价格±2%估算）
    if indices:
        sh = indices.get("上证", {}); cy = indices.get("创业板", {})
        sh_p = sh.get("price", 0); cy_p = cy.get("price", 0)
        sh_low = sh.get("low", sh_p * 0.98) if sh_p > 0 else 0
        sh_high = sh.get("high", sh_p * 1.02) if sh_p > 0 else 0
        cy_low = cy.get("low", cy_p * 0.98) if cy_p > 0 else 0
        cy_high = cy.get("high", cy_p * 1.02) if cy_p > 0 else 0
        if sh_p > 0:
            parts.append(f"上证支撑 {sh_low:.0f} / 压力 {sh_high:.0f} | "
                        f"创业板支撑 {cy_low:.0f} / 压力 {cy_high:.0f}")

    if pcts_all:
        up = sum(1 for p in pcts_all if p > 0)
        if up >= len(pcts_all)-1 and all(p > 0.3 for p in pcts_all): env = "普涨格局，操作环境积极"
        elif up == 0 and all(p < -1 for p in pcts_all): env = "情绪退潮，防守为主"
        elif max(pcts_all)-min(pcts_all) > 2: env = "结构性分化，重结构轻指数"
        elif all(abs(p) < 0.5 for p in pcts_all): env = "窄幅震荡，观望等方向"
        else: env = "震荡分化，控制仓位高抛低吸"
        parts.append(f"定性：{env}")

    # ═══ 二、市场情绪（量化评分）═══
    score = 50  # 基准
    sp = []
    if up_n and dn_n and up_n+dn_n > 0:
        wr = up_n/(up_n+dn_n)*100
        sp.append(f"上涨{up_n}家/下跌{dn_n}家 赚钱效应{wr:.0f}%")
        score += (wr - 50) * 0.5  # 赚钱效应贡献 ±25分
    if zt is not None and dt is not None:
        sp.append(f"涨停≈{zt}家/跌停≈{dt}家")
        if zt > 50: score += 20
        elif zt > 20: score += 10
        elif zt < 5: score -= 15
        if dt > 30: score -= 20
        elif dt > 10: score -= 10
    # 连板高度估算
    if zt and zt > 100: lh = "高（>8板）"; score += 15
    elif zt and zt > 50: lh = "中（5-7板）"; score += 5
    elif zt and zt > 10: lh = "低（3-4板）"; score -= 5
    else: lh = "冰点（≤2板）"; score -= 10
    sp.append(f"最高连板≈{lh}")
    # 炸板率估算（涨停数少+跌停数多=炸板率高）
    if zt and dt and zt > 0:
        zbr = min(dt/(zt+dt)*100, 50) if (zt+dt) > 0 else 0
        sp.append(f"炸板率≈{zbr:.0f}%")
        if zbr > 30: score -= 15
        elif zbr < 10: score += 5

    score = max(0, min(100, score))
    if score < 25: grade = "冰点❄️"
    elif score < 40: grade = "偏冷🧊"
    elif score < 60: grade = "中性🌤️"
    elif score < 75: grade = "偏暖🔥"
    else: grade = "火热🚀"
    sp.append(f"情绪评分：{score}分 {grade}")
    parts.append(f"【二、市场情绪】{' | '.join(sp)}")

    # ═══ 三、资金面 ═══
    parts.append(_capital(bd, hot_results, quotes_pool))

    # ═══ 四、消息面 ═══
    parts.append(_news(nd, hot_results, watch_results, all_down))

    # ═══ 五、半导体+光模块深度 ═══
    parts.append(_semi_deep(hot_results, quotes_pool))

    # ═══ 六、跌幅板块+风险 ═══
    parts.append(_risk(watch_results, hot_results, all_down, quotes_pool))

    # ═══ 七、明日推演 ═══
    parts.append(_tomorrow(indices, hot_results, watch_results, all_down))

    # ═══ 八、仓位策略 ═══
    bull = sum(1 for _, d in watch_results.items() if "偏多" in d.get("analysis", {}).get("suggestion", ""))
    bear = sum(1 for _, d in watch_results.items() if "偏空" in d.get("analysis", {}).get("suggestion", ""))
    parts.append(_position(bull, bear, hot_results, watch_results, all_down))

    return "\n\n".join(parts)


# ── 资金面 V2 ──
def _capital(bd, hot_results, quotes):
    lines = []
    nf = bd.get("北向净流入")
    if nf is not None:
        d = "净流入" if nf > 0 else "净流出"
        lines.append(f"北向资金：{d}{abs(nf):.1f}亿" + ("（积极做多）" if nf>30 else "（偏多）" if nf>10 else "（偏空）" if nf<-20 else ""))
    else:
        lines.append("北向资金：数据源故障（push2.eastmoney不可用），参考港股通替代数据暂缺")

    # 从盘面估算主力净流入/流出板块
    if quotes:
        sec_flow = {}
        for code, q in quotes.items():
            pct = q.get("pct_change", 0); amt = q.get("amount", 0)
            sec = _sec(q.get("name",""), code)
            if pct > 1.5:
                sec_flow.setdefault("in", {}).setdefault(sec, 0)
                sec_flow["in"][sec] += amt
            elif pct < -1.5:
                sec_flow.setdefault("out", {}).setdefault(sec, 0)
                sec_flow["out"][sec] += amt

        top_in = sorted(sec_flow.get("in", {}).items(), key=lambda x: x[1], reverse=True)[:3]
        top_out = sorted(sec_flow.get("out", {}).items(), key=lambda x: x[1], reverse=True)[:3]
        if top_in:
            lines.append("主力净流入TOP3（估算）：" + " | ".join(f"{s}({v/1e8:.0f}亿)" for s, v in top_in))
        if top_out:
            lines.append("主力净流出TOP3（估算）：" + " | ".join(f"{s}({v/1e8:.0f}亿)" for s, v in top_out))

    # 风格
    tech_n = sum(1 for h in hot_results[:20] if any(k in h.get("driver_note","") for k in ["半导体","AI","光模块","算力","机器人"]))
    med_n = sum(1 for h in hot_results[:20] if "医药" in h.get("driver_note",""))
    if tech_n > med_n * 2: style = "资金聚焦科技成长，短线游资抱团AI/半导体"
    elif med_n > tech_n: style = "资金偏向防御，医药消费获关注"
    else: style = "资金分散，板块轮动加速"
    lines.append(f"风格：{style}")
    return f"【三、资金面】\n  " + "\n  ".join(lines)


# ── 消息面 V2（利好利空分色折叠）──
def _news(nd, hot_results, watch_results, all_down):
    skip_kw = ["海外个股","场外基金","ETF华宝","ETF（","小炮APP","观影团","微博","足球","冰岛","比利时",
               "易捷航空","洛克希德","黑石","TeraWulf","游艇","Zuber","哈萨克","五角大楼"]
    rb = [n for n in nd.get("利好", []) if not any(k in n.get("title","") for k in skip_kw)]
    rbe = [n for n in nd.get("利空", []) if not any(k in n.get("title","") for k in skip_kw)]
    ro = [n for n in nd.get("其他", []) if not any(k in n.get("title","") for k in skip_kw)]

    lines = []
    # HTML折叠标记
    if rb:
        titles = "<br>".join(f"· {n['title'][:80]}" for n in rb[:8])
        lines.append(f'<details open><summary><b>🟢 利好({len(rb)}条)</b></summary>{titles}</details>')
    if rbe:
        titles = "<br>".join(f"· {n['title'][:80]}" for n in rbe[:5])
        lines.append(f'<details open><summary><b>🔴 利空({len(rbe)}条)</b></summary>{titles}</details>')
    if ro:
        titles = "<br>".join(f"· {n['title'][:80]}" for n in ro[:3])
        lines.append(f'<details><summary><b>📋 其他({len(ro)}条)</b></summary>{titles}</details>')

    inf_bull = []; inf_bear = []
    if any("AI" in h.get("driver_note","") or "半导体" in h.get("driver_note","") for h in hot_results[:15]):
        inf_bull.append("AI算力/半导体产业链持续活跃")
    if any("机器人" in h.get("driver_note","") for h in hot_results[:15]):
        inf_bull.append("机器人概念维持活跃")
    if all_down: inf_bear.append("三大指数全线收跌")
    weak = [n for n, d in watch_results.items() if (d.get("quote") or {}).get("pct_change", 0) < -4]
    if weak: inf_bear.append(f"自选{'、'.join(weak)}跌超4%")

    if inf_bull: lines.append(f"盘面利好：{'；'.join(inf_bull)}")
    if inf_bear: lines.append(f"盘面利空：{'；'.join(inf_bear)}")
    if not lines: lines.append("今日暂无重大消息面驱动")
    return f"【四、消息面汇总】\n  " + "\n  ".join(lines)


# ── 半导体深度 V2 ──
SEMI = {
    "设备": ["688012","002371","688200","688082"],
    "材料": ["688126","688019","300346","688233"],
    "封测": ["002156","002185","600584","688362"],
    "存储": ["688525","603986","688110","002049"],
    "设计": ["688256","688041","688107","688536","688047","688123"],
    "制造": ["688981","688396"],
}

def _semi_deep(hot_results, quotes):
    lines = ["【五、半导体+光模块深度】"]
    if not quotes: return "\n  ".join(lines) + "\n  数据收集中"

    sub_lines = []
    for sub, codes in SEMI.items():
        items = [(c, quotes[c]) for c in codes if c in quotes]
        if items:
            avg = sum(q["pct_change"] for _, q in items) / len(items)
            vol_sum = sum(q.get("volume", 0) for _, q in items)
            arrow = "↑" if avg > 0 else "↓"
            sub_lines.append(f"{sub}({len(items)}只){arrow}{avg:+.1f}% 量{vol_sum/1e4:.0f}万手")
    lines.append("半导体细分：" + " | ".join(sub_lines))

    # 光模块
    opt_codes = ["300308","300394","300502","688498","300570","688313","002281","688205","301191","300499"]
    opt = [(c, quotes[c]) for c in opt_codes if c in quotes]
    if opt:
        avg = sum(q["pct_change"] for _, q in opt) / len(opt)
        tops = sorted(opt, key=lambda x: x[1]["pct_change"], reverse=True)[:3]
        names = ", ".join(f"{quotes[c]['name']}({quotes[c]['pct_change']:+.1f}%)" for c, _ in tops)
        lines.append(f"光模块/液冷均涨幅{avg:+.1f}% 龙头：{names}")
        # 区分驱动
        overseas = ["300308","300394","300502","688498"]  # 海外大客户绑定
        overseas_in_pool = [c for c in overseas if c in quotes]
        if overseas_in_pool:
            o_avg = sum(quotes[c]["pct_change"] for c in overseas_in_pool) / len(overseas_in_pool)
            lines.append(f"海外大客户链(中际/天孚/新易盛/源杰)均涨{o_avg:+.1f}%——北美云厂商资本开支驱动，中线景气确定")
        domestic = ["300570","688313","002281","301191","300499"]
        domestic_in_pool = [c for c in domestic if c in quotes]
        if domestic_in_pool:
            d_avg = sum(quotes[c]["pct_change"] for c in domestic_in_pool) / len(domestic_in_pool)
            lines.append(f"国内算力链(太辰光/仕佳/光迅/菲菱科思/高澜)均涨{d_avg:+.1f}%——国内算力自建+液冷渗透，短线博弈属性强")
        if avg > 3: lines.append("判定：主线延续，800G/1.6T放量逻辑验证中，龙头中线持有，短线注意高换手分歧")
        elif avg > 0: lines.append("判定：温和修复，关注北美云厂商Q3资本开支指引")
        else: lines.append("判定：回调消化估值，中线AI算力需求确定性高，超跌龙头可布局")

    # 成交量环比
    for sub, codes in SEMI.items():
        items = [(c, quotes[c]) for c in codes if c in quotes]
        if items:
            avg_vol = sum(q.get("volume", 0) for _, q in items) / len(items)
            if avg_vol > 5e6:
                lines.append(f"⚠ {sub}细分放量明显（均量{avg_vol/1e4:.0f}万手），短线活跃度提升，关注持续性")

    high_pe = [h for h in hot_results[:15] if h.get("pe", 0) > 200]
    if high_pe:
        names = ", ".join(f"{h['name']}(PE{h['pe']:.0f})" for h in high_pe[:5])
        lines.append(f"⚠ 高PE预警(TTM)：{names}——依赖行业景气兑现消化估值，警惕增速不及预期导致戴维斯双杀")

    return "\n  ".join(lines)


# ── 风险 V2 ──
def _risk(watch_results, hot_results, all_down, quotes):
    lines = ["【六、跌幅板块&市场风险】"]
    if quotes:
        weak_sec = {}
        for code, q in quotes.items():
            pct = q.get("pct_change", 0)
            if pct < -2:
                sec = _sec(q.get("name",""), code)
                weak_sec.setdefault(sec, []).append(pct)
        if weak_sec:
            ws = sorted(weak_sec.items(), key=lambda x: sum(x[1])/len(x[1]))[:4]
            lines.append("弱势板块：" + " | ".join(f"{s}(均{sum(p)/len(p):+.1f}%)" for s, p in ws))
    wn = [n for n, d in watch_results.items() if (d.get("quote") or {}).get("pct_change", 0) < -3]
    if wn: lines.append(f"自选弱势：{'、'.join(wn)}")
    hr = [h for h in hot_results if h.get("pct_change", 0) > 9 and h.get("turnover", 0) > 10]
    if hr: lines.append(f"⚠ 高位放量预警：{'、'.join(h['name'] for h in hr)}——防获利兑现回落风险")
    ht = [h for h in hot_results if h.get("turnover", 0) > 20]
    if ht: lines.append(f"⚠ 高换手预警(>20%)：{'、'.join(h['name'] for h in ht)}——短线筹码博弈激烈，注意波动风险")
    lines.append("避雷：纯题材无业绩支撑、ST/问题股、大股东减持中、高位放量滞涨")
    return "\n  ".join(lines)


# ── 明日推演 V2 ──
def _tomorrow(indices, hot_results, watch_results, all_down):
    lines = ["【七、明日行情推演】"]
    if indices:
        sh = indices.get("上证", {}); cy = indices.get("创业板", {})
        sh_p = sh.get("price", 0); cy_p = cy.get("price", 0)
        lines.append(f"关键点位：上证支撑{(sh.get('low') or sh_p*0.98):.0f}/压力{(sh.get('high') or sh_p*1.02):.0f} | "
                    f"创业板支撑{(cy.get('low') or cy_p*0.98):.0f}/压力{(cy.get('high') or cy_p*1.02):.0f}")

    tech_n = sum(1 for h in hot_results[:15] if any(k in h.get("driver_note","") for k in ["半导体","AI","光模块","算力"]))
    med_n = sum(1 for h in hot_results[:15] if "医药" in h.get("driver_note",""))
    ne_n = sum(1 for h in hot_results[:15] if "新能源" in h.get("driver_note",""))

    if tech_n >= 5: rotate = "科技方向资金认可度高，有望延续活跃"
    elif tech_n >= 2: rotate = "科技局部活跃，关注量能持续性"
    else: rotate = "科技休整，关注医药/新能源能否承接轮动"
    lines.append(f"轮动预判：{rotate}")

    lines.append("情景① 偏多（概率30%）：早盘放量+科技延续 → 侧重半导体设备/光模块龙头")
    lines.append("情景② 震荡（概率50%）：量能持平+板块轮动 → 轮动医药/新能源，高抛低吸")
    lines.append("情景③ 偏空（概率20%）：低开低走+缩量 → 偏向红利防御/现金，等企稳信号")
    return "\n  ".join(lines)


# ── 仓位策略 V2 ──
def _position(bull, bear, hot_results, watch_results, all_down):
    lines = ["【八、仓位策略】"]
    total = len(watch_results)
    if all_down: pt, pm = "3成以下", "3成以下"
    elif bull >= bear + 2: pt, pm = "5-7成", "5-7成"
    elif bear >= bull + 2: pt, pm = "3-5成", "3-4成"
    else: pt, pm = "4-6成", "4-5成"
    lines.append(f"今日仓位：{pt} | 明日建议：{pm}")

    mains = []
    if hot_results:
        bs = {}
        for h in hot_results:
            if h["sector"] != "全市场热门":
                bs.setdefault(h["sector"], []).append(h["pct_change"])
        mains = [s for s, p in sorted(bs.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True) if sum(p)/len(p) > 1.5]
    lines.append(f"主打：{'、'.join(mains) if mains else '跟随资金选择强势板块'}")

    # 潜伏+差异化催化剂
    latent_parts = []
    for n, d in watch_results.items():
        tech = d.get("analysis", {}).get("technical", {})
        macd = tech.get("macd_trend", {})
        ma = tech.get("ma_trend", {})
        if macd.get("golden_cross") and "下方" in ma.get("price_vs_ma20", ""):
            cat = d.get("analysis", {}).get("latent_catalyst", "")
            latent_parts.append(f"{n}({cat[:40] if cat else '等信号'})")
    lines.append(f"潜伏：{' | '.join(latent_parts) if latent_parts else '等回调企稳信号'}")

    lines.append(f"规避：纯题材无业绩、ST/问题股、大股东减持中、高位放量滞涨")

    notable = [h for h in hot_results[:12] if h["pct_change"] >= 2]
    st = f"短线(1-3日)：{'博弈' + '、'.join(h['name'] for h in notable[:4]) if notable else '减少操作'}，快进快出±5%止损"
    mt = f"中线(1-4周)：{'持有' if bull >= bear else '观望'}均线多头标的，MA20附近分批建仓，目标10-20%波段"
    lines.append(f"短线：{st}")
    lines.append(f"中线：{mt}")
    return "\n  ".join(lines)


def _sec(name, code):
    nc = name + code
    if any(k in nc for k in ["半导体","芯片","集成","晶圆","封测","光刻"]): return "半导体"
    if any(k in nc for k in ["光模块","光通信","CPO","液冷","算力","服务器"]): return "AI算力"
    if any(k in nc for k in ["机器人","自动","伺服","减速"]): return "机器人"
    if any(k in nc for k in ["新能","锂电","光伏","储能","风电"]): return "新能源"
    if any(k in nc for k in ["医药","生物","制药","医疗"]): return "医药"
    if any(k in nc for k in ["汽车","整车","零部件","智驾"]): return "汽车"
    if any(k in nc for k in ["军工","航天","导弹"]): return "军工"
    return "其他"

def _sf(v):
    try:
        if pd.isna(v): return 0.0
        return float(v)
    except: return 0.0

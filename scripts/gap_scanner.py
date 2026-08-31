# -*- coding: utf-8 -*-
"""断层补涨战法扫描器（资金断层 + 主线内补涨位）
四层逻辑（2026-08-31 紫光股份 000938 实盘验证：+8.53%/日，选股逻辑见 references/gap-rules.md）：
  ① 资金断层识别（方向）：主力净流入榜前列"同一板块≥3只抱团"=主线候选。
     —— 资金流只指路（告诉我钱去了哪个板块），不选股；选股交给价格结构。
  ② 主线内选补涨位（选股）：板块内选"资金靠前但当日涨幅最小 + 价格贴MA20"的票。
     —— 买第二不买第一：资金第一往往已涨高（追高=抬轿）。
  ③ 价格结构确认（买点）：一阳穿三线 或 长阳修复（昨收<MA20 且 今收>MA20 收回）+ 放量。
  ④ 排雷（风控）：ST/主力流出/高价一手>8000/688,300,301 排除 + 大盘环境提示。

数据源：东财 clist 快照（行业聚类）+ push2his K线（datasource 5源降级），强制直连。
用法：
    python gap_scanner.py                 # 自动模式：行业断层识别 + 补涨选股（最近交易日）
    python gap_scanner.py 20260831        # 指定日期
    python gap_scanner.py 20260831 算力    # 概念模式：按关键词找东财概念板块，在其成分内选补涨
    python gap_scanner.py 20260831 算力,芯片  # 多概念（逗号分隔）
"""
import sys, json, re, time, datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from datasource import get_kline

requests.Session.trust_env = False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# ── 断层补涨战法量化参数（可调）──
FLOW_SUM_MIN     = 1.5    # 行业断层门槛：行业主力净流入合计 ≥1.5亿
FLOW_CNT_MIN     = 3      # 行业断层门槛：行业内主力净流入>0 的票 ≥3只（防单票撑行业）
MAX_CHG          = 5.0    # 补涨位：当日涨幅 <5%（越小越靠前）
PRICE_MAX        = 80.0   # 排雷：股价 <80（一手<8000，适配小仓）
BIAS_MA20        = (-2.0, 3.0)  # 贴MA20：价/MA20 在 -2% ~ +3%（起步位，不是半山腰）
VOL_RATIO_MIN    = 1.5    # 放量：量比 ≥1.5（无量异动多假）
TOP_SECTORS      = 3      # 自动模式最多输出 TOP3 断层行业
TOP_PER_SECTOR   = 5      # 每个行业最多输出 TOP5 补涨候选

def last_trade_date():
    if len(sys.argv) > 1 and re.match(r"^\d{8}$", sys.argv[1]):
        return sys.argv[1]
    d = datetime.date.today()
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.strftime("%Y%m%d")

def em_clist(host, params, retries=3):
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"})
    for a in range(retries):
        try:
            r = s.get(f"https://{host}/api/qt/clist/get", params=params, timeout=20)
            return (r.json().get("data") or {}).get("diff") or []
        except Exception:
            time.sleep(1.2)
    return []

def snapshot_all():
    """全市场快照（东财 clist，f3 排序分页，含行业 f100 + 量比 f10 + 主力 f62）。
    返回 [{code,name,chg,price,vol_ratio,main_wan,industry}]，排雷 ST/退/688,300,301。"""
    rows = []
    host = "push2delay.eastmoney.com"
    for pn in range(1, 60):
        diff = em_clist(host, {"pn": pn, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3",
                               "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                               "fields": "f2,f3,f5,f8,f10,f12,f14,f62,f100"})
        if not diff:
            break
        for x in diff:
            nm = str(x.get("f14", ""))
            if "ST" in nm.upper() or "退" in nm:
                continue
            code = str(x.get("f12")).zfill(6)
            if code.startswith(("688", "300", "301")):
                continue
            try:
                chg = float(x.get("f3")); price = float(x.get("f2"))
            except (TypeError, ValueError):
                continue
            try:
                vr = float(x.get("f10"))
            except (TypeError, ValueError):
                vr = None
            rows.append({"code": code, "name": nm, "chg": chg, "price": price, "vol_ratio": vr,
                         "main_wan": (x.get("f62") or 0) / 1e4 if x.get("f62") is not None else 0,
                         "industry": x.get("f100") or "—"})
        try:
            last_chg = float(diff[-1].get("f3"))
        except (TypeError, ValueError):
            last_chg = None
        # f3 升序分页，已到底（涨幅转负且持续走低）提前停
        if last_chg is not None and last_chg < -8 and pn > 5:
            break
        time.sleep(0.25)
    return rows

def concept_boards(keywords):
    """按关键词找东财概念板块代码，返回 [(bk, 名称)]。关键词可逗号分隔多个。
    ⚠️ push2delay 单页 pz 上限≈100（pz=600 会返空），必须分页拉全概念列表。"""
    boards = []
    for pn in range(1, 8):
        diff = em_clist("push2delay.eastmoney.com",
                        {"pn": pn, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3",
                         "fs": "m:90+t:3", "fields": "f12,f14,f3,f62"})
        if not diff:
            break
        boards += diff
        if len(diff) < 100:
            break
        time.sleep(0.3)
    out = []
    for kw in keywords:
        for b in boards:
            nm = str(b.get("f14", ""))
            if kw and kw in nm:
                out.append((str(b.get("f12")), nm))
    # 去重保序
    seen = set(); uniq = []
    for bk, nm in out:
        if bk not in seen:
            seen.add(bk); uniq.append((bk, nm))
    return uniq[:6]

def concept_stocks(bk):
    """拉概念板块成分股（含主力资金 f62），返回与 snapshot_all 同构的 rows"""
    rows = []
    for pn in range(1, 30):
        diff = em_clist("push2delay.eastmoney.com",
                        {"pn": pn, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f62",
                         "fs": f"b:{bk}", "fields": "f2,f3,f10,f12,f14,f62,f100"})
        if not diff:
            break
        for x in diff:
            nm = str(x.get("f14", ""))
            if "ST" in nm.upper() or "退" in nm:
                continue
            code = str(x.get("f12")).zfill(6)
            if code.startswith(("688", "300", "301")):
                continue
            try:
                chg = float(x.get("f3")); price = float(x.get("f2"))
            except (TypeError, ValueError):
                continue
            try:
                vr = float(x.get("f10"))
            except (TypeError, ValueError):
                vr = None
            rows.append({"code": code, "name": nm, "chg": chg, "price": price, "vol_ratio": vr,
                         "main_wan": (x.get("f62") or 0) / 1e4 if x.get("f62") is not None else 0,
                         "industry": x.get("f100") or "—"})
        time.sleep(0.25)
    return rows

def sector_detect(rows):
    """行业断层识别：按 f100 行业聚合，主力合计≥FLOW_SUM_MIN 且 流入家数≥FLOW_CNT_MIN = 主线候选。
    返回按 (合计主力, 流入家数) 排序的 [(industry, main_sum, cnt, stocks)]"""
    agg = defaultdict(lambda: {"sum": 0.0, "cnt": 0, "stocks": []})
    for s in rows:
        agg[s["industry"]]["sum"] += s["main_wan"]
        if s["main_wan"] > 0:
            agg[s["industry"]]["cnt"] += 1
        agg[s["industry"]]["stocks"].append(s)
    sectors = []
    for ind, v in agg.items():
        if ind == "—" or v["sum"] < FLOW_SUM_MIN or v["cnt"] < FLOW_CNT_MIN:
            continue
        sectors.append((ind, v["sum"], v["cnt"], v["stocks"]))
    sectors.sort(key=lambda x: (-x[1], -x[2]))
    return sectors[:TOP_SECTORS]

def check_structure(code, name, date):
    """价格结构确认（K线，datasource 5源降级）：一阳穿三线 或 长阳修复。
    返回 dict 或 None。"""
    k = get_kline(code, n=70)
    kdate = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    if len(k) < 35 or k[-1]["d"] != kdate:
        return None
    i = len(k) - 1
    closes = [x["c"] for x in k]; highs = [x["h"] for x in k]; lows = [x["l"] for x in k]
    vols = [x["v"] for x in k]
    o, c = k[i]["o"], k[i]["c"]
    ma5 = sum(closes[i-4:i+1]) / 5; ma10 = sum(closes[i-9:i+1]) / 10
    ma20 = sum(closes[i-19:i+1]) / 20; ma30 = sum(closes[i-29:i+1]) / 30
    prev_c = closes[i-1]
    yang = c > o
    # ① 一阳穿三线：今日实体覆盖 MA5/MA10/MA20 三线
    body_low, body_high = min(o, c), max(o, c)
    cross3 = yang and body_low < min(ma5, ma10, ma20) and body_high > max(ma5, ma10, ma20)
    # ② 长阳修复：昨日收在 MA20 下方，今日收回 MA20 之上（从下方拉回）
    repair = yang and prev_c < ma20 and c > ma20 and c > prev_c
    if not (cross3 or repair):
        return None
    # 量能：当日量/昨量 ≥1.5 或 快照量比 ≥1.5（放量确认）
    vr = vols[i] / vols[i-1] if i > 0 and vols[i-1] else 9
    if vr < VOL_RATIO_MIN:
        return None
    prev_high = max(highs[max(0, i-60):i]) if i >= 1 else 0  # 目标=60日前高
    return {"code": code, "name": name, "close": c, "open": o, "yang": yang,
            "cross3": cross3, "repair": repair, "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma30": ma30,
            "vol_ratio": round(vr, 2), "target": prev_high,
            "buy_ref": round(c, 2), "stop": round(max(ma10, c * 0.97), 2)}

def pick_pull_late(stocks, date):
    """板块内补涨位选股：主力>0 + 涨幅<5% + 价/MA20贴均线 + 结构确认。"""
    # 预筛（K线前的便宜过滤）
    pre = [s for s in stocks
           if s["main_wan"] > 0 and s["chg"] < MAX_CHG and s["price"] < PRICE_MAX]
    pre.sort(key=lambda s: s["chg"])  # 涨幅最小优先
    pre = pre[:40]  # 控制K线请求量
    out = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(check_structure, s["code"], s["name"], date): s for s in pre}
        for f in as_completed(futs):
            s = futs[f]; r = f.result()
            if not r:
                continue
            bias = (r["close"] / r["ma20"] - 1) * 100
            if not (BIAS_MA20[0] <= bias <= BIAS_MA20[1]):
                continue
            r.update({"chg": s["chg"], "main_wan": s["main_wan"], "bias_ma20": round(bias, 1),
                      "vol_ratio_q": s["vol_ratio"], "industry": s["industry"]})
            out.append(r)
    out.sort(key=lambda x: -x["main_wan"])
    return out[:TOP_PER_SECTOR]

def market_state():
    """大盘环境（上证收盘 vs MA20）：右侧战法弱市禁用，仅提示不硬拦。"""
    try:
        r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                         params={"param": "sh000001,day,,,70,qfq"}, headers={"User-Agent": UA}, timeout=12)
        node = r.json()["data"]["sh000001"]
        rows = node.get("qfqday") or node.get("day") or []
        closes = [float(x[2]) for x in rows]
        ma20 = sum(closes[-20:]) / 20
        cur, date = closes[-1], rows[-1][0]
        return cur, ma20, date, cur > ma20
    except Exception:
        return None, None, None, None

def fmt_main(wan):
    return f"{wan / 1e4:+.2f}亿"

def main():
    date = last_trade_date()
    kw = None
    if len(sys.argv) > 2:
        kw = sys.argv[2]
    sh, ma20, gdate, ok = market_state()
    if sh is None:
        print("⚠️ 大盘数据取数失败")
    elif ok:
        print(f"✅ 大盘：上证 {sh:.2f} > MA20 {ma20:.2f}（{gdate}）——环境允许")
    else:
        print(f"🔴 大盘：上证 {sh:.2f} < MA20 {ma20:.2f}（{gdate}）——弱市断层补涨禁用，结果仅供观察")
    print(f"断层补涨战法 | 日期 {date}" + (f" | 概念: {kw}" if kw else " | 自动: 行业断层识别"))

    # ── 数据层：概念模式 or 自动模式 ──
    if kw:
        keywords = [x.strip() for x in kw.split(",") if x.strip()]
        boards = concept_boards(keywords)
        if not boards:
            print(f"❌ 未找到含关键词的概念板块: {keywords}（换词试试，如: 算力/机器人/创新药/芯片）")
            return
        print(f"命中概念板块 {len(boards)} 个: " + " / ".join(f"{nm}({bk})" for bk, nm in boards))
        print("拉成分股 + 板块内补涨位选股...")
        for bk, bname in boards[:2]:  # 最多处理前2个板块，防超时
            stocks = concept_stocks(bk)
            print(f"\n{'='*70}\n📌 概念板块: {bname}（成分 {len(stocks)} 只）\n{'='*70}")
            pool = [s for s in stocks if s["main_wan"] > 0]
            bsum = sum(s["main_wan"] for s in pool)
            print(f"  板块主力净流入合计: {fmt_main(bsum)}（流入 {len(pool)} 只）")
            if not pool:
                print("  ⚠️ 板块整体主力流出，断层不成立，跳过"); continue
            hits = pick_pull_late(pool, date)
            if not hits:
                print("  无补涨位候选（主力>0 + 涨幅<5% + 贴MA20 + 穿三线/长阳修复 + 放量）")
            for r in hits:
                tag = "穿三线" if r["cross3"] else "长阳修复"
                print(f"  ▶ {r['code']} {r['name']} 收{r['close']} 涨{r['chg']:+.1f}% 乖离MA20 {r['bias_ma20']:+.1f}% "
                      f"量比{r['vol_ratio']} 主力{fmt_main(r['main_wan'])} [{tag}] "
                      f"买{r['buy_ref']} 止损{r['stop']} 目标{r['target']}")
        return

    # ── 自动模式 ──
    print("拉全市场快照（约15-25秒）...")
    rows = snapshot_all()
    print(f"全市场有效 {len(rows)} 只")
    sectors = sector_detect(rows)
    if not sectors:
        print(f"❌ 无行业断层（主力合计≥{FLOW_SUM_MIN}亿 且 流入≥{FLOW_CNT_MIN}只 均不满足）——"
              f"今天没有板块级资金抱团，断层补涨空仓等待，不硬做")
        return
    print(f"\n🔍 行业断层 TOP{len(sectors)}（板块级资金抱团）:")
    for ind, sm, cnt, _ in sectors:
        print(f"  {ind:8s} 主力合计 {fmt_main(sm)}  流入 {cnt} 只")
    all_hits = []
    for ind, sm, cnt, stocks in sectors:
        print(f"\n{'='*70}\n📌 断层行业: {ind}（合计 {fmt_main(sm)}，流入 {cnt} 只）\n{'='*70}")
        hits = pick_pull_late(stocks, date)
        if not hits:
            print("  无补涨位候选（行业断层但内部无 涨幅<5%+贴MA20+结构确认 的票）")
        for r in hits:
            tag = "穿三线" if r["cross3"] else "长阳修复"
            line = (f"  ▶ {r['code']} {r['name']} 收{r['close']} 涨{r['chg']:+.1f}% 乖离MA20 {r['bias_ma20']:+.1f}% "
                    f"量比{r['vol_ratio']} 主力{fmt_main(r['main_wan'])} [{tag}] "
                    f"买{r['buy_ref']} 止损{r['stop']} 目标{r['target']}")
            print(line)
            r["sector"] = ind; all_hits.append(line)
    out = {"date": date, "mode": "auto", "sectors": [{"name": s[0], "main": s[1], "cnt": s[2]} for s in sectors],
           "count": len(all_hits)}
    with open(f"gap_result_{date}.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print(f"\n结果已存 gap_result_{date}.json")

if __name__ == "__main__":
    main()

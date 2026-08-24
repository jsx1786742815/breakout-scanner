# -*- coding: utf-8 -*-
"""低吸战法扫描器（缩量回踩）
扫描强势股（上涨趋势中）回调缩量到 5/10 日线附近、不破前低的标的，输出低吸挂单价 + 操作注意事项。
数据源：东方财富（快照 clist + 历史K线 push2his），强制直连（trust_env=False）。
用法：
    python pullback_scanner.py            # 扫最近交易日
    python pullback_scanner.py 20260814   # 扫指定交易日
"""
import json, sys, time, re, datetime, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

requests.Session.trust_env = False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# ── 低吸战法量化参数（可调）──
TREND_CHG_MIN  = 0.15      # 强势股门槛：近20日涨幅 ≥15%
PULLBACK_B5    = (-0.03, 0.02)  # 回踩位置：乖离MA5 在 -3% ~ +2%（贴近5/10日线）
VOL_RATIO_MAX  = 0.7       # 缩量：回调日量比 < 0.7（缩量=洗盘，放量=出货嫌疑）
MA_LOOSE       = 0.99      # 均线多头容忍：MA5≥MA10×0.99 且 MA10≥MA20×0.99

def last_trade_date():
    if len(sys.argv) > 1 and re.match(r"^\d{8}$", sys.argv[1]):
        return sys.argv[1]
    d = datetime.date.today()
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.strftime("%Y%m%d")

def em_clist(host, params):
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"})
    r = s.get(f"https://{host}/api/qt/clist/get", params=params, timeout=20)
    return (r.json().get("data") or {}).get("diff") or []

def snapshot():
    """全市场快照：候选=当日回调/小涨小跌（涨幅 -3%~+3%）+ 非ST，缩小范围后再精算"""
    rows = []
    for pn in range(1, 50):
        diff = em_clist("push2delay.eastmoney.com",
                        {"pn": pn, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3",
                         "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                         "fields": "f2,f3,f5,f8,f10,f12,f14,f62,f100"})
        if not diff:
            break
        for x in diff:
            nm = str(x.get("f14", "")); chg = x.get("f3")
            try:
                chg = float(chg)
            except (TypeError, ValueError):
                continue
            if not (-3.0 <= chg <= 3.0):
                continue
            if "ST" in nm.upper() or "退" in nm:
                continue
            rows.append({"code": str(x.get("f12")).zfill(6), "name": nm, "chg": chg,
                         "main_wan": (x.get("f62") or 0) / 1e4 if x.get("f62") is not None else 0,
                         "industry": x.get("f100") or ""})
        last_chg = diff[-1].get("f3")
        try:
            last_chg = float(last_chg)
        except (TypeError, ValueError):
            last_chg = None
        if last_chg is not None and last_chg < -3.0:
            break
        time.sleep(0.3)
    return rows

def em_kline(code, n=70):
    mkt = 1 if code.startswith("6") else 0
    try:
        r = requests.get("https://push2his.eastmoney.com/api/qt/stock/kline/get",
                         params={"secid": f"{mkt}.{code}", "fields1": "f1,f2,f3,f4,f5,f6",
                                 "fields2": "f51,f52,f53,f54,f55,f56,f57,f58", "klt": 101, "fqt": 1,
                                 "end": "20500101", "lmt": n}, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=12)
        kl = (r.json().get("data") or {}).get("klines") or []
        rows = []
        for line in kl:
            p = line.split(",")
            rows.append({"d": p[0], "o": float(p[1]), "c": float(p[2]), "h": float(p[3]),
                         "l": float(p[4]), "v": float(p[5])})
        return rows
    except Exception:
        return []

def check_pullback(cand, date):
    code, name = cand["code"], cand["name"]
    k = em_kline(code)
    kdate = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    if len(k) < 25 or k[-1]["d"] != kdate:
        return None
    i = len(k) - 1
    closes = [x["c"] for x in k]; highs = [x["h"] for x in k]; lows = [x["l"] for x in k]; vols = [x["v"] for x in k]
    ma5 = sum(closes[i-4:i+1]) / 5; ma10 = sum(closes[i-9:i+1]) / 10; ma20 = sum(closes[i-19:i+1]) / 20

    # ① 强势股：近20日涨幅 ≥15%
    if i < 20:
        return None
    chg20 = closes[i] / closes[i-20] - 1
    if chg20 < TREND_CHG_MIN:
        return None
    # ② 趋势仍在：均线接近多头（MA5≥MA10×0.99 且 MA10≥MA20×0.99）
    if not (ma5 >= ma10 * MA_LOOSE and ma10 >= ma20 * MA_LOOSE):
        return None
    # ③ 回踩位置：乖离MA5 在 -3% ~ +2%（贴近5/10日线，不是追高）
    b5 = closes[i] / ma5 - 1
    if not (PULLBACK_B5[0] <= b5 <= PULLBACK_B5[1]):
        return None
    # ④ 缩量：量比 < 0.7（缩量回调=洗盘）
    vr = vols[i] / vols[i-1] if i > 0 and vols[i-1] else 9
    if vr >= VOL_RATIO_MAX:
        return None
    # ⑤ 不破前低：近20日（除当日）最低价 < 当日最低（回调未破前低）
    prev_low = min(lows[max(0, i-20):i])
    if lows[i] < prev_low:
        return None

    # 操作参数
    prev_high = max(highs[max(0, i-60):i]) if i >= 1 else 0  # 反弹目标=前高
    buy_ref = round(ma5, 2)      # 挂单价参考=MA5
    buy_ref2 = round(ma10, 2)    # 更稳=MA10
    stop = round(ma20, 2)        # 止损=MA20
    mw = cand["main_wan"]
    if mw > 0:
        zj = "资金流入"
    elif mw > -1000 and vr < VOL_RATIO_MAX:
        zj = "洗盘观察"   # 小幅流出+缩量：可能是洗盘（见 pullback-rules 六·五），保留观察
    elif mw > -1000:
        zj = "中性"
    else:
        zj = "出货嫌疑"   # 大额流出(>1000万)：降级
    return {"code": code, "name": name, "chg": round(cand["chg"], 2), "close": closes[i],
            "b5": round(b5 * 100, 2), "vol_ratio": round(vr, 2), "chg20": round(chg20 * 100, 1),
            "ma5": round(ma5, 2), "ma10": round(ma10, 2), "ma20": round(ma20, 2),
            "buy_ref": buy_ref, "buy_ref2": buy_ref2, "stop": stop,
            "target": round(prev_high, 2), "main_wan": cand["main_wan"], "zj_tag": zj,
            "industry": cand["industry"]}

def market_gate():
    """大盘环境过滤（2026-08-24 4.5年回测落地）：上证收盘站上 MA20 才允许低吸。
    回测依据：弱市2023年低吸胜率38.7% vs 牛市2024-25年53-55%——弱市做低吸=慢性失血。
    返回 (通过?, 上证收盘, MA20, 日期)；数据源=腾讯 ifzq（不封IP）。"""
    try:
        r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                         params={"param": "sh000001,day,,,70,qfq"}, headers={"User-Agent": UA}, timeout=12)
        node = r.json()["data"]["sh000001"]
        rows = node.get("qfqday") or node.get("day") or []
        closes = [float(x[2]) for x in rows]
        ma20 = sum(closes[-20:]) / 20
        cur, date = closes[-1], rows[-1][0]
        return cur > ma20, cur, ma20, date
    except Exception:
        return None, None, None, None

def main():
    date = last_trade_date()
    gate, sh, ma20, gdate = market_gate()
    if gate is None:
        print("⚠️ 大盘数据取数失败，闸门状态未知，默认按通过处理（人工复核大盘）")
    elif gate:
        print(f"✅ 大盘闸门通过：上证 {sh:.2f} > MA20 {ma20:.2f}（{gdate}）——低吸可执行")
    else:
        print(f"🔴 大盘闸门关闭：上证 {sh:.2f} < MA20 {ma20:.2f}（{gdate}）——弱市低吸胜率仅38.7%(2023回测)，结果仅供观察，禁止买入")
    print(f"低吸战法扫描(缩量回踩) | 日期 {date} | 强势股近20日≥15% + 回踩MA5/10 + 缩量<0.7")
    cands = snapshot()
    total = len(cands)
    cands = [c for c in cands if c["main_wan"] >= -300]   # 资金预过滤提速：主力≥-300万才精算K线
    cands = [c for c in cands if not c["code"].startswith(("688", "300", "301"))]  # 用户权限：无科创/创业板
    print(f"初筛候选(当日-3%~+3%): {total} 只，资金/权限过滤后 {len(cands)} 只，精算低吸条件...")
    result = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(check_pullback, c, date): c for c in cands}
        for f in as_completed(futs):
            r = f.result()
            if r:
                result.append(r)
    result.sort(key=lambda x: -x["main_wan"])
    print(f"\n{'='*80}\n✅ 低吸标的 {len(result)} 只" + ("（🔴 大盘闸门关闭，仅供观察）" if (gate is not None and not gate) else "") + f"\n{'='*80}")
    for r in result:
        print(f"  {r['code']} {r['name']} 收{r['close']} 乖离MA5 {r['b5']}% 量比{r['vol_ratio']} 20日{r['chg20']}% "
              f"挂{r['buy_ref']}(MA5)/{r['buy_ref2']}(MA10) 止损{r['stop']}(MA20) 目标{r['target']} "
              f"[{r['zj_tag']}] 主力{r['main_wan']/1e4:+.2f}亿 {r['industry']}")
    out = {"date": date, "count": len(result), "items": result}
    with open(f"pullback_result_{date}.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print(f"\n结果已存 pullback_result_{date}.json")

if __name__ == "__main__":
    main()
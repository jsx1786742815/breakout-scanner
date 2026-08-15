# -*- coding: utf-8 -*-
"""突破战法扫描器（量价确认）
扫描"放量突破平台/箱体/前高"的股票，输出标的 + 操作注意事项。
数据源：多源容灾（东财主源 + 腾讯备胎，见 datasource.py）。
用法：python breakout_scanner.py [YYYYMMDD]   （缺省=最近交易日）
"""
import json, sys, re, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from datasource import get_snapshot, get_kline

# ── 战法量化参数（可调）──
VOL_RATIO_MIN = 1.5      # 量比下限（<1.3 无量突破90%假）
BOX_AMP_MAX   = 0.15     # 平台/箱体振幅上限
BREAK_LOOKBACK = 60      # 前高回看天数（颈线）
CHG_MAX       = 7.0      # 当日涨幅上限（涨停难追）
BREAK_PCT_MAX = 15.0     # 突破幅度上限
STOP_PCT      = 0.03     # 止损=颈线下方3%

def last_trade_date():
    if len(sys.argv) > 1 and re.match(r"^\d{8}$", sys.argv[1]):
        return sys.argv[1]
    d = datetime.date.today()
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.strftime("%Y%m%d")

def check_breakout(cand, date):
    code, name = cand["code"], cand["name"]
    k = get_kline(code)
    kdate = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    if len(k) < 25 or k[-1]["d"] != kdate:
        return None
    i = len(k) - 1
    closes = [x["c"] for x in k]; highs = [x["h"] for x in k]; lows = [x["l"] for x in k]; vols = [x["v"] for x in k]

    prev_high = max(highs[max(0, i-BREAK_LOOKBACK):i]) if i >= 1 else 0
    if prev_high <= 0 or closes[i] <= prev_high:
        return None
    vr = vols[i] / vols[i-1] if i > 0 and vols[i-1] else 0
    if vr < VOL_RATIO_MIN:
        return None
    box_high = max(highs[max(0, i-20):i]); box_low = min(lows[max(0, i-20):i])
    if box_low > 0 and (box_high - box_low) / box_low > BOX_AMP_MAX:
        return None
    chg = (closes[i] / closes[i-1] - 1) * 100 if i > 0 else 0
    if chg > CHG_MAX:
        return None
    break_pct = (closes[i] / prev_high - 1) * 100
    if break_pct > BREAK_PCT_MAX:
        return None

    box_height = box_high - box_low
    stop = round(prev_high * (1 - STOP_PCT), 2)
    target = round(prev_high + box_height, 2)
    return {"code": code, "name": name, "chg": round(chg, 2), "close": closes[i],
            "neckline": round(prev_high, 2), "break_pct": round(break_pct, 2),
            "vol_ratio": round(vr, 2), "box_height": round(box_height, 2),
            "stop": stop, "target": target, "main_wan": cand["main_wan"],
            "industry": cand["industry"], "cth": round(closes[i] / k[i]["h"] * 100, 1)}

def main():
    date = last_trade_date()
    print(f"突破战法扫描 | 日期 {date} | 量比≥{VOL_RATIO_MIN} 突破近{BREAK_LOOKBACK}日前高")
    cands = get_snapshot(1.0, 9.0)
    print(f"初筛候选(涨幅1-9%): {len(cands)} 只，精算突破条件...")
    result = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(check_breakout, c, date): c for c in cands}
        for f in as_completed(futs):
            r = f.result()
            if r:
                result.append(r)
    result.sort(key=lambda x: -x["main_wan"])
    print(f"\n{'='*80}\n✅ 放量突破标的 {len(result)} 只\n{'='*80}")
    for r in result:
        print(f"  {r['code']} {r['name']} 收{r['close']} 涨{r['chg']}% 突破{r['break_pct']}% 量比{r['vol_ratio']} "
              f"颈线{r['neckline']} 止损{r['stop']} 目标{r['target']} 主力{r['main_wan']/1e4:+.1f}亿 {r['industry']}")
    out = {"date": date, "count": len(result), "items": result}
    with open(f"breakout_result_{date}.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print(f"\n结果已存 breakout_result_{date}.json")

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""策略验证 v5：组合优化——找"能赚钱"的低吸配置
变体矩阵：
  G1: 无闸门（基准）
  G2: 上证>MA20
  G3: 上证>MA20 且 上证>MA60
  G4: 上证>MA20 且 红盘回踩(当日收涨)
  G5: 上证>MA20且>MA60 且 红盘回踩
止损模拟：持5日内任意收盘跌破 买入×(1-5%) → 当日按止损价卖出；否则持满5日
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

requests.Session.trust_env = False
UA = {'User-Agent': 'Mozilla/5.0'}

def fetch_kline(sym):
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    segs = []
    for start, end in [("2022-01-01", "2023-12-31"), ("2023-12-01", "2026-08-24")]:
        try:
            r = requests.get(url, params={"param": f"{sym},day,{start},{end},800,qfq"}, headers=UA, timeout=12)
            node = r.json()["data"][sym]
            rows = node.get("qfqday") or node.get("day") or []
            segs.extend([(str(x[0]), float(x[2])) for x in rows])
        except Exception:
            pass
    seen = {}
    for d, c in segs:
        seen[d] = c
    return [{"d": d, "c": c} for d, c in sorted(seen.items())]

def get_signal_dates(code):
    sym = ("sh" if code.startswith(("6", "5")) else "sz") + code
    try:
        k = fetch_kline(sym)
    except Exception:
        return None
    if len(k) < 120:
        return None
    closes = [x["c"] for x in k]
    dates = [x["d"] for x in k]
    sigs = []
    n = len(closes)
    for i in range(60, n - 5):
        ma5 = sum(closes[i-4:i+1]) / 5
        ma10 = sum(closes[i-9:i+1]) / 10
        ma20 = sum(closes[i-19:i+1]) / 20
        ma30 = sum(closes[i-29:i+1]) / 30
        if not (ma5 >= ma10 * 0.99 and ma10 >= ma20 * 0.99 and ma20 >= ma30 * 0.99):
            continue
        chg20 = closes[i] / closes[i-20] - 1
        if not (0.10 <= chg20 <= 0.60):
            continue
        b10 = closes[i] / ma10 - 1
        if not (0.0 <= b10 <= 0.03):
            continue
        if closes[i] / closes[i-1] - 1 > 0.05:
            continue
        sigs.append((i, closes[i], dates[i], closes[i]/closes[i-1]-1))  # 含当日涨幅
    return code, sigs, closes

def main():
    items = json.load(open("trend_v2_result_20260824.json", encoding="utf-8"))["items"]
    sh = fetch_kline("sh000001")
    sh_map = {x["d"]: x["c"] for x in sh}
    sh_dates = [x["d"] for x in sh]
    sh_ma20, sh_ma60 = {}, {}
    for j in range(19, len(sh)):
        d = sh_dates[j]
        sh_ma20[d] = sum(sh[j-19:j+1][k]["c"] for k in range(20)) / 20
    for j in range(59, len(sh)):
        sh_ma60[sh_dates[j]] = sum(sh[j-59:j+1][k]["c"] for k in range(60)) / 60

    data = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(get_signal_dates, it["code"]): it for it in items}
        for f in as_completed(futs):
            r = f.result()
            if r and r[1]:
                data.append(r)

    def gate(grp, date):
        if date not in sh_map:
            return False
        c = sh_map[date]
        if "g20" in grp and c <= sh_ma20.get(date, 9e9):
            return False
        if "g60" in grp and c <= sh_ma60.get(date, 9e9):
            return False
        return True

    def simulate(ret5_calc, stop=0.05):
        """持5日+止损模拟：返回(收益率, 是否止损)"""
        pass

    variants = {
        "G1 无闸门(基准)":     (set(), False),
        "G2 上证>MA20":        ({"g20"}, False),
        "G3 上证>MA20+MA60":   ({"g20", "g60"}, False),
        "G4 上证>MA20+红盘":   ({"g20"}, True),
        "G5 上证>MA20+MA60+红盘": ({"g20", "g60"}, True),
    }
    print("=== 低吸策略变体对比（持5日）===", flush=True)
    for name, (grp, red_only) in variants.items():
        stop = 0.05  # 止损线 -5%
        r5, r5sl = [], []
        for code, sigs, closes in data:
            for i, price, date, chg in sigs:
                if i + 5 >= len(closes) or not gate(grp, date):
                    continue
                if red_only and chg < 0:
                    continue
                # 无止损：持满5日
                r5.append(closes[i+5] / price - 1)
                # 带-5%止损模拟
                hit = None
                for t in range(1, 6):
                    if closes[i+t] / price - 1 <= -stop:
                        hit = closes[i+t] / price - 1
                        break
                r5sl.append(hit if hit is not None else closes[i+5] / price - 1)
        def show(arr, tag):
            if not arr:
                print(f"  {tag}: 无样本"); return
            win = sum(1 for x in arr if x > 0) / len(arr)
            avg = sum(arr) / len(arr)
            wins = [x for x in arr if x > 0]; losses = [x for x in arr if x <= 0]
            rr = (sum(wins)/len(wins))/abs(sum(losses)/len(losses)) if wins and losses else 0
            print(f"  {tag}: 信号{len(arr)} 胜率{win*100:.1f}% 平均{avg*100:+.2f}% 盈亏比{rr:.2f}:1 最差{min(arr)*100:.1f}%")
        print(f"◆ {name}")
        show(r5, "  持5日(无止损)")
        show(r5sl, "  持5日(-5%止损)")

if __name__ == "__main__":
    main()

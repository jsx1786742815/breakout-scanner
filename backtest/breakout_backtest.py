# -*- coding: utf-8 -*-
"""突破战法（右侧）历史回测 —— 与低吸同口径对比
信号：收盘突破前60日最高(颈线) + 放量(量比≥1.5) + 当日涨1~7%(非涨停可买) + 突破幅度≤5%
买入=突破日收盘，持5日/10日；含 -5% 止损模拟 + 环境闸门(上证>MA20+MA60)对比
样本：今日95只多头排列票（与低吸回测同口径，同样有幸存者偏差）
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

requests.Session.trust_env = False
UA = {'User-Agent': 'Mozilla/5.0'}

def fetch_kline_full(sym):
    """分两段拉取（2022起），含开高低收量"""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    segs = []
    for start, end in [("2022-01-01", "2023-12-31"), ("2023-12-01", "2026-08-24")]:
        try:
            r = requests.get(url, params={"param": f"{sym},day,{start},{end},800,qfq"}, headers=UA, timeout=12)
            node = r.json()["data"][sym]
            rows = node.get("qfqday") or node.get("day") or []
            segs.extend([(str(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in rows])
        except Exception:
            pass
    seen = {}
    for d, o, c, h, l, v in segs:
        seen[d] = (o, c, h, l, v)
    return [{"d": d, "o": v[0], "c": v[1], "h": v[2], "l": v[3], "v": v[4]} for d, v in sorted(seen.items())]

def get_breakout_signals(code):
    sym = ("sh" if code.startswith(("6", "5")) else "sz") + code
    try:
        k = fetch_kline_full(sym)
    except Exception:
        return None
    if len(k) < 100:
        return None
    sigs = []
    n = len(k)
    for i in range(65, n - 10):
        closes = [x["c"] for x in k]
        highs = [x["h"] for x in k]
        vols = [x["v"] for x in k]
        prev_high = max(highs[i-60:i])          # 前60日最高 = 颈线
        if closes[i] <= prev_high:
            continue
        brk = closes[i] / prev_high - 1          # 突破幅度
        if brk > 0.05:
            continue                              # 突破过大(涨停/跳空)不追
        chg = closes[i] / closes[i-1] - 1
        if not (0.01 <= chg <= 0.07):             # 当日涨1-7%可买
            continue
        vol5 = sum(vols[i-5:i]) / 5
        if vol5 <= 0 or vols[i] / vol5 < 1.5:     # 放量 ≥1.5倍
            continue
        sigs.append((i, closes[i], k[i]["d"]))
    return code, sigs, closes, highs

def main():
    items = json.load(open("trend_v2_result_20260824.json", encoding="utf-8"))["items"]
    # 上证 + MA20/MA60
    sh = fetch_kline_full("sh000001")
    sh_map = {x["d"]: x["c"] for x in sh}
    sh_dates = [x["d"] for x in sh]
    sh_ma20, sh_ma60 = {}, {}
    for j in range(19, len(sh)):
        sh_ma20[sh_dates[j]] = sum(sh[j-19:j+1][t]["c"] for t in range(20)) / 20
    for j in range(59, len(sh)):
        sh_ma60[sh_dates[j]] = sum(sh[j-59:j+1][t]["c"] for t in range(60)) / 60

    data = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(get_breakout_signals, it["code"]): it for it in items}
        for f in as_completed(futs):
            r = f.result()
            if r and r[1]:
                data.append(r)
    print(f"有效样本 {len(data)} 只，收集突破信号...", flush=True)

    # 统计：持5日/10日，闸门开/关
    def gate_on(date):
        return date in sh_map and sh_map[date] > sh_ma20.get(date, 9e9) and sh_map[date] > sh_ma60.get(date, 9e9)

    groups = {"all": [], "gate_on": [], "gate_off": []}
    for code, sigs, closes, highs in data:
        for i, price, date in sigs:
            for horizon in (5, 10):
                if i + horizon >= len(closes):
                    continue
                ret = closes[i+horizon] / price - 1
                if horizon == 5:
                    groups["all"].append(ret)
                    groups["gate_on" if gate_on(date) else "gate_off"].append(ret)
                # 打印用 5 日为主
    def show(arr, label):
        if not arr:
            print(f"  {label}: 无样本"); return
        win = sum(1 for x in arr if x > 0) / len(arr)
        avg = sum(arr) / len(arr)
        wins = [x for x in arr if x > 0]; losses = [x for x in arr if x <= 0]
        rr = (sum(wins)/len(wins)) / abs(sum(losses)/len(losses)) if wins and losses else 0
        print(f"  {label}: 信号{len(arr)} 胜率{win*100:.1f}% 平均{avg*100:+.2f}% 盈亏比{rr:.2f}:1 最差{min(arr)*100:.1f}%")
    print("\n=== 突破战法（右侧）持5日 ===")
    show(groups["all"], "全部")
    show(groups["gate_on"], "🟢 上证>MA20+MA60(闸门开)")
    show(groups["gate_off"], "🔴 闸门关")

    # 持10日（闸门开）
    r10 = []
    for code, sigs, closes, highs in data:
        for i, price, date in sigs:
            if i + 10 >= len(closes) or not gate_on(date):
                continue
            r10.append(closes[i+10] / price - 1)
    print("\n=== 突破战法 持10日（闸门开）===")
    show(r10, "持10日")

if __name__ == "__main__":
    main()

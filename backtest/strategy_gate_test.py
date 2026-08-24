# -*- coding: utf-8 -*-
"""策略验证 v4：环境开关（上证MA20闸门）对低吸胜率的影响
思路：低吸信号按"信号日上证收盘 vs MA20"分组，验证环境过滤能否把负期望变正期望
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

requests.Session.trust_env = False
UA = {'User-Agent': 'Mozilla/5.0'}

def fetch_kline(sym):
    """分两段拉取拼接（2022-01-01 起）"""
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

def get_signal_dates(code, name):
    """返回该股的历史低吸信号 (index, price, date)"""
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
        sigs.append((i, closes[i], dates[i]))
    return code, name, sigs, closes

def main():
    items = json.load(open("trend_v2_result_20260824.json", encoding="utf-8"))["items"]
    # 上证指数日K + MA20
    sh = fetch_kline("sh000001")
    sh_map = {x["d"]: x["c"] for x in sh}
    sh_dates = [x["d"] for x in sh]
    sh_ma20 = {}
    for j in range(19, len(sh)):
        d = sh[j]["c"]
        sh_ma20[sh_dates[j]] = sum(sh[j-19:j+1][k]["c"] for k in range(20)) / 20
    print(f"上证K线 {len(sh)} 根（{sh[0]['d']} ~ {sh[-1]['d']}），MA20 映射 {len(sh_ma20)} 天", flush=True)

    data = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(get_signal_dates, it["code"], it["name"]): it for it in items}
        for f in as_completed(futs):
            r = f.result()
            if r and r[2]:
                data.append(r)

    groups = {"gate_on": [], "gate_off": []}
    gate_on_count = 0
    for code, name, sigs, closes in data:
        for i, price, date in sigs:
            if i + 5 >= len(closes):
                continue
            if date not in sh_map or date not in sh_ma20:
                continue
            ret5 = closes[i+5] / price - 1
            if sh_map[date] > sh_ma20[date]:
                groups["gate_on"].append(ret5)
                gate_on_count += 1
            else:
                groups["gate_off"].append(ret5)

    print(f"\n=== 上证MA20环境闸门对低吸胜率的影响（持5日）===")
    for label, key in [("🟢 上证站上MA20（闸门开）", "gate_on"), ("🔴 上证跌破MA20（闸门关）", "gate_off")]:
        arr = groups[key]
        if not arr:
            print(f"{label}: 无样本"); continue
        win = sum(1 for x in arr if x > 0) / len(arr)
        avg = sum(arr) / len(arr)
        wins = [x for x in arr if x > 0]; losses = [x for x in arr if x <= 0]
        rr = (sum(wins)/len(wins)) / abs(sum(losses)/len(losses)) if wins and losses else 0
        print(f"{label}: 信号{len(arr)} 胜率{win*100:.1f}% 平均{avg*100:+.2f}% 盈亏比{rr:.2f}:1 最差{min(arr)*100:.1f}%")

    # 年度细分（闸门开时的年份分布）
    print("\n=== 闸门开（可做低吸）时，按年份 ===")
    by_year = {}
    for code, name, sigs, closes in data:
        for i, price, date in sigs:
            if i + 5 >= len(closes) or date not in sh_map or date not in sh_ma20:
                continue
            if sh_map[date] > sh_ma20[date]:
                by_year.setdefault(date[:4], []).append(closes[i+5]/price - 1)
    for yr in sorted(by_year):
        arr = by_year[yr]
        win = sum(1 for x in arr if x > 0) / len(arr)
        avg = sum(arr) / len(arr)
        print(f"  {yr}年: 信号{len(arr)} 胜率{win*100:.1f}% 平均{avg*100:+.2f}%")

if __name__ == "__main__":
    main()

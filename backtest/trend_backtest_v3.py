# -*- coding: utf-8 -*-
"""低吸/波段信号历史回测 v3 —— 4.5年窗口（2022起，含2024熊市+2025牛市）
腾讯 fqkline 单次上限~640根，分两段拉取拼接（2022-2023 / 2024-2026）
信号：MA5>MA10>MA20>MA30(0.99) + 20日涨10~60% + 乖离MA10 0~3% + 当日涨≤5%
统计：总体 + 按年份分组（含红盘回踩变体）
⚠️ 幸存者偏差：样本=今日仍多头排列的95只
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

requests.Session.trust_env = False
UA = {'User-Agent': 'Mozilla/5.0'}

def fetch_kline(sym):
    """分两段拉取拼接（2022-01-01 起），按日期去重"""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    segs = []
    for start, end in [("2022-01-01", "2023-12-31"), ("2023-12-01", "2026-08-24")]:
        try:
            r = requests.get(url, params={"param": f"{sym},day,{start},{end},800,qfq"},
                             headers=UA, timeout=12)
            node = r.json()["data"][sym]
            rows = node.get("qfqday") or node.get("day") or []
            segs.extend([(str(x[0]), float(x[2])) for x in rows])
        except Exception:
            pass
    seen = {}
    for d, c in segs:
        seen[d] = c
    return [{"d": d, "c": c} for d, c in sorted(seen.items())]

def backtest_one(code, name):
    sym = ("sh" if code.startswith(("6", "5")) else "sz") + code
    try:
        k = fetch_kline(sym)
    except Exception:
        return None
    if len(k) < 120:
        return None
    closes = [x["c"] for x in k]
    dates = [x["d"] for x in k]
    sigs = []  # (index, price, date)
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
        chg = closes[i] / closes[i-1] - 1
        if chg > 0.05:
            continue
        sigs.append((i, closes[i], dates[i]))
    return code, name, sigs, closes

def stat(arr, label):
    if not arr:
        print(f"  {label}: 无样本"); return
    win = sum(1 for x in arr if x > 0) / len(arr)
    avg = sum(arr) / len(arr)
    wins = [x for x in arr if x > 0]; losses = [x for x in arr if x <= 0]
    rr = (sum(wins)/len(wins)) / abs(sum(losses)/len(losses)) if wins and losses else 0
    print(f"  {label}: 信号{len(arr)} 胜率{win*100:.1f}% 平均{avg*100:+.2f}% 盈亏比{rr:.2f}:1 最差{min(arr)*100:.1f}%")

def main():
    items = json.load(open("trend_v2_result_20260824.json", encoding="utf-8"))["items"]
    print(f"[v3 4.5年回测] 样本 {len(items)} 只（2022起，含2024熊市+2025牛市）...", flush=True)
    data = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(backtest_one, it["code"], it["name"]): it for it in items}
        for f in as_completed(futs):
            r = f.result()
            if r and r[2]:
                data.append(r)
    total_sigs = sum(len(d[2]) for d in data)
    print(f"有效样本 {len(data)} 只，历史信号 {total_sigs} 个（覆盖 {min(d[2][0][2] for d in data)} ~ 2026-08）\n", flush=True)

    # 按年份分组：所有信号（红盘+绿盘）
    by_year = {}
    all_r5 = []
    for code, name, sigs, closes in data:
        for i, price, date in sigs:
            if i + 5 >= len(closes):
                continue
            ret5 = closes[i+5] / price - 1
            all_r5.append(ret5)
            yr = date[:4]
            by_year.setdefault(yr, []).append(ret5)
    print("=== 持5日 全信号（红+绿盘）按年份 ===")
    stat(all_r5, "2022-2026 总体")
    for yr in sorted(by_year):
        stat(by_year[yr], f"{yr}年")

    # 红盘回踩变体（当日收涨）
    by_year_r = {}
    all_r5r = []
    for code, name, sigs, closes in data:
        for i, price, date in sigs:
            if i + 5 >= len(closes) or i < 1:
                continue
            chg = closes[i] / closes[i-1] - 1
            if chg < 0:
                continue
            ret5 = closes[i+5] / price - 1
            all_r5r.append(ret5)
            by_year_r.setdefault(date[:4], []).append(ret5)
    print("\n=== 持5日 红盘回踩变体（当日收涨=资金承接）按年份 ===")
    stat(all_r5r, "2022-2026 总体")
    for yr in sorted(by_year_r):
        stat(by_year_r[yr], f"{yr}年")

if __name__ == "__main__":
    main()

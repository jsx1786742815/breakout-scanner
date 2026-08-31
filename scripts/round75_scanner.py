# -*- coding: utf-8 -*-
"""75A战法扫描器（圆弧底右侧刚抬头）
量化：低位圆弧底（左半缓跌+右半缓升+量能弧）+ 75A位置（距颈线空间≥10% + MA5≥MA10）。
数据源：datasource.py 多源容灾（东财主源 + 腾讯/新浪备胎），强制直连。
用法：
    python round75_scanner.py            # 扫最近交易日
    python round75_scanner.py 20260817   # 扫指定交易日
"""
import json, sys, re, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from datasource import get_snapshot, get_kline

# ── 75A战法量化参数（可调）──
WINDOW      = 50       # U形检测窗口（交易日）
MIN_DROP    = 0.15     # 左半回撤下限（错杀下限）
MAX_DROP    = 0.45     # 左半回撤上限（暴跌排除）
MIN_RISE    = 0.03     # 右半最低涨幅（已抬头）
MAX_RISE    = 0.30     # 右半最高涨幅（已走完排除）
SPACE_MIN   = 0.10     # 距颈线空间 ≥10%（75A 硬条件）
VOL_PREV    = 0.85     # 左半均量 ≤ 更早15日均量×0.85（缩量）
VOL_SCALE   = 1.15     # 右半均量 ≥ 左半均量×1.15（温和放量）
LIN_LEFT    = 0.25     # 左半线性残差占比上限（平滑）
LIN_RIGHT   = 0.15     # 右半线性残差占比上限（平滑）
CHG_MAX     = 7.0      # 当日涨幅上限（未爆拉）
STOP_PCT    = 0.97     # 止损 = 锅底×0.97

def last_trade_date():
    if len(sys.argv) > 1 and re.match(r"^\d{8}$", sys.argv[1]):
        return sys.argv[1]
    d = datetime.date.today()
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.strftime("%Y%m%d")

def lin_resid(idx_list, closes, offset):
    """收盘价对索引的线性拟合残差占比（越小越平滑）"""
    xs = [j - offset for j in idx_list]
    ys = [closes[j] for j in idx_list]
    n = len(xs)
    if n < 4:
        return 1.0
    mx = sum(xs) / n; my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 1.0
    ss_tot = sum((y - my) ** 2 for y in ys)
    if ss_tot == 0:
        return 0.0
    k = sxy / sxx
    ss_res = sum((y - (my + k * (x - mx))) ** 2 for x, y in zip(xs, ys))
    return ss_res / ss_tot

def check_75a(cand, date):
    code, name = cand["code"], cand["name"]
    k = get_kline(code, n=120)
    kdate = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    if len(k) < 80 or k[-1]["d"] != kdate:
        return None
    closes = [x["c"] for x in k]; highs = [x["h"] for x in k]
    lows = [x["l"] for x in k]; vols = [x["v"] for x in k]
    n = len(k); i = n - 1
    win_start = max(0, i - WINDOW + 1)
    seg = list(range(win_start, i + 1))
    idx_min = min(seg, key=lambda j: lows[j])
    pos = seg.index(idx_min)
    left = seg[:pos]; right = seg[pos + 1:]
    if len(left) < 8 or len(right) < 5:
        return None

    # ① 左半回撤 15%~45%（错杀，非暴跌/横盘）
    a_high = max(highs[j] for j in left)
    b_low = lows[idx_min]
    if a_high <= 0 or b_low <= 0:
        return None
    drop = (a_high - b_low) / a_high
    if not (MIN_DROP <= drop <= MAX_DROP):
        return None

    # ② 右半涨幅 3%~30%（已抬头但未走完）
    rise = (closes[i] - b_low) / b_low
    if not (MIN_RISE <= rise <= MAX_RISE):
        return None

    # ③ 圆弧平滑（线性残差占比）
    if lin_resid(left, closes, win_start) > LIN_LEFT:
        return None
    if lin_resid(right, closes, win_start) > LIN_RIGHT:
        return None

    # ④ 量能弧：左半缩量 + 右半温和放量
    v_left = sum(vols[j] for j in left) / len(left)
    v_right = sum(vols[j] for j in right) / len(right) if right else 0
    prev_start = max(0, win_start - 15)
    v_prev = sum(vols[j] for j in range(prev_start, win_start)) / max(1, win_start - prev_start)
    if v_left > v_prev * VOL_PREV:
        return None
    if v_right < v_left * VOL_SCALE:
        return None

    # ⑤ 75A：距颈线空间 ≥10%（颈线=窗口内左半+锅底段最高点）
    neck = max(highs[j] for j in seg[:pos + 1])
    if neck <= 0:
        return None
    space = (neck - closes[i]) / neck
    if space < SPACE_MIN:
        return None

    # ⑥ MA5 ≥ MA10（右侧转强）
    ma5 = sum(closes[i - 4:i + 1]) / 5
    ma10 = sum(closes[i - 9:i + 1]) / 10
    if ma5 < ma10:
        return None

    # ⑦ 当日涨幅过滤
    chg = (closes[i] / closes[i - 1] - 1) * 100
    if chg > CHG_MAX:
        return None

    stop = round(b_low * STOP_PCT, 2)
    return {"code": code, "name": name, "close": round(closes[i], 2), "chg": round(chg, 2),
            "bottom": round(b_low, 2), "neck": round(neck, 2), "space": round(space * 100, 1),
            "drop": round(drop * 100, 1), "rise": round(rise * 100, 1),
            "vr_lr": round(v_right / max(v_left, 1e-9), 2),
            "ma5": round(ma5, 2), "ma10": round(ma10, 2), "buy_ref": round(ma5, 2),
            "stop": stop, "target": round(neck, 2),
            "main_wan": cand["main_wan"], "industry": cand["industry"]}

def main():
    date = last_trade_date()
    print(f"75A战法扫描(圆弧底右侧刚抬头) | 日期 {date} | 距颈线≥{SPACE_MIN*100:.0f}% + MA5≥MA10")
    cands = get_snapshot(-3.0, 5.0)
    cands = [c for c in cands if not c["code"].startswith(("688", "300", "301"))]  # 用户权限：无科创/创业板
    print(f"初筛候选(当日-3%~+5%): {len(cands)} 只，精算圆弧底+75A条件...")
    result = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(check_75a, c, date): c for c in cands}
        for f in as_completed(futs):
            r = f.result()
            if r:
                result.append(r)
    result.sort(key=lambda x: -x["main_wan"])
    print(f"\n{'='*80}\n✅ 75A 标的 {len(result)} 只\n{'='*80}")
    for r in result:
        print(f"  {r['code']} {r['name']} 收{r['close']} 锅底{r['bottom']} 颈线{r['neck']} "
              f"距颈线{r['space']}% 左回撤{r['drop']}% 右涨{r['rise']}% 量比LR{r['vr_lr']} "
              f"挂{r['buy_ref']}(MA5) 止损{r['stop']} 目标{r['target']} "
              f"主力{r['main_wan']/1e4:+.1f}亿 {r['industry']}")
    out = {"date": date, "count": len(result), "items": result}
    with open(f"round75_result_{date}.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print(f"\n结果已存 round75_result_{date}.json")

if __name__ == "__main__":
    main()

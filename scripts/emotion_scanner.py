# -*- coding: utf-8 -*-
"""情绪周期 + 打板/接力 扫描器（龙头战法）
拉涨停池/炸板池 → 判断市场情绪周期（冰点→修复→发酵→高潮→退潮）→ 输出打板候选（最高标/龙头/首板二板）+ 操作纪律。
数据源：东财 push2ex 涨停池/炸板池。
用法：python emotion_scanner.py [YYYYMMDD]   （缺省=最近交易日）
"""
import json, sys, re, datetime, requests
from collections import Counter

requests.Session.trust_env = False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
UT = "7eea3edcaed734bea9cbfc24409ed989"

def last_trade_date():
    if len(sys.argv) > 1 and re.match(r"^\d{8}$", sys.argv[1]):
        return sys.argv[1]
    d = datetime.date.today()
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.strftime("%Y%m%d")

def _pool(kind, date):
    url = f"https://push2ex.eastmoney.com/getTopic{kind}Pool"
    try:
        r = requests.get(url, params={"ut": UT, "dpt": "wz.ztzt", "Pageindex": 0, "pagesize": 10000,
                                      "sort": "fbt:asc", "date": date},
                         headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15)
        data = r.json().get("data") or {}
        return data.get("pool") or []
    except Exception:
        return []

def judge_phase(zt_count, zb_count, max_lbc, lbc_dist):
    """情绪周期判断（量化阈值，可调）"""
    zbr = zb_count / (zt_count + zb_count) * 100 if (zt_count + zb_count) else 0
    # 连板高度梯队
    if zt_count < 30 and max_lbc <= 2:
        phase = "冰点"
    elif zt_count > 100 and zbr < 20:
        phase = "高潮"
    elif max_lbc >= 4 and zt_count >= 60:
        phase = "发酵"
    elif zt_count >= 30 and zt_count < 60:
        phase = "修复"
    else:
        phase = "修复"  # 默认偏谨慎
    return phase, zbr

def main():
    date = last_trade_date()
    print(f"情绪周期 + 打板扫描 | 日期 {date}")
    zt = _pool("ZT", date)
    zb = _pool("ZB", date)
    zt_count, zb_count = len(zt), len(zb)
    if zt_count == 0 and zb_count == 0:
        print("涨停池/炸板池数据为空（可能非交易日或接口异常）")
        return

    lbc_dist = Counter(x.get("lbc", 1) for x in zt)
    max_lbc = max(lbc_dist.keys()) if lbc_dist else 0
    phase, zbr = judge_phase(zt_count, zb_count, max_lbc, lbc_dist)

    # 行业分布
    ind = Counter(x.get("hybk", "?") for x in zt)

    print(f"\n{'='*70}")
    print(f"【情绪周期诊断】")
    print(f"{'='*70}")
    print(f"  涨停 {zt_count} 家 | 炸板 {zb_count} 家 | 炸板率 {zbr:.1f}%")
    print(f"  连板梯队: {dict(sorted(lbc_dist.items()))}")
    print(f"  最高标: {max_lbc} 连板")
    print(f"  涨停行业分布: {dict(ind.most_common(8))}")
    print(f"  >>> 情绪周期判定: 【{phase}】")

    # 操作建议
    advice = {
        "冰点": "情绪极弱，空仓等待，不抄底不接力",
        "修复": "可轻仓试错首板/一进二，题材要有想象力",
        "发酵": "主线明确，可做主线龙头首板/二板/空间板",
        "高潮": "高潮日不追高（≥3板成群/集体涨停），只减仓兑现，防退潮",
        "退潮": "空仓！高位股炸板/天地板风险最大，这是短线生死线",
    }
    print(f"  操作建议: {advice.get(phase, '谨慎')}")

    # 打板候选
    print(f"\n{'='*70}")
    print(f"【打板候选】（只做最高标/龙头，封单大、换手健康）")
    print(f"{'='*70}")
    # 最高标/空间板
    top_lbc = sorted(zt, key=lambda x: (-x.get("lbc", 0), -(x.get("fund") or 0)))
    print(f"\n  ▶ 最高标/空间板（连板高度）:")
    for x in top_lbc[:3]:
        fund_yi = (x.get("fund") or 0) / 1e8
        print(f"    {x['c']} {x['n']} {x.get('lbc',0)}连板 涨{x.get('zdp',0):.1f}% 封单{fund_yi:.2f}亿 换手{x.get('hs',0):.1f}% {x.get('hybk','')}")
    # 首板（封单大 + 换手健康）
    shouban = [x for x in zt if x.get("lbc", 0) == 1]
    shouban.sort(key=lambda x: -(x.get("fund") or 0))
    print(f"\n  ▶ 首板（封单量大、换手健康 3-15%）:")
    for x in shouban[:8]:
        fund_yi = (x.get("fund") or 0) / 1e8
        hs = x.get("hs", 0)
        tag = "✓" if 3 <= hs <= 15 else ("换手异常" if hs > 20 else "换手偏低")
        print(f"    {x['c']} {x['n']} 首板 涨{x.get('zdp',0):.1f}% 封单{fund_yi:.2f}亿 换手{hs:.1f}% {tag} {x.get('hybk','')}")
    # 二板
    erban = [x for x in zt if x.get("lbc", 0) == 2]
    print(f"\n  ▶ 二板（题材确认）:")
    for x in erban[:5]:
        fund_yi = (x.get("fund") or 0) / 1e8
        print(f"    {x['c']} {x['n']} 2连板 封单{fund_yi:.2f}亿 换手{x.get('hs',0):.1f}% {x.get('hybk','')}")

    # 打板纪律
    print(f"\n{'='*70}")
    print(f"【打板/接力纪律】")
    print(f"{'='*70}")
    print(f"  买点: 首板(确定性低溢价高)/二板(确认题材)/龙头首次分歧转一致")
    print(f"  卖点: 次日竞价弱转强持有、高开不封板就走、破位/炸板立即止损")
    print(f"  铁律: 退潮期空仓；不接力 ≥3 连板高位；20cm/ST 生态已变，老数板玩法衰减")

    out = {"date": date, "phase": phase, "zt_count": zt_count, "zb_count": zb_count,
           "zbr": round(zbr, 1), "max_lbc": max_lbc, "lbc_dist": dict(lbc_dist),
           "industry": dict(ind.most_common(10)), "top": [x["n"] for x in top_lbc[:3]]}
    with open(f"emotion_result_{date}.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print(f"\n结果已存 emotion_result_{date}.json")

if __name__ == "__main__":
    main()

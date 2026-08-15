# -*- coding: utf-8 -*-
"""多数据源容灾模块（5 源自动降级）
供各战法扫描脚本 import，统一返回格式，主源失败自动切备胎，全部强制直连（trust_env=False 防代理污染）。

K线（按实测可用性排序）：
  1. 东财 push2his（主，字段全）
  2. 腾讯 fqkline（备）
  3. 新浪 getKLineData（备）
  4. 百度股市通（备，接口可能已失效，失败静默跳过）
  5. mootdx/通达信（备，本机当前连服务器取数返回空，排最后；恢复后自动生效）
全市场快照：
  1. 东财 clist（主，push2delay→push2 双域名，含主力资金/量比/行业）
  2. 新浪/akshare stock_zh_a_spot（备，缺主力资金/行业字段，置空）
"""
import requests, time

requests.Session.trust_env = False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def _req(url, params=None, referer="https://quote.eastmoney.com/", timeout=12):
    try:
        return requests.get(url, params=params,
                            headers={"User-Agent": UA, "Referer": referer}, timeout=timeout)
    except Exception:
        return None

# ═══════════════ K线：5 源降级 ═══════════════

def _em_kline(code, n=70):
    mkt = 1 if code.startswith("6") else 0
    r = _req("https://push2his.eastmoney.com/api/qt/stock/kline/get",
             params={"secid": f"{mkt}.{code}", "fields1": "f1,f2,f3,f4,f5,f6",
                     "fields2": "f51,f52,f53,f54,f55,f56,f57,f58", "klt": 101, "fqt": 1,
                     "end": "20500101", "lmt": n})
    if r is None:
        return []
    kl = (r.json().get("data") or {}).get("klines") or []
    rows = []
    for line in kl:
        p = line.split(",")
        try:
            rows.append({"d": p[0], "o": float(p[1]), "c": float(p[2]), "h": float(p[3]),
                         "l": float(p[4]), "v": float(p[5])})
        except (ValueError, IndexError):
            continue
    return rows

def _tx_kline(code, n=70):
    pre = "sh" if code.startswith(("6", "9", "5")) else "sz"
    r = _req(f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pre}{code},day,,,{n},qfq",
             referer="https://gu.qq.com/")
    if r is None:
        return []
    try:
        node = r.json()["data"][f"{pre}{code}"]
        raw = node.get("qfqday") or node.get("day") or []
    except Exception:
        return []
    rows = []
    for x in raw:
        try:
            rows.append({"d": x[0], "o": float(x[1]), "c": float(x[2]), "h": float(x[3]),
                         "l": float(x[4]), "v": float(x[5])})
        except (ValueError, IndexError, TypeError):
            continue
    return rows

def _sina_kline(code, n=70):
    pre = "sh" if code.startswith("6") else "sz"
    r = _req("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
             params={"symbol": f"{pre}{code}", "scale": 240, "ma": "no", "datalen": n},
             referer="https://finance.sina.com.cn/")
    if r is None:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    rows = []
    for x in data:
        try:
            rows.append({"d": x["day"], "o": float(x["open"]), "c": float(x["close"]),
                         "h": float(x["high"]), "l": float(x["low"]), "v": float(x["volume"]) / 100})
        except (KeyError, ValueError, TypeError):
            continue
    return rows

def _baidu_kline(code, n=70):
    # 百度股市通 K线接口（历史接口可能已失效，失败静默降级）
    try:
        r = _req("https://gushitong.baidu.com/opendata",
                 params={"openapi": 1, "dspName": "iphone", "tn": "tangram", "client": "app",
                         "query": "Kline", "code": code, "ktype": "day", "count": n},
                 referer="https://gushitong.baidu.com/", timeout=8)
        if r is None:
            return []
        data = r.json().get("Result", []) or []
        rows = []
        for x in data:
            try:
                rows.append({"d": x.get("date", ""), "o": float(x.get("open", 0)),
                             "c": float(x.get("close", 0)), "h": float(x.get("high", 0)),
                             "l": float(x.get("low", 0)), "v": float(x.get("volume", 0))})
            except (ValueError, TypeError):
                continue
        return rows
    except Exception:
        return []

def _mootdx_kline(code, n=70):
    # mootdx/通达信：本机当前连服务器取数返回空，恢复后自动生效
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std", timeout=6)
        df = client.bars(symbol=code, frequency=9, offset=n, adjust="qfq")
        if df is None or len(df) == 0:
            return []
        rows = []
        for idx, row in df.iterrows():
            try:
                d = str(idx)[:10]
                rows.append({"d": d, "o": float(row["open"]), "c": float(row["close"]),
                             "h": float(row["high"]), "l": float(row["low"]),
                             "v": float(row.get("vol", row.get("volume", 0)))})
            except Exception:
                continue
        return rows
    except Exception:
        return []

def get_kline(code, n=70):
    """取日K（5 源降级），返回 [{d,o,c,h,l,v}] 或 []"""
    for fn in (_em_kline, _tx_kline, _sina_kline, _baidu_kline, _mootdx_kline):
        try:
            k = fn(code, n)
            if k and k[-1].get("d"):
                return k
        except Exception:
            continue
    return []

# ═══════════════ 全市场快照：2 源降级 ═══════════════

def _em_snapshot(host, min_chg, max_chg):
    rows = []
    for pn in range(1, 50):
        r = _req(f"https://{host}/api/qt/clist/get",
                 params={"pn": pn, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3",
                         "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                         "fields": "f2,f3,f5,f8,f10,f12,f14,f62,f100"})
        if r is None:
            return []
        diff = (r.json().get("data") or {}).get("diff") or []
        if not diff:
            break
        for x in diff:
            nm = str(x.get("f14", ""))
            try:
                chg = float(x.get("f3"))
            except (TypeError, ValueError):
                continue
            if not (min_chg <= chg <= max_chg):
                continue
            if "ST" in nm.upper() or "退" in nm:
                continue
            try:
                vr = float(x.get("f10"))
            except (TypeError, ValueError):
                vr = None
            rows.append({"code": str(x.get("f12")).zfill(6), "name": nm, "chg": chg,
                         "vol_ratio": vr,
                         "main_wan": (x.get("f62") or 0) / 1e4 if x.get("f62") is not None else 0,
                         "industry": x.get("f100") or ""})
        try:
            last_chg = float(diff[-1].get("f3"))
        except (TypeError, ValueError):
            last_chg = None
        if last_chg is not None and last_chg < min_chg:
            break
        time.sleep(0.3)
    return rows

def _sina_snapshot(min_chg, max_chg):
    # 新浪/akshare 全市场（缺主力资金/行业字段，置空）
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot()
        if df is None or len(df) == 0:
            return []
        rows = []
        for _, x in df.iterrows():
            code = str(x.get("代码", "")).zfill(6)
            nm = str(x.get("名称", ""))
            if not code or "ST" in nm.upper() or "退" in nm:
                continue
            try:
                chg = float(x.get("涨跌幅", 0))
            except (TypeError, ValueError):
                continue
            if not (min_chg <= chg <= max_chg):
                continue
            try:
                vr = float(x.get("量比", 0))
            except (TypeError, ValueError):
                vr = None
            rows.append({"code": code, "name": nm, "chg": chg, "vol_ratio": vr,
                         "main_wan": 0.0, "industry": ""})
        return rows
    except Exception:
        return []

def get_snapshot(min_chg, max_chg):
    """全市场快照候选（2 源降级），返回 [{code,name,chg,vol_ratio,main_wan,industry}]"""
    for host in ("push2delay.eastmoney.com", "push2.eastmoney.com"):
        try:
            rows = _em_snapshot(host, min_chg, max_chg)
            if rows:
                return rows
        except Exception:
            continue
    return _sina_snapshot(min_chg, max_chg)

# ═══════════════ 个股资金流（东财主）═══════════════

def get_fund_flow(code, lmt=5):
    mkt = 1 if code.startswith("6") else 0
    r = _req("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
             params={"secid": f"{mkt}.{code}", "fields1": "f1,f2,f3,f7",
                     "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                     "lmt": str(lmt)})
    if r is None:
        return []
    kl = (r.json().get("data") or {}).get("klines") or []
    out = []
    for line in kl:
        p = line.split(",")
        try:
            out.append({"d": p[0], "main_wan": float(p[1] or 0) / 1e4})
        except (ValueError, IndexError):
            continue
    return out

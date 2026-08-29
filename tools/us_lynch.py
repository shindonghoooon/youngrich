#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
미국 종목 린치 분류용 데이터 일괄 수집 — SEC XBRL companyfacts

수집: 매출/영업이익/순이익 시계열, ROE, 발생액, 재고·매출채권 방향, 부채
목적: 린치 6분류 판정 + 분류별 검증 항목
"""
import json, urllib.request, re, time, sys
from datetime import date

UA = {"User-Agent": "DHResearch dh@research.kr"}
CIK = {}


def load_cik():
    global CIK
    r = urllib.request.Request("https://www.sec.gov/files/company_tickers.json", headers=UA)
    d = json.load(urllib.request.urlopen(r, timeout=30))
    CIK = {v["ticker"]: f"{v['cik_str']:010d}" for v in d.values()}


def facts(tk):
    if tk not in CIK: return None
    u = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK[tk]}.json"
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40))
    except Exception:
        return None


def annual(g, tags, flow=True):
    """연간(10-K, FY) 값. tags는 우선순위 순 후보 목록."""
    for tag in tags:
        if tag not in g: continue
        out = {}
        for u in g[tag]["units"].get("USD", []):
            if u.get("form") != "10-K" or u.get("fp") != "FY" or not u.get("fy"): continue
            if flow and "start" in u:
                s, e = date.fromisoformat(u["start"]), date.fromisoformat(u["end"])
                if (e - s).days < 350: continue
            out[u["fy"]] = u["val"]
        if len(out) >= 3: return out
    return {}


REV = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
       "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]
OP  = ["OperatingIncomeLoss"]
NI  = ["NetIncomeLoss", "ProfitLoss"]
OCF = ["NetCashProvidedByUsedInOperatingActivities",
       "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]


def cagr(d, n):
    ys = sorted(d)
    if len(ys) < n + 1: return None
    a, b = d[ys[-1 - n]], d[ys[-1]]
    if a <= 0 or b <= 0: return None
    return ((b / a) ** (1 / n) - 1) * 100


def classify(g3, g1, hist, roe):
    """린치 6분류 1차. 사이클 판별을 우선한다."""
    gr = [x for x in hist if x is not None]
    cyc = len(gr) >= 4 and min(gr) < -15 and max(gr) > 25
    g = g1 if g1 is not None else g3
    if g is None: return "판정불가", cyc
    if cyc:      return "경기순환주 의심", cyc
    if g >= 50:  return "고성장(과열)", cyc
    if g >= 20:  return "고성장", cyc
    if g >= 10:  return "대형우량", cyc
    if g >= 2:   return "저성장", cyc
    return "역성장/회생?", cyc


def run(tk):
    f = facts(tk)
    if not f: return None
    g = f["facts"].get("us-gaap", {})
    rev, op, ni = annual(g, REV), annual(g, OP), annual(g, NI)
    ocf = annual(g, OCF)
    ast = annual(g, ["Assets"], flow=False)
    eq  = annual(g, ["StockholdersEquity"], flow=False)
    inv = annual(g, ["InventoryNet"], flow=False)
    ar  = annual(g, ["AccountsReceivableNetCurrent"], flow=False)
    lia = annual(g, ["Liabilities"], flow=False)
    if len(rev) < 3: return None

    ys = sorted(rev)
    hist = [((rev[ys[i]] / rev[ys[i-1]] - 1) * 100) if rev[ys[i-1]] > 0 else None
            for i in range(1, len(ys))][-6:]
    y = ys[-1]
    o = {"tk": tk, "fy": y, "rev": rev[y],
         "g1": hist[-1] if hist else None, "g3": cagr(rev, 3), "g5": cagr(rev, 5),
         "opm": (op[y] / rev[y] * 100) if op.get(y) else None,
         "roe": (ni[y] / eq[y] * 100) if (ni.get(y) and eq.get(y)) else None,
         "de": ((lia[y] - eq[y]) / eq[y]) if (lia.get(y) and eq.get(y) and eq[y] > 0) else None,
         "acc": ((ni[y] - ocf[y]) / ast[y] * 100) if (ni.get(y) and ocf.get(y) and ast.get(y)) else None}
    # 린치 킬: 재고·매출채권이 매출보다 빠르게 증가
    if len(ys) >= 2:
        p = ys[-2]
        gr = (rev[y] / rev[p] - 1) * 100 if rev[p] > 0 else None
        for k, src in (("inv", inv), ("ar", ar)):
            if src.get(y) and src.get(p) and src[p] > 0 and gr is not None:
                o[k + "_g"] = (src[y] / src[p] - 1) * 100
                o[k + "_flag"] = o[k + "_g"] > gr + 10
    o["cls"], o["cyc"] = classify(o["g3"], o["g1"], hist, o["roe"])
    return o


if __name__ == "__main__":
    load_cik()
    tks = sys.argv[1:] or ["STRL", "PWR", "TTMI", "ORCL", "FORM", "UUUU",
                           "LPTH", "EROC", "ONDS", "XE", "USAR", "ASPI", "OPTT"]
    rows = []
    print(f"{'종목':<7}{'FY':<6}{'매출성장':>9}{'3년CAGR':>9}{'OPM':>8}{'ROE':>8}"
          f"{'부채/자본':>9}{'발생액':>8}  린치 1차분류")
    print("-" * 88)
    for tk in tks:
        r = run(tk)
        if not r:
            print(f"{tk:<7}조회실패 또는 데이터 부족"); continue
        rows.append(r)
        p = lambda v, s="%": f"{v:>7.1f}{s}" if v is not None else "      - "
        flag = ""
        if r.get("inv_flag"): flag += " ★재고급증"
        if r.get("ar_flag"): flag += " ★채권급증"
        print(f"{r['tk']:<7}{r['fy']:<6}{p(r['g1'])}{p(r['g3'])}{p(r['opm'])}{p(r['roe'])}"
              f"{(f'{r[chr(100)+chr(101)]:>8.2f}' if r.get('de') is not None else '       -')}"
              f"{p(r['acc'])}  {r['cls']}{flag}")
        time.sleep(0.3)
    json.dump(rows, open("us_lynch.json", "w"), indent=1)
    print(f"\n{len(rows)}/{len(tks)} → us_lynch.json")

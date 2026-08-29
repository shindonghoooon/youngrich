# -*- coding: utf-8 -*-
import json, urllib.request, time
from datetime import date
UA = {"User-Agent": "DHResearch dh@research.kr"}
_m = json.load(urllib.request.urlopen(urllib.request.Request(
    "https://www.sec.gov/files/company_tickers.json", headers=UA), timeout=30))
M = {v["ticker"]: f"{v['cik_str']:010d}" for v in _m.values()}

def eps_series(tk):
    f = json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{M[tk]}.json", headers=UA), timeout=40))
    g = f["facts"]["us-gaap"]
    for tag in ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"]:
        if tag not in g: continue
        o = {}
        for u in g[tag]["units"].get("USD/shares", []):
            if u.get("form") != "10-K" or u.get("fp") != "FY" or not u.get("fy"): continue
            if "start" in u:
                s, e = date.fromisoformat(u["start"]), date.fromisoformat(u["end"])
                if (e - s).days < 350: continue
            o[u["fy"]] = u["val"]
        if len(o) >= 4: return o
    return {}

c = {x['tk']: x for x in json.load(open('consensus.json'))}
PX = {"STRL": 470.52, "TTMI": 118.65, "PWR": 602.70, "FORM": 101.69, "ORCL": 150.85}
print(f"{'종목':<7}{'EPS 4년':<30}{'3Y CAGR':>9}{'단년':>9}{'PEG 3Y':>9}{'PEG 1Y':>9}  판정")
print("-" * 86)
for tk, px in PX.items():
    e = eps_series(tk); k = c.get(tk, {})
    ys = sorted(e)[-4:]
    if len(ys) < 4:
        print(f"{tk:<7}EPS 이력 부족"); continue
    a, b = e[ys[0]], e[ys[-1]]
    cagr = ((b / a) ** (1/3) - 1) * 100 if (a > 0 and b > 0) else None
    g1 = k.get("g_eps")
    epf = k.get("eps_cy")
    per = px / epf if (epf and epf > 0) else None
    p3 = per / cagr if (per and cagr and cagr > 0) else None
    p1 = per / g1 if (per and g1 and g1 > 0) else None
    j = lambda p: "통과" if (p and p < 1) else ("킬" if (p and p > 2) else ("경계" if p else "-"))
    hist = " → ".join(f"{e[y]:.2f}" for y in ys)
    f = lambda x, s="": f"{x:>8.1f}{s}" if x is not None else "        -"
    print(f"{tk:<7}{hist:<30}{f(cagr,'%')}{f(g1,'%')}"
          f"{(f'{p3:>9.2f}' if p3 else '        -')}{(f'{p1:>9.2f}' if p1 else '        -')}"
          f"  {j(p3)} (단년 {j(p1)})")
    time.sleep(0.3)

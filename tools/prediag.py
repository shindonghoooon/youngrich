#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사전진단 v1.6 — 판정 프레임워크 진입 전 필수 실행 레이어

이번 세션에서 드러난 4개 결함을 자동으로 막는다:
  D1 트리거 레벨 노후화 (대한조선 무효화선 57,300 = 5개월 전 52주 저점)
  D2 데이터 신선도 미검증 (우진 meta 07/19 고착 → -37% 오차)
  D3 섹터/종목특이 미분해 (조선 섹터 전체가 맞았는데 종목 악재로 오독할 뻔)
  D4 환율 노출 누락 (대한조선 최대 드라이버였는데 체크리스트에 없었음)
"""
import json, urllib.request, datetime, statistics, sys

UA = {"User-Agent": "Mozilla/5.0"}
Y = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range={}&interval={}"

# 섹터 피어 맵 (D3용) — 커버리지 종목 기준
PEERS = {
    "439260.KS": ("한국 조선", ["329180.KS","009540.KS","010140.KS","042660.KS","097230.KS"]),
    "STRL":      ("미국 E&C / 데이터센터 인프라", ["PWR","EME","MYRG","DY","FIX"]),
    "TTMI":      ("PCB / 전자부품", ["BHE","SANM","PLXS","CTS"]),
    "ORCL":      ("하이퍼스케일러", ["MSFT","GOOGL","AMZN","IBM"]),
    "047050.KS": ("종합상사/에너지", ["001120.KS","011760.KS","001740.KS","010060.KS","267250.KS"]),
    "047050.KS": ("종합상사", ["001120.KS","011760.KS","001250.KS","009240.KS"]),
    "019210.KQ": ("절삭공구/공작기계", ["014900.KS","056080.KQ","booked","104480.KQ","007460.KS"]),
}
# 수출 비중 높은 종목 = 환율 민감 (D4용)
FX_SENSITIVE = {"047050.KS","019210.KQ","439260.KS","329180.KS","009540.KS","010140.KS","042660.KS",
                "000660.KS","010120.KS","126340.KQ","098460.KQ"}


def fetch(sym, rng="1y", iv="1d"):
    r = urllib.request.Request(Y.format(sym, rng, iv), headers=UA)
    return json.load(urllib.request.urlopen(r, timeout=20))["chart"]["result"][0]


def series(d):
    q = d["indicators"]["quote"][0]
    ts, c, lo, hi = d["timestamp"], q["close"], q["low"], q["high"]
    out = [(ts[i], c[i], lo[i], hi[i]) for i in range(len(ts)) if c[i] is not None]
    return out


# ---------- D2: 신선도 검증 ----------
def freshness(d, ser):
    """meta 가격과 시계열 최종가가 어긋나면 시계열을 신뢰한다 (우진 버그)."""
    m = d["meta"]
    meta_p, meta_t = m["regularMarketPrice"], m["regularMarketTime"]
    last_t, last_p = ser[-1][0], ser[-1][1]
    age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(meta_t)).days
    gap = abs(meta_p / last_p - 1) * 100
    if age > 5 or gap > 5:
        return last_p, f"⚠ meta 이상 (meta {meta_p:,.2f}/{age}일 경과, 시계열 {last_p:,.2f}, 괴리 {gap:.1f}%) → 시계열 채택"
    return meta_p, f"정상 (meta·시계열 괴리 {gap:.2f}%)"


# ---------- 기술 지표 ----------
def tech(ser, cur):
    c = [x[1] for x in ser]
    lo = [x[2] for x in ser]
    hi = [x[3] for x in ser]
    out = {"cur": cur}
    for n in (20, 60, 120, 200):
        out[f"ma{n}"] = sum(c[-n:]) / n if len(c) >= n else None
    g = l = 0
    for i in range(-14, 0):
        ch = c[i] - c[i-1]
        g += max(ch, 0); l += max(-ch, 0)
    out["rsi"] = 100 - 100/(1 + (g/14)/(l/14)) if l else 100
    rets = [c[i]/c[i-1]-1 for i in range(-20, 0)]
    out["vol"] = statistics.pstdev(rets) * 100
    out["lo52"], out["hi52"] = min(lo[-252:]), max(hi[-252:])
    out["bars"] = len(c)
    out["lo3m"] = min(lo[-60:]); out["hi3m"] = max(hi[-60:])
    return out


# ---------- D1: 트리거 레벨 자동 도출 ----------
def triggers(t):
    """하드코딩 폐기. 매 실행 시 실제 데이터에서 재도출한다."""
    cur = t["cur"]
    lvls = [("52주 저점", t["lo52"]), ("3개월 저점", t["lo3m"]),
            ("MA200", t["ma200"]), ("MA60", t["ma60"]), ("MA20", t["ma20"])]
    below = sorted([(n, v) for n, v in lvls if v and v < cur], key=lambda x: -x[1])
    above = sorted([(n, v) for n, v in lvls if v and v >= cur], key=lambda x: x[1])
    inval = t["lo52"] if t["lo3m"] <= t["lo52"] * 1.02 else t["lo3m"]
    return {
        "지지": below[:3],
        "저항": above[:3],
        "무효화선": inval,
        "무효화까지": (inval/cur - 1) * 100,
        "진입존": (inval * 1.00, inval * 1.09),
    }


# ---------- D3: 섹터 / 종목특이 분해 ----------
def sector_split(sym, cur, ser):
    if sym not in PEERS:
        return None
    name, peers = PEERS[sym]
    c = [x[1] for x in ser]
    def ret(cl, days):
        return (cl[-1]/cl[-1-days] - 1) * 100 if len(cl) > days else None
    W = (21, 63, 126, 252)
    self_r = {d: ret(c, d) for d in W}
    prs = {}
    for p in peers:
        try:
            pc = [x[1] for x in series(fetch(p, "2y"))]
            prs[p] = {d: ret(pc, d) for d in W}
        except Exception:
            pass
    med = {d: statistics.median([v[d] for v in prs.values() if v[d] is not None])
           for d in W if any(v[d] is not None for v in prs.values())}
    return {"sector": name, "self": self_r, "peer_median": med, "n": len(prs),
            "alpha": {d: self_r[d] - med[d] for d in med if self_r.get(d) is not None}}


# ---------- D4: 환율 노출 ----------
def fx_check(sym):
    if sym not in FX_SENSITIVE:
        return None
    d = fetch("KRW=X"); s = series(d)
    c = [x[1] for x in s]; cur = d["meta"]["regularMarketPrice"]
    out = {"cur": cur}
    for lbl, n in [("1개월", 21), ("3개월", 63), ("6개월", 126)]:
        if len(c) > n:
            out[lbl] = (1 - cur/c[-1-n]) * 100   # + = 원화 절상 = 수출기업 역풍
    return out


def run(sym, label=""):
    d = fetch(sym, "2y"); ser = series(d)
    cur, fnote = freshness(d, ser)
    t = tech(ser, cur); tr = triggers(t)
    cy = d["meta"]["currency"]
    f = (lambda v: f"{v:,.0f}") if cy == "KRW" else (lambda v: f"{v:,.2f}")

    print("=" * 74)
    print(f" 사전진단 v1.6 — {label or sym} ({sym})   {datetime.date.today()}")
    print("=" * 74)
    print(f"\n[D2 신선도] {fnote}")
    print(f"\n[시세] {f(cur)} {cy} | 52주 {f(t['lo52'])}~{f(t['hi52'])} "
          f"(고점대비 {(cur/t['hi52']-1)*100:+.1f}%)")
    print(f"       RSI(14) {t['rsi']:.1f} | 일간변동성 {t['vol']:.2f}%")
    for n in (20, 60, 120, 200):
        v = t[f"ma{n}"]
        if v: print(f"       MA{n:<4} {f(v):>12}  이격 {(cur/v-1)*100:+6.1f}%")

    print(f"\n[D1 트리거 — 자동 재도출]")
    print("       지지:", " · ".join(f"{n} {f(v)}" for n, v in tr["지지"]) or "없음")
    print("       저항:", " · ".join(f"{n} {f(v)}" for n, v in tr["저항"]) or "없음")
    print(f"       무효화선 {f(tr['무효화선'])} ({tr['무효화까지']:+.1f}%)")
    print(f"       진입존 {f(tr['진입존'][0])}~{f(tr['진입존'][1])}")
    if abs(tr["무효화까지"]) < t["vol"] * 2:
        print(f"       ⚠ 손절폭({abs(tr['무효화까지']):.1f}%)이 2일 변동성"
              f"({t['vol']*2:.1f}%) 이내 — 노이즈 손절 위험")

    t_bars = t["bars"]
    ss = sector_split(sym, cur, ser)
    if ss:
        print(f"\n[D3 섹터 분해] {ss['sector']} (피어 {ss['n']}개)")
        print(f"       {'기간':<6}{'종목':>9}{'피어중앙값':>12}{'초과수익':>11}")
        for dd, lbl in [(21, "1개월"), (63, "3개월"), (126, "6개월"), (252, "12개월")]:
            if dd in ss["alpha"]:
                print(f"       {lbl:<6}{ss['self'][dd]:>8.1f}%{ss['peer_median'][dd]:>11.1f}%"
                      f"{ss['alpha'][dd]:>10.1f}%p")
        if t_bars < 300:
            print(f"       ⚠ 상장 후 {t_bars}거래일 — 12개월 알파는 IPO 초기 "
                  f"가격 왜곡 포함, 참고용")
        a3, a12 = ss["alpha"].get(63), ss["alpha"].get(252)
        if a3 is not None:
            v = "섹터 동조 (종목 악재 아님)" if abs(a3) < 10 else (
                "종목 특이 악재 우세" if a3 < 0 else "종목 특이 호재 우세")
            print(f"       → 3개월 판정: {v}")
        # 런업 되돌림 검사: 단기 언더퍼폼이 장기 아웃퍼폼의 반납인가?
        if a3 is not None and a12 is not None and t_bars >= 300:
            if a3 < -10 and a12 > 0:
                print(f"       → 12개월 초과수익 {a12:+.1f}%p — 단기 부진은 "
                      f"런업 되돌림 (구조적 악재 아님)")
            elif a3 < -10 and a12 < -10:
                print(f"       → 12개월 초과수익 {a12:+.1f}%p — 장·단기 동반 부진, "
                      f"구조적 문제 의심 ★조사 필요")
            elif a3 > 10 and a12 > 20:
                print(f"       → 12개월 초과수익 {a12:+.1f}%p — 지속 아웃퍼폼, "
                      f"기대치 과열 점검 필요")

    fx = fx_check(sym)
    if fx:
        print(f"\n[D4 환율 노출] USD/KRW {fx['cur']:,.1f}")
        for k in ("1개월", "3개월", "6개월"):
            if k in fx:
                mark = "  ← 역풍" if fx[k] > 5 else ("  ← 순풍" if fx[k] < -5 else "")
                print(f"       {k} 대비 원화 {fx[k]:+.1f}% 절상{mark}")
        if fx.get("3개월", 0) > 5:
            print("       ⚠ 수출기업 · 3개월 절상 5% 초과 → 컨센서스 목표가의 환율 가정 재검증 필수")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for s in sys.argv[1:]: run(s)
    else:
        run("439260.KS", "대한조선"); run("STRL", "Sterling Infrastructure")

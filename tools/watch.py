#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
일일 감시 — watchlist.json 을 읽고 변화가 있을 때만 보고한다.

원칙: 침묵이 기본값. 변화 없으면 아무것도 출력하지 않는다.
판단은 하지 않는다. "이게 바뀌었다"까지만 알린다.
"""
import json, os, sys, urllib.request, datetime, statistics, math

UA = {"User-Agent": "Mozilla/5.0"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WL = os.path.join(ROOT, "data", "watchlist.json")

YMAP = {"KR": lambda t: t + (".KS" if t in ("047050",) else ".KQ")}


def ysym(st):
    if st["market"] == "KR":
        return st["ticker"] + (".KS" if st["ticker"] in ("047050", "010120", "000660", "010130") else ".KQ")
    return st["ticker"]


def bars(sym, rng="1y"):
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"
    d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25))
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    c = [x for x in q["close"] if x is not None]
    lo = [x for x in q["low"] if x is not None]
    return c, lo, r["meta"]


def check(st):
    """반환: 알림 사유 목록. 비어 있으면 침묵."""
    alerts = []
    try:
        c, lo, m = bars(ysym(st))
    except Exception as e:
        return [f"시세 조회 실패 ({str(e)[:40]})"]

    cur = m["regularMarketPrice"]
    ts = m["regularMarketTime"]
    age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(ts)).days

    # 보조검사 A — 데이터 신선도
    if age > 5 and abs(cur / c[-1] - 1) > 0.05:
        cur = c[-1]
        alerts.append(f"⚠ 데이터 신선도: meta {age}일 경과, 시계열 채택")

    # 보조검사 C — 무효화선(3개월 저점) 이탈
    lo3 = min(lo[-60:]) if len(lo) >= 60 else min(lo)
    lo52 = min(lo[-252:]) if len(lo) >= 252 else min(lo)
    inval = lo52 if lo3 <= lo52 * 1.02 else lo3
    if cur < inval:
        alerts.append(f"■ 무효화선 이탈: {cur:,.2f} < {inval:,.2f}")
    elif cur < inval * 1.05:
        alerts.append(f"◆ 무효화선 근접 ({(cur/inval-1)*100:+.1f}%)")

    # 급변
    if len(c) > 5:
        w = (cur / c[-6] - 1) * 100
        if abs(w) >= 15:
            alerts.append(f"{'▲' if w>0 else '▼'} 5일 {w:+.1f}%")

    # 52주 신고가·신저가
    if cur >= max(c[-252:]) * 0.999:
        alerts.append("★ 52주 신고가")
    if cur <= min(c[-252:]) * 1.001:
        alerts.append("★ 52주 신저가")

    return alerts


def main():
    wl = json.load(open(WL, encoding="utf-8"))
    today = datetime.date.today().isoformat()
    out = []
    for st in wl["stocks"]:
        if st["grade"] == "X":      # 회피 등급은 감시 제외
            continue
        a = check(st)
        if a:
            out.append((st, a))

    if not out:
        print(f"[{today}] 변화 없음")
        return 0

    print(f"[{today}] 확인 필요 {len(out)}건\n")
    for st, a in out:
        print(f"── {st['grade']} {st['name']} ({st['ticker']})")
        for x in a:
            print(f"   {x}")
        print(f"   추적: " + " / ".join(t["item"] for t in st["tracking"]))
        print()
    return 1


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 0)

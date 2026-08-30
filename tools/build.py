#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대시보드 생성 — watchlist.json + 실시간 시세 → docs/index.html

케이스별로 묶어서 표시. GitHub Pages로 서빙.
"""
import json, os, urllib.request, datetime, html, time

UA = {"User-Agent": "Mozilla/5.0"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CASES = {
    "01-lynch": ("케이스 1 · 흑자 성장주", "피터 린치"),
    "02-cyclical": ("케이스 2 · 경기순환주", "린치 순환주"),
    "03-bg": ("케이스 3 · 적자 성장주", "베일리 기포드"),
}
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "X": 4}


KOSPI = ("047050", "010120", "000660", "010130", "439260")


def ysym(st):
    t = st.get("ticker")
    if not t:                       # 종목코드 미확인 건은 시세 조회를 건너뛴다
        return None
    if st.get("market") != "KR":
        return t
    return t + (".KS" if t in KOSPI else ".KQ")


def quote(st):
    sym = ysym(st)
    if not sym:
        return None
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20))
        r = d["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        c = [x for x in q["close"] if x is not None]
        lo = [x for x in q["low"] if x is not None]
        m = r["meta"]
        lo3 = min(lo[-60:]) if len(lo) >= 60 else min(lo)
        lo52 = m["fiftyTwoWeekLow"]
        return {"p": m["regularMarketPrice"], "cur": m["currency"],
                "lo52": lo52, "hi52": m["fiftyTwoWeekHigh"],
                "inval": lo52 if lo3 <= lo52 * 1.02 else lo3,
                "d5": (c[-1] / c[-6] - 1) * 100 if len(c) > 5 else None,
                "spark": c[-60:]}
    except Exception:
        return None


def spark(vals, w=120, h=28):
    if not vals or len(vals) < 2: return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i/(len(vals)-1)*w:.1f},{h-(v-lo)/rng*h:.1f}" for i, v in enumerate(vals))
    up = vals[-1] >= vals[0]
    col = "#16a34a" if up else "#dc2626"
    return (f'<svg viewBox="0 0 {w} {h}" class="spark"><polyline points="{pts}" '
            f'fill="none" stroke="{col}" stroke-width="1.5"/></svg>')


def fmt(v, cur):
    if v is None: return "—"
    return f"{v:,.0f}" if cur == "KRW" else f"{v:,.2f}"


def card(st, q):
    g = st["grade"]
    e = html.escape
    if not q:
        return f'<div class="card g{g}"><div class="hd"><span class="badge b{g}">{g}</span>' \
               f'<b>{e(st["name"])}</b></div><div class="err">시세 조회 실패</div></div>'
    p, cur = q["p"], q["cur"]
    j = (st.get("metrics") or {}).get("price_at_judgment")
    chg = (p / j - 1) * 100 if j else None
    pos = (p - q["lo52"]) / ((q["hi52"] - q["lo52"]) or 1) * 100
    dist = (p / q["inval"] - 1) * 100
    peg = (st.get("metrics") or {}).get("peg_3y")

    warn = ""
    if dist < 0:
        warn = '<div class="warn">■ 무효화선 이탈</div>'
    elif dist < 5:
        warn = f'<div class="warn">◆ 무효화선 근접 (+{dist:.1f}%)</div>'
    elif q["d5"] is not None and abs(q["d5"]) >= 15:
        warn = f'<div class="warn">{"▲" if q["d5"]>0 else "▼"} 5일 {q["d5"]:+.1f}%</div>'

    tr = "".join(
        f'<li><b>{e(t["item"])}</b><span class="src">{e(t["source"])}</span>'
        f'<div class="cond"><span class="up">↑ {e(t["promote"])}</span>'
        f'<span class="dn">↓ {e(t["demote"])}</span></div></li>'
        for t in st["tracking"])

    kills = ""
    if st.get("kill_reasons"):
        kills = '<div class="kill"><b>킬 사유</b><ul>' + "".join(
            f"<li>{e(k)}</li>" for k in st["kill_reasons"]) + "</ul></div>"

    chg_cls = "up" if (chg or 0) >= 0 else "dn"
    chg_txt = f"{chg:+.1f}%" if isinstance(chg, (int, float)) else "—"
    pos = pos if isinstance(pos, (int, float)) else 0.0
    dist = dist if isinstance(dist, (int, float)) else 0.0
    return f"""<div class="card g{g}">
  <div class="hd"><span class="badge b{g}">{g}</span>
    <div><b>{e(st['name'])}</b><span class="tk">{e(st.get('ticker') or '—')} · {e(st.get('classification') or '')}</span></div>
    {spark(q['spark'])}
  </div>
  <div class="px">
    <div class="now">{fmt(p,cur)}<span class="cur">{cur}</span></div>
    <div class="sub">판정가 {fmt(j,cur)} <span class="{chg_cls}">{chg_txt}</span></div>
  </div>
  <div class="bars">
    <div class="lbl">52주 위치 <b>{pos:.0f}%</b></div>
    <div class="bar"><i style="left:{min(max(pos,0),100):.0f}%"></i></div>
    <div class="lbl">무효화선 {fmt(q['inval'],cur)} <b>{dist:+.1f}%</b>
      {'· PEG '+str(peg) if peg else ''}</div>
  </div>
  {warn}{kills}
  <div class="story">{e(st['story'])}</div>
  <ul class="tr">{tr}</ul>
</div>"""


def main():
    wl = json.load(open(os.path.join(ROOT, "data", "watchlist.json"), encoding="utf-8"))
    groups = {}
    for st in wl["stocks"]:
        q = quote(st); time.sleep(0.15)
        groups.setdefault(st["case"], []).append((st, q))

    body = ""
    for ck, items in sorted(groups.items()):
        title, logic = CASES.get(ck, (ck, ""))
        items.sort(key=lambda x: (GRADE_ORDER.get(x[0]["grade"], 9), x[0]["name"]))
        counts = {}
        for st, _ in items:
            counts[st["grade"]] = counts.get(st["grade"], 0) + 1
        chips = " ".join(f'<span class="chip c{g}">{g} {n}</span>'
                         for g, n in sorted(counts.items(), key=lambda x: GRADE_ORDER.get(x[0], 9)))
        body += (f'<section><h2>{title}<span class="logic">{logic}</span></h2>'
                 f'<div class="chips">{chips}</div><div class="grid">'
                 + "".join(card(st, q) for st, q in items) + "</div></section>")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = TPL.replace("{{BODY}}", body).replace("{{NOW}}", now)
    out = os.path.join(ROOT, "docs")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(doc)
    print(f"생성 완료: docs/index.html ({len(wl['stocks'])}종목)")


TPL = """<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>종목 판정보드</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font:14px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;padding:20px 14px 60px}
header{max-width:1160px;margin:0 auto 26px}
h1{font-size:19px;font-weight:650;letter-spacing:-.2px}
.meta{color:#7d8590;font-size:12px;margin-top:4px}
section{max-width:1160px;margin:0 auto 34px}
h2{font-size:15px;font-weight:600;color:#e6edf3;padding-bottom:8px;border-bottom:1px solid #21262d;display:flex;align-items:baseline;gap:9px}
.logic{font-size:11px;color:#7d8590;font-weight:400}
.chips{margin:10px 0 14px;display:flex;gap:6px}
.chip{font-size:11px;padding:2px 8px;border-radius:10px;background:#161b22;border:1px solid #30363d}
.cA{color:#3fb950;border-color:#238636}.cB{color:#58a6ff;border-color:#1f6feb}
.cC{color:#d29922}.cX{color:#f85149;border-color:#da3633}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(330px,1fr))}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px}
.card.gA{border-left:3px solid #238636}.card.gB{border-left:3px solid #1f6feb}
.card.gX{border-left:3px solid #da3633;opacity:.72}
.hd{display:flex;align-items:flex-start;gap:9px;margin-bottom:11px}
.hd b{font-size:14px;display:block}
.tk{font-size:11px;color:#7d8590}
.badge{width:21px;height:21px;border-radius:5px;display:grid;place-items:center;font-size:11px;font-weight:700;flex:none}
.bA{background:#238636}.bB{background:#1f6feb}.bC{background:#9e6a03}.bX{background:#da3633}
.spark{width:80px;height:26px;margin-left:auto;flex:none}
.px{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:11px}
.now{font-size:21px;font-weight:650;font-variant-numeric:tabular-nums}
.cur{font-size:10px;color:#7d8590;margin-left:4px;font-weight:400}
.sub{font-size:11px;color:#7d8590}
.up{color:#3fb950}.dn{color:#f85149}
.bars{margin-bottom:10px}
.lbl{font-size:11px;color:#7d8590;margin-bottom:4px;font-variant-numeric:tabular-nums}
.bar{height:3px;background:#21262d;border-radius:2px;position:relative;margin-bottom:6px}
.bar i{position:absolute;top:-2px;width:2px;height:7px;background:#58a6ff;border-radius:1px}
.warn{background:#2d1a00;border:1px solid #9e6a03;color:#e3b341;font-size:11px;padding:5px 8px;border-radius:5px;margin-bottom:9px}
.kill{background:#2a0f0f;border:1px solid #da3633;border-radius:5px;padding:7px 9px;margin-bottom:9px;font-size:11px}
.kill b{color:#f85149;display:block;margin-bottom:3px}
.kill ul{list-style:none}.kill li{color:#ffa198;padding-left:9px;position:relative}
.kill li:before{content:"·";position:absolute;left:2px}
.story{font-size:12px;color:#adbac7;padding:9px 0;border-top:1px solid #21262d;line-height:1.6}
.tr{list-style:none;border-top:1px solid #21262d;padding-top:9px}
.tr li{padding:6px 0;border-bottom:1px dashed #21262d;font-size:11px}
.tr li:last-child{border:0}
.tr b{font-size:12px;color:#e6edf3}
.src{color:#7d8590;margin-left:6px;font-size:10px}
.cond{display:flex;gap:10px;margin-top:2px;font-size:10px;flex-wrap:wrap}
.err{color:#7d8590;font-size:12px;padding:8px 0}
footer{max-width:1160px;margin:0 auto;color:#7d8590;font-size:11px;text-align:center;padding-top:14px;border-top:1px solid #21262d}
</style></head><body>
<header><h1>종목 판정보드</h1>
<div class="meta">갱신 {{NOW}} · 판정 로직은 cases/ · 가격은 판정 시점 대비</div></header>
{{BODY}}
<footer>github.com/shindonghoooon/youngrich · 투자 판단은 본인 책임</footer>
</body></html>"""

if __name__ == "__main__":
    main()

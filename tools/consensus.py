#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
컨센서스 수집기 — stockanalysis.com forecast

수집 항목: 올해/내년 매출·EPS 컨센, 애널리스트 수, 과거 매출 시계열
용도: 린치 6분류의 1차 판정 기준(매출 성장률) + 컨센 대조

주의:
  - 애널리스트 수가 적으면(<5) 컨센 신뢰도 낮음. 한 명만 틀려도 크게 흔들림
  - 경기순환주는 정점에서 컨센이 가장 낙관적 → 역지표로 읽을 것
  - FY+2 이후는 유료 벽
"""
import re, html, json, urllib.request, sys, time

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}


def url_for(tk):
    return (f"https://stockanalysis.com/quote/krx/{tk}/forecast/"
            if re.match(r'^\d{6}$', tk)
            else f"https://stockanalysis.com/stocks/{tk.lower()}/forecast/")


def num(s):
    """1.34T / 4.10B / 132.20M / 7.32K → float"""
    if not s: return None
    s = s.strip()
    if s in ('-', '', '--'): return None
    m = re.match(r'^(-?[\d.]+)\s*([TBMK]?)$', s)
    if not m: return None
    v = float(m.group(1))
    return v * {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3, "": 1}[m.group(2)]


def fetch(tk, retries=2):
    for a in range(retries):
        try:
            r = urllib.request.Request(url_for(tk), headers=UA)
            raw = urllib.request.urlopen(r, timeout=25).read().decode("utf-8", "ignore")
            break
        except Exception:
            if a == retries - 1: return None
            time.sleep(1)
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', raw, flags=re.S)
    t = re.sub(r'</t[dh]>', ' | ', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'\s+', ' ', html.unescape(t))

    g = lambda p: (re.search(p, t).groups() if re.search(p, t) else None)
    o = {"tk": tk}
    m = g(r'Revenue This Year ([\d.]+[TBMK]?) from ([\d.]+[TBMK]?)')
    if m: o["rev_cy"], o["rev_ly"] = num(m[0]), num(m[1])
    m = g(r'Revenue Next Year ([\d.]+[TBMK]?)')
    if m: o["rev_ny"] = num(m[0])
    m = g(r'EPS This Year ([-\d.]+[TBMK]?) from ([-\d.]+[TBMK]?)')
    if m: o["eps_cy"], o["eps_ly"] = num(m[0]), num(m[1])
    m = g(r'EPS Next Year ([-\d.]+[TBMK]?)')
    if m: o["eps_ny"] = num(m[0])
    # 애널리스트 수: "No. Analysts | ... | N |" 행
    m = re.search(r'No\. Analysts \|([^\n]{0,120})', t)
    if m:
        ns = re.findall(r'\|\s*(\d+)\s*\|', m.group(1) + " |")
        if ns: o["n_analysts"] = int(ns[-1])
    # 과거 매출 행 (5년 성장 추세용)
    m = re.search(r'Revenue \|((?:\s*[\d.]+[TBMK]?\s*\|){3,})', t)
    if m:
        o["rev_hist"] = [num(x) for x in re.findall(r'([\d.]+[TBMK]?)', m.group(1))]
    return o


def growth(a, b):
    return (a / b - 1) * 100 if (a and b and b > 0) else None


def lynch_hint(g_cy, g_ny, g_hist):
    """린치 6분류 1차 힌트. 확정이 아니라 출발점."""
    gs = [x for x in (g_cy, g_ny) if x is not None]
    if not gs: return "판정불가"
    avg = sum(gs) / len(gs)
    # 과거 변동성 → 경기순환주 의심
    cyc = ""
    if g_hist and len(g_hist) >= 3:
        if min(g_hist) < -10 and max(g_hist) > 20:
            cyc = " ★사이클 의심"
    if avg >= 50: return "고성장(과열)" + cyc
    if avg >= 20: return "고성장" + cyc
    if avg >= 10: return "대형우량" + cyc
    if avg >= 2:  return "저성장" + cyc
    return "역성장/회생?" + cyc


# ── 한국 소형주 대체 소스 (stockanalysis 미커버 종목용) ──────────────
WR = "https://comp.wisereport.co.kr/company/c1010001.aspx?cmp_cd={}"

def fetch_kr(tk):
    """wisereport. stockanalysis가 404인 한국 중소형주에 사용."""
    try:
        r = urllib.request.Request(WR.format(tk),
            headers={**UA, "Referer": "https://comp.wisereport.co.kr/"})
        raw = urllib.request.urlopen(r, timeout=25).read().decode("utf-8", "ignore")
    except Exception:
        return None
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', raw, flags=re.S)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'\s+', ' ', html.unescape(t))
    o = {"tk": tk, "src": "wisereport"}
    m = re.search(r'EPS\s+(-?[\d,]+)원\s+(-?[\d,]+)원\s+(-?[\d,]+)원', t)
    if m:
        f = lambda x: float(x.replace(',', ''))
        o["eps_ly"], o["eps_cy"], o["eps_fwd"] = f(m[1]), f(m[2]), f(m[3])
    m = re.search(r'PER\s+([\d,.]+|N/A)\s+([\d,.]+|N/A)\s+([\d,.]+|N/A)', t)
    if m:
        o["per_cy"] = None if m[2] == 'N/A' else float(m[2].replace(',', ''))
        o["per_fwd"] = None if m[3] == 'N/A' else float(m[3].replace(',', ''))
    m = re.search(r'기업실적코멘트[^가-힣]*\[기준:([\d.]+)\]\s*(.{0,300})', t)
    if m:
        o["asof"], o["comment"] = m[1], m[2].strip()
    return o


if __name__ == "__main__":
    KR = ["010120","439260","017510","147830","098460","083650","105840",
          "046120","000660","126340","006910","033100","010130","019210","047050"]
    US = ["STRL","EROC","UUUU","TTMI","ORCL","LPTH","FORM","PWR","XE",
          "USAR","ONDS","ASPI","OPTT"]
    NM = {"010120":"LS ELECTRIC","439260":"대한조선","017510":"세명전기",
          "147830":"제룡산업","098460":"고영","083650":"비에이치아이",
          "105840":"우진","046120":"오르비텍","000660":"SK하이닉스",
          "126340":"비나텍","006910":"보성파워텍","033100":"제룡전기",
          "010130":"고려아연","019210":"와이지원","047050":"포스코인터"}
    tks = sys.argv[1:] or (KR + US)
    out = []
    print(f"{'종목':<16}{'올해성장':>9}{'내년성장':>9}{'EPS성장':>9}{'애널':>5}  린치 1차분류")
    print("-" * 74)
    for tk in tks:
        d = fetch(tk)
        if (not d or d.get("rev_cy") is None) and re.match(r'^\d{6}$', tk):
            k = fetch_kr(tk)
            if k: d = k
        if not d:
            print(f"{NM.get(tk,tk):<16}  조회실패"); continue
        if d.get("src") == "wisereport":
            ge2 = growth(d.get("eps_cy"), d.get("eps_ly"))
            fw = d.get("eps_fwd")
            gf = growth(fw, d.get("eps_cy"))
            print(f"{NM.get(tk,tk):<16}{'  (컨센 제한)':<18}"
                  f"{(f'{ge2:>7.0f}%' if ge2 is not None else '      -')}"
                  f"{'':>5}  EPS 올해 {d.get('eps_cy','-')} → Fwd {fw or '-'}"
                  f"{f' ({gf:+.0f}%)' if gf is not None else ''}")
            d.update(g_eps=ge2); out.append(d); time.sleep(0.4); continue
        gc = growth(d.get("rev_cy"), d.get("rev_ly"))
        gn = growth(d.get("rev_ny"), d.get("rev_cy"))
        ge = growth(d.get("eps_cy"), d.get("eps_ly"))
        gh = None
        if d.get("rev_hist") and len(d["rev_hist"]) >= 4:
            h = d["rev_hist"]
            gh = [growth(h[i], h[i-1]) for i in range(1, len(h))]
            gh = [x for x in gh if x is not None]
        hint = lynch_hint(gc, gn, gh)
        d.update(g_cy=gc, g_ny=gn, g_eps=ge, hint=hint)
        out.append(d)
        f = lambda v: f"{v:>8.1f}%" if v is not None else "       -"
        print(f"{NM.get(tk,tk):<16}{f(gc)}{f(gn)}{f(ge)}"
              f"{d.get('n_analysts','-'):>5}  {hint}")
        time.sleep(0.4)
    json.dump(out, open("consensus.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n{len(out)}/{len(tks)} 수집 → consensus.json")

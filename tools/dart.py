#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DART 반기보고서에서 린치 검증용 재무 추출

목적: 컨센/리포트 없는 한국 소형주의 STEP 3·4 검증 데이터 확보
추출: 매출·영업이익·순이익·영업현금흐름·재고·매출채권·부채·자본·현금
"""
import urllib.request, urllib.parse, re, html, json, sys, time

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
SEARCH = ("https://dart.fss.or.kr/dsab007/detailSearch.ax?"
          "currentPage=1&maxResults=30&textCrpNm={}&startDate=20260101&endDate=20260930")


def get(u, timeout=30):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA),
                                  timeout=timeout).read().decode("utf-8", "ignore")


def find_report(name, kinds=("반기보고서", "분기보고서")):
    """최신 반기/분기보고서의 rcpNo를 찾는다."""
    try:
        t = get(SEARCH.format(urllib.parse.quote(name)))
    except Exception:
        return None
    best = None
    for r in re.findall(r'<tr>(.*?)</tr>', t, re.S):
        rc = re.search(r'rcpNo=(\d+)', r)
        txt = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', r)))
        if not rc: continue
        for k in kinds:
            if k in txt:
                if best is None: best = (rc.group(1), k, txt[:60])
                break
    return best


def doc_tree(rcp):
    """보고서 내 문서 노드 목록 (title, eleId, offset, length, dcmNo)"""
    t = get(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp}")
    recs, seen = {}, []
    for m in re.finditer(r"(node\d+)\['(\w+)'\]\s*=\s*\"([^\"]*)\"", t):
        recs.setdefault(m.group(1) + "_" + str(m.start() // 4000), {})[m.group(2)] = m.group(3)
    out = []
    for v in recs.values():
        if "text" in v and "eleId" in v:
            key = (v["text"], v["eleId"])
            if key in seen: continue
            seen.append(key)
            out.append(v)
    return out


def read(rcp, dcm, ele, off, ln):
    u = (f"https://dart.fss.or.kr/report/viewer.do?rcpNo={rcp}&dcmNo={dcm}"
         f"&eleId={ele}&offset={off}&length={ln}&dtd=dart4.xsd")
    t = get(u, 40)
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', t, flags=re.S)
    t = re.sub(r'</t[dh]>', ' | ', t)
    t = re.sub(r'</tr>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = html.unescape(t)
    return '\n'.join(re.sub(r'[ \t]+', ' ', l).strip() for l in t.split('\n') if l.strip())


NUM = r'\(?-?[\d,]{3,}\)?'


def pick(txt, label, n=3):
    """DART 요약재무: 라벨 줄 다음 n개 줄에 값이 온다. 같은 줄 | 구분도 지원."""
    ls = txt.split('\n')
    pat = re.compile(rf'^[ⅠⅡⅢⅣ\dㆍ.\s]*{re.escape(label)}\s*(\||$)')
    for i, l in enumerate(ls):
        if not pat.match(l.strip()): continue
        vals = re.findall(NUM, l)          # 같은 줄
        if not vals:                       # 다음 줄들
            for j in range(i + 1, min(i + 1 + n * 2, len(ls))):
                m = re.fullmatch(NUM, ls[j].strip())
                if m: vals.append(ls[j].strip())
                elif vals: break
        out = []
        for v in vals[:n]:
            neg = v.startswith('(')
            v = v.strip('()').replace(',', '')
            try: out.append(-float(v) if neg else float(v))
            except: pass
        if out: return out
    return []


def extract(name):
    rep = find_report(name)
    if not rep: return {"name": name, "err": "보고서 없음"}
    rcp, kind, _ = rep
    nodes = doc_tree(rcp)
    tgt = [n for n in nodes if '요약' in n["text"] and '재무' in n["text"]]
    if not tgt:
        tgt = [n for n in nodes if '재무에 관한' in n["text"]]
    if not tgt: return {"name": name, "err": "재무 섹션 없음", "rcp": rcp}
    n = tgt[0]
    try:
        txt = read(rcp, n["dcmNo"], n["eleId"], n["offset"], n["length"])
    except Exception as e:
        return {"name": name, "err": f"본문 실패", "rcp": rcp}
    m = re.search(r'\(단위\s*:?\s*([^)]{0,12})\)', txt)
    u = m.group(1) if m else "원"
    mul = 1e6 if "백만" in u else (1e3 if "천" in u else (1e8 if "억" in u else 1))
    o = {"name": name, "rcp": rcp, "kind": kind, "unit": u, "mul": mul}
    for k, lab in [("rev", "매출액"), ("op", "영업이익"), ("ni", "당기순이익"),
                   ("inv", "재고자산"), ("ar", "매출채권및기타유동채권"),
                   ("cash", "현금및현금성자산"),
                   ("liab", "부채총계"), ("eq", "자본총계"),
                   ("cur_a", "유동자산"), ("cur_l", "유동부채")]:
        v = pick(txt, lab)
        if v: o[k] = v
    return o


if __name__ == "__main__":
    import urllib.parse
    names = sys.argv[1:] or ["보성파워텍", "제룡산업", "세명전기", "우진",
                             "오르비텍", "비나텍", "엘에스일렉트릭"]
    res = []
    for nm in names:
        r = extract(nm)
        res.append(r)
        if r.get("err"):
            print(f"{nm:<12} {r['err']}")
        else:
            mu = r.get("mul", 1)
            f = lambda k: (f"{r[k][0]*mu/1e8:,.0f}억" if r.get(k) else "-")
            print(f"{nm:<12} {r['kind']:<8} 매출 {f('rev'):>10} 영업익 {f('op'):>9} "
                  f"재고 {f('inv'):>9} 부채 {f('liab'):>10} 자본 {f('eq'):>10}")
        time.sleep(0.5)
    json.dump(res, open("kr_dart.json", "w"), ensure_ascii=False, indent=1)

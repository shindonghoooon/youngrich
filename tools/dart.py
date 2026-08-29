#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DART 반기/분기보고서에서 린치 검증용 재무 추출

원칙
  - 연결 우선. 연결이 없으면 별도로 폴백하되 basis 필드에 반드시 남긴다 (보조검사 D)
  - 손익은 '누적' 컬럼을 쓴다. 3개월 컬럼을 집으면 반기 매출이 반토막 난다
  - 검산에 실패하면 err를 붙인다. 조용히 틀린 값이 가장 위험하다

추출: 매출·영업이익·순이익·영업현금흐름·재고·매출채권·현금·부채·자본·자산
"""
import urllib.request, urllib.parse, re, html, json, sys, time, os

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
SEARCH = ("https://dart.fss.or.kr/dsab007/detailSearch.ax?"
          "currentPage=1&maxResults=30&textCrpNm={}&startDate={}&endDate={}")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get(u, timeout=30, tries=3):
    """DART는 간헐적으로 끊긴다. 재시도 없으면 통과율이 회차마다 달라진다."""
    last = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(u, headers=UA),
                timeout=timeout).read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


# ---------------------------------------------------------------- 보고서 탐색

def find_report(name, kinds=("반기보고서", "분기보고서", "사업보고서"),
                start="20250101", end="20261231"):
    try:
        t = get(SEARCH.format(urllib.parse.quote(name), start, end))
    except Exception:
        return None
    cands = []
    for r in re.findall(r"<tr>(.*?)</tr>", t, re.S):
        rc = re.search(r"rcpNo=(\d+)", r)
        if not rc:
            continue
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", r))).strip()
        kind = next((k for k in kinds if k in txt), None)
        if not kind:
            continue
        d = re.search(r"(20\d{2}\.\d{2}\.\d{2})", txt)
        exact = bool(re.search(rf"(^|\s){re.escape(name)}(\s|$)", txt))
        cands.append((exact, d.group(1) if d else "", rc.group(1), kind, txt[:70]))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _, dt, rcp, kind, txt = cands[0]
    return {"rcp": rcp, "kind": kind, "filed": dt, "row": txt}


def toc(rcp):
    """목차 전체. 구버전은 노드를 4000바이트 버킷으로 묶어 61개 중 15개만 남겼다."""
    t = get(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp}")
    out = []
    for b in re.split(r"var node\d+ = \{\};", t)[1:]:
        d = dict(re.findall(r"node\d+\['(\w+)'\]\s*=\s*\"([^\"]*)\"", b))
        if "text" in d and "eleId" in d:
            out.append(d)
    return out


def read(n):
    u = ("https://dart.fss.or.kr/report/viewer.do?"
         f"rcpNo={n['rcpNo']}&dcmNo={n['dcmNo']}&eleId={n['eleId']}"
         f"&offset={n['offset']}&length={n['length']}&dtd={n.get('dtd','dart4.xsd')}")
    t = get(u, 40)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = re.sub(r"</t[dh]>", " | ", t)
    t = re.sub(r"</tr>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n") if l.strip())


# ---------------------------------------------------------------- 표 파싱

NUM = re.compile(r"^\(?-?[\d,]+\)?$")


def cells(txt):
    out = []
    for line in txt.split("\n"):
        for c in line.split("|"):
            c = c.strip()
            if c:
                out.append(c)
    return out


def tonum(s):
    neg = s.startswith("(")
    try:
        v = float(s.strip("()").replace(",", ""))
    except ValueError:
        return None
    return -v if neg else v


def rows(txt):
    """[(라벨, [값...])] — 라벨 셀 뒤에 붙은 숫자 셀을 한 행으로 묶는다."""
    cs = cells(txt)
    out, i = [], 0
    while i < len(cs):
        if NUM.match(cs[i]):
            i += 1
            continue
        lab, vals, j = cs[i], [], i + 1
        while j < len(cs) and NUM.match(cs[j]):
            v = tonum(cs[j])
            if v is None:
                break
            vals.append(v)
            j += 1
        if vals:
            out.append((lab, vals))
        i = j if vals else i + 1
    return out


def unit_mul(txt):
    m = re.search(r"\(\s*단위\s*:?\s*([^)]{0,12})\)", txt)
    u = m.group(1).strip() if m else "원"
    return u, (1e8 if "억" in u else 1e6 if "백만" in u else 1e3 if "천" in u else 1)


def cum_idx(txt):
    """손익표 컬럼 배치가 [3개월, 누적, 3개월, 누적] 이면 누적은 1번."""
    return 1 if "누적" in "\n".join(txt.split("\n")[:20]) else 0


ALIAS = {
    "rev":  ["매출액", "수익(매출액)", "영업수익", "매출", "수익"],
    "op":   ["영업이익(손실)", "영업손익", "영업이익"],
    "ni":   ["당기순이익(손실)", "반기순이익(손실)", "분기순이익(손실)",
             "당기순이익", "반기순이익", "분기순이익"],
    "assets": ["자산총계"],
    "liab": ["부채총계"],
    "eq":   ["자본총계"],
    "cash": ["현금및현금성자산"],
    "inv":  ["유동 재고자산", "재고자산"],
    "ar":   ["매출채권 및 기타 유동 채권", "매출채권및기타유동채권",
             "매출채권 및 기타유동채권", "매출채권"],
    "cfo":  ["영업활동현금흐름", "영업활동으로 인한 현금흐름",
             "영업활동으로부터의 현금흐름"],
}


# 라벨에 붙는 주석참조를 떼어낸다. LS일렉트릭의 "매출 (주4,23,24,31)" 때문에
# 완전일치가 깨지고 "기타수익"이 매출로 잡혔다.
BAN = ("원가", "총이익", "채권", "에누리", "할인", "차감", "누계")


def clean(lab):
    lab = re.sub(r"\((주|Note)[^)]*\)", "", lab)
    lab = re.sub(r"\(단위[^)]*\)", "", lab)
    # 세명전기 "Ⅰ.수익" 처럼 로마숫자·번호 접두가 붙는 서식이 있다
    lab = re.sub(r"^[\(\[]?[0-9IVXLCDMⅠ-ⅿ]+[\)\]]?[\.\s·ㆍ]*", "", lab)
    return re.sub(r"\s+", "", lab)


def grab(rs, keys, idx):
    pick = lambda v: v[idx] if idx < len(v) else v[0]
    for k in keys:                       # 완전일치만 신뢰한다
        kk = clean(k)
        for lab, vals in rs:
            if clean(lab) == kk:
                return pick(vals)
    for k in keys:                       # 접두 폴백 — 파생항목은 제외
        kk = clean(k)
        for lab, vals in rs:
            cl = clean(lab)
            if cl.startswith(kk) and not any(b in cl for b in BAN):
                return pick(vals)
    return None


# ---------------------------------------------------------------- 추출

EMPTY = re.compile(r"해당\s?사항\s?(없음|없습니다)|기재를\s?생략|작성하지\s?않")


def sect(nodes, names):
    norm = lambda s: re.sub(r"\s+", "", s)
    for nm in names:
        for n in nodes:
            if norm(n["text"]) == norm(nm):
                return n
    return None


def statements(nodes):
    """(basis, 재무상태표, 포괄손익계산서, 현금흐름표)"""
    con = sect(nodes, ["2. 연결재무제표"])
    if con:
        try:
            if not EMPTY.search(read(con)):
                bs = sect(nodes, ["2-1. 연결 재무상태표", "2-1. 연결재무상태표"])
                is_ = sect(nodes, ["2-2. 연결 포괄손익계산서", "2-2. 연결 손익계산서",
                                   "2-2. 연결포괄손익계산서"])
                cf = sect(nodes, ["2-4. 연결 현금흐름표", "2-4. 연결현금흐름표"])
                if bs and is_:
                    return "연결", bs, is_, cf
        except Exception:
            pass
    bs = sect(nodes, ["4-1. 재무상태표"])
    is_ = sect(nodes, ["4-2. 포괄손익계산서", "4-2. 손익계산서"])
    cf = sect(nodes, ["4-4. 현금흐름표"])
    if bs and is_:
        return "별도", bs, is_, cf
    return None, None, None, None


def check(o):
    bad = []
    a, l, e = o.get("assets"), o.get("liab"), o.get("eq")
    if a and l and e and abs(a - (l + e)) > a * 0.005:
        bad.append("자산≠부채+자본")
    r, p = o.get("rev"), o.get("op")
    if r is not None and p is not None:
        if r <= 0:
            bad.append("매출≤0")
        elif abs(r - p) < 1:
            bad.append("매출=영업이익")
        elif p > r:
            bad.append("영업이익>매출")
    for k in ("rev", "op", "assets"):
        if o.get(k) is None:
            bad.append(f"{k} 누락")
    return bad


def extract(name):
    rep = find_report(name)
    if not rep:
        return {"name": name, "err": "보고서 없음"}
    o = {"name": name, "rcp": rep["rcp"], "kind": rep["kind"], "filed": rep["filed"]}
    try:
        nodes = toc(rep["rcp"])
    except Exception:
        return {**o, "err": "목차 실패"}
    basis, bs, is_, cf = statements(nodes)
    if not basis:
        return {**o, "err": "재무제표 섹션 없음"}
    o["basis"] = basis
    try:
        tb, ti = read(bs), read(is_)
    except Exception:
        return {**o, "err": "본문 실패"}

    ub, mb = unit_mul(tb)
    ui, mi = unit_mul(ti)
    rb, ri = rows(tb), rows(ti)
    ci = cum_idx(ti)
    o["unit"] = {"bs": ub, "is": ui}
    o["col"] = "누적" if ci else "단일"

    for k in ("assets", "liab", "eq", "cash", "inv", "ar"):
        v = grab(rb, ALIAS[k], 0)
        if v is not None:
            o[k] = v * mb
    for k in ("rev", "op", "ni"):
        v = grab(ri, ALIAS[k], ci)
        if v is not None:
            o[k] = v * mi
    if cf:
        try:
            tc = read(cf)
            v = grab(rows(tc), ALIAS["cfo"], cum_idx(tc))
            if v is not None:
                o["cfo"] = v * unit_mul(tc)[1]
        except Exception:
            pass

    bad = check(o)
    if bad:
        o["err"] = "검산실패: " + ", ".join(bad)
    return o


# ---------------------------------------------------------------- CLI

def fmt(v):
    return f"{v/1e8:,.0f}억" if isinstance(v, (int, float)) else "-"


if __name__ == "__main__":
    names = sys.argv[1:] or ["보성파워텍", "제룡산업", "제룡전기", "세명전기",
                             "우진", "오르비텍", "비나텍", "엘에스일렉트릭"]
    res = []
    for nm in names:
        r = extract(nm)
        res.append(r)
        if "rev" not in r:
            print(f"{nm:<10} ✗ {r.get('err','알수없음')}")
        else:
            opm = r["op"] / r["rev"] * 100 if r.get("op") is not None else float("nan")
            flag = "  ⚠ " + r["err"] if r.get("err") else ""
            print(f"{nm:<10} {r['basis']:<3} {r['kind'][:4]} "
                  f"매출 {fmt(r.get('rev')):>9} 영업익 {fmt(r.get('op')):>8} "
                  f"OPM {opm:>5.1f}%  자산 {fmt(r.get('assets')):>9} "
                  f"자본 {fmt(r.get('eq')):>9}{flag}")
        time.sleep(0.6)
    out = os.path.join(ROOT, "data", "kr_dart.json")
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    ok = sum(1 for r in res if not r.get("err"))
    print(f"\n{ok}/{len(res)} 통과 → data/kr_dart.json")

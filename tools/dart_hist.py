#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DART 사업보고서의 '1. 요약재무정보'를 여러 해 겹쳐 읽어 장기 이력을 만든다.
케이스 2(경기순환주)의 10년 마진 밴드 계산용.

  python tools/dart_hist.py 고려아연 SK하이닉스

요약재무정보는 한 보고서에 3개년이 담긴다. 3년 간격으로 사업보고서를 훑으면
중복 없이 이력이 이어진다. 겹치는 연도는 최신 보고서 값을 쓴다(정정 반영).
"""
import re, sys, json, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dart

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# publicType=A001 → 사업보고서만. 없으면 결과 30건 상한에 밀려 누락된다
ANNUAL_SEARCH = ("https://dart.fss.or.kr/dsab007/detailSearch.ax?currentPage=1"
                 "&maxResults=30&textCrpNm={}&startDate={}&endDate={}&publicType=A001")
NUM = re.compile(r"^\(?-?[\d,]+\)?$")   # (4,672,124) 형태의 음수 포함
# 서식이 두 가지다.
#  A) "제52기 (2025년 12월말)"  한 셀에 기수+연도
#  B) "제49기" / "2022년 12월말"  두 셀로 분리
YEAR = re.compile(r"\(?(\d{4})\.\d{2}\.\d{2}\s*~\s*(\d{4})\.\d{2}\.\d{2}\)?")
FYEND = re.compile(r"(\d{4})년\s*(?:\d{1,2}월)?\s*말")   # "2025년 12월말" / "(2025년 말)"
GISU  = re.compile(r"제\s*(\d+)\s*기")


def annual_reports(name, start="20140101", end="20261231"):
    """사업보고서 목록. DART 검색은 결과 30건이 상한이라 연 단위로 나눠 조회한다."""
    import urllib.parse
    rows = []
    for y in range(int(end[:4]), int(start[:4]) - 1, -1):
        try:
            t = dart.get(ANNUAL_SEARCH.format(
                urllib.parse.quote(name), f"{y}0101", f"{y}1231"))
            rows += re.findall(r"<tr>(.*?)</tr>", t, re.S)
        except Exception:
            continue
    out = {}
    for r in rows:
        rc = re.search(r"rcpNo=(\d+)", r)
        if not rc:
            continue
        import html as H
        txt = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", r))).strip()
        if "사업보고서" not in txt:
            continue
        if not re.search(rf"(^|\s){re.escape(name)}(\s|$)", txt):
            continue
        m = re.search(r"사업보고서\s*\((\d{4})\.(\d{2})\)", txt)
        fy = m.group(1) if m else None
        d = re.search(r"(20\d{2}\.\d{2}\.\d{2})", txt)
        key = fy or (d.group(1) if d else rc.group(1))
        # 같은 사업연도는 가장 최근 접수건(정정본)만
        if key not in out or (d and d.group(1) > out[key][1]):
            out[key] = (rc.group(1), d.group(1) if d else "")
    return sorted(((k, v[0], v[1]) for k, v in out.items()), reverse=True)


def parse_summary(txt, fy=None):
    """요약재무정보 본문 → {연도: {항목: 값}} (단위 백만원 가정, 헤더에서 확인)"""
    mul = 1e6 if "백만원" in txt[:400] else (1e8 if "억원" in txt[:400] else 1e3 if "천원" in txt[:400] else 1)
    cells = [c.strip() for line in txt.split("\n") for c in line.split("|") if c.strip()]

    # 연결 파트만 사용 (없으면 전체)
    joined = "\n".join(cells)
    # "나. 별도 요약재무정보" / "나. 요약 별도재무정보" 두 표기 모두
    m = re.search(r"나\.\s*(별도\s*요약재무정보|요약\s*별도재무정보)", joined)
    if m:
        cells = joined[:m.start()].split("\n")

    def dedup(xs):
        out = []
        for x in xs:
            if x not in out:
                out.append(x)
        return out

    bs_years, is_years = [], []
    for c in cells:
        m = FYEND.search(c)
        if m:
            bs_years.append(int(m.group(1)))
        m2 = YEAR.search(c)
        if m2:
            is_years.append(int(m2.group(2)))
    bs_years = dedup(bs_years)[:3]
    is_years = dedup(is_years)[:3] or bs_years   # 손익 기간 표기가 없으면 재무상태표 열 순서를 따른다

    # C) 연도 표기가 아예 없고 기수만 있는 서식 (SK하이닉스). 보고 사업연도로 역산한다
    if not bs_years and fy:
        gs = dedup([int(m.group(1)) for c in cells for m in [GISU.search(c)] if m])[:3]
        if gs:
            top = max(gs)
            bs_years = [int(fy) - (top - g) for g in gs]
            is_years = is_years or bs_years

    out = {}

    def norm(c):
        c = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ0-9]+\s*[\.\)]?\s*", "", c.strip())
        return re.sub(r"\s+", "", c).strip("[]ㆍ·")

    def grab(label, years):
        if not years:
            return
        for i, c in enumerate(cells):
            if norm(c) == label:
                vals = []
                for x in cells[i + 1:i + 1 + len(years)]:
                    if not NUM.match(x):
                        break
                    neg = x.startswith("(")
                    v = float(x.strip("()").replace(",", "")) * mul
                    vals.append(-v if neg else v)
                if len(vals) == len(years):
                    for y, v in zip(years, vals):
                        out.setdefault(y, {})[label] = v
                return

    for lab in ("매출액", "영업이익", "당기순이익"):
        grab(lab, is_years)
    for lab in ("재고자산", "현금및현금성자산", "부채총계", "자본총계", "자산총계"):
        grab(lab, bs_years)
    return out


def history(name, span=("20140101", "20261231")):
    reps = annual_reports(name, *span)
    if not reps:
        return {"name": name, "err": "사업보고서 없음"}
    hist, used = {}, []
    for fy, rcp, filed in reps:
        if used and len(hist) >= 12:
            break
        # 3년 간격으로만 읽는다 (요약이 3개년을 담으므로)
        if used and any(abs(int(fy) - int(u)) < 3 for u in used):
            continue
        try:
            nodes = dart.toc(rcp)
            s = dart.sect(nodes, ["1. 요약재무정보"])
            if not s:
                continue
            txt = dart.read(s)
            if dart.EMPTY.search(txt[:300]):
                continue
            d = parse_summary(txt, fy)
            for y, v in d.items():
                hist.setdefault(y, {}).update({k: x for k, x in v.items() if k not in hist.get(y, {})})
            used.append(fy)
            time.sleep(0.5)
        except Exception:
            continue
    return {"name": name, "reports": used, "years": dict(sorted(hist.items()))}


if __name__ == "__main__":
    names = sys.argv[1:] or ["고려아연", "SK하이닉스", "대한조선", "와이지원"]
    res = []
    for nm in names:
        h = history(nm)
        res.append(h)
        if h.get("err"):
            print(f"{nm:<10} ✗ {h['err']}")
            continue
        ys = h["years"]
        print(f"### {nm}  (보고서 {h['reports']})")
        print(f"{'연도':<6}{'매출(억)':>12}{'영업익(억)':>12}{'OPM':>8}{'재고(억)':>12}")
        for y in sorted(ys):
            v = ys[y]
            r, o = v.get("매출액"), v.get("영업이익")
            inv = v.get("재고자산")
            f = lambda x: f"{x/1e8:11,.0f}" if isinstance(x, (int, float)) else "          -"
            m = f"{o/r*100:7.1f}%" if (r and o is not None) else "       -"
            print(f"{y:<6}{f(r)}{f(o)}{m}{f(inv)}")
        print()
    json.dump(res, open(os.path.join(ROOT, "data", "kr_hist.json"), "w"),
              ensure_ascii=False, indent=1)
    print("→ data/kr_hist.json")

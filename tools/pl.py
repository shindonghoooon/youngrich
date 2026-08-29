# -*- coding: utf-8 -*-
"""DART '4. 재무제표' 섹션에서 손익계산서 전항목 추출 (전년동기 포함)"""
import dart, re

LAB = ["매출액","수익(매출액)","영업수익","매출원가","매출총이익",
       "판매비와관리비","영업이익","영업이익(손실)"]

def pl(name):
    rep = dart.find_report(name)
    if not rep: return None
    nodes = dart.doc_tree(rep[0])
    # 손익계산서가 들어있는 노드 후보: '재무제표' 계열
    cands = [n for n in nodes if re.search(r'재무제표$|^4\.|^2\.', n['text'])]
    cands += [n for n in nodes if '재무에 관한' in n['text']]
    for n in cands:
        try:
            t = dart.read(rep[0], n['dcmNo'], n['eleId'], n['offset'], n['length'])
        except Exception:
            continue
        if '매출총이익' not in t and '매출원가' not in t: continue
        out = {"rcp": rep[0], "ele": n['eleId']}
        for lab in LAB:
            i = t.find('\n'+lab+'\n')
            if i < 0: continue
            seg = t[i+len(lab)+2 : i+len(lab)+180].split('\n')
            vals = []
            for s in seg:
                s = s.strip()
                m = re.fullmatch(r'\(?-?[\d,]{4,}\)?', s)
                if m:
                    neg = s.startswith('(')
                    vals.append(-float(s.strip('()').replace(',','')) if neg
                                else float(s.replace(',','')))
                elif vals: break
            if vals: out[lab] = vals[:4]
        if len(out) > 3: return out
    return None

def judge(name):
    d = pl(name)
    if not d: return print(f"{name:<12} 추출 실패")
    gp = d.get('매출총이익'); cogs = d.get('매출원가')
    sga = d.get('판매비와관리비')
    op = d.get('영업이익') or d.get('영업이익(손실)')
    if not (gp and cogs): return print(f"{name:<12} 손익 항목 부족 {list(d)}")
    n = min(len(gp), len(cogs))
    rev = [gp[i]+cogs[i] for i in range(n)]
    # 열 구조: 4개면 [당3M, 당누적, 전3M, 전누적] / 2개면 [당, 전]
    if n >= 4: ci, pi = 1, 3
    elif n >= 2: ci, pi = 0, 1
    else: return print(f"{name:<12} 비교열 없음")
    gmc, gmp = gp[ci]/rev[ci]*100, gp[pi]/rev[pi]*100
    gr = (rev[ci]/rev[pi]-1)*100
    gs = (sga[ci]/sga[pi]-1)*100 if (sga and len(sga)>pi and sga[pi]>0) else None
    opc = op[ci] if (op and len(op)>ci) else None
    opm = opc/rev[ci]*100 if opc is not None else None
    k = []
    if gmc < 0: k.append("GM음수")
    if gs is not None and gs > gr: k.append("판관비>매출")
    if gmc < gmp - 2: k.append("GM악화")
    v = "★킬: "+"·".join(k) if k else "통과"
    f = lambda x,s='%': f"{x:>8.1f}{s}" if x is not None else "        -"
    print(f"{name:<12}{rev[ci]/1e8:>9,.0f}억{f(gr)}{f(gmp)}→{f(gmc)}{f(gs)}{f(opm)}  {v}")

if __name__ == "__main__":
    import sys
    print(f"{'종목':<12}{'매출':>11}{'매출성장':>9}{'GM 전년':>9} {'GM 당기':>9}{'판관비증가':>9}{'OPM':>9}  판정")
    print("-"*94)
    for nm in (sys.argv[1:] or ["보성파워텍","제룡산업","세명전기","우진","오르비텍","엘에스일렉트릭"]):
        try: judge(nm)
        except Exception as e: print(f"{nm:<12} 오류 {str(e)[:40]}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 이슈 본문 → data/*.json 반영

명령 4개. 이슈 본문 첫 줄이 명령어다.

  /judge   판정 결과 등록. A·B·C → watchlist, D·X → rejected
  /queue   케이스 미확정 종목 대기열 등록
  /drop    제거 (어느 파일에 있든)
  /move    watchlist ↔ rejected 이동 (등급 변경)

블록 형식 (key: value / track은 파이프 4칸)

  /judge
  ticker: 439260
  name: 대한조선
  market: KR
  case: 02-cyclical
  grade: B
  classification: 경기순환주
  story: 컨테이너 발주 사이클 하강 국면에서도 ...
  kill: 오버행 미해소; 원화 절상 민감도
  track:
  - 신조선가 지수 | 클락슨 주간 | 상승 전환 | 3주 연속 하락
  - 수주잔고 | 분기실적 | 2.5년분 이상 | 2년 미만

검증에 실패하면 파일을 건드리지 않고 STDERR로 사유를 낸다.
"""
import json, os, re, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = {"watch": "data/watchlist.json",
         "rej":   "data/rejected.json",
         "queue": "data/queue.json"}
GRADES = ("A", "B", "C", "D", "X")
WATCH_GRADES = ("A", "B", "C")


def load(k):
    return json.load(open(os.path.join(ROOT, FILES[k]), encoding="utf-8"))


def save(k, d):
    d["updated_at"] = datetime.date.today().isoformat()
    with open(os.path.join(ROOT, FILES[k]), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write("\n")


def parse(body):
    lines = [l.rstrip() for l in body.replace("\r", "").split("\n")]
    lines = [l for l in lines if l.strip() not in ("```", "```text")]
    cmd = None
    for l in lines:
        if l.strip().startswith("/"):
            cmd = l.strip().split()[0][1:]
            break
    if cmd is None:
        return None, {}, []
    d, track, mode = {}, [], None
    for l in lines:
        s = l.strip()
        if not s or s.startswith("/"):
            continue
        if s.startswith("-") and mode == "track":
            parts = [p.strip() for p in s.lstrip("-").split("|")]
            if len(parts) == 4:
                track.append(dict(zip(("item", "source", "promote", "demote"), parts)))
            else:
                raise ValueError(f"track 항목은 4칸이어야 한다: {s}")
            continue
        m = re.match(r"^([a-zA-Z_]+)\s*:\s*(.*)$", s)
        if m:
            k, v = m.group(1).lower(), m.group(2).strip()
            mode = "track" if k == "track" else None
            if k != "track":
                d[k] = v
    return cmd, d, track


def need(d, keys):
    miss = [k for k in keys if not d.get(k)]
    if miss:
        raise ValueError("필수 항목 누락: " + ", ".join(miss))


def rm(d, ticker, name):
    before = len(d["stocks"])
    d["stocks"] = [s for s in d["stocks"]
                   if not ((ticker and s.get("ticker") == ticker)
                           or (not ticker and s.get("name") == name))]
    return before - len(d["stocks"])


def run(body):
    cmd, d, track = parse(body)
    if cmd is None:
        raise ValueError("명령어가 없다. 첫 줄에 /judge · /queue · /drop · /move")
    today = datetime.date.today().isoformat()
    tk, nm = d.get("ticker") or None, d.get("name")

    if cmd == "judge":
        need(d, ["name", "case", "grade", "story"])
        g = d["grade"].upper()
        if g not in GRADES:
            raise ValueError(f"등급은 {'/'.join(GRADES)} 중 하나여야 한다")
        if g in WATCH_GRADES and not track:
            raise ValueError("A·B·C는 추적 항목이 최소 1개 필요하다")
        rec = {"ticker": tk, "name": nm, "market": d.get("market", "KR"),
               "case": d["case"], "grade": g,
               "classification": d.get("classification"),
               "story": d["story"],
               "kill_reasons": [x.strip() for x in d.get("kill", "").split(";") if x.strip()]}
        for k in ("watch", "rej", "queue"):      # 중복 제거
            x = load(k); n = rm(x, tk, nm)
            if n: save(k, x)
        if g in WATCH_GRADES:
            rec["judged_at"] = today
            rec["tracking"] = track
            w = load("watch"); w["stocks"].append(rec); save("watch", w)
            return f"{nm} {g} → watchlist (추적 {len(track)}개)"
        rec["rejected_at"] = today
        rec["recheck"] = track
        r = load("rej"); r["stocks"].append(rec); save("rej", r)
        return f"{nm} {g} → rejected"

    if cmd == "queue":
        need(d, ["name"])
        q = load("queue"); rm(q, tk, nm)
        q["stocks"].append({"ticker": tk, "name": nm,
                            "market": d.get("market", "KR"),
                            "case": d.get("case") or None,
                            "queued_at": today,
                            "note": d.get("note", "")})
        save("queue", q)
        return f"{nm} → queue ({d.get('case') or '케이스 미배정'})"

    if cmd == "drop":
        need(d, ["name"])
        hits = []
        for k in ("watch", "rej", "queue"):
            x = load(k); n = rm(x, tk, nm)
            if n:
                save(k, x); hits.append(FILES[k])
        if not hits:
            raise ValueError(f"{nm} 을(를) 어디서도 찾지 못했다")
        return f"{nm} 제거 → " + ", ".join(hits)

    if cmd == "move":
        need(d, ["name", "grade"])
        g = d["grade"].upper()
        src = "rej" if g in WATCH_GRADES else "watch"
        dst = "watch" if g in WATCH_GRADES else "rej"
        s0 = load(src)
        hit = next((s for s in s0["stocks"]
                    if (tk and s.get("ticker") == tk) or (not tk and s.get("name") == nm)), None)
        if not hit:
            raise ValueError(f"{nm} 이(가) {FILES[src]} 에 없다")
        rm(s0, tk, nm); save(src, s0)
        hit["grade"] = g
        if track:
            hit["tracking" if dst == "watch" else "recheck"] = track
        hit["judged_at" if dst == "watch" else "rejected_at"] = today
        d1 = load(dst); d1["stocks"].append(hit); save(dst, d1)
        return f"{nm} → {g} ({FILES[src]} → {FILES[dst]})"

    raise ValueError(f"모르는 명령: /{cmd}")


if __name__ == "__main__":
    body = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    try:
        print("✅ " + run(body))
    except Exception as e:
        print("❌ " + str(e), file=sys.stderr)
        sys.exit(1)

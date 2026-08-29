#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
텔레그램 알림 전송

환경변수:
  TELEGRAM_BOT_TOKEN  BotFather에서 받은 토큰
  TELEGRAM_CHAT_ID    받을 채팅 ID

표준입력으로 받은 텍스트를 전송한다. '변화 없음'이면 전송하지 않는다.

  python tools/notify.py                 → 제목 "📊 종목 감시" (기본)
  python tools/notify.py "✅ 판정 반영"   → 제목 지정
"""
import os, sys, json, urllib.request, urllib.parse

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = os.environ.get("TELEGRAM_CHAT_ID")
API = "https://api.telegram.org/bot{}/sendMessage"


def send(text):
    if not TOKEN or not CHAT:
        print("토큰 또는 chat_id 없음. 전송 생략", file=sys.stderr)
        return False
    # 텔레그램 메시지 상한 4096자
    for i in range(0, len(text), 3900):
        chunk = text[i:i + 3900]
        data = urllib.parse.urlencode({
            "chat_id": CHAT,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(API.format(TOKEN), data=data), timeout=20)
            ok = json.load(r).get("ok")
            if not ok:
                print("전송 실패", file=sys.stderr); return False
        except Exception as e:
            print(f"전송 오류: {str(e)[:60]}", file=sys.stderr); return False
    return True


if __name__ == "__main__":
    body = sys.stdin.read().strip()
    if not body or "변화 없음" in body:
        print("변화 없음 — 전송 생략")
        sys.exit(0)
    title = sys.argv[1] if len(sys.argv) > 1 else "📊 종목 감시"
    msg = f"<b>{title}</b>\n<pre>" + body.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
    print("전송 완료" if send(msg) else "전송 실패")
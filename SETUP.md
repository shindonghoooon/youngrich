# 텔레그램 알림 설정

3단계, 5분이면 끝난다.

## 1. 봇 만들기

텔레그램에서 **@BotFather** 검색 → 대화 시작

```
/newbot
→ 봇 이름 입력 (예: 종목감시)
→ 사용자명 입력 (예: my_stock_watch_bot, 반드시 bot 으로 끝나야 함)
```

토큰이 나온다. 이렇게 생겼다:
```
7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
**이게 TELEGRAM_BOT_TOKEN 이다. 노출되면 안 된다.**

## 2. chat_id 확인

만든 봇과 대화를 시작한다 (아무 메시지나 하나 보낸다. `/start` 등).

그다음 브라우저에서 아래 주소를 연다. `<토큰>` 자리에 1단계 토큰을 넣는다.

```
https://api.telegram.org/bot<토큰>/getUpdates
```

응답에서 `"chat":{"id":123456789` 부분의 숫자가 **TELEGRAM_CHAT_ID** 다.

> 메시지를 안 보냈으면 `"result":[]` 로 빈 값이 나온다. 봇에게 먼저 말을 걸어야 한다.

## 3. GitHub Secrets 등록

리포지토리 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 1단계 토큰 |
| `TELEGRAM_CHAT_ID` | 2단계 숫자 |

## 4. 테스트

**Actions** 탭 → `daily-watch` → **Run workflow** 로 수동 실행.

정상이면 텔레그램에 이런 메시지가 온다.

```
📊 종목 감시

[2026-08-29] 확인 필요 2건

── A Sterling Infrastructure (STRL)
   ◆ 무효화선 근접 (+0.5%)
   추적: book-to-burn / E-Infra 조정 영업이익률 / ...
```

## 동작 규칙

- **평일 오전 7시(KST)** 자동 실행
- **변화가 있을 때만** 전송. 없으면 아무것도 안 온다
- **X등급은 감시 제외** (회피 판정한 종목)
- 메시지가 길면 자동 분할 전송

## 알림 조건

| 조건 | 표시 |
|---|---|
| 무효화선(3개월 저점) 이탈 | ■ |
| 무효화선 5% 이내 근접 | ◆ |
| 5일 등락 ±15% 이상 | ▲▼ |
| 52주 신고가·신저가 | ★ |
| 데이터 신선도 이상 | ⚠ |

조건을 바꾸려면 `tools/watch.py` 의 `check()` 함수를 수정한다.

## 텔레그램 없이 쓰려면

Secrets를 등록하지 않으면 전송 단계를 건너뛴다.
대신 **GitHub Issue**가 자동 생성되므로 그것으로도 확인 가능하다.

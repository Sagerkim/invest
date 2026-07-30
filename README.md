# kofia-daily

금융투자협회 FreeSIS에서 **투자자예탁금 / 신용거래융자 / 예탁증권담보융자**를 매일 아침 자동 수집해
텔레그램으로 요약을 보내고, 웹 대시보드에 추이를 그린다.

- 실행: GitHub Actions (평일 07:30 KST, `.github/workflows/daily.yml`)
- 대시보드: GitHub Pages → `docs/`
- 데이터: `docs/data/latest.json`, `docs/data/history.json`

## 최초 설정

1. **Secrets** — 저장소 `Settings > Secrets and variables > Actions > Secrets`
   - `TELEGRAM_BOT_TOKEN` : BotFather가 준 토큰
   - `TELEGRAM_CHAT_ID` : 내 대화방 번호
2. **Variables** — 같은 화면의 `Variables` 탭
   - `DASHBOARD_URL` : `https://<아이디>.github.io/kofia-daily/`
   - `DEBUG` : 응답 원본을 로그로 보고 싶을 때만 `1`
3. **Pages** — `Settings > Pages` → Source `Deploy from a branch` → `main` / `/docs`

## 수동 실행 (데모)

`Actions` 탭 → 왼쪽에서 워크플로 선택 → `Run workflow` 버튼.

## 안 될 때 확인 순서

1. `Actions` 탭에서 마지막 실행이 빨간 X인지 확인하고 로그를 연다.
2. `ds1 비어 있음` 오류 → FreeSIS 화면이 바뀐 것. 브라우저 F12 > Network에서
   `getMetaDataList.do` 요청을 다시 캡처해 `fetch_kofia.py` 의 `SOURCES` payload를 교체한다.
3. 텔레그램만 실패 → 봇 토큰이 살아 있는지, 봇에게 먼저 말을 건 적이 있는지 확인.
   토큰 재발급은 BotFather에서 `/token`.
4. 대시보드가 비어 있음 → `docs/data/history.json` 이 커밋되었는지 확인.

## 구성

| 파일 | 역할 |
|---|---|
| `fetch_kofia.py` | FreeSIS 조회 → 조원 단위로 정리 → JSON 저장 |
| `notify_telegram.py` | 최신값 + 전일 대비 증감을 텔레그램으로 발송 |
| `docs/index.html` | 카드 3종 + 기간별 추이 그래프 |
| `.github/workflows/daily.yml` | 스케줄 실행, 데이터 커밋, 알림 발송 |

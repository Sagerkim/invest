# kofia-daily

금융투자협회 FreeSIS **'한눈에 보는 자본시장'** 페이지에서 **투자자예탁금 / 신용융자 / CMA잔고**를
매일 아침 자동 수집해 텔레그램으로 요약을 보내고, 웹 대시보드에 추이를 그린다.

- 데이터 출처: <https://freesis.kofia.or.kr/stat/main.do> (서버가 값을 HTML에 직접 넣어주는 페이지)
- 실행: GitHub Actions (평일 07:30 KST, `.github/workflows/daily.yml`)
- 대시보드: GitHub Pages → `docs/`
- 데이터: `docs/data/latest.json`, `docs/data/history.json`

## 최초 설정

1. **Secrets** — 저장소 `Settings > Secrets and variables > Actions > Secrets`
   - `TELEGRAM_BOT_TOKEN` : BotFather가 준 토큰
   - `TELEGRAM_CHAT_ID` : 내 대화방 번호
2. **Variables** — 같은 화면의 `Variables` 탭
   - `DASHBOARD_URL` : `https://sagerkim.github.io/invest/`
   - `DEBUG` : 파싱 결과를 로그로 보고 싶을 때만 `1`
3. **Pages** — `Settings > Pages` → Source `Deploy from a branch` → `main` / `/docs`

## 수동 실행 (데모)

`Actions` 탭 → 왼쪽에서 워크플로 선택 → `Run workflow` 버튼.

## 알아둘 점

- **과거 데이터는 쌓이는 방식이다.** 출처 페이지가 '오늘의 값' 하나만 보여주기 때문에,
  실행할 때마다 `history.json`에 하루씩 누적된다. 그래프는 운영 일수만큼 길어진다.
- **기준일**은 보통 전영업일이다. 금투협 수치는 하루 뒤 확정 게시된다.
- 전일 대비 증감은 페이지의 증감란이 비어 있는 경우가 있어, **우리가 쌓은 기록으로 직접 계산**한다.
  따라서 첫 실행 때는 증감이 표시되지 않는다.

## 안 될 때 확인 순서

1. `Actions` 탭에서 마지막 실행 로그를 연다.
2. `필수 지표를 찾지 못했습니다` → 출처 페이지 구조가 바뀐 것.
   `DEBUG=1`로 실행해 파싱 결과를 보고 `fetch_kofia.py` 의 `INDICATORS` / 정규식을 고친다.
3. 텔레그램만 실패 → 봇 토큰이 살아 있는지, 봇에게 먼저 말을 건 적이 있는지 확인.
   토큰 재발급은 BotFather에서 `/token`.
4. 대시보드가 비어 있음 → `docs/data/history.json` 이 커밋되었는지 확인.

## 구성

| 파일 | 역할 |
|---|---|
| `fetch_kofia.py` | FreeSIS 메인 페이지 파싱 → 조원 단위로 정리 → JSON 저장 |
| `notify_telegram.py` | 최신값 + 전일 대비 증감을 텔레그램으로 발송 |
| `docs/index.html` | 카드 3종 + 기간별 추이 그래프 |
| `.github/workflows/daily.yml` | 스케줄 실행, 데이터 커밋, 알림 발송 |

"""금융투자협회 FreeSIS '한눈에 보는 자본시장'에서 증시 수급지표를 수집한다.

수집 대상 (https://freesis.kofia.or.kr/stat/main.do 의 주요지표 영역)
  - 투자자예탁금 : 투자자가 증권계좌에 넣어둔 대기 자금 (사려는 힘)
  - 신용융자     : 돈을 빌려 주식을 산 금액 (빚투 규모)
  - CMA잔고      : 단기 자금 대기처. 예탁금과 함께 시장 유동성을 본다.

이 페이지는 서버가 값을 HTML에 직접 넣어 내려주므로 브라우저 없이 그대로 읽을 수 있다.
결과는 docs/data/latest.json, docs/data/history.json 으로 저장한다.
docs/ 아래에 두는 이유는 GitHub Pages가 그 폴더를 그대로 웹에 공개하기 때문이다.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SOURCE_URL = "https://freesis.kofia.or.kr/stat/main.do"
KST = timezone(timedelta(hours=9))

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "docs" / "data"
LATEST = DATA_DIR / "latest.json"
HISTORY = DATA_DIR / "history.json"

# 페이지의 지표 코드 -> 저장할 이름, 표시 이름, 원래 단위
INDICATORS = {
    "OS0021": ("deposit", "투자자예탁금", "백만원"),
    "OS0026": ("credit_loan", "신용융자", "백만원"),
    "OS0030": ("cma", "CMA잔고", "백만원"),
}

# 조원으로 환산하기 위한 나눗셈 값
TO_JO = {"백만원": 1_000_000, "억원": 10_000}

DEBUG = os.environ.get("DEBUG") == "1"


def fetch_html() -> str:
    """FreeSIS 메인 페이지를 가져온다. 일시적 실패는 3회까지 재시도한다."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(SOURCE_URL, headers=headers, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 재시도 대상
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"FreeSIS 페이지를 가져오지 못했습니다: {last_error}")


def _resolve_year(month: int, day: int, today) -> str:
    """페이지는 '07/29'처럼 연도 없이 준다. 오늘 기준으로 연도를 붙인다."""
    year = today.year
    if month > today.month + 1:  # 12월 값을 1월에 보는 경우
        year -= 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse(html: str) -> dict:
    """지표 블록을 잘라 코드별 값을 뽑는다."""
    today = datetime.now(KST).date()
    found: dict[str, dict] = {}

    # 지표 하나가 <li>...</li> 블록 하나에 들어있다.
    for block in html.split("<li>"):
        code_match = re.search(r"clickJisuMenu\('([A-Z0-9]+)'\)", block)
        if not code_match or code_match.group(1) not in INDICATORS:
            continue

        key, label, unit = INDICATORS[code_match.group(1)]

        value_match = re.search(r'class="num1">([^<]*)<', block)
        date_match = re.search(r'class="date">\s*(\d{1,2})/(\d{1,2})\s*<', block)
        pct_match = re.search(r'class="num3[^"]*">([^<]*)<', block)
        if not value_match or not date_match:
            continue

        raw = value_match.group(1).strip().replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue

        found[key] = {
            "label": label,
            "date": _resolve_year(int(date_match.group(1)), int(date_match.group(2)), today),
            "value": round(value / TO_JO[unit], 3),  # 조원으로 환산
            "pct": (pct_match.group(1).strip() if pct_match else ""),
        }

    if DEBUG:
        print(f"[debug] 파싱 결과: {json.dumps(found, ensure_ascii=False)}")

    missing = {"deposit", "credit_loan"} - set(found)
    if missing:
        raise RuntimeError(
            f"필수 지표를 찾지 못했습니다: {sorted(missing)}. "
            "FreeSIS 메인 화면 구조가 바뀌었을 수 있습니다. DEBUG=1 로 다시 실행해 보세요."
        )
    return found


def merge_history(found: dict) -> list[dict]:
    """기존 기록에 이번 수집분을 날짜 기준으로 합친다."""
    existing: dict[str, dict] = {}
    if HISTORY.exists():
        for row in json.loads(HISTORY.read_text(encoding="utf-8")):
            existing[row["date"]] = row

    for key, item in found.items():
        row = existing.setdefault(item["date"], {"date": item["date"]})
        row[key] = item["value"]

    return [existing[day] for day in sorted(existing)]


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    found = parse(fetch_html())
    history = merge_history(found)

    # 전일 대비 증감은 우리가 쌓은 기록으로 직접 계산한다.
    # (페이지의 증감란은 값이 비어 있는 경우가 있어 신뢰하지 않는다.)
    metrics: dict[str, dict] = {}
    for key, item in found.items():
        points = [row for row in history if row.get(key) is not None]
        change = None
        prev_date = None
        if len(points) > 1:
            change = round(points[-1][key] - points[-2][key], 3)
            prev_date = points[-2]["date"]
        metrics[key] = {
            "label": item["label"],
            "date": item["date"],
            "value": item["value"],
            "change": change,
            "prev_date": prev_date,
            "pct": item["pct"],
        }

    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    LATEST.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
                "unit": "조원",
                "source": SOURCE_URL,
                "metrics": metrics,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    print(f"수집 완료: 기록 {len(history)}일치")
    for item in metrics.values():
        delta = "" if item["change"] is None else f" ({item['change']:+.2f}조)"
        print(f"  {item['label']}: {item['value']:,.2f}조원{delta}  [{item['date']}]")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

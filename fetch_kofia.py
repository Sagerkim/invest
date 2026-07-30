"""금융투자협회 FreeSIS에서 증시 수급지표를 수집한다.

수집 대상
  - 투자자예탁금       (투자자가 증권계좌에 넣어둔 대기 자금)
  - 신용거래융자       (돈을 빌려 주식을 산 금액)
  - 예탁증권담보융자   (보유 주식을 담보로 빌린 금액)

결과는 docs/data/latest.json, docs/data/history.json 으로 저장한다.
docs/ 아래에 두는 이유는 GitHub Pages가 그 폴더를 그대로 웹에 공개하기 때문이다.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ENDPOINT = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
KST = timezone(timedelta(hours=9))

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "docs" / "data"
LATEST = DATA_DIR / "latest.json"
HISTORY = DATA_DIR / "history.json"

# 조회 기간: 오늘로부터 LOOKBACK_DAYS 전까지. 넉넉히 잡아도 응답이 작아서 부담 없다.
LOOKBACK_DAYS = 400

# ---------------------------------------------------------------------------
# FreeSIS 요청 정의
#
# 아래 dmSearch 내용은 브라우저 개발자도구(F12 > Network)에서 캡처한 실제 요청을
# 그대로 옮긴 것이다. 사이트 화면이 개편되면 이 부분만 다시 캡처해 바꾸면 된다.
# {START} / {END} 자리에 조회 시작일·종료일(YYYYMMDD)이 채워진다.
# ---------------------------------------------------------------------------
SOURCES = [
    {
        "key": "credit",
        "label": "신용공여",
        "payload": {
            "dmSearch": {
                "tmpV40": "1",
                "tmpV41": "1",
                "tmpV1": "1",
                "tmpV45": "s",
                "tmpV46": "d",
                "tmpV3": "{START}",
                "tmpV4": "{END}",
                "OBJ_NM": "STATSCU0100000070BO",
            }
        },
    },
    {
        "key": "deposit",
        "label": "증시자금추이",
        "payload": {
            "dmSearch": {
                "tmpV40": "1",
                "tmpV41": "1",
                "tmpV1": "1",
                "tmpV45": "s",
                "tmpV46": "d",
                "tmpV3": "{START}",
                "tmpV4": "{END}",
                "OBJ_NM": "STATSCU0100000010BO",
            }
        },
    },
]

# ds1 응답의 컬럼명 -> 우리가 쓸 지표 이름.
# 첫 실행에서 실제 컬럼명을 로그로 확인한 뒤 채운다. (DEBUG=1 로 실행하면 원본이 찍힌다)
COLUMN_MAP = {
    "투자자예탁금": "deposit",
    "신용거래융자": "credit_loan",
    "예탁증권담보융자": "collateral_loan",
}

# FreeSIS 금액 단위는 억원이다. 화면에는 조원으로 보여준다.
EOK_PER_JO = 10_000

METRIC_LABELS = {
    "deposit": "투자자예탁금",
    "credit_loan": "신용거래융자",
    "collateral_loan": "예탁증권담보융자",
}

DEBUG = os.environ.get("DEBUG") == "1"


def _post(payload: dict) -> dict:
    """FreeSIS에 조회 요청을 보낸다. 일시적 실패는 3회까지 재시도한다."""
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(ENDPOINT, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 재시도 대상
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"FreeSIS 요청 실패: {last_error}")


def _to_number(value) -> float | None:
    """'1,234' 같은 문자열을 숫자로 바꾼다. 값이 없으면 None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _find_date(row: dict) -> str | None:
    """행에서 날짜처럼 생긴 값을 찾아 YYYY-MM-DD 로 돌려준다."""
    for value in row.values():
        text = str(value or "").strip()
        digits = text.replace("-", "").replace("/", "").replace(".", "")
        if len(digits) == 8 and digits.isdigit():
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return None


def collect() -> dict[str, dict[str, float]]:
    """날짜별 지표를 모아 {'2026-07-29': {'deposit': 58.2, ...}} 형태로 돌려준다."""
    end = datetime.now(KST).date()
    start = end - timedelta(days=LOOKBACK_DAYS)

    by_date: dict[str, dict[str, float]] = {}

    for source in SOURCES:
        payload = json.loads(
            json.dumps(source["payload"])
            .replace("{START}", start.strftime("%Y%m%d"))
            .replace("{END}", end.strftime("%Y%m%d"))
        )
        result = _post(payload)
        rows = result.get("ds1") or []

        if DEBUG:
            print(f"[debug] {source['label']} unit={result.get('unit')!r}")
            print(f"[debug] {source['label']} rows={len(rows)}")
            if rows:
                print(f"[debug] {source['label']} 첫 행: {json.dumps(rows[0], ensure_ascii=False)}")

        if not rows:
            raise RuntimeError(
                f"{source['label']} 응답에 데이터가 없습니다(ds1 비어 있음). "
                "FreeSIS 화면에서 요청을 다시 캡처해 SOURCES 의 payload 를 갱신하세요."
            )

        for row in rows:
            day = _find_date(row)
            if not day:
                continue
            bucket = by_date.setdefault(day, {})
            for column, value in row.items():
                metric = COLUMN_MAP.get(column.strip())
                if metric is None:
                    continue
                number = _to_number(value)
                if number is None:
                    continue
                bucket[metric] = round(number / EOK_PER_JO, 3)  # 억원 -> 조원

    if not by_date:
        raise RuntimeError(
            "날짜를 인식하지 못했습니다. DEBUG=1 로 실행해 첫 행의 컬럼명을 확인한 뒤 "
            "COLUMN_MAP 을 실제 컬럼명에 맞게 고치세요."
        )
    return by_date


def merge_history(new_rows: dict[str, dict[str, float]]) -> list[dict]:
    """기존 기록에 이번 수집분을 덮어쓰며 합친다. 날짜 오름차순으로 정렬해 돌려준다."""
    existing: dict[str, dict] = {}
    if HISTORY.exists():
        for row in json.loads(HISTORY.read_text(encoding="utf-8")):
            existing[row["date"]] = row

    for day, metrics in new_rows.items():
        merged = existing.get(day, {"date": day})
        merged.update(metrics)
        existing[day] = merged

    return [existing[day] for day in sorted(existing)]


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    history = merge_history(collect())
    if not history:
        print("수집 결과가 비었습니다.", file=sys.stderr)
        return 1

    # 지표별로 값이 실제로 있는 마지막 날짜를 찾는다.
    # (예탁금과 신용융자의 최신 반영일이 하루씩 다를 수 있어 지표별로 따로 잡는다.)
    latest: dict[str, dict] = {}
    for metric, label in METRIC_LABELS.items():
        points = [row for row in history if row.get(metric) is not None]
        if not points:
            continue
        current, previous = points[-1], (points[-2] if len(points) > 1 else None)
        latest[metric] = {
            "label": label,
            "date": current["date"],
            "value": current[metric],
            "change": (
                round(current[metric] - previous[metric], 3) if previous else None
            ),
            "prev_date": previous["date"] if previous else None,
        }

    HISTORY.write_text(
        json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    LATEST.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
                "unit": "조원",
                "metrics": latest,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    print(f"수집 완료: {len(history)}일치, 최신 지표 {len(latest)}종")
    for metric in latest.values():
        print(f"  {metric['label']}: {metric['value']}조 ({metric['date']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

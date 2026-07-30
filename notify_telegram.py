"""수집한 지표를 텔레그램으로 보낸다.

필요한 환경변수 (GitHub 저장소 Settings > Secrets 에 등록해 둔 값)
  TELEGRAM_BOT_TOKEN : BotFather 가 발급한 봇 토큰
  TELEGRAM_CHAT_ID   : 내 대화방 번호
  DASHBOARD_URL      : (선택) 대시보드 주소. 있으면 메시지 끝에 링크로 붙인다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

LATEST = Path(__file__).parent / "docs" / "data" / "latest.json"

# 지표를 보여줄 순서. 요청하신 두 지표를 위에 둔다.
ORDER = ["deposit", "credit_loan", "cma"]


def _format_change(change: float | None) -> str:
    """전일 대비 증감을 화살표와 함께 만든다."""
    if change is None:
        return ""
    if change > 0:
        return f"  🔺 +{change:,.2f}조"
    if change < 0:
        return f"  🔻 {change:,.2f}조"
    return "  ― 보합"


def build_message(latest: dict) -> str:
    metrics = latest.get("metrics", {})
    lines = ["📊 *오늘의 증시 수급*", ""]

    for key in ORDER:
        metric = metrics.get(key)
        if not metric:
            continue
        lines.append(f"*{metric['label']}*")
        lines.append(f"  {metric['value']:,.2f}조원{_format_change(metric.get('change'))}")
        lines.append(f"  _{metric['date']} 기준_")
        lines.append("")

    lines.append("💡 예탁금이 늘면 대기 매수자금이 쌓이는 것, 신용융자가 늘면 빚투가 늘어난 것입니다.")

    url = os.environ.get("DASHBOARD_URL", "").strip()
    if url:
        lines.append("")
        lines.append(f"[📈 추이 그래프 보기]({url})")

    return "\n".join(lines)


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print(
            "TELEGRAM_BOT_TOKEN 과 TELEGRAM_CHAT_ID 가 필요합니다. "
            "저장소 Settings > Secrets and variables > Actions 에 등록하세요.",
            file=sys.stderr,
        )
        return 1

    if not LATEST.exists():
        print("latest.json 이 없습니다. fetch_kofia.py 를 먼저 실행하세요.", file=sys.stderr)
        return 1

    text = build_message(json.loads(LATEST.read_text(encoding="utf-8")))

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"텔레그램 전송 실패 {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    print("텔레그램 전송 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

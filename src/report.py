import os

import requests


def send(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    resp.raise_for_status()
    return True


def format_product_drops(store: str, drops: list[dict]) -> str:
    lines = [f"<b>📦 {store}</b> — {len(drops)} bajada(s)"]
    for d in drops:
        lines.append(
            f'  ↓ {d["change_pct"]}%  {d["name"][:70]}\n'
            f'  ${d["prev_price"]:.0f} → ${d["price"]:.0f}\n'
            f'  {d["url"]}'
        )
    return "\n".join(lines)


def format_flight_alerts(alerts: list[dict]) -> str:
    lines = [f"<b>✈️ Vuelo(s)</b> — {len(alerts)} alerta(s)"]
    for a in alerts:
        carrier = f" ({a['carrier']})" if a.get("carrier") else ""
        lines.append(
            f'  {a["origin"]}→{a["destination"]} {a["departure_date"]}\n'
            f'  ${a["price"]:,.0f}{carrier} — {a["reason"]}\n'
            f'  {a.get("url", "")}'
        )
    return "\n".join(lines)

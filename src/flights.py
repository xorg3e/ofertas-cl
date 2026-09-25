import re
import time
from datetime import date, timedelta

from .scrapers.browser import launch

PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+)\s*CLP")
NON_BREAKING = "\xa0"


def _dates_for(cfg: dict, route: dict) -> list[str]:
    fixed = route.get("dates")
    if fixed:
        return sorted(set(fixed))
    lo = int(cfg.get("days_ahead_min", 7))
    hi = int(cfg.get("days_ahead_max", 60))
    offsets = sorted({lo, (lo + hi) // 2, hi})
    today = date.today()
    return [(today + timedelta(days=d)).isoformat() for d in offsets]


def _url(origin: str, dest: str, dep: str, ret: str | None = None) -> str:
    q = f"Flights from {origin} to {dest} on {dep}"
    if ret:
        q += f" through {ret}"
    return (
        "https://www.google.com/travel/flights"
        f"?q={q.replace(' ', '+')}&curr=CLP&hl=es&gl=CL"
    )


def _parse_prices(page) -> list[float]:
    text = page.locator("body").inner_text().replace(NON_BREAKING, " ")
    prices = []
    for m in PRICE_RE.finditer(text):
        value = float(m.group(1).replace(".", ""))
        if 10_000 <= value <= 20_000_000:
            prices.append(value)
    return prices


def _parse_carrier(page) -> str:
    text = page.locator("body").inner_text()
    for name in (
        "LATAM", "Sky Airline", "SKY", "GOL", "G3", "JetSMART", "AMERICAN",
        "American Airlines", "Avianca", "Copa", "Iberia", "Air France",
        "KLM", "United", "Delta",
    ):
        if name in text:
            return name
    return ""


def search_all(cfg: dict) -> list[dict]:
    """Scrapea Google Flights (ida, 1 adulto, CLP) para las rutas configuradas."""
    if not cfg.get("enabled"):
        return []
    results: list[dict] = []
    session, browser, context = launch()
    page = context.new_page()
    try:
        for route in cfg.get("routes", []):
            ret = route.get("return_date")
            for dep in _dates_for(cfg, route):
                search_url = _url(route["origin"], route["destination"], dep, ret)
                page.goto(search_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                try:
                    page.wait_for_selector("text=CLP", timeout=25000)
                except Exception:
                    continue
                page.wait_for_timeout(2500)
                prices = _parse_prices(page)
                if not prices:
                    continue
                carrier = _parse_carrier(page)
                for p in prices:
                    results.append(
                        {
                            "origin": route["origin"],
                            "destination": route["destination"],
                            "departure_date": dep,
                            "price": p,
                            "carrier": carrier,
                            "stops": 0,
                            "url": search_url,
                        }
                    )
    finally:
        context.close()
        browser.close()
        session.stop()
    return results


def _best_per_key(rows: list[dict]) -> dict[tuple, dict]:
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["origin"], r["destination"], r["departure_date"])
        if key not in best or r["price"] < best[key]["price"]:
            best[key] = r
    return best


def detect_flight_errors(
    current: list[dict],
    history: list[tuple],  # (origin, dest, departure_date, price, ts)
    threshold_pct: float,
    percentile: int,
    price_min: float | None = None,
    price_max: float | None = None,
) -> list[dict]:
    """Alerta si el precio actual está en el objetivo, < percentil histórico o cayó > umbral vs 24h."""
    cutoff = time.time() - 86400
    hist_prices: dict[tuple, list[float]] = {}
    recent_prices: dict[tuple, list[float]] = {}
    for origin, dest, dep, price, ts in history:
        key = (origin, dest, dep)
        hist_prices.setdefault(key, []).append(price)
        if ts >= cutoff:
            recent_prices.setdefault(key, []).append(price)

    alerts = []
    for key, cur in _best_per_key(current).items():
        reason = None
        if price_max is not None and cur["price"] <= price_max:
            if price_min is not None and cur["price"] < price_min:
                reason = f"precio excelente ${cur['price']:,.0f} (< objetivo ${price_min:,.0f})"
            else:
                reason = f"en rango objetivo ${cur['price']:,.0f} (≤${price_max:,.0f})"
        hist = hist_prices.get(key) or []
        if len(hist) >= 8:
            ordered = sorted(hist)
            idx = max(0, min(len(ordered) - 1, round(percentile / 100 * len(ordered)) - 1))
            threshold_price = ordered[idx]
            if cur["price"] <= threshold_price:
                piece = f"P{percentile} histórico (${threshold_price:,.0f})"
                reason = f"{reason} | {piece}" if reason else piece
        recent = recent_prices.get(key) or []
        if recent:
            best_recent = min(recent)
            if best_recent > 0:
                change = (cur["price"] - best_recent) / best_recent * 100
                if change <= -threshold_pct:
                    piece = f"caída {change:.0f}% vs 24h (${best_recent:,.0f})"
                    reason = f"{reason} | {piece}" if reason else piece
        if reason:
            alerts.append({**cur, "reason": reason})
    return alerts

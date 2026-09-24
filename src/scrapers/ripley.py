import re
from urllib.parse import urlparse

from .browser import launch

PRICE_RE = re.compile(r"\$\s*([\d.]+)")
PID_RE = re.compile(r"(?:mpm\d+|\d{9,})(?:p)?$", re.I)


def _to_clp(raw: str) -> float | None:
    digits = raw.replace(".", "").replace(" ", "")
    if not digits.isdigit():
        return None
    value = float(digits)
    return value if 100 <= value <= 20_000_000 else None


def _product_id(url: str) -> str | None:
    path = urlparse(url).path.rstrip("/")
    last = path.split("/")[-1]
    if not last:
        return None
    # un solo segmento = página de producto (categorías tienen /a/b/c)
    if "/" in path.strip("/"):
        return None
    m = PID_RE.search(last)
    if m:
        return m.group(0)
    return None


def _from_links(page) -> list[dict]:
    raw = page.locator("a").evaluate_all(
        """els => els
             .filter(e => /\\$\\s*[\\d.]+/.test(e.innerText || ''))
             .map(e => ({
                href: e.href || '',
                text: e.innerText || '',
                imgAlt: ((e.querySelector('img') || {}).alt) || ''
             }))"""
    )
    products: dict[str, dict] = {}
    for item in raw:
        href = (item.get("href") or "").split("?")[0]
        if not href.startswith("http"):
            continue
        pid = _product_id(href)
        if not pid:
            continue
        text = item.get("text") or ""
        prices = [p for p in (_to_clp(m) for m in PRICE_RE.findall(text)) if p]
        if not prices:
            continue
        name = (item.get("imgAlt") or "").strip()
        if not name:
            lines = [
                ln.strip()
                for ln in text.split("\n")
                if ln.strip()
                and not ln.strip().startswith("$")
                and not re.match(r"^-?\d+%", ln.strip())
            ]
            name = (lines[-1] if lines else "")[:140]
        if not name:
            continue
        current = min(prices)
        original = max(prices) if max(prices) > current else None
        if pid not in products:
            products[pid] = {
                "product_id": pid,
                "name": name,
                "url": href,
                "price": current,
                "original_price": original,
            }
    return list(products.values())


def scrape(store_config: dict) -> list[dict]:
    import time

    session, browser, context = launch()
    page = context.new_page()
    found: dict[str, dict] = {}
    try:
        for i, url in enumerate(store_config.get("urls", [])):
            if i:
                time.sleep(0.6)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2200)
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(900)
                for p in _from_links(page):
                    found[p["product_id"]] = p
            except Exception:
                continue
    finally:
        context.close()
        browser.close()
        session.stop()
    return list(found.values())

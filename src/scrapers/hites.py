import re
from urllib.parse import urlparse

from .browser import launch

PRICE_RE = re.compile(r"\$\s*([\d.]+)")


def _to_clp(raw: str) -> float | None:
    digits = raw.replace(".", "").replace(" ", "")
    if not digits.isdigit():
        return None
    value = float(digits)
    return value if 100 <= value <= 20_000_000 else None


def _product_id(url: str, data_pid: str | None) -> str | None:
    if data_pid:
        return str(data_pid)
    path = urlparse(url).path.rstrip("/")
    last = path.split("/")[-1]
    if not last.endswith(".html"):
        return None
    m = re.search(r"(\d{6,})\.html$", last)
    return m.group(1) if m else last[:80]


def _from_tiles(page) -> list[dict]:
    raw = page.locator("[data-pid]").evaluate_all(
        """els => els.map(e => ({
             pid: e.getAttribute('data-pid') || '',
             text: e.innerText || '',
             href: (e.querySelector('a[href*=".html"]') || {}).href || '',
             name: ((e.querySelector('[class*=product-name]') || {}).innerText || '')
                    || (((e.querySelector('img') || {}).alt) || '')
           }))"""
    )
    products: dict[str, dict] = {}
    for item in raw:
        href = (item.get("href") or "").split("?")[0]
        if not href or ".html" not in href:
            continue
        prices = [p for p in (_to_clp(m) for m in PRICE_RE.findall(item.get("text") or "")) if p]
        if not prices:
            continue
        name = (item.get("name") or "").strip()[:140]
        if not name:
            continue
        pid = _product_id(href, item.get("pid"))
        if not pid or pid in products:
            continue
        current = min(prices)
        original = max(prices) if max(prices) > current else None
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
                page.wait_for_timeout(2500)
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(900)
                for p in _from_tiles(page):
                    found[p["product_id"]] = p
            except Exception:
                continue
    finally:
        context.close()
        browser.close()
        session.stop()
    return list(found.values())

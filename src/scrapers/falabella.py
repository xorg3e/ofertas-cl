import re
from urllib.parse import urlparse

from .browser import launch

PRICE_RE = re.compile(r"\$\s*([\d.]+)")

SKIP_NAMES = {
    "envío gratis", "envio gratis", "llega gratis hoy",
    "agregar al carro", "comprar", "más información",
    "vista previa", "promocionado", "3 cuotas sin interés",
    "cuotas sin interés", "cuotas sin interes",
}


def _to_clp(raw: str) -> float | None:
    digits = raw.replace(".", "").replace(" ", "")
    if not digits.isdigit():
        return None
    value = float(digits)
    return value if value > 0 else None


def _product_id(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if "/product/" in path:
        segs = path.split("/")
        for seg in reversed(segs):
            if seg.isdigit() or re.fullmatch(r"prod\d+", seg):
                return seg
    return path or url


def _good(s: str) -> bool:
    s = (s or "").strip()
    if not s or s.lower() in SKIP_NAMES or s.startswith("$"):
        return False
    if re.match(r"^-?\d+%$", s) or re.fullmatch(r"\d+", s):
        return False
    return len(s) >= 8


def _extract_from_pods(page) -> list[dict]:
    """Tarjetas de producto Falabella (pod-link clásico o ProductLink nuevo)."""
    items = page.locator("a.pod-link")
    if items.count() == 0:
        items = page.locator('a[href*="/product/"]')
    products: dict[str, dict] = {}
    for i in range(items.count()):
        pod = items.nth(i)
        try:
            href = pod.get_attribute("href") or ""
            if "/product/" not in href:
                continue
            if href.startswith("/"):
                href = "https://www.falabella.com" + href
            text = pod.inner_text(timeout=1000)
            prices = [_to_clp(m) for m in PRICE_RE.findall(text)]
            prices = [p for p in prices if p]
            if not prices:
                prices = [
                    _to_clp(m)
                    for m in PRICE_RE.findall(
                        pod.evaluate(
                            "el => (el.closest('[class*=pod]') || el.closest('[class*=Container]') || el.parentElement)?.innerText || ''"
                        )
                    )
                ]
                prices = [p for p in prices if p]
            if not prices:
                continue
            lines = [ln.strip() for ln in text.split("\n") if _good(ln.strip())]
            name = max(lines, key=len) if lines else ""
            if not name:
                img = pod.locator("img").first
                alt = (img.get_attribute("alt") or "").strip() if img.count() else ""
                if _good(alt) and len(alt.split()) >= 2:
                    name = alt
            # formato "MARCA|Nombre" → solo Nombre
            if "|" in name:
                name = name.split("|")[-1].strip()
            name = name[:140].strip()
            if not name:
                continue
            pid = _product_id(href)
            if pid not in products:
                current = min(prices)
                original = max(prices) if max(prices) > current else None
                products[pid] = {
                    "product_id": pid,
                    "name": name,
                    "url": href.split("?")[0],
                    "price": current,
                    "original_price": original,
                }
        except Exception:
            continue
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
                page.wait_for_selector('a[href*="/product/"], a.pod-link', timeout=10000)
                page.wait_for_timeout(1500)
                for p in _extract_from_pods(page):
                    found[p["product_id"]] = p
            except Exception:
                continue
    finally:
        context.close()
        browser.close()
        session.stop()
    return list(found.values())

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


def _product_id(url: str) -> str | None:
    path = urlparse(url).path.rstrip("/")
    if "/" in path.strip("/") or not path.endswith(".html"):
        return None
    stem = path.split("/")[-1][: -len(".html")]
    m = re.search(r"(\d{6,})$", stem)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Z0-9]{8,}", stem.split("-")[-1] or ""):
        return stem.split("-")[-1]
    return stem[:80] or None


def _from_links(page) -> list[dict]:
    raw = page.locator("a").evaluate_all(
        """els => els
             .filter(e => {
                const h = (e.getAttribute('href') || '').split('?')[0];
                // un solo segmento en raíz terminado en .html = ficha de producto
                if (!/^\\/[^\\/]+\\.html$/.test(h) && !/^https?:\\/\\/[^/]+\\/[^/]+\\.html$/.test(e.href || '')) {
                  const path = (e.getAttribute('href') || '').split('?')[0];
                  if (!(path.endsWith('.html') && path.split('/').filter(Boolean).length === 1)) return false;
                }
                return /\\$\\s*[\\d.]+/.test(e.innerText || '');
             })
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
        prices = [p for p in (_to_clp(m) for m in PRICE_RE.findall(item.get("text") or "")) if p]
        if not prices:
            continue
        BAD_EXACT = {
            "imagen de producto", "producto", "ver producto", "nuevo",
            "vista previa", "agregar al carro", "promocionado",
            "agregar a favoritos",
        }
        lines = [
            ln.strip()
            for ln in (item.get("text") or "").split("\n")
            if ln.strip()
            and not ln.strip().startswith("$")
            and not re.match(r"^-?\d+%$", ln.strip())
            and not re.match(r"^\d+$", ln.strip())
            and ln.strip().lower() not in BAD_EXACT
        ]
        # el nombre real suele ser la línea más larga (marca suelta = muy corta)
        name = max(lines, key=len) if lines else ""
        if not name:
            # fallback: slug del URL sin id final
            slug = href.split("/")[-1][: -len(".html")] if href.endswith(".html") else ""
            slug = re.sub(r"[-_]?\d{6,}$", "", href.split("/")[-1].replace(".html", ""))
            name = slug.replace("-", " ").strip()[:140]
        if len(name) < 4:
            continue
        if pid not in products:
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
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(900)
                items = _from_links(page)
                if not items:
                    print(
                        f"  [debug paris] 0 productos status="
                        f"{resp.status if resp else '?'} title="
                        f"{page.title()[:80]!r} {url}",
                        flush=True,
                    )
                for p in items:
                    found[p["product_id"]] = p
            except Exception as exc:
                print(f"  [debug paris] {type(exc).__name__} {url}", flush=True)
                continue
    finally:
        context.close()
        browser.close()
        session.stop()
    return list(found.values())

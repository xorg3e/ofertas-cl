import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.scrapers.browser import launch

CASES = {
    "ripley": [
        "https://simple.ripley.cl/tecno/celulares",
        "https://simple.ripley.cl/dormitorio/camas",
    ],
    "paris": [
        "https://www.paris.cl/mujer/moda/",
        "https://www.paris.cl/electro/",
    ],
}

EXTRA_HEADERS = {
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
    "sec-ch-ua": '"Chromium";v="126", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def price_count(page, store: str) -> int:
    if store == "paris":
        return page.locator("a").evaluate_all(
            "els => els.filter(e => (e.innerText || '').includes('$')).length"
        )
    return page.locator("a").evaluate_all(
        "els => els.filter(e => (e.innerText || '').includes('$')).length"
    )


def probe(page, store: str, url: str, label: str) -> None:
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        status = resp.status if resp else 0
        title = page.title()[:50]
        n = price_count(page, store) if status == 200 else 0
        print(f"  {label}: status={status} prices={n} title={title!r}", flush=True)
    except Exception as exc:
        print(f"  {label}: {type(exc).__name__}", flush=True)


session, browser, context = launch()
try:
    for store, urls in CASES.items():
        print(f"==== {store}", flush=True)
        page = context.new_page()

        # A: baseline
        print(" [A] baseline", flush=True)
        for url in urls:
            probe(page, store, url, "A")
            time.sleep(0.5)

        # B: esperar 15s (reto JS) + reload
        print(" [B] wait 15s + reload", flush=True)
        for url in urls:
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                status = resp.status if resp else 0
                page.wait_for_timeout(15000)
                if status != 200 or "momento" in page.title().lower():
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    status = resp.status if resp else 0
                    page.wait_for_timeout(5000)
                n = price_count(page, store) if status == 200 else 0
                print(
                    f"  B: status={status} prices={n} title={page.title()[:50]!r}",
                    flush=True,
                )
            except Exception as exc:
                print(f"  B: {type(exc).__name__}", flush=True)
            time.sleep(0.5)

        # C: headers extra + cookie previa de google + esperas largas
        print(" [C] extra headers + google referrer", flush=True)
        page.close()
        page = context.new_page()
        page.set_extra_http_headers(EXTRA_HEADERS)
        try:
            page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
        except Exception:
            pass
        for url in urls:
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                status = resp.status if resp else 0
                page.wait_for_timeout(8000)
                n = price_count(page, store) if status == 200 else 0
                print(
                    f"  C: status={status} prices={n} title={page.title()[:50]!r}",
                    flush=True,
                )
            except Exception as exc:
                print(f"  C: {type(exc).__name__}", flush=True)
            time.sleep(0.5)

        page.close()
finally:
    context.close()
    browser.close()
    session.stop()

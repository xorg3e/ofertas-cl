import sys
import time

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.scrapers.browser import launch

with open("config.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

session, browser, context = launch()
page = context.new_page()
total_ok = total_bad = 0
try:
    for store, scfg in cfg["stores"].items():
        print("====", store)
        for url in scfg["urls"]:
            try:
                r = page.goto(url, wait_until="domcontentloaded", timeout=40000)
                status = r.status if r else 0
                n = 0
                if status == 200:
                    if store == "falabella":
                        try:
                            page.wait_for_selector(
                                'a[href*="/product/"]', timeout=10000
                            )
                        except Exception:
                            pass
                        n = page.locator('a[href*="/product/"]').count()
                    else:
                        page.wait_for_timeout(2200)
                        page.evaluate("window.scrollBy(0, 600)")
                        page.wait_for_timeout(400)
                        n = page.locator("a").evaluate_all(
                            "els => els.filter(e => (e.innerText || '').includes('$')).length"
                        )
                ok = status == 200 and n > 0
                total_ok += int(ok)
                total_bad += int(not ok)
                mark = "OK  " if ok else "FAIL"
                print(f"  {mark} {status} prices={n:3d} {url}", flush=True)
                if status == 429:
                    print("  [429] waiting 180s...", flush=True)
                    time.sleep(180)
                else:
                    time.sleep(0.7)
            except Exception as e:
                total_bad += 1
                print(f"  ERR {type(e).__name__} {url}", flush=True)
finally:
    context.close()
    browser.close()
    session.stop()

print(f"--- total OK={total_ok} FAIL={total_bad}")

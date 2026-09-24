from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_stealth = Stealth()


def launch():
    """Playwright con evasiones stealth (necesario contra WAF de Ripley)."""
    pw_cm = _stealth.use_sync(sync_playwright())
    pw = pw_cm.__enter__()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="es-CL",
        viewport={"width": 1366, "height": 900},
        extra_http_headers={"Accept-Language": "es-CL,es;q=0.9"},
    )

    class _Session:
        def __init__(self, cm, pw, browser, context):
            self._cm = cm
            self.pw = pw
            self.browser = browser
            self.context = context

        def stop(self):
            self._cm.__exit__(None, None, None)

    return _Session(pw_cm, pw, browser, context), browser, context

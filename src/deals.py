import unicodedata

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _norm(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )


def fetch_deals(cfg: dict) -> list[dict]:
    """Lee ofertas de Secret Flying y filtra por keywords del config."""
    if not cfg.get("enabled"):
        return []
    url = cfg.get("url", "https://www.secretflying.com/south-america-flight-deals/")
    keywords = [_norm(k) for k in cfg.get("keywords", [])]
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    deals: list[dict] = []
    for h3 in soup.find_all("h3"):
        a = h3.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a["href"]
        if not keywords or any(k in _norm(title) for k in keywords):
            deals.append({"title": title, "url": href})
    return deals

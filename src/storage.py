import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    store TEXT NOT NULL,
    product_id TEXT NOT NULL,
    url TEXT NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (store, product_id)
);
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store TEXT NOT NULL,
    product_id TEXT NOT NULL,
    price REAL NOT NULL,
    original_price REAL,
    ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_lookup
    ON price_history (store, product_id, ts DESC);
CREATE TABLE IF NOT EXISTS flight_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    price REAL NOT NULL,
    carrier TEXT,
    stops INTEGER,
    ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flight_lookup
    ON flight_history (origin, destination, departure_date, ts DESC);
CREATE TABLE IF NOT EXISTS deals_seen (
    url TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS flight_alerts_seen (
    key TEXT PRIMARY KEY,
    price REAL NOT NULL,
    ts INTEGER NOT NULL
);
"""


def get_conn(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def save_products(conn: sqlite3.Connection, store: str, products: list[dict]) -> None:
    now = int(time.time())
    for p in products:
        conn.execute(
            """INSERT INTO products (store, product_id, url, name)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(store, product_id) DO UPDATE
               SET url=excluded.url, name=excluded.name""",
            (store, p["product_id"], p["url"], p["name"]),
        )
        conn.execute(
            """INSERT INTO price_history
               (store, product_id, price, original_price, ts)
               VALUES (?, ?, ?, ?, ?)""",
            (store, p["product_id"], p["price"], p.get("original_price"), now),
        )
    conn.commit()


def last_price(conn: sqlite3.Connection, store: str, product_id: str) -> float | None:
    row = conn.execute(
        """SELECT price FROM price_history
           WHERE store=? AND product_id=? ORDER BY ts DESC, id DESC LIMIT 1""",
        (store, product_id),
    ).fetchone()
    return row[0] if row else None


def detect_drops(
    conn: sqlite3.Connection, store: str, products: list[dict], threshold_pct: float
) -> list[dict]:
    """Compara precio actual vs último registrado. Devuelve productos con bajada > umbral."""
    drops = []
    for p in products:
        prev = last_price(conn, store, p["product_id"])
        if prev is None or prev <= 0:
            continue
        change = (p["price"] - prev) / prev * 100
        if change <= -threshold_pct:
            drops.append(
                {
                    **p,
                    "prev_price": prev,
                    "change_pct": round(change, 1),
                }
            )
    return drops


def save_flights(conn: sqlite3.Connection, offers: list[dict]) -> None:
    now = int(time.time())
    for o in offers:
        conn.execute(
            """INSERT INTO flight_history
               (origin, destination, departure_date, price, carrier, stops, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                o["origin"],
                o["destination"],
                o["departure_date"],
                o["price"],
                o.get("carrier"),
                o.get("stops"),
                now,
            ),
        )
    conn.commit()


def flight_history(conn: sqlite3.Connection) -> list[tuple]:
    rows = conn.execute(
        """SELECT origin, destination, departure_date, price, ts
           FROM flight_history"""
    ).fetchall()
    return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]


def new_deals(conn: sqlite3.Connection, deals: list[dict]) -> list[dict]:
    """Inserta deals vistos; devuelve solo los nuevos. Primera corrida: ninguno nuevo."""
    first = not conn.execute("SELECT 1 FROM deals_seen LIMIT 1").fetchone()
    now = int(time.time())
    fresh: list[dict] = []
    for d in deals:
        row = conn.execute(
            "SELECT 1 FROM deals_seen WHERE url=?", (d["url"],)
        ).fetchone()
        if row:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO deals_seen (url, title, ts) VALUES (?, ?, ?)",
            (d["url"], d["title"], now),
        )
        if not first:
            fresh.append(d)
    conn.commit()
    return fresh


def filter_new_flight_alerts(
    conn: sqlite3.Connection, alerts: list[dict]
) -> list[dict]:
    """Suprime alertas de vuelo repetidas: solo avisa si el precio bajó vs la última alerta de esa ruta."""
    now = int(time.time())
    fresh: list[dict] = []
    for a in alerts:
        key = f'{a["origin"]}->{a["destination"]}|{a["departure_date"]}'
        row = conn.execute(
            "SELECT price FROM flight_alerts_seen WHERE key=?", (key,)
        ).fetchone()
        if row is not None and a["price"] >= row[0]:
            continue
        conn.execute(
            """INSERT INTO flight_alerts_seen (key, price, ts) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET price=excluded.price, ts=excluded.ts""",
            (key, a["price"], now),
        )
        fresh.append(a)
    conn.commit()
    return fresh

import argparse
import os
import sys

import yaml
from dotenv import load_dotenv

from src import deals, flights, report, storage
from src.scrapers import falabella, hites, paris, ripley

SCRAPERS = {"ripley": ripley, "falabella": falabella, "hites": hites, "paris": paris}


def main() -> int:
    parser = argparse.ArgumentParser(description="Recolector de ofertas CL")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scrapear e imprimir resumen sin escribir en SQLite",
    )
    parser.add_argument(
        "--store",
        action="append",
        help="ejecutar solo estas tiendas (repitable): ripley|falabella|hites|paris",
    )
    parser.add_argument(
        "--flights-only",
        action="store_true",
        help="solo consulta de vuelos Amadeus (sin scrapers)",
    )
    parser.add_argument(
        "--no-flights",
        action="store_true",
        help="omite vuelos aunque estén habilitados en config",
    )
    parser.add_argument(
        "--no-deals",
        action="store_true",
        help="omite Secret Flying aunque esté habilitado en config",
    )
    args = parser.parse_args()

    load_dotenv()
    with open("config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    threshold = config.get("thresholds", {}).get("product_drop_pct", 15)
    db_path = config.get("storage", {}).get("path", "data/ofertas.db")
    conn = None if args.dry_run else storage.get_conn(db_path)

    total_products = 0
    total_drops = 0
    total_flight_alerts = 0
    total_new_deals = 0
    errors = []
    product_drop_msgs: list[str] = []
    flight_alert_msg: str | None = None
    deal_msgs: list[str] = []

    run_flights = (
        (config.get("flights") or {}).get("enabled")
        and not args.no_flights
        and (args.flights_only or not args.store)
    )
    if args.flights_only:
        pass  # no correr tiendas
    elif not args.flights_only:
        for store_name, store_cfg in config.get("stores", {}).items():
            if args.store and store_name not in args.store:
                continue
            if not store_cfg.get("enabled") or store_name not in SCRAPERS:
                continue
            try:
                products = SCRAPERS[store_name].scrape(store_cfg)
            except Exception as exc:  # noqa: BLE001 - un fallo no detiene el resto
                errors.append(f"{store_name}: {exc}")
                print(f"[ERROR] {store_name}: {exc}", file=sys.stderr)
                continue

            drops = []
            if conn is not None:
                drops = storage.detect_drops(conn, store_name, products, threshold)
                storage.save_products(conn, store_name, products)

            total_products += len(products)
            total_drops += len(drops)
            print(f"[OK] {store_name}: {len(products)} productos, {len(drops)} bajadas >{threshold}%")
            for d in drops:
                print(
                    f"  ↓ {d['change_pct']}%  {d['name'][:60]}  "
                    f"${d['prev_price']:.0f} → ${d['price']:.0f}"
                )
            if drops:
                product_drop_msgs.append(report.format_product_drops(store_name, drops))

    if run_flights:
        fcfg = config["flights"]
        th = config.get("thresholds", {})
        try:
            offers = flights.search_all(fcfg)
            history = storage.flight_history(conn) if conn else []
            if conn is not None:
                storage.save_flights(conn, offers)
            falerts = flights.detect_flight_errors(
                offers,
                history,
                threshold_pct=float(th.get("flight_drop_pct", 20)),
                percentile=int(th.get("flight_percentile", 10)),
                price_min=th.get("flight_price_min"),
                price_max=th.get("flight_price_max"),
            )
            total_flight_alerts = len(falerts)
            # resumen: mejor precio por ruta×fecha
            best: dict[tuple, dict] = {}
            for o in offers:
                key = (o["origin"], o["destination"], o["departure_date"])
                if key not in best or o["price"] < best[key]["price"]:
                    best[key] = o
            print(f"[OK] vuelos: {len(offers)} ofertas, {len(best)} rutas×fecha, {len(falerts)} alertas")
            for a in falerts:
                print(
                    f"  ✈ ALERTA {a['origin']}→{a['destination']} {a['departure_date']} "
                    f"${a['price']:,.0f} ({a['carrier']}) — {a['reason']}"
                )
            if falerts:
                flight_alert_msg = report.format_flight_alerts(falerts)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"flights: {exc}")
            print(f"[ERROR] flights: {exc}", file=sys.stderr)

    run_deals = (
        (config.get("deals") or {}).get("enabled")
        and not args.flights_only
        and not args.no_deals
        and not args.store
    )
    if run_deals:
        try:
            found = deals.fetch_deals(config.get("deals") or {})
            fresh = storage.new_deals(conn, found) if conn is not None else []
            total_new_deals = len(fresh)
            print(f"[OK] deals: {len(found)} ofertas en keywords, {total_new_deals} nuevas")
            for d in fresh:
                print(f"  🔥 {d['title'][:80]}")
            if fresh:
                deal_msgs.append(report.format_deals(fresh))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"deals: {exc}")
            print(f"[ERROR] deals: {exc}", file=sys.stderr)

    if conn:
        conn.close()

    msgs = product_drop_msgs + ([flight_alert_msg] if flight_alert_msg else []) + deal_msgs
    if msgs and not args.dry_run:
        try:
            ok = report.send("\n\n".join(msgs))
            if ok:
                print("[OK] Telegram: alerta enviada")
        except Exception as exc:  # noqa: BLE001 - un fallo de Telegram no debe tumbar la corrida
            errors.append(f"telegram: {exc}")
            print(f"[ERROR] telegram: {exc}", file=sys.stderr)

    print(
        f"\nTotal: {total_products} productos, {total_drops} bajadas, "
        f"{total_flight_alerts} alertas vuelo, {total_new_deals} deals nuevos, "
        f"{len(errors)} errores"
    )
    return 1 if errors and total_products == 0 and not args.flights_only else 0


if __name__ == "__main__":
    raise SystemExit(main())

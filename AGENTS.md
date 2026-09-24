# ofertas-cl

Vigilancia de precios: tiendas Chile (Ripley, Falabella, Hites, Paris) + vuelos SCL↔GIG/GRU (Google Flights vía Playwright). **Rubros:** camas, celulares, notebooks, drones, ropa, maletas, perfumes, TV/smartTV, scooters, powerbank, muebles, iPad, audífonos, relojes, zapatillas, smartwatch. Alertas por Telegram.

## Comandos

```bash
# venv ya creada en .venv/
.\.venv\Scripts\python.exe run.py                 # tiendas + vuelos
.\.venv\Scripts\python.exe run.py --dry-run       # sin escribir SQLite
.\.venv\Scripts\python.exe run.py --store ripley --store paris  # tiendas (repitable)
.\.venv\Scripts\python.exe run.py --flights-only  # solo Google Flights
.\.venv\Scripts\python.exe run.py --no-flights    # solo tiendas
```

## Estructura

- `config.yaml` — URLs por tienda, umbrales, rutas de vuelo
- `src/scrapers/browser.py` — Playwright + playwright-stealth (obligatorio: WAF de Ripley bloquea Playwright "pelado")
- `src/scrapers/ripley.py` — anclas con `$`, id de producto en la URL (un solo segmento `/slug-id`); cuidado 429 si se scrapear mucho seguido
- `src/scrapers/falabella.py` — intenta `a.pod-link`, si no hay usa `a[href*="/product/"]` (markup cambió a `ProductLink` + texto `MARCA|Nombre`); NO sirve `?ajax=true` ni JSON del HTML
- `src/scrapers/hites.py` — tiles `[data-pid]`; precios FUERA del ancla (`.price-item`); pid = data-pid o dígitos del `.html`
- `src/scrapers/paris.py` — anclas `/*.html` raíz con `$` en texto; pid = dígitos finales o código MK…
- `src/storage.py` — SQLite `data/ofertas.db` (products + price_history + flight_history)
- `src/report.py` — Telegram: `send(text)`, `format_product_drops()`, `format_flight_alerts()`; usa `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` del `.env`; si no hay credenciales, no falla (solo no envía)
- `src/flights.py` — **Google Flights** (URL `q=Flights from A to B on DATE&curr=CLP`); parsea precios `NNN.NNN CLP`; `detect_flight_errors` (P10 / caída >20% en 24h). *Amadeus Self-Service descontinuado 17-jul-2026 — no usar.*
- `run.py` — orquestador CLI (`--flights-only`, `--no-flights`, `--store` repitable, `--dry-run`); al final envía alertas por Telegram si las hay

## Decisiones clave

- Hosting previsto: **GitHub Actions** (productos c/1h, vuelos c/3h; cuota 2000 min gratis)
- Vuelos: **Google Flights** con Playwright+stealth (gratis; Amadeus Self-Service ya no existe)
- Ripley: categorías reales tipo `/outlet`, `/tecno/celulares`, `/electro/recomendados-linea-blanca` (NO `/electro/linea-blanca` ni `/tienda/ofertas-del-dia` → 404). Si 429 "Error en Ripley.com | IUA" = rate limit por tanto test; esperar y reintentar.
- Ambos scrapers: precio actual = precio **mínimo** de la tarjeta; original = máximo
- Nombres de producto: línea **más larga** de la tarjeta (img alt de Paris = "Imagen de producto" inútil; Falabella alt = solo marca). Filtrar "Envío gratis", "$…", "%", "Vista Previa".
- .env solo para Telegram (Fase 4) — nunca commitear; los vuelos NO requieren API key

## Optimización anti-bloqueo

- Esperas por página: ~2.2-2.5s + 1 scroll (antes 4s + 2 scrolls)
- `time.sleep(0.6)` entre URLs del mismo dominio
- Ripley/Hites/Paris: try/except por URL (una 429 no mata la tienda)
- Falabella: `wait_for_selector` timeout 10s
- URLs de búsqueda Ripley `/s/list/<kw>` casi siempre 404; solo `/s/list/bateria-portatil` funciona verificado. Preferir categorías reales (ej. `/dormitorio/camas`, `/belleza/perfumes`, `/tecno/audio-y-musica/audifonos`, `/accesorios-y-complementos/relojes/relojeria-mujer`, `/marca/head/bolsos-y-maletas`, `/deporte-y-aventura/electromovilidad`, `/jugueteria-y-ninos/.../drones-y-juguetes-a-control`).
- Falabella: preferir `/category/cat*/Slug` (estables); `verify_urls.py` espera selector de producto en Falabella (no 2.5s fijo). 66/66 URLs OK verificadas 24-sep-2026.

## Pendiente (Fase 5)

- [ ] Workflow `.github/workflows/ofertas.yml`

## Telegram (Fase 4 ✓)

1. Hablar con `@BotFather` en Telegram → `/newbot` → copiar **token**
2. Hablar con el bot recién creado → `/start`
3. Visitar `https://api.telegram.org/bot<TOKEN>/getUpdates` → copiar `chat.id`
4. Crear `.env` (ver `.env.example`):
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   TELEGRAM_CHAT_ID=987654321
   ```
5. Probar: `.\.venv\Scripts\python.exe run.py --no-flights --store paris` (si hay bajadas, llega mensaje)

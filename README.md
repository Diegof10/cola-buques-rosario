# Cola de Buques · Up-River Rosario

Prototipo local interactivo (español) del escritorio de logística de granos Up-River / Gran Rosario.

Muestra:
- **Cola de buques** agrupada por puerto/zona (San Lorenzo, Timbúes, Rosario, Punta Alvear, Gral. Lagos, Arroyo Seco, etc.)
- **Próximos arribos** (ETA anunciados, filtra ETA pasadas, agrupados por puerto)
- **Volumen por destino** (torta + mapa mundial): toneladas agregadas por país de destino NABSA
- **Camiones** del día por producto y zona (muestra realista si no hay API MAGyP/BCR)
- **Cobertura camiones vs demanda**: tn estimadas (30 tn/camión; 25 girasol) vs stock export Up-River; % cobertura, días a cubrir y semáforo Verde/Amarillo/Rojo

## Requisitos

- Python 3.11+ (probado con 3.13)

## Arranque rápido

```bash
cd /workspace/cola-buques-rosario
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/refresh_data.py   # descarga/parsea NABSA
.venv/bin/python server.py                 # http://localhost:5173
```

Atajo:

```bash
./dev.sh
```

Abrir **http://127.0.0.1:5173**

## Datos en vivo

En el sitio desplegado, `GET /api/vessels` refresca NABSA automáticamente si `vessels.json` tiene más de ~45 min (configurable con `VESSELS_MAX_AGE_SEC`) o falta. El refresh corre en background; la API responde de inmediato con el último cache bueno. En Render (FS efímero) escribe bajo `/tmp/cola-buques-data` (o `DATA_DIR`). También: `POST /api/vessels/refresh`, y `GET /api/health` muestra edad del cache.

La UI oculta **próximos arribos** cuya fecha ETA (DD/MM en America/Argentina/Cordoba) sea **anterior a hoy**. Los arribos se agrupan por puerto/zona (secciones colapsables).

`scripts/refresh_data.py` intenta:

1. Descargar `https://www.nabsa.com.ar/assets/vessel_update.pdf`
2. Parsear con **pdfplumber** (buque, terminal, ETA/ETB/ETF, toneladas, commodity, destino, charterer)
3. Clasificar: `cargando` / `en_rada` / `arribando` / `en_cola`
4. Guardar `data/vessels.json` (+ copia `data/sample-vessels.json`)
5. Camiones: si MAGyP/BCR no ofrecen JSON usable, mantiene `data/trucks.json` (seed realista) y `data/sample-trucks.json`

## Volumen por destino

- Agrega toneladas del lineup Up-River por campo `destination` (NABSA).
- **Argentina** (y variantes AR/ARG) → tarjeta **Descarga AR** (importación / descarga). No entra en la torta ni en los círculos de exportación.
- Destino vacío / `NOT AVAILABLE` → tarjeta **Sin destino (NABSA)** (aparte de la torta). Nunca se mezcla en la torta como si fueran países desconocidos.
- Torta: top ~14 países de exportación conocidos + rebanada **Resto países** (otros destinos *con* país, no “Otros”/unknown).
- Si NABSA no trae destino pero el charterer tiene mapeo conservador (p. ej. AL GHURAIR→UAE, COFCO→China), se completa con `destination_inferred` / `destination_source: inferred` y badge **estimado** en la UI. No se inventa si el charterer también es NOT AVAILABLE.
- Lista ordenada por toneladas + mapa Leaflet mundial (solo exportación).
- Respeta filtros de zona / commodity / estado / búsqueda.


## Cobertura camiones / semáforo

Estima el flujo diario de camiones frente al stock de exportación Up-River:

- **Tn camiones**: `Σ by_product.camiones × factor` — 30 tn/camión (soja, maíz, trigo, sorgo, cebada, etc.) y **25 tn/camión solo girasol** (se ignoran campos `tn` stale si usaban 30 para girasol).
- **Demanda**: suma de toneladas anunciadas de buques Up-River con commodity en {soja, maíz, trigo, girasol, sorgo, cebada}, **excluyendo** destinos Argentina / Descarga AR.
- **Métricas**: `coverage_pct = 100 × truck_tn / demand_tn`, `days_to_cover = demand_tn / truck_tn`.
- **Semáforo** (sobre `days_to_cover`; etiqueta = flujo de camiones vs stock):
  - Verde · **Alto**: ≤ 30 días
  - Amarillo · **Normal**: 30–55 días
  - Rojo · **Bajo**: > 55 días

Calibración histórica (pie de UI + comentario en código): MAGyP 2025 Rosario y aledaños 964.503 cam/año ≈ 2.640/día; MAGyP ago-2026 ~2,4–4,5k/día; picos AgroEntregas/BCR 5.500–7.000; stock Up-River típico ~3,5–5 Mt. A ~4,8 Mt: ~60d promedio (rojo), ~40d flujo bueno (amarillo), ≤30d picos (verde).

## API local

- `GET /api/health`
- `GET /api/vessels`
- `GET /api/trucks`
- `GET /api/coverage` (tn camiones est. vs demanda export Up-River + semáforo)
- `GET /api/terminals` (coords legacy; la UI ya no usa el mapa de terminales Up-River)
- UI estática en `/` y `/static/*`

## Stack

HTML + CSS + JS (escritorio agro: navy `#0B1F3A`, verde bosque) + Leaflet (mapa mundial CDN) + FastAPI (sirve JSON sin CORS).

Filtros: puerto/zona, commodity, estado, búsqueda por buque (sincronizados con torta y mapa de destinos).

## Notas

- Sin logos oficiales BCR/NABSA.
- Pie: Fuentes NABSA · MAGyP · BCR · Prototipo local DHF

# Cola de Buques · Up-River Rosario

Prototipo local interactivo (español) del escritorio de logística de granos Up-River / Gran Rosario.

Muestra:
- **Cola de buques** agrupada por puerto/zona (San Lorenzo, Timbúes, Rosario, Punta Alvear, Gral. Lagos, Arroyo Seco, etc.)
- **Próximos arribos** (ETA anunciados, filtra ETA pasadas, agrupados por puerto)
- **Volumen por destino** (torta + mapa mundial): toneladas agregadas por país de destino NABSA
- **Camiones** del día por producto y zona (muestra realista si no hay API MAGyP/BCR)

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

## API local

- `GET /api/health`
- `GET /api/vessels`
- `GET /api/trucks`
- `GET /api/terminals` (coords legacy; la UI ya no usa el mapa de terminales Up-River)
- UI estática en `/` y `/static/*`

## Stack

HTML + CSS + JS (escritorio agro: navy `#0B1F3A`, verde bosque) + Leaflet (mapa mundial CDN) + FastAPI (sirve JSON sin CORS).

Filtros: puerto/zona, commodity, estado, búsqueda por buque (sincronizados con torta y mapa de destinos).

## Notas

- Sin logos oficiales BCR/NABSA.
- Pie: Fuentes NABSA · MAGyP · BCR · Prototipo local DHF

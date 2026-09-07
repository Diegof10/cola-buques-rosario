# Cola de Buques · Up-River Rosario

Prototipo local interactivo (español) del escritorio de logística de granos Up-River / Gran Rosario.

Muestra:
- **Cola de buques** agrupada por puerto/zona (San Lorenzo, Timbúes, Rosario, Punta Alvear, Gral. Lagos, Arroyo Seco, etc.)
- **Próximos arribos** (ETA anunciados)
- **Mapa georreferenciado** (Leaflet): buques ubicados en coordenadas aproximadas del complejo portuario según lineup NABSA (no AIS)
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

`scripts/refresh_data.py` intenta:

1. Descargar `https://www.nabsa.com.ar/assets/vessel_update.pdf`
2. Parsear con **pdfplumber** (buque, terminal, ETA/ETB/ETF, toneladas, commodity, destino, charterer)
3. Clasificar: `cargando` / `en_rada` / `arribando` / `en_cola`
4. Guardar `data/vessels.json` (+ copia `data/sample-vessels.json`)
5. Camiones: si MAGyP/BCR no ofrecen JSON usable, mantiene `data/trucks.json` (seed realista) y `data/sample-trucks.json`


## Mapa (terminal ≈ posición)

- Coordenadas en `data/terminals.json` (WGS84 aproximadas por zona Up-River).
- El cliente mapea `zone` / `port` / `terminal` del lineup a esas coords (nombres fuzzy) y aplica un jitter leve para no solapar marcadores.
- Colores por commodity; popups con estado, tn, ETA/ETB/ETF; clusters Leaflet.
- **AIS en tiempo real (futuro):** hace falta API key de MarineTraffic, AISStream u otro proveedor AIS. Placeholder de capa: consumir posiciones MMSI/IMO y superponer sobre el mapa actual sin reemplazar el fallback NABSA-por-terminal.

## API local

- `GET /api/health`
- `GET /api/vessels`
- `GET /api/trucks`
- `GET /api/terminals`
- UI estática en `/` y `/static/*`

## Stack

HTML + CSS + JS (escritorio agro: navy `#0B1F3A`, verde bosque) + Leaflet (CDN) + FastAPI (sirve JSON sin CORS).

Filtros: puerto/zona, commodity, estado, búsqueda por buque (sincronizados con el mapa).

## Notas

- Sin logos oficiales BCR/NABSA.
- Pie: Fuentes NABSA · MAGyP · BCR · Prototipo local DHF

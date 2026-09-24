# Cobertura camiones vs demanda export (días de cobertura)

Documento de referencia de la fórmula del KPI **días de cobertura** / semáforo
en el dashboard Up-River (`cola-buques-rosario`).

Implementación canónica:

- Backend: `server.py` → `compute_coverage()`, `estimate_truck_tn()`, `estimate_demand_tn()`, `classify_semaforo()`
- Factores de tn/camión: `scripts/stock_math.py` (`truck_factor`)
- Frontend (mismo cálculo, sin filtros de UI): `web/static/app.js` → `computeCoverageClient()`
- API: `GET /api/coverage`

---

## Idea en una frase

¿Cuántos **días de flujo actual de camiones** harían falta para “llenar” la
**demanda de exportación** anunciada en la cola Up-River?

No es el “días de stock en planta” clásico (inventario ÷ egreso diario). Acá el
numerador es la **tonelaje anunciado de buques export** y el denominador es el
**ingreso diario estimado de camiones** (MAGyP).

---

## Fórmulas

### 1. Toneladas de camiones del día (`truck_tn`)

Fuente: `data/trucks.json` (scrape MAGyP, Rosario y aledaños), mix `by_product`.

\[
\text{truck\_tn} = \sum_i \text{camiones}_i \times f(producto_i)
\]

Factores (acordados con Diego):

| Producto | tn / camión |
|----------|-------------|
| Soja, maíz, trigo, sorgo, cebada, resto | **30** |
| Girasol | **25** |

Si no hay `by_product` y solo existe `total_camiones`, se usa fallback
`total_camiones × 30`.

Código: `estimate_truck_tn` / `estimateTruckTn`.

### 2. Demanda export Up-River (`demand_tn`)

Fuente: lineup NABSA (`vessels.json`), **solo** buques `up_river`.

Se suman las toneladas anunciadas (`tons`) si:

1. `commodity` ∈ `{soja, maiz, trigo, girasol, sorgo, cebada}`
2. El destino efectivo **no** es Argentina / Descarga AR

Se excluyen destinos AR (raw o inferido). No se aplican los filtros de la UI
(puerto, commodity, estado, búsqueda): la demanda es siempre el universo
Up-River completo, para que el KPI no “salte” al filtrar listas.

Código: `estimate_demand_tn` / `estimateDemandTn`.

### 3. Ratio de cobertura porcentual (`coverage_pct`)

\[
\text{coverage\_pct} = 100 \times \frac{\text{truck\_tn}}{\text{demand\_tn}}
\]

Interpretación: qué % de la demanda anunciada representa **un día** de flujo
de camiones. Si `demand_tn = 0` → `null`.

### 4. Días de cobertura (`days_to_cover`) — el ratio principal

\[
\text{days\_to\_cover} = \frac{\text{demand\_tn}}{\text{truck\_tn}}
\]

Equivale a \( 100 / \text{coverage\_pct} \) cuando hay demanda.

Interpretación: a este ritmo de camiones, cuántos días se tardaría en aportar
toneladas equivalentes a toda la demanda export sentada en la cola.

- **Menos días** → flujo fuerte frente a la cola → semáforo verde (**Alto**)
- **Más días** → flujo flojo frente a la cola → semáforo rojo (**Bajo**)

Si `truck_tn = 0` → `null`.

---

## Semáforo

Umbrales sobre `days_to_cover` (constantes `DAYS_GREEN_MAX = 30`,
`DAYS_YELLOW_MAX = 55`):

| Color | Código | Etiqueta (flujo) | Condición |
|-------|--------|------------------|-----------|
| Verde | `verde` | Alto | ≤ 30 días |
| Amarillo | `amarillo` | Normal | 30–55 días |
| Rojo | `rojo` | Bajo | > 55 días |
| Gris | `sin_datos` | Sin datos | sin flujo o sin demanda |

La etiqueta habla del **flujo de camiones** (Alto/Normal/Bajo), no del “nivel
de stock” en sentido de inventario físico.

---

## Calibración histórica (por qué 30 / 55)

Referencias usadas al armar el semáforo (comentarios en `server.py` / `app.js`):

- MAGyP 2025 Rosario y aledaños: 964.503 cam/año ≈ **2.640/día** promedio
- MAGyP ago-2026: frecuentemente **~2,4k–4,5k/día**
- Picos cosecha AgroEntregas/BCR: **5.500–7.000 cam/día**
- Stock / demanda Up-River típica de referencia: **~3,5–5 Mt**

A ~4,8 Mt de demanda:

| Flujo camiones | Días aprox. | Semáforo |
|----------------|-------------|----------|
| Promedio anual ~2,6k × 30 tn | ~60 d | Rojo |
| Flujo bueno | ~40 d | Amarillo |
| Picos | ≤ 30 d | Verde |

Si cambian umbrales o factores, actualizar este doc, `DAYS_*` en server/JS y
el pie de la UI.

---

## Ejemplo numérico

Supongamos:

- 4.000 camiones (mix sin girasol) → `truck_tn = 4.000 × 30 = 120.000 tn`
- Cola Up-River export granos = **4.800.000 tn**

Entonces:

\[
\text{coverage\_pct} = 100 \times \frac{120.000}{4.800.000} = 2{,}5\%
\]

\[
\text{days\_to\_cover} = \frac{4.800.000}{120.000} = 40\ \text{días} \rightarrow \text{Amarillo · Normal}
\]

---

## Qué no es esta métrica

- **No** usa el bloque “Stock estimado (1° + camiones − embarques)” de la
  tabla por producto. Ese stock es otra proxy (baseline MAGyP 1° del mes +
  camiones nacionales − sailed NABSA). Ver `estimate_stock_tn` en
  `scripts/stock_math.py`.
- **No** es días de cobertura de silobolsa / planta física.
- **No** convierte ¢/bu ni toca precios Chicago; es solo logística.

---

## Dónde se muestra

- KPIs bajo el encabezado: Tn camiones (est.), % cobertura, Días cobertura +
  semáforo
- Pie de cobertura en la UI (`#coverageFootnote`)
- Endpoint JSON: `GET /api/coverage`

---

## Changelog de diseño

- Factores 30 / 25 tn: decisión Diego (girasol más liviano).
- Demanda = lineup export Up-River (no filtros UI): para KPI estable.
- Semáforo calibrado a stock/demanda ~3,5–5 Mt y flujos MAGyP/BCR tipificados.

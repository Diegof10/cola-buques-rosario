# Destinos YTD · ledger NABSA sailed

## Problema

El PDF diario `vessels_sailed_update.pdf` de NABSA se titula **CUMULATIVE YYYY**,
pero en la práctica es una **ventana rolling** (~mes en curso). Los `prior1–4`
rotan en la misma ventana. Tomar un solo PDF como “YTD calendario” inflaba
cobertura (p. ej. `from: 2026-01-01` cuando solo había filas de septiembre).

## Fuente histórica (xlsx)

NABSA publica el acumulado en Excel bajo:

`https://www.nabsa.com.ar/SAILED/sailedYYYYMMDD.xlsx`

- Índice con meta-refresh: `https://www.nabsa.com.ar/SAILED/` (apunta al xlsx
  del día hábil más reciente).
- Mismas columnas que el PDF: Port, Terminal, Vessel, Status, Date, Tons, Cargo,
  Origin, Destination, …
- Snapshots mensuales se guardan (gitignorados) en
  `data/sailed_archive/YYYY-MM_nabsa_sailed.xlsx`.

El refresh diario intenta bajar el xlsx actual (meta-refresh o probe de fechas
recientes) y lo **upsert** al mismo ledger que el PDF (dedupe por clave estable).

Ingest offline de archivo:

```bash
.venv/bin/python scripts/refresh_data.py --ingest-sailed-archive --skip-refresh
```

## Solución

Misma idea que `truck_inflow_ledger.json`:

1. Cada refresh parsea el PDF actual (+ `vessels_sailed_prior1…4` si existen) y,
   si está disponible, el xlsx actual de `/SAILED/`.
2. Upsert en `data/sailed_rows_ledger.json` con clave estable:
   `date|vessel|port|terminal|tons|cargo|destination`.
3. Copia fechada bajo `data/sailed_archive/` (PDF/xlsx gitignorados;
   el ledger JSON **sí** se commitea como seed).
4. `sailed_destinations_ytd.json` se **reconstruye desde el ledger**.
   `from` / `through` = min/max fechas reales del año — nunca se fuerza el 1º
   de enero si no hay filas ese día.
5. La UI muestra el rango real (`DD/MM → DD/MM`) y aclara cobertura parcial
   cuando `from` es posterior al 1/1.

## Honestidad de cobertura

Con los xlsx Jan–Ago + PDF/xlsx de septiembre el ledger cubre el YTD real
disponible. Si faltan días (p. ej. 1/1 sin zarpes), `from` refleja la primera
fecha presente — no se inventan toneladas.

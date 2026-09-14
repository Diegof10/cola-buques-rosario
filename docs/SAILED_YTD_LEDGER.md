# Destinos YTD · ledger NABSA sailed

## Problema

El PDF diario `vessels_sailed_update.pdf` de NABSA se titula **CUMULATIVE YYYY**,
pero en la práctica es una **ventana rolling** (~mes en curso). Los `prior1–4`
rotan en la misma ventana. Tomar un solo PDF como “YTD calendario” inflaba
cobertura (p. ej. `from: 2026-01-01` cuando solo había filas de septiembre).

No hay snapshots Wayback 2026 confiables; **no inventamos** toneladas Jan–Ago.

## Solución

Misma idea que `truck_inflow_ledger.json`:

1. Cada refresh parsea el PDF actual (+ `vessels_sailed_prior1…4` si existen).
2. Upsert en `data/sailed_rows_ledger.json` con clave estable:
   `date|vessel|port|terminal|tons|cargo|destination`.
3. Copia fechada bajo `data/sailed_archive/YYYY-MM-DD_*.pdf` (gitignorada;
   el ledger JSON **sí** se commitea como seed).
4. `sailed_destinations_ytd.json` se **reconstruye desde el ledger**.
   `from` / `through` = min/max fechas reales del año — nunca se fuerza el 1º
   de enero si no hay filas ese día.
5. La UI muestra el rango real (`DD/MM → DD/MM`) y aclara cobertura parcial
   cuando `from` es posterior al 1/1.

## Honestidad de cobertura

Hasta que el ledger crezca (refreshes diarios y/o PDFs viejos aportados a mano),
el acumulado **no es YTD completo**. El pie/nota de la API lo deja explícito.

# Loop Engineering — Cola de Buques Rosario

Diseño acordado para que el Loop (agente / humano) abra issues, implemente
cambios en una rama y —más adelante— los mergeé con un gate de tests.

**Stage 1 está hecho.** Stages 2+ no están implementados a propósito.

## Diseño acordado (alto nivel)

| Pieza | Ahora (stage 1) | Después |
| --- | --- | --- |
| Señales | Labels + issue form `Loop signal` | Detector routine (stage 2) que abra issues `signal:data-stale` si MAGyP/NABSA están atrasados |
| Cadencia | Manual | Weekday, **una vez al día** (stage 3) |
| Merge | Manual | Auto-merge del PR del Loop si CI verde (stage 3–4) |
| Gate | `pytest -q` en GitHub Actions | Pre-merge script + checks requeridos (stage 4) |
| Métrica | — | Issues Loop abiertos / mergeados / revertidos por semana; edad del seed NABSA+MAGyP |

El refresh matutino **sigue pusheando seeds a `main`** (`data/*.json`). Por eso
**no** se habilita branch protection dura en stage 1.

## Stages

### Stage 1 — hecho

- Labels del Loop (prioridad, estado, tipo, señal).
- Issue template GitHub form: `.github/ISSUE_TEMPLATE/loop_signal.yml`.
- Tests offline (`tests/`) + workflow `.github/workflows/ci.yml` (`pytest -q`).
- Este documento. Recomendaciones de branch protection **solo documentadas**.

### Stage 2 — no empezado

Detector routine (cron / script) que compare `updated_at` / fechas MAGyP y NABSA
contra el día hábil en `America/Argentina/Cordoba` y abra un issue con
`loop` + `signal:data-stale` + `status:triage`.

### Stage 3 — no empezado

Loop weekday once-daily: toma issues `status:triage` / `status:plan-ok`,
implementa en rama, abre PR. Sin auto-merge todavía (o draft).

### Stage 4 — no empezado (branch protection)

Recién acá: checks requeridos + pre-merge script + auto-merge.

**No habilitar ahora** reglas que bloqueen push directo a `main`. El refresh
de seeds (NABSA circ. + MAGyP trucks) sigue haciendo `git push` a `main`.
Si se activa “require PR” o status checks en `main` antes de que ese job
use una rama/PR, el push matutino falla.

Recomendación (cuando llegue stage 4):

- Require CI (`CI / test`) en PRs, no en push directo de data.
- Bypass o path allowlist para `data/*.json` **o** mover el refresh a una
  rama `data/refresh-YYYY-MM-DD` con auto-merge si solo toca seeds.
- Restrict force-push / deletion of `main`.
- No exigir review humano en PRs del Loop si el pre-merge script + CI pasan;
  sí exigir humano si el issue tiene `status:needs-human`.

## Labels

| Label | Uso |
| --- | --- |
| `loop` | Trabajo del Loop (siempre en issues/PRs del ciclo) |
| `signal:data-stale` | MAGyP y/o NABSA atrasado vs día hábil |
| `priority:P0` | Bloquea el escritorio (API caída, seed vacío, números absurdos) |
| `priority:P1` | Dato stale o bug visible; el sitio sigue usable |
| `priority:P2` | Mejora / deuda / docs |
| `type:data` | Seeds, parsers, fórmulas de stock/cobertura |
| `type:bug` | Comportamiento incorrecto |
| `type:feature` | Cambio de producto |

## Estados de issue

Flujo: `status:triage` → `status:plan-ok` → `status:in-progress` →
`status:review` → `status:espera-merge` → cerrado.

| Label | Significado |
| --- | --- |
| `status:triage` | Recién abierto (el form aplica este + `loop`) |
| `status:plan-ok` | Alcance y prioridad acordados; listo para implementar |
| `status:in-progress` | Hay rama / agente trabajando |
| `status:review` | PR abierto, CI corriendo o en revisión |
| `status:espera-merge` | CI verde; falta merge (manual hoy; auto después) |
| `status:needs-human` | El Loop no debe auto-mergear (producto, datos dudosos, secretos) |

## Tests y CI

- Helpers puros en `scripts/stock_math.py` (factor camión, fórmula de stock,
  mapa de cargo NABSA sailed). `server.py` y `refresh_data.py` los importan.
- `pytest -q` no usa red. Deps de test: `requirements-dev.txt` o
  `pip install pytest` además de `requirements.txt`.
- Workflow: push a `main` y `pull_request` → Python 3.12 → `pytest -q`.

## Fuera de stage 1

No hay detector, no hay auto-merge, no hay pre-merge script, no hay
protección dura de `main`.

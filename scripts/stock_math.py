"""Pure stock / truck helpers — no I/O, no FastAPI, no network.

Used by server.py (coverage + stock estimado) and refresh_data.py
(NABSA sailed cargo → grain key). Safe to import from pytest.
"""
from __future__ import annotations

TN_PER_TRUCK_DEFAULT = 30
TN_PER_TRUCK_GIRASOL = 25


def truck_factor(product: str) -> int:
    """30 tn/camión general; 25 tn/camión solo girasol. Ignore stale tn fields."""
    return TN_PER_TRUCK_GIRASOL if str(product or "").lower() == "girasol" else TN_PER_TRUCK_DEFAULT


def estimate_stock_tn(baseline_tn: float, inflow_tn: float, export_tn: float) -> float:
    """Stock estimado = baseline (1° mes) + inflow − export.

    Raw formula, no clamp — can be negative if egresos > baseline+ingresos.
    """
    return float(baseline_tn) + float(inflow_tn) - float(export_tn)


def map_sailed_commodity(cargo_raw: str | None) -> str:
    """Map NABSA Cargo text → maiz|soja|trigo|girasol|sorgo|cebada|otro (contains)."""
    c = str(cargo_raw or "").lower()
    if "corn" in c:
        return "maiz"
    # Soy complex (meal/oil/beans/hulls) counts against soja stock
    if (
        "soybean meal" in c
        or "soybeanmeal" in c
        or "soybean oil" in c
        or "soybeanoil" in c
        or "soy bean" in c
        or "soybean" in c
        or "soya" in c
    ):
        return "soja"
    if "wheat" in c:
        return "trigo"
    if "sun flower" in c or "sunflower" in c:
        return "girasol"
    if "sorghum" in c:
        return "sorgo"
    if "barley" in c:
        return "cebada"
    return "otro"

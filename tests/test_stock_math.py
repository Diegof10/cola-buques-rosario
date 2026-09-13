"""Offline unit tests for truck factor, stock formula, and sailed cargo map."""
from __future__ import annotations

from stock_math import (
    TN_PER_TRUCK_DEFAULT,
    TN_PER_TRUCK_GIRASOL,
    estimate_stock_tn,
    map_sailed_commodity,
    truck_factor,
)


def test_tn_constants():
    assert TN_PER_TRUCK_DEFAULT == 30
    assert TN_PER_TRUCK_GIRASOL == 25


def test_truck_factor_girasol_vs_default():
    assert truck_factor("girasol") == TN_PER_TRUCK_GIRASOL
    assert truck_factor("Girasol") == TN_PER_TRUCK_GIRASOL
    assert truck_factor("soja") == TN_PER_TRUCK_DEFAULT
    assert truck_factor("maiz") == TN_PER_TRUCK_DEFAULT
    assert truck_factor("trigo") == TN_PER_TRUCK_DEFAULT
    assert truck_factor("") == TN_PER_TRUCK_DEFAULT
    assert truck_factor(None) == TN_PER_TRUCK_DEFAULT  # type: ignore[arg-type]


def test_estimate_stock_tn_baseline_plus_inflow_minus_export():
    # 1_000_000 + (100 camiones × 30 tn) − 20_000 = 983_000
    inflow = 100 * truck_factor("soja")
    assert estimate_stock_tn(1_000_000, inflow, 20_000) == 983_000.0


def test_estimate_stock_tn_girasol_factor_and_negative_allowed():
    inflow = 10 * truck_factor("girasol")  # 250
    assert estimate_stock_tn(100, inflow, 50) == 300.0
    # raw formula, no clamp
    assert estimate_stock_tn(100, 0, 250) == -150.0


def test_map_sailed_commodity_soy_complex():
    assert map_sailed_commodity("SOYBEAN MEAL") == "soja"
    assert map_sailed_commodity("SOYBEANMEAL") == "soja"
    assert map_sailed_commodity("SOYBEAN OIL") == "soja"
    assert map_sailed_commodity("SOYBEANOIL REFINED") == "soja"
    assert map_sailed_commodity("SOYA BEAN") == "soja"
    assert map_sailed_commodity("SOYA HULL PELLETS") == "soja"


def test_map_sailed_commodity_other_grains():
    assert map_sailed_commodity("CORN") == "maiz"
    assert map_sailed_commodity("CORN FLINT") == "maiz"
    assert map_sailed_commodity("WHEAT") == "trigo"
    assert map_sailed_commodity("SUN FLOWER OIL") == "girasol"
    assert map_sailed_commodity("SUNFLOWER MEAL") == "girasol"
    assert map_sailed_commodity("SORGHUM") == "sorgo"
    assert map_sailed_commodity("BARLEY") == "cebada"
    assert map_sailed_commodity("BIODIESEL") == "otro"
    assert map_sailed_commodity("") == "otro"
    assert map_sailed_commodity(None) == "otro"

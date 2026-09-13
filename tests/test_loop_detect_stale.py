"""Offline unit tests for Loop stage 2 stale-date helpers (no network)."""
from __future__ import annotations

from datetime import date

from loop_detect_stale import (
    assess_staleness,
    business_days_behind,
    choose_priority,
    is_stale,
    parse_iso_date,
    previous_business_day,
    same_stale_window,
    stale_window_marker,
)


def test_previous_business_day_monday_to_friday():
    # Monday 2026-09-14 → Friday 2026-09-11
    assert previous_business_day(date(2026, 9, 14)) == date(2026, 9, 11)


def test_previous_business_day_midweek():
    # Tuesday → Monday
    assert previous_business_day(date(2026, 9, 15)) == date(2026, 9, 14)
    # Wednesday → Tuesday
    assert previous_business_day(date(2026, 9, 16)) == date(2026, 9, 15)
    # Friday → Thursday
    assert previous_business_day(date(2026, 9, 18)) == date(2026, 9, 17)


def test_previous_business_day_weekend():
    # Saturday → Friday
    assert previous_business_day(date(2026, 9, 12)) == date(2026, 9, 11)
    # Sunday → Friday
    assert previous_business_day(date(2026, 9, 13)) == date(2026, 9, 11)


def test_parse_iso_date():
    assert parse_iso_date("2026-09-10") == date(2026, 9, 10)
    assert parse_iso_date("2026-09-10T08:36:31.370705-03:00") == date(2026, 9, 10)
    assert parse_iso_date(None) is None
    assert parse_iso_date("") is None
    assert parse_iso_date("not-a-date") is None


def test_is_stale_comparison():
    expected = date(2026, 9, 11)
    assert is_stale(date(2026, 9, 10), expected) is True
    assert is_stale(date(2026, 9, 11), expected) is False
    assert is_stale(date(2026, 9, 12), expected) is False
    assert is_stale(None, expected) is True


def test_business_days_behind():
    expected = date(2026, 9, 11)  # Friday
    assert business_days_behind(date(2026, 9, 11), expected) == 0
    assert business_days_behind(date(2026, 9, 10), expected) == 1
    assert business_days_behind(date(2026, 9, 9), expected) == 2
    # Weekend gap: Mon expected Sep 14, actual Fri Sep 11 → 1 business day
    assert business_days_behind(date(2026, 9, 11), date(2026, 9, 14)) == 1
    assert business_days_behind(None, expected) == 999


def test_choose_priority_p0_when_both_more_than_one_day_behind():
    assert (
        choose_priority(
            trucks_stale=True,
            vessels_stale=True,
            trucks_behind=2,
            vessels_behind=2,
        )
        == "priority:P0"
    )
    # Only one day behind → P1
    assert (
        choose_priority(
            trucks_stale=True,
            vessels_stale=True,
            trucks_behind=1,
            vessels_behind=1,
        )
        == "priority:P1"
    )
    # Only trucks stale → P1 even if far behind
    assert (
        choose_priority(
            trucks_stale=True,
            vessels_stale=False,
            trucks_behind=5,
            vessels_behind=0,
        )
        == "priority:P1"
    )


def test_assess_staleness_fresh():
    a = assess_staleness(
        today=date(2026, 9, 12),  # Sat → expected Fri 11
        trucks_date=date(2026, 9, 11),
        nabsa_date=date(2026, 9, 11),
    )
    assert a.expected == date(2026, 9, 11)
    assert a.stale is False
    assert a.trucks_stale is False
    assert a.vessels_stale is False


def test_assess_staleness_both_stale():
    a = assess_staleness(
        today=date(2026, 9, 12),
        trucks_date=date(2026, 9, 10),
        nabsa_date=date(2026, 9, 10),
    )
    assert a.stale is True
    assert a.trucks_stale is True
    assert a.vessels_stale is True
    assert a.trucks_behind == 1
    assert a.vessels_behind == 1
    assert a.priority == "priority:P1"


def test_same_stale_window_marker_roundtrip():
    expected = date(2026, 9, 11)
    trucks = date(2026, 9, 10)
    nabsa = date(2026, 9, 10)
    body = "intro\n" + stale_window_marker(expected, trucks, nabsa) + "\nmore"
    assert same_stale_window(body, expected, trucks, nabsa) is True
    assert same_stale_window(body, expected, trucks, date(2026, 9, 9)) is False
    assert same_stale_window("no marker here", expected, trucks, nabsa) is False

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


def test_nabsa_lineup_date_from_header():
    from datetime import date as _d

    import loop_detect_stale as lds

    meta = {"header": "Line Up: October 1, 2026 Circ.Nbr.: 183", "circular": "183"}
    assert lds.nabsa_lineup_date(meta) == _d(2026, 10, 1)
    assert lds.nabsa_lineup_date({"lineup_date": "2026-09-30"}) == _d(2026, 9, 30)
    assert lds.nabsa_lineup_date({"header": "garbage"}) is None
    assert lds.nabsa_lineup_date(None) is None


def test_create_stale_issue_invokes_gh(monkeypatch):
    import loop_detect_stale as lds

    seen = {}

    class _P:
        returncode = 0
        stdout = "https://github.com/x/y/issues/9\n"
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return _P()

    monkeypatch.setattr(lds.subprocess, "run", fake_run)
    url = lds.create_stale_issue("x/y", title="t", body="b", priority="priority:P1")
    assert seen["cmd"][:3] == ["gh", "issue", "create"]
    assert url.endswith("/9")

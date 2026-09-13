#!/usr/bin/env python3
"""Loop stage 2 — weekday MAGyP / NABSA stale-data detector.

Fetches live site APIs, compares truck `date` and vessels `meta.lineup_date`
against the previous business day in America/Argentina/Cordoba, and opens a
deduplicated GitHub issue when data looks stale.

Pure date helpers are importable offline (no network) for unit tests.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

ART = ZoneInfo("America/Argentina/Cordoba")
DEFAULT_REPO = "Diegof10/cola-buques-rosario"
DEFAULT_SITE = "https://cola-buques-rosario.vercel.app"
STALE_MARKER_RE = re.compile(
    r"<!--\s*loop:stale-window\s+"
    r"expected=(?P<expected>\d{4}-\d{2}-\d{2})\s+"
    r"trucks=(?P<trucks>\S+)\s+"
    r"nabsa=(?P<nabsa>\S+)\s*-->",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested, no I/O)
# ---------------------------------------------------------------------------


def now_art(now: datetime | None = None) -> datetime:
    """Current time in America/Argentina/Cordoba (or convert `now`)."""
    if now is None:
        return datetime.now(ART)
    if now.tzinfo is None:
        return now.replace(tzinfo=ART)
    return now.astimezone(ART)


def previous_business_day(d: date) -> date:
    """Latest Mon–Fri strictly before `d`.

    Monday → previous Friday; Tue–Sun → walk back past weekends.
    """
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5:  # Sat=5, Sun=6
        cur -= timedelta(days=1)
    return cur


def parse_iso_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD (or ISO datetime prefix) to date; None if missing/bad."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"none", "null", "n/a", "-"}:
        return None
    # Allow full ISO timestamps: take date part
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def is_stale(actual: date | None, expected: date) -> bool:
    """True when actual is missing or strictly older than expected."""
    if actual is None:
        return True
    return actual < expected


def business_days_behind(actual: date | None, expected: date) -> int:
    """Count Mon–Fri steps from actual forward to expected (0 if not behind)."""
    if actual is None:
        return 999
    if actual >= expected:
        return 0
    n = 0
    cur = actual
    while cur < expected:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def choose_priority(
    trucks_stale: bool,
    vessels_stale: bool,
    trucks_behind: int,
    vessels_behind: int,
) -> str:
    """P0 if both sources stale by >1 business day; else P1 when any stale."""
    if (
        trucks_stale
        and vessels_stale
        and trucks_behind > 1
        and vessels_behind > 1
    ):
        return "priority:P0"
    return "priority:P1"


def format_date(d: date | None) -> str:
    return d.isoformat() if d else "missing"


def stale_window_marker(
    expected: date,
    trucks_date: date | None,
    nabsa_date: date | None,
) -> str:
    return (
        f"<!-- loop:stale-window expected={expected.isoformat()} "
        f"trucks={format_date(trucks_date)} nabsa={format_date(nabsa_date)} -->"
    )


def parse_stale_window_marker(text: str | None) -> dict[str, str] | None:
    if not text:
        return None
    m = STALE_MARKER_RE.search(text)
    if not m:
        return None
    return m.groupdict()


def same_stale_window(
    issue_body: str | None,
    expected: date,
    trucks_date: date | None,
    nabsa_date: date | None,
) -> bool:
    """True if an open issue already covers this expected window + stale dates."""
    parsed = parse_stale_window_marker(issue_body)
    if not parsed:
        return False
    return (
        parsed["expected"] == expected.isoformat()
        and parsed["trucks"] == format_date(trucks_date)
        and parsed["nabsa"] == format_date(nabsa_date)
    )


@dataclass
class StaleAssessment:
    expected: date
    trucks_date: date | None
    nabsa_date: date | None
    trucks_stale: bool
    vessels_stale: bool
    trucks_behind: int
    vessels_behind: int
    priority: str

    @property
    def stale(self) -> bool:
        return self.trucks_stale or self.vessels_stale


def assess_staleness(
    *,
    today: date,
    trucks_date: date | None,
    nabsa_date: date | None,
) -> StaleAssessment:
    expected = previous_business_day(today)
    trucks_stale = is_stale(trucks_date, expected)
    vessels_stale = is_stale(nabsa_date, expected)
    trucks_behind = business_days_behind(trucks_date, expected)
    vessels_behind = business_days_behind(nabsa_date, expected)
    priority = choose_priority(
        trucks_stale, vessels_stale, trucks_behind, vessels_behind
    )
    return StaleAssessment(
        expected=expected,
        trucks_date=trucks_date,
        nabsa_date=nabsa_date,
        trucks_stale=trucks_stale,
        vessels_stale=vessels_stale,
        trucks_behind=trucks_behind,
        vessels_behind=vessels_behind,
        priority=priority,
    )


def build_issue_title(assessment: StaleAssessment) -> str:
    return (
        f"[Loop] Datos atrasados: MAGyP {format_date(assessment.trucks_date)} "
        f"/ NABSA {format_date(assessment.nabsa_date)}"
    )


def build_issue_body(
    assessment: StaleAssessment,
    *,
    site_url: str,
    checked_at: datetime,
    trucks_payload: dict[str, Any] | None,
    vessels_meta: dict[str, Any] | None,
    health_payload: dict[str, Any] | None,
    magyp_confirm: dict[str, Any] | None,
) -> str:
    checked_art = now_art(checked_at).strftime("%Y-%m-%d %H:%M:%S ART")
    lines = [
        stale_window_marker(
            assessment.expected, assessment.trucks_date, assessment.nabsa_date
        ),
        "",
        "## Señal: datos atrasados vs día hábil esperado",
        "",
        f"- **Checked at:** {checked_art}",
        f"- **Site:** {site_url}",
        f"- **Expected (prev business day):** `{assessment.expected.isoformat()}`",
        f"- **MAGyP trucks.date:** `{format_date(assessment.trucks_date)}`"
        f" — stale={assessment.trucks_stale}"
        f" (behind {assessment.trucks_behind} business day(s))",
        f"- **NABSA meta.lineup_date:** `{format_date(assessment.nabsa_date)}`"
        f" — stale={assessment.vessels_stale}"
        f" (behind {assessment.vessels_behind} business day(s))",
        f"- **Priority label:** `{assessment.priority}`",
        "",
        "### Evidence — GET /api/trucks (snippet)",
        "",
        "```json",
        _json_snippet(trucks_payload, keys=("date", "updated_at", "source", "total_camiones", "source_note")),
        "```",
        "",
        "### Evidence — GET /api/vessels meta (snippet)",
        "",
        "```json",
        _json_snippet(
            {"meta": vessels_meta} if vessels_meta is not None else None,
            keys=("meta",),
        ),
        "```",
    ]
    if health_payload is not None:
        lines += [
            "",
            "### Evidence — GET /api/health (snippet)",
            "",
            "```json",
            _json_snippet(
                health_payload,
                keys=(
                    "ok",
                    "vessels_updated_at",
                    "vessels_age_seconds",
                    "vessels_stale",
                    "last_refresh_error",
                ),
            ),
            "```",
        ]
    if magyp_confirm is not None:
        lines += [
            "",
            "### Optional MAGyP scrape confirmation (`try_fetch_trucks`)",
            "",
            "```json",
            _json_snippet(
                magyp_confirm,
                keys=("date", "updated_at", "source", "total_camiones", "national_total"),
            ),
            "```",
        ]
    lines += [
        "",
        "---",
        "_Opened by Loop stage 2 detector (`scripts/loop_detect_stale.py`). "
        "No auto-merge. Stage 3 coder not enabled yet._",
        "",
    ]
    return "\n".join(lines)


def _json_snippet(payload: dict[str, Any] | None, keys: tuple[str, ...]) -> str:
    if payload is None:
        return "null"
    slim = {k: payload.get(k) for k in keys}
    return json.dumps(slim, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def http_get_json(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "cola-buques-rosario-loop-detect/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def optional_magyp_confirm(*, timeout: int = 45) -> dict[str, Any] | None:
    """Best-effort live MAGyP scrape via refresh_data.try_fetch_trucks."""
    try:
        from refresh_data import try_fetch_trucks  # type: ignore
    except Exception as ex:  # pragma: no cover - import env dependent
        print(f"note: try_fetch_trucks import skipped: {ex}", file=sys.stderr)
        return None
    try:
        return try_fetch_trucks(timeout=timeout)
    except Exception as ex:  # pragma: no cover
        print(f"note: try_fetch_trucks failed: {ex}", file=sys.stderr)
        return None


def gh_json(args: list[str]) -> Any:
    cmd = ["gh", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"gh failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stderr: {proc.stderr.strip()}"
        )
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def list_open_stale_issues(repo: str) -> list[dict[str, Any]]:
    data = gh_json(
        [
            "issue",
            "list",
            "-R",
            repo,
            "--state",
            "open",
            "--label",
            "signal:data-stale",
            "--label",
            "loop",
            "--json",
            "number,title,body,url,labels",
            "--limit",
            "50",
        ]
    )
    return list(data or [])


def create_stale_issue(
    repo: str,
    *,
    title: str,
    body: str,
    priority: str,
) -> str:
    labels = ["loop", "signal:data-stale", "status:triage", "type:data", priority]
    args = [
        "issue",
        "create",
        "-R",
        repo,
        "--title",
        title,
        "--body",
        body,
    ]
    for lab in labels:
        args.extend(["--label", lab])
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"gh issue create failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    url = (proc.stdout or "").strip()
    return url


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Loop stage 2: detect stale MAGyP/NABSA data and open a GitHub issue."
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print assessment / would-be issue; do not call gh issue create.",
    )
    p.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repo (default: {DEFAULT_REPO})",
    )
    p.add_argument(
        "--site-url",
        default=DEFAULT_SITE,
        help=f"Deployed site base URL (default: {DEFAULT_SITE})",
    )
    p.add_argument(
        "--skip-magyp-scrape",
        action="store_true",
        help="Do not call try_fetch_trucks for confirmation.",
    )
    p.add_argument(
        "--today",
        default=None,
        help="Override 'today' as YYYY-MM-DD (testing).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    site = args.site_url.rstrip("/")
    checked_at = now_art()

    if args.today:
        today = date.fromisoformat(args.today)
    else:
        today = checked_at.date()

    print(f"loop_detect_stale: site={site} today={today.isoformat()} ART")

    trucks_url = f"{site}/api/trucks"
    vessels_url = f"{site}/api/vessels"
    health_url = f"{site}/api/health"

    try:
        trucks = http_get_json(trucks_url)
    except Exception as ex:
        print(f"ERROR fetching {trucks_url}: {ex}", file=sys.stderr)
        return 2

    try:
        vessels = http_get_json(vessels_url)
    except Exception as ex:
        print(f"ERROR fetching {vessels_url}: {ex}", file=sys.stderr)
        return 2

    health: dict[str, Any] | None
    try:
        health = http_get_json(health_url)
    except Exception as ex:
        print(f"note: health fetch skipped: {ex}", file=sys.stderr)
        health = None

    trucks_date = parse_iso_date(trucks.get("date") if isinstance(trucks, dict) else None)
    meta = vessels.get("meta") if isinstance(vessels, dict) else None
    if not isinstance(meta, dict):
        meta = {}
    nabsa_date = parse_iso_date(meta.get("lineup_date"))

    magyp_confirm = None
    if not args.skip_magyp_scrape:
        magyp_confirm = optional_magyp_confirm()

    assessment = assess_staleness(
        today=today,
        trucks_date=trucks_date,
        nabsa_date=nabsa_date,
    )

    print(
        f"expected={assessment.expected.isoformat()} "
        f"trucks={format_date(assessment.trucks_date)} "
        f"(stale={assessment.trucks_stale}, behind={assessment.trucks_behind}) "
        f"nabsa={format_date(assessment.nabsa_date)} "
        f"(stale={assessment.vessels_stale}, behind={assessment.vessels_behind}) "
        f"priority={assessment.priority}"
    )

    if not assessment.stale:
        print("OK: data fresh vs previous business day — no issue.")
        return 0

    title = build_issue_title(assessment)
    body = build_issue_body(
        assessment,
        site_url=site,
        checked_at=checked_at,
        trucks_payload=trucks if isinstance(trucks, dict) else None,
        vessels_meta=meta,
        health_payload=health,
        magyp_confirm=magyp_confirm,
    )

    # Dedup against open loop + signal:data-stale issues
    try:
        open_issues = list_open_stale_issues(args.repo)
    except Exception as ex:
        print(f"ERROR listing issues: {ex}", file=sys.stderr)
        if args.dry_run:
            print("--- dry-run: would create issue (could not list existing) ---")
            print(f"title: {title}")
            print(body)
            return 0
        return 3

    for iss in open_issues:
        if same_stale_window(
            iss.get("body"),
            assessment.expected,
            assessment.trucks_date,
            assessment.nabsa_date,
        ):
            url = iss.get("url") or f"#{iss.get('number')}"
            print(f"DEDUP: open issue already covers this stale window: {url}")
            return 0

    if args.dry_run:
        print("--- dry-run: would create issue ---")
        print(f"title: {title}")
        print(f"labels: loop, signal:data-stale, status:triage, type:data, {assessment.priority}")
        print(body)
        return 0

    try:
        url = create_stale_issue(
            args.repo,
            title=title,
            body=body,
            priority=assessment.priority,
        )
    except Exception as ex:
        print(f"ERROR creating issue: {ex}", file=sys.stderr)
        return 4

    print(f"CREATED: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

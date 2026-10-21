# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The Running Call's calendar and size rules, as published, in code: cycles, deadlines, orbit limits.

Source: the CHEOPS Guest Observers Running Call page (last updated 15 October 2026) and its Policies and
Procedures document, CHEOPS-EST-SCI-TN-018 v1.0 (8 July 2026), both read on 21 October 2026. The official
documents govern; these functions only restate them so a proposer can plan, and every rule names where it
comes from (:data:`RULE_SOURCES`).

* The Running Call's observing period is 1 October 2026 to 31 December 2029. It spans the last quarter of the
  first extended mission (EM1, which ends 31 December 2026) and the whole second extended mission (EM2,
  1 January 2027 to 31 December 2029; P&P section 2).
* Proposals are grouped into monthly cycles; a cycle's deadline is 23:59 CET/CEST on its last calendar day.
* The TAC evaluates in the first weeks of the following month; outcomes in the last week of month M+1;
  Phase 2 in M+2; earliest start of observations in M+3, nominal start in M+4 (P&P Table 1). The call page
  says awarded programmes "ideally start three months after the closing date".
* Regular: up to 120 orbits, any month. Large: 121-500 orbits, April and October cycles only, 2026-2029.
  HST/JWST coordinated fast-track: up to 25 orbits (up to 50 only in exceptional, justified cases), any
  month, no TAC.
* A visit is at least 1 orbit (5 or more recommended for high precision) and at most 100 orbits.
* Proposals submitted 8 July - 30 September 2026 could only ask for observations before 31 December 2026;
  the last ordinary batch is expected to be September 2029 (P&P Table 1, notes 1 and 3).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

CALL_START = date(2026, 10, 1)   # the Running Call's observing period (P&P section 1)
CALL_END = date(2029, 12, 31)
EM2_FROM = date(2027, 1, 1)      # EM1 runs to 31 December 2026; EM2 from 1 January 2027 (P&P section 2)
FIRST_CYCLE = (2026, 7)          # the Running Call opened on 8 July 2026
RESTRICTED_UNTIL = (2026, 9)     # cycles up to September 2026: observations only before 31 December 2026
FINAL_ORDINARY_CYCLE = (2029, 9)  # P&P Table 1, note 3
PARIS = "Europe/Paris"

CALL_PAGE = "https://www.cosmos.esa.int/web/cheops-guest-observers-programme/cheops-running-call"
POLICIES = ("Policies and Procedures, Running Call, CHEOPS-EST-SCI-TN-018 v1.0 (8 July 2026), linked from "
            + CALL_PAGE)
RULE_SOURCES = {
    "window": f"{CALL_PAGE} (observation window); {POLICIES}, section 1",
    "deadline": f"{CALL_PAGE} (Monthly Proposal Submission Deadline); {POLICIES}, Table 1",
    "timeline": f"{POLICIES}, Table 1 (indicative timeline)",
    "orbits": f"{CALL_PAGE} (Regular and Large Programmes); {POLICIES}, sections 4.1 and 4.4",
    "visits": f"{POLICIES}, section 4.4",
}


@dataclass(frozen=True)
class Programme:
    key: str
    label: str
    min_orbits: int
    max_orbits: int
    months: tuple[int, ...] | None  # cycles in which it may be submitted; None = every month
    years: tuple[int, ...] | None
    tac: bool
    exceptional_max: int | None = None


PROGRAMMES = {
    "regular": Programme("regular", "Regular programme", 1, 120, None, None, True),
    "large": Programme("large", "Large programme", 121, 500, (4, 10), (2026, 2027, 2028, 2029), True),
    "fasttrack": Programme("fasttrack", "HST/JWST coordinated fast-track programme", 1, 25, None, None, False,
                           exceptional_max=50),
}
VISIT_MIN_ORBITS, VISIT_RECOMMENDED_MIN, VISIT_MAX_ORBITS = 1, 5, 100


def programme(key: str) -> Programme:
    try:
        return PROGRAMMES[key]
    except KeyError:
        raise ValueError(f"programme must be one of {', '.join(PROGRAMMES)}") from None


# ---------------------------------------------------------------- Paris time


def _paris():
    """The Europe/Paris zone from the system's tz database, or None when it is missing (then the EU rule below)."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(PARIS)
    except Exception:  # noqa: BLE001 (no tz database: fall back to the EU rule)
        return None


def _last_sunday(year: int, month: int) -> int:
    last = calendar.monthrange(year, month)[1]
    return last - (date(year, month, last).weekday() + 1) % 7


def eu_summer_time(utc: datetime) -> bool:
    """Whether CEST applies at this UTC instant: from 01:00 UTC on the last Sunday of March to 01:00 UTC on the
    last Sunday of October (EU Directive 2000/84/EC). Used when the system has no tz database."""
    utc = utc.astimezone(timezone.utc)
    y = utc.year
    start = datetime(y, 3, _last_sunday(y, 3), 1, tzinfo=timezone.utc)
    end = datetime(y, 10, _last_sunday(y, 10), 1, tzinfo=timezone.utc)
    return start <= utc < end


def paris_local(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """An aware datetime for a Paris wall-clock time."""
    tz = _paris()
    if tz is not None:
        return datetime(year, month, day, hour, minute, tzinfo=tz)
    naive = datetime(year, month, day, hour, minute)
    # Wall clock to UTC: try CEST first, keep it only if CEST is in force then.
    as_cest = (naive - timedelta(hours=2)).replace(tzinfo=timezone.utc)
    offset = 2 if eu_summer_time(as_cest) else 1
    return naive.replace(tzinfo=timezone(timedelta(hours=offset), "CEST" if offset == 2 else "CET"))


def zone_name(dt: datetime) -> str:
    """CET or CEST for an aware datetime."""
    off = dt.utcoffset()
    return "CEST" if off == timedelta(hours=2) else "CET" if off == timedelta(hours=1) else (dt.tzname() or "?")


def to_paris(dt: datetime) -> datetime:
    tz = _paris()
    if tz is not None:
        return dt.astimezone(tz)
    utc = dt.astimezone(timezone.utc)
    off = 2 if eu_summer_time(utc) else 1
    return utc.astimezone(timezone(timedelta(hours=off), "CEST" if off == 2 else "CET"))


# ---------------------------------------------------------------- cycles


def add_months(y: int, m: int, k: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + k
    return i // 12, i % 12 + 1


def add_months_date(d: date, k: int) -> date:
    y, m = add_months(d.year, d.month, k)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def parse_cycle(text: str) -> tuple[int, int]:
    try:
        y, m = (int(x) for x in str(text).split("-"))
    except ValueError:
        raise ValueError(f"cycle must be YYYY-MM, got {text!r}") from None
    if not 1 <= m <= 12:
        raise ValueError(f"cycle month must be 01-12, got {text!r}")
    return y, m


def deadline(year: int, month: int) -> datetime:
    """The cycle's deadline: 23:59 Paris time (CET or CEST, as applicable) on the month's last calendar day."""
    return paris_local(year, month, calendar.monthrange(year, month)[1], 23, 59)


def cycle_open(year: int, month: int) -> datetime:
    return paris_local(year, month, 1, 0, 0)


def current_cycle(now: datetime) -> tuple[int, int]:
    """The cycle a proposal submitted at ``now`` falls in: the Paris calendar month, or the next one once that
    month's 23:59 deadline has passed (conservative: the last minute of the month counts as late)."""
    local = to_paris(now)
    y, m = local.year, local.month
    return add_months(y, m, 1) if now >= deadline(y, m) else (y, m)


def _allowed(prog: Programme, y: int, m: int) -> bool:
    return (prog.months is None or m in prog.months) and (prog.years is None or y in prog.years)


def next_cycle(now: datetime, prog: Programme | str = "regular") -> tuple[int, int] | None:
    """The first cycle at or after ``now`` whose deadline is still ahead and that accepts this programme type,
    within the Running Call (up to December 2029), or None."""
    prog = programme(prog) if isinstance(prog, str) else prog
    y, m = max(current_cycle(now), FIRST_CYCLE)
    while (y, m) <= (CALL_END.year, CALL_END.month):
        if _allowed(prog, y, m) and deadline(y, m) > now:
            return y, m
        y, m = add_months(y, m, 1)
    return None


def cycle_info(year: int, month: int, prog: Programme | str, now: datetime) -> dict:
    """Everything the calendar says about one cycle for one programme type, with errors and warnings."""
    prog = programme(prog) if isinstance(prog, str) else prog
    dl = deadline(year, month)
    errors, warnings = [], []
    if (year, month) < FIRST_CYCLE:
        errors.append(f"{year}-{month:02d} is before the Running Call opened (July 2026).")
    if (year, month) > (CALL_END.year, CALL_END.month):
        errors.append(f"{year}-{month:02d} is after the Running Call observing period ends (31 December 2029).")
    if dl <= now:
        errors.append(f"The {year}-{month:02d} deadline ({dl.isoformat()}) has passed.")
    if not _allowed(prog, year, month):
        errors.append(f"{prog.label}s may only be submitted in the April and October cycles, 2026-2029; "
                      f"{year}-{month:02d} is not one.")
    if FIRST_CYCLE <= (year, month) <= RESTRICTED_UNTIL:
        warnings.append("Cycles from July to September 2026 may only request observations executed by "
                        "31 December 2026 (P&P Table 1, note 1).")
    if (year, month) > FINAL_ORDINARY_CYCLE and not errors:
        warnings.append("The final ordinary Running Call batch is expected to be September 2029 "
                        "(P&P Table 1, note 3); check the call page before relying on a later cycle.")
    close = dl.date()
    m1, m2, m3, m4 = (add_months(year, month, k) for k in (1, 2, 3, 4))
    earliest = date(*m3, 1)
    return {
        "cycle": f"{year}-{month:02d}",
        "programme": prog.key,
        "opens_local": cycle_open(year, month).isoformat(),
        "deadline_local": dl.isoformat(),
        "deadline_zone": zone_name(dl),
        "deadline_utc": dl.astimezone(timezone.utc).isoformat(),
        "time_left_days": round((dl - now).total_seconds() / 86400.0, 2),
        "tac": ("first weeks of " + f"{m1[0]}-{m1[1]:02d}") if prog.tac
               else "no TAC: straight to feasibility evaluation and scheduling",
        "outcome_expected": f"last week of {m1[0]}-{m1[1]:02d}",
        "phase2": f"{m2[0]}-{m2[1]:02d} (awarded programmes only)",
        "earliest_start": earliest.isoformat(),
        "earliest_start_note": f"month M+3 ({m3[0]}-{m3[1]:02d}), subject to scheduling and operational constraints",
        "nominal_start_month": f"{m4[0]}-{m4[1]:02d}",
        "about_three_months_after_close": add_months_date(close, 3).isoformat(),
        "observable_by_note": ("At least one target or event should become observable no later than "
                               f"{add_months_date(close, 6).isoformat()} (6 months after the deadline), "
                               "or the Scientific Justification must justify a later window (P&P section 4.1)."),
        "errors": errors,
        "warnings": warnings,
        "sources": [RULE_SOURCES["deadline"], RULE_SOURCES["timeline"]],
    }


# ---------------------------------------------------------------- orbits and the window


def check_orbits(orbits: int | None, prog: Programme | str) -> dict:
    """The orbit request against the programme type's limits."""
    prog = programme(prog) if isinstance(prog, str) else prog
    errors, warnings, hints = [], [], []
    if orbits is None:
        return {"orbits": None, "limit": [prog.min_orbits, prog.max_orbits], "errors": [], "warnings": [],
                "hints": ["No --orbits given: the pack estimates a number below; enter your own once the ETC agrees."],
                "source": RULE_SOURCES["orbits"]}
    if orbits < 1:
        errors.append("The request must be at least 1 orbit.")
    elif prog.key == "regular" and orbits > prog.max_orbits:
        errors.append(f"Regular programmes are capped at {prog.max_orbits} orbits; {orbits} orbits "
                      + ("would be a Large programme (April or October cycles only)." if orbits <= 500
                         else "exceeds even a Large programme (500)."))
    elif prog.key == "large" and orbits < prog.min_orbits:
        errors.append(f"Large programmes request 121-500 orbits; {orbits} orbits is a Regular programme.")
    elif prog.key == "large" and orbits > prog.max_orbits:
        errors.append(f"Large programmes are capped at {prog.max_orbits} orbits.")
    elif prog.key == "fasttrack" and orbits > (prog.exceptional_max or prog.max_orbits):
        errors.append(f"HST/JWST fast-track requests are capped at {prog.max_orbits} orbits "
                      f"({prog.exceptional_max} only in exceptional, justified cases).")
    elif prog.key == "fasttrack" and orbits > prog.max_orbits:
        warnings.append(f"Above {prog.max_orbits} orbits a fast-track request is considered only in exceptional, "
                        "well-justified cases (up to 50).")
    if prog.key == "fasttrack":
        hints.append("Fast-track proposals need evidence that the CHEOPS PI is PI or Co-I of an awarded HST or JWST "
                     "programme executing during EM2 (P&P sections 4.4 and 5.2.2).")
    return {"orbits": orbits, "limit": [prog.min_orbits, prog.max_orbits], "errors": errors, "warnings": warnings,
            "hints": hints, "source": RULE_SOURCES["orbits"]}


def check_visit(orbits_per_visit: int) -> list[str]:
    out = []
    if orbits_per_visit < VISIT_MIN_ORBITS:
        out.append("A visit is at least 1 orbit.")
    elif orbits_per_visit < VISIT_RECOMMENDED_MIN:
        out.append("Visits needing high photometric precision should be at least 5 orbits, for detrending "
                   "(P&P section 4.4).")
    if orbits_per_visit > VISIT_MAX_ORBITS:
        out.append("A visit should not exceed 100 orbits (one week's activity plan; P&P section 4.4).")
    return out


def check_window(start: date, end: date, earliest: date | None = None) -> dict:
    """A requested observing window against the Running Call's observing period and the cycle's earliest start."""
    errors, warnings = [], []
    if end < start:
        errors.append("The window ends before it starts.")
    if start < CALL_START or end > CALL_END:
        errors.append(f"The window {start}..{end} leaves the Running Call observing period "
                      f"({CALL_START}..{CALL_END}).")
    if earliest and start < earliest:
        warnings.append(f"Observations cannot start before about {earliest} for this cycle (month M+3); "
                        "the usable window starts then.")
    return {"start": start.isoformat(), "end": end.isoformat(), "errors": errors, "warnings": warnings,
            "source": RULE_SOURCES["window"]}

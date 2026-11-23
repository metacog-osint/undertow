"""When what an Undertow item describes happened (feed contract revision 2.1: event_start, event_end,
event_time_precision).

A disclosure's time is the period its publisher gives for the action or the activity. A period can run past the
report that states it (Meta's "H2 2026" in an August report), so its end is held at the month of the disclosure: a
publisher cannot have reported what had not happened yet.

Two kinds of item have no such period, and neither is given one:
- OpenAI's `period` is only the month of the post, so the item's time is the disclosure itself.
- A reporter's item with no stated activity period covers its reports: event_start is the first report and there is
  no event_end, because a reporter going quiet is not evidence the operation stopped (the contract reads the interval
  as first report to data_as_of, the last report).
"""
from __future__ import annotations

import re

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR = re.compile(r"^(\d{4})$")
_HALF = re.compile(r"^H([12]) (\d{4})$")
_RANGE = re.compile(r"^(\d{4}-\d{2}) to (\d{4}-\d{2})$")


def _month(year: int | str, month: int | str) -> str:
    return f"{int(year):04d}-{int(month):02d}-01T00:00:00Z"


def period_months(period) -> tuple[str, str] | None:
    """A publisher's period as (first month, last month), each at midnight UTC on the 1st; None if not understood."""
    text = str(period or "").strip()
    if m := _MONTH.match(text):
        if 1 <= int(m[2]) <= 12:
            return _month(m[1], m[2]), _month(m[1], m[2])
        return None
    if m := _YEAR.match(text):
        return _month(m[1], 1), _month(m[1], 12)
    if m := _HALF.match(text):
        first = 1 if m[1] == "1" else 7
        return _month(m[2], first), _month(m[2], first + 5)
    if m := _RANGE.match(text):
        a, b = period_months(m[1]), period_months(m[2])
        if a and b and a[0] <= b[0]:
            return a[0], b[0]
    return None


def _stated(value) -> tuple[str, str] | None:
    """A date the register states, as (time, precision)."""
    text = str(value or "").strip()
    if _DAY.match(text):
        return f"{text}T00:00:00Z", "day"
    if m := _MONTH.match(text):
        return _month(m[1], m[2]), "month"
    return None


def _moment(value, precision=None) -> dict:
    """One time as it stands: a date-only value reads at day precision."""
    text = str(value or "")
    if _DAY.match(text):
        return {"event_start": f"{text}T00:00:00Z", "event_time_precision": "day"}
    if not text.endswith("Z"):
        return {}
    return {"event_start": text, **({"event_time_precision": precision} if precision else {})}


def fields(r: dict) -> dict:
    """The event_* fields of one record."""
    disclosed = r.get("disclosed_at")
    act = r.get("activity")
    if act:
        ap = act.get("activity_period") or {}
        start, end = _stated(ap.get("from")), _stated(ap.get("to"))
        if start and end and start[0] <= end[0]:
            coarse = "month" if "month" in (start[1], end[1]) else "day"
            if coarse == "month":                     # both ends read at the whole month
                start, end = (start[0][:8] + "01T00:00:00Z", ""), (end[0][:8] + "01T00:00:00Z", "")
            return {"event_start": start[0], "event_end": end[0], "event_time_precision": coarse}
        return _moment(act.get("first_report")) or _moment(disclosed, r.get("disclosed_precision"))
    if r.get("publisher") == "openai":
        return _moment(disclosed, r.get("disclosed_precision"))
    span = period_months(r.get("period"))
    if not span:
        return _moment(disclosed, r.get("disclosed_precision"))
    first, last = span
    if disclosed:
        held = str(disclosed)[:7] + "-01T00:00:00Z"
        if first > held:                              # a period after its own report: the report's date stands
            return _moment(disclosed, r.get("disclosed_precision"))
        last = min(last, held)
    return {"event_start": first, "event_end": last, "event_time_precision": "month"}

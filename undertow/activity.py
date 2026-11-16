"""Reported activity: one item per operation and reporter, kept apart from disclosures (decision 1, Tom, 16 Nov 2026).

A disclosure is a platform's or a government's report of an operation it acted on or named (grade A2), and it
arrives 1 to 8 months after the activity. A reported-activity item says that an independent reporter has reported an
operation while it runs: who reported it, the first and last report, how many reports, and a state:

- "active": the reporter's last report is no more than QUIET_DAYS old;
- "quiet": no report from this reporter for longer than that.

Never "ended": a reporter falling silent is not evidence that an operation stopped. QUIET_DAYS is 180 (Tom,
16 Nov 2026): DFRLab's 15 reports on tracked operations span 30 months, so a shorter window would mark most
operations quiet most of the time. Graded by the reporter (B2 or B3, reporters.REPORTERS).

Two ways in (decision 2):
1. Tracked operations, automatically: the reporter lanes' report records, grouped here by (reporter, operation).
2. New activity, by hand: rows Tom promotes from the private triage list into config/register/watch.json. Each row
   is a cited, hand-kept entry; it publishes as a reported-activity item with publisher "watch".

Origin (decision 4): a reporter lane never adds an origin. A watch row's origin counts toward Undertow's origin
confidence only when Tom has checked the row (`checked_by`) and the reporter shows its own evidence for the origin
(`origin_evidence` "own"), not when it repeats a platform's or a government's attribution ("cites-other"). Even then
the cap stays Moderate (analysis.py): origin is easy to fake.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from . import reporters, text

ROOT = Path(__file__).resolve().parents[1]
WATCH_PATH = ROOT / "config" / "register" / "watch.json"
QUIET_DAYS = 180
GRADES = {"B2", "B3"}
EVIDENCE = {"own", "cites-other", "none"}


def _day(s: str) -> date:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date() if "T" in s else date.fromisoformat(s[:10])


def state(last: str, today: date) -> str:
    return "active" if (today - _day(last)).days <= QUIET_DAYS else "quiet"


def _title(op_name: str, who: str, st: str, last: str) -> str:
    # A name match says the reporter wrote about the operation, not that it found the operation running, so the title
    # states the report and puts the state in brackets.
    if st == "active":
        return f"{op_name}: reported by {who}, last on {last[:10]} (active)"
    return f"{op_name}: last reported by {who} on {last[:10]} (quiet)"


def aggregate(reports_by_lane: dict[str, list[dict]], today: date) -> list[dict]:
    """Report records from the reporter lanes -> one reported-activity record per (reporter, tracked operation)."""
    names = {o["id"]: o["name"] for o in text.operations()}
    groups: dict[tuple[str, str], list[dict]] = {}
    for lane, recs in reports_by_lane.items():
        for r in recs or []:
            for op in r.get("named_operations") or []:
                if op in names:
                    groups.setdefault((lane, op), []).append(r)
    out = []
    for (lane, op), rs in sorted(groups.items()):
        rep = reporters.REPORTERS[lane]
        rs = sorted(rs, key=lambda r: (r["disclosed_at"], r["key"]))
        first, last = rs[0]["disclosed_at"], rs[-1]["disclosed_at"]
        st = state(last, today)
        tech: dict[str, dict] = {}
        for r in rs:
            for d in r.get("disarm") or []:
                tech.setdefault(d["id"], d)
        key = f"{lane}:activity:{op}"
        out.append({
            "key": key, "lane": lane, "publisher": lane, "grade": rep.grade,
            "disclosure": {"id": key, "title": f"{rep.name} reporting on {names[op]}", "url": rs[-1]["url"]},
            "title": _title(names[op], rep.name, st, last),
            "operation_name": names[op],
            "named_operations": [op],
            "period": last[:7],
            "disclosed_at": last,
            "disclosed_precision": None,
            "origin": [], "origin_text": None, "origin_wording": None, "origin_level": "not read",
            "alignment": [],
            "targets": [],
            "target_regions": sorted({x for r in rs for x in r.get("target_regions") or []}),
            "target_text": None,
            "countries_named": sorted({x for r in rs for x in r.get("countries_named") or []}),
            "platforms": sorted({x for r in rs for x in r.get("platforms") or []}),
            "counts": {},
            "summary": None, "summary_note": None,
            "orgs": [],
            "url": rs[-1]["url"],
            "withheld": 0,
            "disarm": sorted(tech.values(), key=lambda d: d["id"]),
            "activity": {
                "unit": "reported activity", "operation": op, "operation_name": names[op],
                "reporter": lane, "reporter_name": rep.credit, "grade": rep.grade,
                "first_report": first, "last_report": last, "reports": len(rs), "state": st,
                "quiet_after_days": QUIET_DAYS, "state_as_of": today.isoformat(),
                "report_links": [{"date": r["disclosed_at"], "url": r["url"]} for r in reversed(rs)],
                "source": "reporter lane (tracked operation matched by name)",
            },
        })
    return out


MAPPED_AT = "countries named in the reports that a platform's or the EEAS's disclosure of this operation records as targets"


def place(records: list[dict]) -> None:
    """Map a reporter lane's item only at targets (Tom, 16 Nov 2026: "Mark only target countries on the map").

    A reporter lane reads no targets, only the countries its reports name, and those often include where the
    operators are said to be (Storm-1516's CORRECTIV story names Russia and the US). So the item's targets are the
    countries named in its reports that a disclosure of the same operation (grade A2) records as targets; an item
    with none is not marked on the map. The countries named stay in `countries_named`. Watch rows keep the countries
    Tom entered as targets. Sets `targets` in place, on reporter-lane records only."""
    disclosed: dict[str, set] = {}
    for r in records:
        if r.get("activity"):
            continue
        for op in r.get("named_operations") or []:
            disclosed.setdefault(op, set()).update(r.get("targets") or [])
    for r in records:
        a = r.get("activity")
        if not a or r.get("publisher") == "watch":
            continue
        r["targets"] = sorted(set(r.get("countries_named") or []) & disclosed.get(a["operation"], set()))
        a["mapped_at"] = MAPPED_AT


# --- the hand-kept watch register (config/register/watch.json) ---------------------------------------------------

def load_watch(path: Path = WATCH_PATH) -> dict:
    if not path.exists():
        return {"register": "watch", "reporter_hosts": [], "rows": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_label(s: str) -> bool:
    """A label that the scrubber leaves untouched: no link, handle, domain or run of unknown capitalised words."""
    out, n = text.scrub(s)
    return n == 0 and out == s


def check_watch(reg: dict) -> list[str]:
    """Problems with the register; collect refuses the lane when there are any."""
    errs = []
    hosts = reg.get("reporter_hosts") or []
    if any(not h.startswith("https://") or not h.endswith("/") for h in hosts):
        errs.append("reporter_hosts must be https:// prefixes ending in /")
    ops = {o["id"] for o in text.operations()}
    seen = set()
    for i, row in enumerate(reg.get("rows") or []):
        rid = row.get("id") or f"row {i}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,60}", row.get("id") or ""):
            errs.append(f"{rid}: id must be a lower-case slug")
        if rid in seen:
            errs.append(f"{rid}: duplicate id")
        seen.add(rid)
        if not row.get("operation") or not _clean_label(row["operation"]):
            errs.append(f"{rid}: operation label missing, or the scrubber would change it (no names, links or handles)")
        rep = row.get("reporter") or {}
        if not rep.get("name") or rep.get("grade") not in GRADES:
            errs.append(f"{rid}: reporter needs a name and a grade of B2 or B3")
        if not rep.get("terms"):
            errs.append(f"{rid}: reporter terms not recorded (read them before entering a row)")
        for k in ("first_report", "last_report"):
            rp = row.get(k) or ({} if k == "last_report" else None)
            if rp is None:
                errs.append(f"{rid}: first_report missing")
                continue
            if not rp:
                continue
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rp.get("date") or ""):
                errs.append(f"{rid}: {k}.date must be YYYY-MM-DD")
            if not any((rp.get("url") or "").startswith(h) for h in hosts):
                errs.append(f"{rid}: {k}.url must be on a reporter host listed in reporter_hosts")
        for cc in (row.get("countries") or []) + (row.get("origin") or []):
            if not re.fullmatch(r"[A-Z]{2}", cc):
                errs.append(f"{rid}: country codes are ISO alpha-2 ({cc!r})")
        if row.get("origin") and row.get("origin_evidence") not in EVIDENCE:
            errs.append(f"{rid}: origin_evidence must be one of {sorted(EVIDENCE)}")
        if row.get("tracked_operation") and row["tracked_operation"] not in ops:
            errs.append(f"{rid}: tracked_operation {row['tracked_operation']!r} is not in config/operations.json")
    return errs


def origin_counts(row: dict) -> bool:
    """Decision 4: only a row Tom has checked, whose reporter shows its own evidence for the origin."""
    return bool(row.get("origin") and row.get("checked_by") and row.get("origin_evidence") == "own")


def watch_records(reg: dict, today: date) -> list[dict]:
    out = []
    for row in reg.get("rows") or []:
        rep = row["reporter"]
        first = row["first_report"]
        last = row.get("last_report") or first
        st = state(last["date"], today)
        counts = origin_counts(row)
        key = f"watch:{row['id']}"
        group = "watch:" + re.sub(r"[^a-z0-9]+", "-", rep["name"].lower()).strip("-")
        out.append({
            "key": key, "lane": "watch", "publisher": "watch", "grade": rep["grade"], "independence_group": group,
            "reporter": rep,
            "disclosure": {"id": key, "title": f"{rep['name']} reporting on {row['operation']}", "url": last["url"]},
            "title": _title(row["operation"], rep["name"], st, last["date"]),
            "operation_name": row["operation"],
            "named_operations": [row["tracked_operation"]] if row.get("tracked_operation") else [],
            "period": last["date"][:7],
            "disclosed_at": last["date"] + "T00:00:00Z",
            "disclosed_precision": "day",
            "origin": list(row.get("origin") or []) if counts else [],
            "origin_text": None,
            "origin_wording": row.get("attribution_wording"),
            "origin_level": ("reported, checked by " + row["checked_by"]) if counts else (
                "reported, not counted (" + ("not checked" if not row.get("checked_by") else
                                             "the reporter cites another's attribution") + ")"
                if row.get("origin") else "none stated"),
            "origin_reported": list(row.get("origin") or []),
            "alignment": [],
            "targets": list(row.get("countries") or []),
            "target_regions": [], "target_text": None, "countries_named": [],
            "platforms": sorted(row.get("platforms") or []),
            "counts": {}, "summary": None, "summary_note": None, "orgs": [],
            "url": last["url"], "withheld": 0, "disarm": [],
            "activity": {
                "unit": "reported activity", "operation": row.get("tracked_operation"),
                "operation_name": row["operation"], "reporter": "watch", "reporter_name": rep["name"],
                "grade": rep["grade"], "first_report": first["date"], "last_report": last["date"],
                "reports": int(row.get("reports") or (2 if row.get("last_report") else 1)), "state": st,
                "quiet_after_days": QUIET_DAYS, "state_as_of": today.isoformat(),
                "report_links": [x for x in ([last] if row.get("last_report") else []) + [first]],
                "source": "watch register (entered by hand from the private triage list)",
                "checked_by": row.get("checked_by"), "checked_on": row.get("checked_on"),
                "closed_into": row.get("closed_into"),
            },
        })
    return out

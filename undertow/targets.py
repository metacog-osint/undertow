"""Reviewed target mappings: config/register/targets.json.

A stored target is a country the cited report itself states as targeted. Most targets are read by a rule: Meta's
Targets column, TikTok's "targeted ..." sentence, and, for the reporter lanes, the countries their feed text names
that a disclosure of the same operation records as targets (activity.place). A rule can misread a report: a region
("the Baltic states") names no country, a feed description can name a country the report does not target, and a
diaspora is an audience, not a place. Each row of this register is a reading of the report itself and wins over the
rule, for one disclosed item (`key`) or for one reporter's report (`report_url`).

A row keeps the value it replaced (`replaces`), and history/ keeps the earlier item, so no earlier mapping is lost.
Rows hold facts and a pointer to where the report states them (`basis`), never a reporter's own text.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "config" / "register" / "targets.json"
FIELDS = {"key", "report_url", "targets", "target_regions", "countries_named", "audience", "basis", "replaces",
          "reviewed_by", "reviewed_at"}
REVIEWED_BY = "tic-analyst"       # an analyst checked the row against the report
MACHINE_READ = "machine-read"     # read from the report by machine; no analyst has checked it yet
READERS = {REVIEWED_BY: "checked against the report by an analyst",
           MACHINE_READ: "read from the report by machine, not yet checked by an analyst"}
REPORT_HOSTS = ("https://dfrlab.org/", "https://checkfirst.network/", "https://correctiv.org/")


def load(path: Path = REGISTER) -> dict:
    if not path.exists():
        return {"rows": []}
    return json.loads(path.read_text(encoding="utf-8"))


def by_key(reg: dict | None = None) -> dict[str, dict]:
    return {r["key"]: r for r in (reg or load())["rows"] if r.get("key")}


def by_report(reg: dict | None = None) -> dict[str, dict]:
    return {r["report_url"]: r for r in (reg or load())["rows"] if r.get("report_url")}


def check(reg: dict | None = None) -> list[str]:
    """Errors in the register: unknown fields, a row for neither or both of an item and a report, codes that are not
    ISO 3166-1 alpha-2, no basis, no earlier value, a reviewer other than the public name, a bad date."""
    from tic_doctrine import geo
    reg = reg or load()
    errs, seen = [], set()
    for i, r in enumerate(reg.get("rows") or []):
        at = f"targets.json row {i + 1}"
        extra = set(r) - FIELDS
        if extra:
            errs.append(f"{at}: unknown fields {sorted(extra)}")
        if bool(r.get("key")) == bool(r.get("report_url")):
            errs.append(f"{at}: needs exactly one of key and report_url")
        ident = r.get("key") or r.get("report_url")
        if ident in seen:
            errs.append(f"{at}: second row for {ident}")
        seen.add(ident)
        if r.get("report_url") and not str(r["report_url"]).startswith(REPORT_HOSTS):
            errs.append(f"{at}: report_url is not a reporter's page")
        for fld in ("targets", "countries_named"):
            for cc in r.get(fld) or []:
                if not (isinstance(cc, str) and re.fullmatch(r"[A-Z]{2}", cc) and geo.name(cc)):
                    errs.append(f"{at}: {fld} has {cc!r}, not an ISO 3166-1 alpha-2 code")
        if not isinstance(r.get("targets"), list) or not isinstance(r.get("target_regions", []), list):
            errs.append(f"{at}: targets and target_regions must be lists")
        if not r.get("basis"):
            errs.append(f"{at}: no basis (where the report states the targets)")
        if not isinstance(r.get("replaces"), dict):
            errs.append(f"{at}: no replaces (the value the rule gave before this reading)")
        if r.get("reviewed_by") not in READERS:
            errs.append(f"{at}: reviewed_by must be one of {sorted(READERS)}")
        try:
            date.fromisoformat(r.get("reviewed_at") or "")
        except ValueError:
            errs.append(f"{at}: reviewed_at is not an ISO date")
    return errs


def analyst_checked(row: dict | None) -> bool:
    return bool(row) and row.get("reviewed_by") == REVIEWED_BY


def review_note(row: dict) -> dict:
    return {"basis": row["basis"], "reviewed_by": row["reviewed_by"], "reviewed_at": row["reviewed_at"],
            "note": READERS[row["reviewed_by"]], "replaces": row["replaces"]}


def human_review(r: dict) -> str:
    """The item's human_review (vocab enums): for the EEAS register's items, "full" only when the register says an
    analyst read its rows against the report (`reviewed_by` "tic-analyst"), else "none" (read from the PDF by
    machine); "sampled" where an analyst checked the item's targets against the report (a person looked at that
    part of the item, not the whole item); otherwise "none", including targets read from the report by machine."""
    if r.get("publisher") == "eeas":
        return "full" if (r.get("register") or {}).get("reviewed_by") == REVIEWED_BY else "none"
    if (r.get("target_review") or {}).get("reviewed_by") == REVIEWED_BY or (r.get("activity") or {}).get("reports_checked"):
        return "sampled"
    return "none"


def apply(records: list[dict], rows: dict[str, dict] | None = None) -> None:
    """Rows keyed by item: set the reviewed targets, regions, audience and countries named, in place. Reporter
    lanes' reports are applied in activity.place."""
    rows = by_key() if rows is None else rows
    for r in records:
        row = rows.get(r.get("key"))
        if not row:
            continue
        r["targets"] = list(row["targets"])
        r["target_regions"] = list(row.get("target_regions") or [])
        if "countries_named" in row:
            r["countries_named"] = list(row["countries_named"])
        if row.get("audience"):
            r["audience"] = row["audience"]
        r["target_review"] = review_note(row)


def keyword_matched(records: list[dict], rows_key: dict | None = None, rows_report: dict | None = None) -> list[dict]:
    """Items whose targets or target regions a rule read from prose and no row has reviewed, each with the sentence
    the rule read where Undertow keeps it. A reporter's text is never kept, so its rows give the report to read."""
    rows_key = by_key() if rows_key is None else rows_key
    rows_report = by_report() if rows_report is None else rows_report
    from undertow import feed
    out = []
    for r in records:
        if r.get("publisher") in ("watch", "eeas", "meta") or r.get("key") in rows_key:
            continue   # hand-entered from the report, or read from Meta's Targets column, or already reviewed
        if not (r.get("targets") or r.get("target_regions")):
            continue
        base = {"id": feed.item_id(r["key"]), "key": r["key"], "publisher": r["publisher"], "title": r["title"],
                "targets": r.get("targets") or [], "target_regions": r.get("target_regions") or []}
        if r.get("activity"):
            reps = [x for x in r.get("_reports") or [] if x["url"] not in rows_report]
            if not reps:
                continue
            base["reports"] = [{"url": x["url"], "countries_named": x["countries_named"],
                                "target_regions": x["target_regions"]} for x in reps]
            base["sentence"] = None
            base["rule"] = "countries the feed text names that a disclosure of the operation records as targets"
        else:
            base["sentence"] = r.get("target_text") or (r.get("summary") or "")[:400] or None
            base["rule"] = ("TikTok's 'targeted ...' sentence" if r["publisher"] == "tiktok"
                            else "regions named in the publisher's description")
        out.append(base)
    return out

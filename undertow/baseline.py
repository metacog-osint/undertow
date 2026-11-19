"""Baseline per layer (Tom, 19 Nov 2026, ideas#16; default accepted the same day). Described, never rated.

1. Dismantled (platform takedowns): items per period by publisher and stated origin, each publisher against its own
   trailing 8 periods, publishers kept apart. Each publisher at its own grain: Google per quarterly bulletin, Meta
   and TikTok per report (about half-yearly), OpenAI per calendar quarter of its posts. This is the only layer that
   may later carry tier "anomaly", worded as unusual enforcement against that publisher's own record, never as
   activity level. No threshold is set yet, so nothing here is rated: `ready` says whether 8 earlier periods exist.
2. Ongoing (named operations): persistence per operation: distinct disclosures and reports, publishers acting,
   last sighting, months since; state "active" or "quiet" at a fixed 6-month window, never "ended".
3. Emerging: the watch register's closing (UT-IND-3, UT-IND-4) stays in analysis/activity; nothing here.
Across layers: a half-year technique mix from the DISARM rules (share of platform items each technique was mapped
on). No warning tier anywhere.

Google's bulletins before the lane's first quarter (TAG Bulletin pages, Q1 2024 to Q4 2025) enter as a counts-only
register, `config/register/google-tag-2024-2025.json`, written on the laptop by `tools/undertow.py tagbackfill`:
per entry the month, the linked-to country code and asset counts; no bulletin text.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "config" / "register" / "google-tag-2024-2025.json"
TAG_URL = "https://blog.google/threat-analysis-group/tag-bulletin-q{q}-{y}/"
TAG_QUARTERS = [(y, q) for y in (2024, 2025) for q in (1, 2, 3, 4)]
TRAILING = 8
QUIET_MONTHS = 6
PLATFORMS = ("meta", "google", "openai", "tiktok")
GRAIN = {"google": "bulletin (quarter)", "meta": "report", "tiktok": "report", "openai": "calendar quarter"}
ENTRY_FIELDS = {"key", "month", "origin", "assets", "ongoing"}
PAGE_FIELDS = {"year", "quarter", "url", "updated", "updated_note", "sha256", "entries", "unparsed"}
MODIFIED_RE = re.compile(r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})')


# ---- the TAG register (laptop: tagbackfill) ----------------------------------------------------------------------

def page_entry(parsed: dict, body: bytes, sha256: str) -> dict:
    """Counts-only register row for one parsed TAG bulletin page (google.parse_page output)."""
    y, q = parsed["year"], parsed["quarter"]
    updated, note = parsed["updated"], None
    q_start = date(y, 3 * (q - 1) + 1, 1).isoformat()
    if updated is None or updated < q_start:
        m = MODIFIED_RE.search(body.decode("utf-8", errors="replace"))
        note = (f"the page's 'last updated' date ({updated}) falls before the quarter; date from the page's "
                f"dateModified") if m else None
        updated = m.group(1) if m else updated
    return {"year": y, "quarter": q, "url": TAG_URL.format(q=q, y=y), "updated": updated, "updated_note": note,
            "sha256": sha256, "unparsed": len(parsed["unparsed"]),
            "entries": [{"key": e["key"], "month": e["month"], "origin": list(e["origin"]),
                         "assets": dict(e["assets"]), "ongoing": bool(e["ongoing"])} for e in parsed["entries"]]}


def load_register(path: Path = REGISTER) -> dict:
    if not path.exists():
        return {"pages": []}
    return json.loads(path.read_text(encoding="utf-8"))


def check_register(reg: dict) -> list[str]:
    """Counts only: refuse any field that could carry Google's text."""
    errs = []
    for pg in reg.get("pages") or []:
        extra = set(pg) - PAGE_FIELDS
        if extra:
            errs.append(f"TAG register Q{pg.get('quarter')} {pg.get('year')}: unexpected fields {sorted(extra)}")
        if not str(pg.get("url", "")).startswith("https://blog.google/threat-analysis-group/tag-bulletin-"):
            errs.append(f"TAG register Q{pg.get('quarter')} {pg.get('year')}: url not a TAG bulletin page")
        for e in pg.get("entries") or []:
            if set(e) - ENTRY_FIELDS:
                errs.append(f"TAG register {e.get('key')}: unexpected fields {sorted(set(e) - ENTRY_FIELDS)}")
            if not all(isinstance(c, str) and len(c) == 2 and c.isupper() for c in e.get("origin") or []):
                errs.append(f"TAG register {e.get('key')}: origin must be ISO country codes")
            if not all(isinstance(v, int) for v in (e.get("assets") or {}).values()):
                errs.append(f"TAG register {e.get('key')}: assets must be counts")
    return errs


# ---- layer 1: dismantled -------------------------------------------------------------------------------------------

def _quarter(iso: str) -> str:
    return f"{iso[:4]}-Q{(int(iso[5:7]) - 1) // 3 + 1}"


def _period(r: dict) -> tuple[str, str] | None:
    """(sort key, label) of the publisher's own period for a platform record."""
    pub, did = r["publisher"], (r.get("disclosure") or {}).get("id", "")
    if pub == "google":
        m = re.match(r"google:(\d{4})-q([1-4])$", did)
        return (f"{m.group(1)}-Q{m.group(2)}", f"Q{m.group(2)} {m.group(1)} bulletin") if m else None
    if pub == "meta":
        m = re.match(r"meta:(h|q)([1-4])-(\d{4})$", did)
        return (f"{m.group(3)}-{m.group(1).upper()}{m.group(2)}", f"{m.group(1).upper()}{m.group(2)} {m.group(3)} report") if m else None
    if pub == "tiktok":
        m = re.match(r"tiktok:report-(\d+)$", did)
        return (f"{int(m.group(1)):03d}", f"report {m.group(1)}") if m else None
    if pub == "openai" and r.get("disclosed_at"):
        q = _quarter(r["disclosed_at"])
        return (q, q)
    return None


def dismantled(records: list[dict], reg: dict) -> dict:
    rows: dict[str, dict[str, dict]] = {p: {} for p in PLATFORMS}

    def add(pub, key, label, origin, source):
        b = rows[pub].setdefault(key, {"period": label, "items": 0, "origin": Counter(), "source": source})
        b["items"] += 1
        for c in origin or ["none"]:
            b["origin"][c] += 1

    live_google = {(r.get("disclosure") or {}).get("id") for r in records if r.get("publisher") == "google"}
    for pg in reg.get("pages") or []:
        if f"google:{pg['year']}-q{pg['quarter']}" in live_google:
            continue    # the lane's own reading wins where both exist
        for e in pg["entries"]:
            add("google", f"{pg['year']}-Q{pg['quarter']}", f"Q{pg['quarter']} {pg['year']} bulletin", e["origin"],
                "TAG register (counts)")
    for r in records:
        if r.get("publisher") not in PLATFORMS or r.get("lane") != r.get("publisher"):
            continue
        p = _period(r)
        if p:
            add(r["publisher"], p[0], p[1], r.get("origin"), "lane")
    out = {}
    for pub in PLATFORMS:
        keys = sorted(rows[pub])
        series = []
        for i, k in enumerate(keys):
            b = rows[pub][k]
            prior = [rows[pub][x]["items"] for x in keys[max(0, i - TRAILING):i]]
            series.append({"key": k, "period": b["period"], "items": b["items"],
                           "origin": dict(sorted(b["origin"].items(), key=lambda kv: (-kv[1], kv[0]))),
                           "source": b["source"],
                           "trailing": {"periods": len(prior), "min": min(prior) if prior else None,
                                        "max": max(prior) if prior else None,
                                        "mean": round(sum(prior) / len(prior), 1) if prior else None},
                           "ready": len(prior) >= TRAILING})
        out[pub] = {"grain": GRAIN[pub], "periods": series}
    return out


# ---- layer 2: ongoing ----------------------------------------------------------------------------------------------

def _months_between(a: str, b: date) -> int:
    y, m = int(a[:4]), int(a[5:7])
    return (b.year - y) * 12 + (b.month - m) - (1 if b.day < int(a[8:10]) else 0)


def ongoing(records: list[dict], today: date) -> list[dict]:
    """One row per operation in config/operations.json that any item names. A platform or EEAS item counts as a
    disclosure; a reporter or watch item adds its number of reports (one item per reporter and operation)."""
    ops: dict[str, dict] = defaultdict(lambda: {"disclosures": set(), "reports": 0, "publishers": set(),
                                                "reporters": set(), "last": None})
    for r in records:
        act = r.get("activity") or {}
        when = act.get("last_report") or r.get("disclosed_at")
        platform = r.get("publisher") in PLATFORMS + ("eeas",) and r.get("lane") == r.get("publisher")
        for op in r.get("named_operations") or []:
            o = ops[op]
            if platform:
                o["disclosures"].add(r.get("key"))
                o["publishers"].add(r["publisher"])
            else:
                o["reports"] += int(act.get("reports") or 1)
                o["reporters"].add(act.get("reporter") or r.get("publisher"))
            if when and (o["last"] is None or when[:10] > o["last"]):
                o["last"] = when[:10]
    out = []
    for name, o in sorted(ops.items()):
        months = _months_between(o["last"], today) if o["last"] else None
        out.append({"operation": name, "disclosures": len(o["disclosures"]), "reports": o["reports"],
                    "publishers_acting": sorted(o["publishers"]), "reporters": sorted(o["reporters"]),
                    "last_sighting": o["last"], "months_since": months,
                    "state": "active" if months is not None and months < QUIET_MONTHS else "quiet"})
    return out


# ---- across layers: technique mix ----------------------------------------------------------------------------------

def _half(iso: str) -> str:
    return f"{iso[:4]}-H{1 if int(iso[5:7]) <= 6 else 2}"


def technique_mix(records: list[dict]) -> list[dict]:
    """Per half-year of the publisher's date and per publisher (kept apart: Google's entries state assets and
    stance, rarely behaviours, so pooled shares would mostly measure Google's volume)."""
    by: dict[tuple[str, str], dict] = defaultdict(lambda: {"items": 0, "t": Counter()})
    for r in records:
        if r.get("publisher") not in PLATFORMS + ("eeas",) or r.get("lane") != r.get("publisher"):
            continue
        if not r.get("disclosed_at"):
            continue
        h = by[(_half(r["disclosed_at"]), r["publisher"])]
        h["items"] += 1
        for t in {d["id"] for d in r.get("disarm") or []}:
            h["t"][t] += 1
    return [{"half": k[0], "publisher": k[1], "items": v["items"],
             "techniques": {t: {"items": n, "share": round(n / v["items"], 3)}
                            for t, n in sorted(v["t"].items(), key=lambda kv: (-kv[1], kv[0]))}}
            for k, v in sorted(by.items())]


def build(records: list[dict], today: date, reg: dict | None = None) -> dict:
    reg = load_register() if reg is None else reg
    return {
        "source": "undertow", "method": "baseline per layer (Tom, 19 Nov 2026)",
        "note": ("Described, never rated: no anomaly tier and no warning tier is set. Counts are of what each "
                 "publisher chose to disclose (its enforcement record), not of influence activity."),
        "dismantled": dismantled(records, reg),
        "ongoing": {"quiet_after_months": QUIET_MONTHS, "operations": ongoing(records, today)},
        "technique_mix": technique_mix(records),
        "google_tag_register": [{"year": p["year"], "quarter": p["quarter"], "url": p["url"], "updated": p["updated"],
                                 "entries": len(p["entries"]), "unparsed": p["unparsed"]}
                                for p in reg.get("pages") or []],
    }

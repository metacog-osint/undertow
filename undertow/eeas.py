"""EEAS lane: named Information Manipulation Sets from the 4th EEAS report on FIMI threats (March 2026).

The report is a 25 MB PDF published once a year, so its named operations were extracted once from the PDF's text
into config/register/eeas-fimi-4.json, each row cited to its printed page. The register's `reviewed_by` says who
read the rows against the report: "machine-read" (a machine reading, checked by a second machine reading) until an
analyst has, then "tic-analyst"; it sets the items' human_review (targets.human_review), and the page's
Sources table (site_src/index.html) says the same. The live part of the lane reads the
EEAS FIMI page each run to confirm the 4th report's page is still listed and to notice a newer report
(a 5th, expected about March 2027): when one appears the lane says so (`newer_report`), and a session extracts
its register the same way. The PDF itself is not fetched on a schedule.

Reuse: the EEAS legal notice authorises reuse provided the source is acknowledged.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import disarm, text

ROOT = Path(__file__).resolve().parents[1]
FIMI_PAGE = ("https://www.eeas.europa.eu/eeas/information-integrity-and-countering-foreign-information-manipulation-"
             "interference-fimi_en")
REGISTERS = ["eeas-fimi-4.json"]
LICENCE = "EEAS: reuse authorised provided the source is acknowledged"
ORDINALS = {"5th": 5, "6th": 6, "fifth": 5, "sixth": 6}


def load_registers() -> list[dict]:
    return [json.loads((ROOT / "config" / "register" / f).read_text(encoding="utf-8")) for f in REGISTERS]


def check_page(body: bytes, reg: dict) -> dict:
    t = body.decode("utf-8", errors="replace")
    landing = reg["report"]["landing_url"].split("eeas.europa.eu", 1)[1]
    newer = sorted({ORDINALS[m.group(1).lower()] for m in
                    re.finditer(r"\b(5th|6th|fifth|sixth)\b[^<]{0,40}(?:EEAS )?(?:Annual )?Report on (?:FIMI|Foreign Information)",
                                t, re.I)})
    return {"listed": landing in t, "newer_report": newer[0] if newer else None}


def build_records(reg: dict) -> list[dict]:
    rep = reg["report"]
    out = []
    for o in reg["operations"]:
        sentences = [b["text"] for b in o.get("behaviours") or []]
        maps = disarm.map_text(sentences)
        for m in maps:
            page = next((b["page"] for b in o["behaviours"] if m["phrase"] in b["text"]), None)
            m["page"] = page
        behaviours = []
        withheld = 0
        for b in o.get("behaviours") or []:
            t, w = text.scrub(b["text"])
            withheld += w
            behaviours.append({"text": t, "page": b["page"]})
        wording, w = text.scrub(o["attribution_wording"])
        withheld += w
        tt, w = text.scrub(o.get("target_text") or "")
        withheld += w
        out.append({
            "key": f"eeas:fimi-4:{o['id']}", "lane": "eeas", "publisher": "eeas",
            "disclosure": {"id": "eeas:fimi-4", "title": rep["title"], "url": rep["landing_url"]},
            "title": f"EEAS: {o['name']}, an Information Manipulation Set active in 2025",
            "operation_name": o["name"],
            "named_operations": [o["id"]],
            "period": rep["covers"],
            "disclosed_at": f"{rep['published']}T00:00:00Z",
            "disclosed_precision": "day",   # the report gives a date, no time
            "origin": o["origin"], "origin_text": o.get("origin_basis"), "origin_wording": wording,
            "origin_level": o["origin_level"],
            "alignment": o.get("alignment") or [],
            "targets": o.get("targets") or [], "target_regions": o.get("target_regions") or [],
            "target_text": tt or None,
            "countries_named": [],
            "platforms": [],
            "counts": o.get("counts") or {},
            "behaviours": behaviours,
            "summary": None, "summary_note": None,
            "orgs": o.get("orgs") or [],
            "url": rep["landing_url"],
            "page": o["page"],
            "register": {"file": f"config/register/{reg['register']}.json", "entered_by": reg["entered_by"],
                         "entered_at": reg["entered_at"], "checked_by": reg.get("checked_by"),
                         "reviewed_by": reg.get("reviewed_by")},
            "withheld": withheld,
            "disarm": maps,
        })
    return out

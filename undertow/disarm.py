"""DISARM v1.6.1: map a publisher's described behaviours to technique ids through the published rule table.

basis "mapped": a rule in config/disarm_rules.json matched the publisher's own words; the phrase is kept.
basis "reported": the publisher itself cites the id (none in the first slice: the EEAS report cites T0075,
T0076 and T0079 for narratives in general, not for any one operation, so they are not attached to items).
A behaviour no rule matches stays as text.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.6.1"


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads((ROOT / "config" / "disarm_rules.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def bundle() -> dict:
    return json.loads((ROOT / "config" / "disarm" / "DISARM-1.6.1-cut.json").read_text(encoding="utf-8"))


def name(tid: str) -> str | None:
    return bundle()["index"].get(tid)


def reviewed() -> bool:
    """True only when the table is marked reviewed and every rule carries review "accepted" (19 Nov 2026):
    a rule added later without review turns the whole table back to "proposed"."""
    r = rules()
    return ((r.get("review") or {}).get("status") == "reviewed"
            and all(x.get("review") == "accepted" for x in r["rules"]))


@lru_cache(maxsize=1)
def _compiled():
    return [(r, re.compile(r["pattern"])) for r in rules()["rules"]]


def map_text(sentences: list[str]) -> list[dict]:
    """Techniques for a list of (already scrubbed) sentences: one entry per technique, first phrase kept."""
    out, seen = [], set()
    for s in sentences:
        for r, rx in _compiled():
            if r["technique"] in seen:
                continue
            m = rx.search(s)
            if m:
                seen.add(r["technique"])
                out.append({"id": r["technique"], "name": name(r["technique"]), "basis": "mapped", "rule": r["id"],
                            "phrase": m.group(0)})
    return out


def attack_patterns(ids) -> list[dict]:
    """DISARM's own attack-pattern objects for these ids, unchanged."""
    want = set(ids)
    return [o for o in bundle()["objects"] if o["type"] == "attack-pattern"
            and o["external_references"][0]["external_id"] in want]


def marking() -> dict:
    return next(o for o in bundle()["objects"] if o["type"] == "marking-definition")


def identity() -> dict:
    return next(o for o in bundle()["objects"] if o["type"] == "identity")

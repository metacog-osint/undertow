"""Standing sanctions listings of the organisations Undertow keeps by hand (config/operations.json "organisations").

Each row is one list's listing of one organisation, read from the publisher's own notice: the list, the programme,
the listing date and the notice's address. A listing says a government acted against the organisation. It
corroborates the operator a publisher names; it is never an origin and changes no confidence. Organisations only:
a person named in the same notice is never entered (16 Nov 2026).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The lists Headwind reads, by Headwind's own list ids, with the hosts each publisher's notices sit on.
LISTS = {
    "ofac-sdn": {"name": "the OFAC SDN List", "short": "OFAC SDN", "publisher": "US Treasury (OFAC)",
                 "hosts": ("https://ofac.treasury.gov/recent-actions/", "https://home.treasury.gov/news/press-releases/")},
    "eu-fsf": {"name": "the EU's sanctions list", "short": "EU", "publisher": "Council of the European Union",
               "hosts": ("https://eur-lex.europa.eu/eli/", "https://eur-lex.europa.eu/legal-content/")},
    "uk-sanctions": {"name": "the UK Sanctions List", "short": "UK", "publisher": "UK Foreign, Commonwealth and Development Office",
                     "hosts": ("https://assets.publishing.service.gov.uk/media/", "https://www.gov.uk/government/")},
    "france-gels": {"name": "France's asset-freeze register", "short": "France",
                    "publisher": "French Treasury (Direction générale du Trésor)",
                    "hosts": ("https://gels-avoirs.dgtresor.gouv.fr/", "https://www.legifrance.gouv.fr/")},
    "canada-sema": {"name": "Canada's consolidated autonomous sanctions list", "short": "Canada",
                    "publisher": "Global Affairs Canada",
                    "hosts": ("https://gazette.gc.ca/rp-pr/p2/", "https://www.gazette.gc.ca/rp-pr/p2/",
                              "https://www.international.gc.ca/", "https://international.gc.ca/")},
}
NOTE = ("A listing says a government acted against the organisation. It corroborates the operator the publisher "
        "names; it is not an origin and changes no confidence.")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load(root: Path = ROOT) -> dict:
    return json.loads((root / "config" / "operations.json").read_text(encoding="utf-8")).get("organisations") or {}


@lru_cache(maxsize=1)
def _by_name() -> dict[str, list[dict]]:
    return {e["name"]: list(e.get("listings") or []) for e in _load().get("entries") or []}


def for_org(name: str) -> list[dict]:
    """One organisation's listings, oldest first, each with the list's display names added."""
    out = []
    for row in sorted(_by_name().get(name) or [], key=lambda r: (r["listed"], r["list"])):
        meta = LISTS[row["list"]]
        out.append({"organisation": name, "list": row["list"], "list_name": meta["name"], "list_short": meta["short"],
                    "list_publisher": meta["publisher"], "programme": row["programme"], "listed": row["listed"],
                    "notice": row["notice"], "notice_title": row["notice_title"]})
    return out


def for_orgs(orgs) -> list[dict]:
    """Listings of the organisations an item names (dicts with "name", or plain names)."""
    out = []
    for o in orgs or []:
        out.extend(for_org(o["name"] if isinstance(o, dict) else o))
    return out


def sentence(orgs) -> str | None:
    """'<org> is listed by ...' for an item's summary, or None when no organisation it names is listed."""
    parts = []
    for o in orgs or []:
        name = o["name"] if isinstance(o, dict) else o
        rows = for_org(name)
        if rows:
            parts.append(f"{name} is listed by " + ", ".join(f"{r['list_short']} ({r['listed']})" for r in rows))
    if not parts:
        return None
    return "; ".join(parts) + ". " + NOTE


def notice_urls(root: Path = ROOT) -> tuple[str, ...]:
    """Every notice address in the table: the leak scan allows these exact addresses in published files."""
    return tuple(sorted({r["notice"] for e in _load(root).get("entries") or [] for r in e.get("listings") or []}))


def check(root: Path = ROOT, known: frozenset[str] | None = None) -> list[str]:
    """Refuse a bad row: an organisation Undertow does not keep, an unknown list, a date not ISO, a notice not on the
    list's own publisher's site, a list given twice for one organisation."""
    errs = []
    cfg = _load(root)
    for e in cfg.get("entries") or []:
        name = e.get("name")
        if known is not None and name not in known:
            errs.append(f"{name!r}: not an organisation kept in config/operations.json or config/register/")
        seen = set()
        for r in e.get("listings") or []:
            lst = r.get("list")
            where = f"{name} / {lst}"
            if lst not in LISTS:
                errs.append(f"{where}: unknown list")
                continue
            if lst in seen:
                errs.append(f"{where}: list given twice")
            seen.add(lst)
            if not DATE.match(r.get("listed") or ""):
                errs.append(f"{where}: listed must be YYYY-MM-DD")
            if not r.get("programme") or not r.get("notice_title"):
                errs.append(f"{where}: programme and notice_title are required")
            if not str(r.get("notice") or "").startswith(LISTS[lst]["hosts"]):
                errs.append(f"{where}: notice is not on the publisher's own site")
            extra = set(r) - {"list", "programme", "listed", "notice", "notice_title", "where"}
            if extra:
                errs.append(f"{where}: fields not allowed: {sorted(extra)}")
    return errs

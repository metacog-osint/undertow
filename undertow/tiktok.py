"""TikTok lane: TikTok's reports under the EU Code of Conduct on Disinformation, read from the Code's
Transparency Centre (disinfocode.eu/reports/tiktok/<n>/json). NEVER tiktok.com: TikTok's terms (updated 15 Jul
2026, read 14 Nov 2026) bar automated extraction from its websites without written approval.

Each report is semiannual (report 8 "March 2026", report 9 "September 2026"). Network-level entries sit in three
places, all read here and merged on (origin, accounts, followers):
- Commitment 14, TTP 6 ("Hungary - 107 Accounts; 37,070 Followers. We assess that this network operated from
  Hungary and targeted a Hungarian audience. ..."): the networks that targeted European audiences.
- The crisis chapter ("Network Origin: Ukraine / Description: ... / Accounts Removed: 27 Followers: 60,918").
- The elections chapter ("In February 2026, we disrupted ... operating from Hungary and targeting a Hungarian
  audience, included 107 accounts with 37,070 followers"), which gives the month.
The Centre states no terms of use (none found, 14 Nov 2026). The partial list runs 3 to 8 months behind TikTok's
own monthly list; that full list needs TikTok's written approval (permission email drafted for Tom).
"""
from __future__ import annotations

import html
import json
import re

from . import disarm, text

REPORT_URL = "https://disinfocode.eu/reports/tiktok/{n}/json"
REPORT_PAGE = "https://disinfocode.eu/reports/tiktok/{n}"
KNOWN_REPORTS = [8, 9]
PROBE_AHEAD = 2
LICENCE = "EU Code of Conduct on Disinformation Transparency Centre (TikTok's report); no terms of use stated"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

TTP6_RE = re.compile(r"(?m)^(?P<label>[A-Z][\w’' \-]{1,40}?) - (?P<acc>\d[\d,]*) Accounts?; (?P<fol>\d[\d,]*) Followers?\.\s*(?P<desc>[^\n]+)")
CRISIS_RE = re.compile(r"Network Origin: (?P<origin>[^\n]+?)\s*\n\s*(?:\n\s*)*Description: (?P<desc>.+?)\s*Accounts (?:Removed|in network): "
                       r"(?P<acc>\d[\d,]*)\s*Followers(?: of network)?: (?P<fol>\d[\d,]*)", re.S)
ELECTION_RE = re.compile(r"(?:assessed to be operating from (?P<origin>[A-Z][\w ]+?) and targeting (?P<target>an? [\w ]+? audiences?|[\w ]+? audiences?)"
                         r", included (?P<acc>\d[\d,]*) accounts with (?P<fol>\d[\d,]*) followers)")
MONTH_IN_RE = re.compile(r"In (?P<m>" + "|".join(MONTHS) + r") (?P<y>\d{4})")
WINDOW_RE = re.compile(r"(?P<m1>January|July) 1\s*-\s*(?P<m2>June|December) 3[01],? (?P<y>\d{4})"
                       r"|Between (?P<m1b>January|July)(?: to | and |\s*-\s*)(?P<m2b>June|December),? (?P<yb>\d{4})")
CRISIS_HEAD_RE = re.compile(r"(War of aggression by Russia on Ukraine|Israel-Hamas Conflict|Iran-Israel)", re.I)


def strip_html(s: str) -> str:
    s = re.sub(r"<(br|p|li|tr|h\d|div)[^>]*>", "\n", s)
    s = re.sub(r"</t[dh]>", " | ", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return s.replace(" ", " ").replace("​", "")


def _strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str) and len(x) > 40:
        yield x


def _int(s: str) -> int:
    return int(s.replace(",", ""))


def _origin(label_or_desc: str) -> list[str]:
    m = re.search(r"operat\w+ from ([A-Z][\w ]+?)(?: and|[,.])", label_or_desc)
    if m:
        cc = text.country_code(m.group(1)) or (text.countries_in(m.group(1)) or [None])[0]
        return [cc] if cc else []
    cc = text.country_code(label_or_desc.strip())
    return [cc] if cc else []


def _target(desc: str) -> tuple[list[str], list[str], str | None]:
    m = re.search(r"target(?:ed|ing) (?P<t>(?:an? |the )?[^.(]+?)(?: audiences?)?(?:\s*\(|\.|,|$)", desc)
    if not m:
        return [], [], None
    t = re.sub(r"\b[\w-]+-speaking\b", "", m.group("t"))
    return text.countries_in(t), text.regions_in(t), m.group(0).rstrip(".,( ")


def parse_report(doc: dict) -> dict:
    """Network entries from one report. Returns {id, name, published, window, entries}."""
    entries: dict[tuple, dict] = {}
    window = None

    def put(origin, acc, fol, **kw):
        k = (tuple(origin), acc, fol)
        e = entries.setdefault(k, {"origin": origin, "accounts": acc, "followers": fol, "descriptions": [],
                                   "contexts": [], "month": None, "target_wording": None, "targets": [],
                                   "target_regions": []})
        for key, v in kw.items():
            if v is None:
                continue
            if key == "description":
                if v not in e["descriptions"]:
                    e["descriptions"].append(v)
            elif key == "context":
                if v not in e["contexts"]:
                    e["contexts"].append(v)
            elif not e.get(key):
                e[key] = v

    seen = set()
    for raw in _strings(doc.get("chapters") or []):
        if "ccount" not in raw:
            continue
        s = strip_html(raw)
        if s in seen:
            continue
        seen.add(s)
        wm = WINDOW_RE.search(s)
        if wm and window is None and (TTP6_RE.search(s) or CRISIS_RE.search(s)):
            y = wm.group("y") or wm.group("yb")
            m1 = wm.group("m1") or wm.group("m1b")
            m2 = wm.group("m2") or wm.group("m2b")
            window = (f"{y}-{'01' if m1 == 'January' else '07'}-01", f"{y}-{'06-30' if m2 == 'June' else '12-31'}")
        for m in TTP6_RE.finditer(s):
            desc = m.group("desc").strip()
            origin = _origin(desc) or _origin(m.group("label"))
            tg, rg, tw = _target(desc)
            put(origin, _int(m.group("acc")), _int(m.group("fol")), description=desc, targets=tg, target_regions=rg,
                target_wording=tw, context="Commitment 14 (TTP 6): networks targeting European audiences")
        for m in CRISIS_RE.finditer(s):
            desc = re.sub(r"\s+", " ", m.group("desc")).strip()
            origin = _origin(desc) or _origin(m.group("origin"))
            heads = [h.group(1) for h in CRISIS_HEAD_RE.finditer(s[: m.start()])]
            tg, rg, tw = _target(desc)
            put(origin, _int(m.group("acc")), _int(m.group("fol")), description=desc, targets=tg, target_regions=rg,
                target_wording=tw, context=("Crisis chapter: " + heads[-1]) if heads else "Crisis chapter")
        for m in ELECTION_RE.finditer(s):
            months = list(MONTH_IN_RE.finditer(s[: m.start()]))
            month = None
            if months:
                mm = months[-1]
                month = f"{mm.group('y')}-{MONTHS.index(mm.group('m')) + 1:02d}"
            cc = text.country_code(m.group("origin").strip())
            tg, rg, tw = _target("targeting " + m.group("target"))
            put([cc] if cc else [], _int(m.group("acc")), _int(m.group("fol")), month=month, targets=tg,
                target_regions=rg, target_wording=tw, context="Elections chapter")
    return {"id": doc.get("id"), "name": doc.get("name"), "published": doc.get("publish_date"),
            "window": window, "entries": list(entries.values())}


def build_records(reports: list[dict]) -> list[dict]:
    out = []
    for rep in reports:
        n = rep["id"]
        pub = (rep.get("published") or "")[:19] + "Z" if rep.get("published") else None
        for e in rep["entries"]:
            origin = e["origin"]
            o = origin[0] if origin else "XX"
            key = f"tiktok:r{n}:{o.lower()}:{e['accounts']}:{e['followers']}"
            descs, withheld = [], 0
            for d in e["descriptions"]:
                t, w = text.scrub(d)
                descs.append(t)
                withheld += w
            sentences = []
            for d in descs:
                sentences += re.split(r"(?<=[.!?])\s+", d)
            where = text.scrub(e["target_wording"])[0] if e["target_wording"] else None
            origin_name = None
            if origin:
                from tic_doctrine import geo
                origin_name = geo.name(origin[0])
            title = (f"TikTok removed a network of {e['accounts']:,} accounts"
                     + (f" operated from {origin_name}" if origin_name else "")
                     + (f" that {where}" if where else ""))
            wording = None
            for d in descs:
                m = re.search(r"(?:We )?assess(?:ed)? that this network operated from [^.]+?(?= and target|\.)", d)
                if m:
                    wording = m.group(0)
                    break
            out.append({
                "key": key, "lane": "tiktok", "publisher": "tiktok",
                "disclosure": {"id": f"tiktok:report-{n}",
                               "title": f"TikTok, Code of Conduct on Disinformation report: {rep.get('name')}",
                               "url": REPORT_PAGE.format(n=n)},
                "title": title,
                "operation_name": None,
                "named_operations": text.named_operations(" ".join(descs)),
                "period": e["month"] or (f"{rep['window'][0][:7]} to {rep['window'][1][:7]}" if rep.get("window") else None),
                "removed_window": rep.get("window"),
                "removed_month": e["month"],
                "disclosed_at": pub,
                # Report 8's publish_date is midnight with zeros (a date); report 9's carries a time.
                "disclosed_precision": "day" if pub and pub.endswith("T00:00:00Z") else None,
                "origin": origin, "origin_text": origin_name,
                "origin_wording": wording or (f"Network Origin: {origin_name}" if origin_name else None),
                "origin_level": "moderate" if origin else "none",
                "alignment": [],
                "targets": [c for c in e["targets"]], "target_regions": e["target_regions"], "target_text": where,
                "countries_named": [],
                "platforms": ["TikTok"],
                "counts": {"accounts": e["accounts"], "followers": e["followers"]},
                "contexts": e["contexts"],
                "summary": " ".join(descs) or None,
                "summary_note": ("TikTok's description from its Code of Conduct report, via the EU Transparency Centre; "
                                 "names withheld by Undertow.") if descs else None,
                "orgs": [],
                "url": REPORT_PAGE.format(n=n),
                "withheld": withheld,
                "disarm": disarm.map_text(sentences),
            })
    return out


def is_report(body: bytes) -> dict | None:
    try:
        doc = json.loads(body)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) and doc.get("chapters") else None

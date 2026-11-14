"""Build Undertow's contract-v2 feed (tic-feed/2, GeoJSON) from the collected records.

One item per disclosed network or operation: kind "observation", tier "routine", status_class "reported". Each is
a publisher's report of its own enforcement action (source grade A2). Undertow states no probability. Geometry
is on the target countries the publisher names (Google and OpenAI name none: there it is the countries named in
the stance or summary, marked as such), or null with a link to the page.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import CONTRACT, geo  # noqa: E402

from . import disarm  # noqa: E402

SITE = "https://undertow.theintelligence.company"
METHOD = "undertow-1.0"
LANGUAGE_KEY = "https://github.com/metacog-osint/tic-doctrine/blob/main/docs/language-key.md"

SOURCES = {
    "meta": {"id": "meta-threat-research", "publisher": "Meta",
             "licence": "MIT (Meta threat-research repository)", "independence_group": "meta",
             "source_type": "platform transparency report",
             "descriptor": "Meta's own report of a network it disrupted for Coordinated Inauthentic Behavior, from its "
                           "threat-research repository. Reliable on its own enforcement; origin is Meta's judgment."},
    "google": {"id": "google-iob", "publisher": "Google",
               "licence": "Google; facts and counts only (no bulletin text republished)", "independence_group": "google",
               "source_type": "platform transparency report",
               "descriptor": "Google's quarterly Influence Operations Bulletin: channels and accounts it terminated, "
                             "with the country Google links the campaign to."},
    "openai": {"id": "openai-news-rss", "publisher": "OpenAI",
               "licence": "OpenAI news RSS feed (title and one-line summary quoted with credit; report pages not read)",
               "independence_group": "openai", "source_type": "platform transparency report",
               "descriptor": "OpenAI's news RSS item announcing an operation it disrupted. Only the feed is read."},
    "tiktok": {"id": "disinfocode-tiktok", "publisher": "TikTok, via the EU Code of Conduct Transparency Centre",
               "licence": "EU Code of Conduct on Disinformation Transparency Centre; no terms of use stated",
               "independence_group": "tiktok", "source_type": "platform transparency report",
               "descriptor": "TikTok's semiannual report under the EU Code of Conduct on Disinformation: covert "
                             "influence networks it removed, with assessed origin and target audience."},
    "eeas": {"id": "eeas-fimi-4", "publisher": "European External Action Service (EEAS)",
             "licence": "EEAS: reuse authorised provided the source is acknowledged", "independence_group": "eu-eeas",
             "source_type": "official report",
             "descriptor": "The EEAS annual report on foreign information manipulation and interference threats; the "
                           "Information Manipulation Sets it names, entered once by hand with page numbers."},
}
REQUIREMENT = {"meta": ["UT-PIR-1", "UT-PIR-2"], "google": ["UT-PIR-1"], "openai": ["UT-PIR-1", "UT-PIR-3"],
               "tiktok": ["UT-PIR-1", "UT-PIR-2"], "eeas": ["UT-PIR-1", "UT-PIR-2", "UT-PIR-3"]}


def item_id(key: str) -> str:
    lane = key.split(":", 1)[0]
    return f"UT-{lane.upper()}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:10]}"


def _geometry(ccs: list[str]):
    pts = []
    for cc in ccs:
        p = geo.point(cc)
        if p:
            pts.append([p[1], p[0]])
    if not pts:
        return None
    return {"type": "Point", "coordinates": pts[0]} if len(pts) == 1 else {"type": "MultiPoint", "coordinates": pts}


def _names(ccs):
    return [geo.name(c) or c for c in ccs]


def _counts_text(c: dict) -> str:
    words = {"facebook_accounts": "Facebook accounts", "instagram_accounts": "Instagram accounts",
             "facebook_pages": "Facebook Pages", "facebook_groups": "Facebook Groups", "accounts": "accounts",
             "pages": "Pages", "groups": "Groups", "followers": "followers", "youtube_channels": "YouTube channels",
             "blogger_blogs": "Blogger blogs", "ads_accounts": "Ads accounts", "play_accounts": "Play accounts",
             "news_discover_domains": "domains blocked from Google News and Discover", "websites": "websites",
             "operations": "operations"}
    parts = [f"{v:,} {words.get(k, k.replace('_', ' '))}" for k, v in c.items()
             if k in words and isinstance(v, int) and v]
    return ", ".join(parts)


def summary(r: dict) -> str:
    pub = SOURCES[r["publisher"]]["publisher"].split(",")[0]
    bits = []
    if r["publisher"] == "eeas":
        bits.append(f"The EEAS names {r['operation_name']} among the Information Manipulation Sets active in 2025 "
                    f"(report p. {r.get('page')}).")
    else:
        bits.append(f"{pub} reports {'terminating' if r['publisher'] == 'google' else 'disrupting'} this "
                    f"{'campaign' if r['publisher'] == 'google' else 'network'}"
                    + (f" ({r['period']})" if r.get("period") else "") + ".")
    if r.get("origin"):
        bits.append(f"Origin as {pub} states it: {', '.join(_names(r['origin']))}"
                    + (f" (\"{r['origin_wording']}\")" if r.get("origin_wording") else "") + ".")
    elif r.get("alignment"):
        bits.append(f"No origin attributed; the publisher calls it aligned with {', '.join(_names(r['alignment']))}.")
    else:
        bits.append("No origin stated.")
    if r.get("targets") or r.get("target_regions"):
        bits.append("Targets as stated: " + ", ".join(_names(r.get("targets") or []) + (r.get("target_regions") or [])) + ".")
    elif r.get("countries_named"):
        bits.append("Countries named in the publisher's description: " + ", ".join(_names(r["countries_named"])) + ".")
    ct = _counts_text(r.get("counts") or {})
    if ct:
        bits.append(f"Counts: {ct}.")
    if r["publisher"] == "meta":
        bits.append(f"Meta lists {r['counts'].get('indicators', 0)} indicators; Undertow keeps the count only.")
    bits.append("Origin is where the operators were, never a finding of who directed it.")
    return " ".join(bits)


def actors(r: dict, sid: str) -> list[dict]:
    out = []
    if r.get("origin"):
        out.append({"name": f"Operators of this network (origin as reported: {', '.join(_names(r['origin']))})",
                    "role": "responsible", "actor_type": "unknown", "status_class": "reported",
                    "country": r["origin"][0], "source_ids": [sid]})
    for o in r.get("orgs") or []:
        out.append({"name": o["name"], "role": "responsible", "actor_type": "company", "status_class": "reported",
                    "country": o.get("country"), "source_ids": [sid]})
    return out


def feature(r: dict, generated: str) -> dict:
    src = dict(SOURCES[r["publisher"]])
    src.update({"title": r["disclosure"]["title"], "url": r["url"], "grade": "A2", "accessed_at": generated})
    if r.get("disclosed_at"):
        src["published_at"] = r["disclosed_at"]
    sid = src["id"]
    places = r.get("targets") or r.get("countries_named") or []
    countries = list(dict.fromkeys((r.get("origin") or []) + places + (r.get("alignment") or [])))
    props = {
        "contract": CONTRACT,
        "id": item_id(r["key"]),
        "program": "undertow",
        "title": r["title"],
        "summary": summary(r),
        "kind": "observation",
        "tier": "routine",
        "status": "actual",
        "msg_type": "new",
        "human_review": "none" if r["publisher"] != "eeas" else "full",
        "us_person_data": "organizations" if r.get("orgs") else "none",
        "status_class": "reported",
        "product_category": "current",
        "data_as_of": r.get("disclosed_at") or generated,
        "published_at": generated,
        "countries": countries,
        "pmesii_pt": ["information", "political"],
        "ie_aspect": ["informational", "human"],
        "ascope": ["people", "organizations"],
        "continuum": "competition",
        "requirement_ids": REQUIREMENT[r["publisher"]],
        "method_version": METHOD,
        "precision_class": "country" if places else "none",
        "visual": {"type": "page", "url": f"{SITE}/#{item_id(r['key'])}"},
        "sources": [src],
        "actors": actors(r, sid),
        "disarm_version": disarm.VERSION,
        "disarm_technique": [d["id"] for d in r.get("disarm") or []],
        "disarm_mapping": [{k: d.get(k) for k in ("id", "name", "basis", "rule", "phrase", "page") if d.get(k) is not None}
                           for d in r.get("disarm") or []],
        "disarm_rules_status": "reviewed" if disarm.reviewed() else "proposed, not yet reviewed",
        "operation": {
            "key": r["key"],
            "publisher": r["publisher"],
            "disclosure": r["disclosure"],
            "operation_name": r.get("operation_name"),
            "named_operations": r.get("named_operations") or [],
            "period": r.get("period"),
            "origin": r.get("origin") or [],
            "origin_wording": r.get("origin_wording"),
            "origin_level_stated": r.get("origin_level"),
            "alignment": r.get("alignment") or [],
            "sponsor": [o["name"] for o in r.get("orgs") or []],
            "targets": r.get("targets") or [],
            "target_regions": r.get("target_regions") or [],
            "countries_named": r.get("countries_named") or [],
            "platforms": r.get("platforms") or [],
            "counts": r.get("counts") or {},
            "corroborated_by": r.get("corroborated_by") or [],
            "withheld": r.get("withheld", 0),
        },
    }
    if r.get("languages"):
        props["operation"]["languages"] = r["languages"]
    if r.get("confidence"):
        props.update(r["confidence"])
    if r.get("coverage_fraction") is not None:
        props["coverage_fraction"] = r["coverage_fraction"]
    return {"type": "Feature", "geometry": _geometry(places), "properties": props}


def build_feed(records: list[dict], generated: str) -> dict:
    feats = [feature(r, generated) for r in records]
    feats.sort(key=lambda f: (f["properties"]["data_as_of"], f["properties"]["id"]), reverse=True)
    return {
        "type": "FeatureCollection",
        "contract": CONTRACT,
        "program": "undertow",
        "generated_at": generated,
        "method_version": METHOD,
        "licence": ("Undertow's own text: CC BY 4.0 (The Intelligence Company). Each item keeps its source's terms: "
                    "Meta MIT; Google facts and counts only; OpenAI RSS quoted with credit; TikTok via the EU Code of "
                    "Conduct Transparency Centre; EEAS reuse with acknowledgement. DISARM technique names CC BY-SA 4.0 "
                    "(DISARM Foundation)."),
        "attribution": ("Undertow, The Intelligence Company. Sources: Meta threat-research repository; Google Influence "
                        "Operations Bulletin; OpenAI news RSS; TikTok's reports to the EU Code of Conduct on "
                        "Disinformation; EEAS 4th report on FIMI threats. DISARM Framework v1.6.1, DISARM Foundation, "
                        "CC BY-SA 4.0."),
        "language_key": LANGUAGE_KEY,
        "note": ("Operation level only: no indicator values, account handles, URLs, domains or names of individuals. "
                 "Origin is the publisher's judgment of where the operators were and is never read as sponsorship."),
        "features": feats,
    }

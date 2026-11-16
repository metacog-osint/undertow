"""STIX 2.1 export (site/data/stix.json): one bundle per build, deterministic ids.

Mapping (plan section 3; STIX 2.1 OS, docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html):
- the suite: identity (organization), one fixed id, created_by_ref on everything Undertow makes
- a disclosure (one Meta report, one Google bulletin, one TikTok report, one OpenAI item, the EEAS report): report
- a disclosed network or operation: campaign, with x_tic_* properties for grade, status class, counts and wording
- origin country: location + relationship originates-from; target countries: location + relationship targets
- a DISARM technique: DISARM's own attack-pattern object, id and content unchanged, with DISARM's CC BY-SA 4.0
  marking, + relationship uses
- a named persistent operation: intrusion-set + relationship attributed-to (campaign -> intrusion-set)
- a named organisation (second slice, 16 Nov 2026): threat-actor + relationship attributed-to (campaign ->
  threat-actor) + located-at (threat-actor -> location), only when the record's own publisher names it and only a
  name hand-kept in config/operations.json or config/register/ (curated organisations, never a person).
  threat_actor_types is ["unknown"] and resource_level "organization": the publisher's naming is not a finding of
  who directed it, and the country is where the publisher places the organisation.
- reported activity on a tracked operation (16 Nov 2026): a report (report_types ["threat-actor"]) by the reporter
  whose object_refs is the operation's intrusion-set, one external reference per report, x_tic_activity_state
  "active" or "quiet". No campaign, origin or relationship: a reporter acted on nothing and adds no origin
- markings: TLP:CLEAR (TLP 2.0, copied from OASIS) plus a statement marking per source licence

Never emitted: indicator, observed-data, any cyber-observable (user-account, url, domain-name), an identity for a
person, or a threat-actor for anything but a curated organisation. Ids are UUIDv5 from NAMESPACE and a stable key, so a rerun on the same
input gives the same ids. Timestamps come from the disclosure, not the build, so a rerun gives the same objects.
"""
from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path

from . import disarm, text
from .feed import SOURCES, item_id, summary

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "undertow.theintelligence.company")
EPOCH = "2026-11-14T00:00:00.000Z"
STIX_CONFIDENCE = {"low": 15, "moderate": 50, "high": 85}    # Appendix A, None/Low/Med/High scale
SPEC_URL = "https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html"


def sid(kind: str, key: str) -> str:
    return f"{kind}--{uuid.uuid5(NAMESPACE, kind + ':' + key)}"


def ts(s: str | None) -> str:
    if not s:
        return EPOCH
    s = s.replace("+00:00", "Z")
    if len(s) == 10:
        s += "T00:00:00Z"
    if s.endswith("Z") and "." not in s:
        s = s[:-1] + ".000Z"
    return s


def tlp_clear() -> dict:
    return json.loads((ROOT / "config" / "stix_markings.json").read_text(encoding="utf-8"))["tlp_clear"]


SUITE = sid("identity", "the-intelligence-company")


def build_bundle(records: list[dict], generated: str) -> dict:
    tlp = tlp_clear()
    objs: dict[str, dict] = {}

    def add(o):
        objs.setdefault(o["id"], o)

    add({"type": "identity", "spec_version": "2.1", "id": SUITE, "created": EPOCH, "modified": EPOCH,
         "name": "The Intelligence Company (Undertow)", "identity_class": "organization",
         "description": "Undertow: attributed influence-operation takedowns at operation level. Public, non-commercial.",
         "contact_information": "https://undertow.theintelligence.company"})
    add(tlp)
    statement = {}
    for lane, s in SOURCES.items():
        m = {"type": "marking-definition", "spec_version": "2.1", "id": sid("marking-definition", "licence:" + lane),
             "created": EPOCH, "created_by_ref": SUITE, "name": f"Source terms: {s['publisher']}",
             "definition_type": "statement", "definition": {"statement": s["licence"]}}
        statement[lane] = m["id"]
    add(disarm.identity())
    add(disarm.marking())

    by_disclosure: dict[str, list[str]] = {}
    disclosures: dict[str, dict] = {}
    used_lanes = set()
    for r in records:
        lane = r["publisher"]
        used_lanes.add(lane)
        marks = [tlp["id"], statement[lane]]
        if r.get("activity") and lane != "watch":
            # Reported activity on a tracked operation: a STIX report by the reporter about the intrusion set, not a
            # campaign of its own (the reporter disclosed nothing it acted on).
            a = r["activity"]
            o = next((x for x in text.operations() if x["id"] == a["operation"]), None)
            if not o:
                continue
            iid = sid("intrusion-set", o["id"])
            iset = {"type": "intrusion-set", "spec_version": "2.1", "id": iid, "created_by_ref": SUITE,
                    "created": EPOCH, "modified": EPOCH, "name": o["name"], "object_marking_refs": [tlp["id"]]}
            if o.get("aliases"):
                iset["aliases"] = o["aliases"]
            add(iset)
            first, last = ts(a["first_report"]), ts(a["last_report"])
            add({"type": "report", "spec_version": "2.1", "id": sid("report", r["key"]), "created_by_ref": SUITE,
                 "created": first, "modified": last, "name": r["title"], "description": summary(r),
                 "report_types": ["threat-actor"], "published": last, "object_refs": [iid],
                 "external_references": [{"source_name": SOURCES[lane]["publisher"], "url": x["url"],
                                          "description": f"report of {x['date'][:10]}"} for x in a["report_links"]]
                 + [{"source_name": "undertow", "external_id": item_id(r["key"]),
                     "url": f"https://undertow.theintelligence.company/#{item_id(r['key'])}"}],
                 "object_marking_refs": marks, "x_tic_source_grade": a["grade"], "x_tic_status_class": "reported",
                 "x_tic_activity_state": a["state"], "x_tic_reports": a["reports"],
                 "x_tic_first_report": first, "x_tic_quiet_after_days": a["quiet_after_days"]})
            continue
        cid = sid("campaign", r["key"])
        when = ts(r.get("disclosed_at"))
        conf = (r.get("confidence") or {}).get("confidence")
        camp = {"type": "campaign", "spec_version": "2.1", "id": cid, "created_by_ref": SUITE, "created": when,
                "modified": when, "name": r.get("operation_name") or r["title"], "description": summary(r),
                "external_references": [{"source_name": SOURCES[lane]["publisher"], "url": r["url"],
                                         "description": r["disclosure"]["title"]},
                                        {"source_name": "undertow", "external_id": item_id(r["key"]),
                                         "url": f"https://undertow.theintelligence.company/#{item_id(r['key'])}"}],
                "object_marking_refs": marks,
                "x_tic_source_grade": (r.get("grade") if lane == "watch" else None) or SOURCES[lane].get("grade", "A2"),
                "x_tic_status_class": "reported",
                "x_tic_attribution_wording": r.get("origin_wording"),
                "x_tic_origin_level_stated": r.get("origin_level"),
                "x_tic_alignment": r.get("alignment") or [],
                "x_tic_period": r.get("period"),
                "x_tic_counts": r.get("counts") or {},
                "x_tic_disarm_basis": {d["id"]: d["basis"] for d in r.get("disarm") or []}}
        if conf:
            camp["confidence"] = STIX_CONFIDENCE[conf]
        camp = {k: v for k, v in camp.items() if v not in (None, [], {})}
        add(camp)
        refs = [cid]

        def rel(kind, target, desc=None):
            o = {"type": "relationship", "spec_version": "2.1", "id": sid("relationship", f"{cid}|{kind}|{target}"),
                 "created_by_ref": SUITE, "created": when, "modified": when, "relationship_type": kind,
                 "source_ref": cid, "target_ref": target, "object_marking_refs": marks}
            if desc:
                o["description"] = desc
            add(o)
            refs.append(o["id"])

        for cc in r.get("origin") or []:
            lid = _location(add, cc)
            refs.append(lid)
            rel("originates-from", lid, "Origin as the publisher states it; not a finding of sponsorship.")
        for cc in r.get("targets") or []:
            lid = _location(add, cc)
            refs.append(lid)
            rel("targets", lid)
        for ap in disarm.attack_patterns([d["id"] for d in r.get("disarm") or []]):
            add(ap)
            refs.append(ap["id"])
            rel("uses", ap["id"], "Mapped by Undertow from the publisher's description (DISARM rule table)")
        for op in r.get("named_operations") or []:
            o = next((x for x in text.operations() if x["id"] == op), None)
            if not o:
                continue
            iid = sid("intrusion-set", op)
            iset = {"type": "intrusion-set", "spec_version": "2.1", "id": iid, "created_by_ref": SUITE,
                    "created": EPOCH, "modified": EPOCH, "name": o["name"], "object_marking_refs": [tlp["id"]]}
            if o.get("aliases"):
                iset["aliases"] = o["aliases"]
            add(iset)
            refs.append(iid)
            rel("attributed-to", iid, "The publisher names this operation.")
        for org in r.get("orgs") or []:
            if org.get("name") not in named_organisations():
                continue   # only a hand-kept organisation name, never free text
            aid = sid("threat-actor", org["name"])
            add({"type": "threat-actor", "spec_version": "2.1", "id": aid, "created_by_ref": SUITE,
                 "created": EPOCH, "modified": EPOCH, "name": org["name"], "threat_actor_types": ["unknown"],
                 "resource_level": "organization", "description": ORG_NOTE, "object_marking_refs": [tlp["id"]]})
            refs.append(aid)
            rel("attributed-to", aid, f"{SOURCES[lane]['publisher']} names this organisation in its disclosure.")
            if org.get("country"):
                lid = _location(add, org["country"])
                refs.append(lid)
                lr = {"type": "relationship", "spec_version": "2.1",
                      "id": sid("relationship", f"{aid}|located-at|{lid}"), "created_by_ref": SUITE,
                      "created": EPOCH, "modified": EPOCH, "relationship_type": "located-at", "source_ref": aid,
                      "target_ref": lid, "object_marking_refs": [tlp["id"]],
                      "description": "Where the publisher places the organisation; not a finding of sponsorship."}
                add(lr)
                refs.append(lr["id"])
        d = r["disclosure"]
        disclosures.setdefault(d["id"], {"d": d, "lane": lane, "published": when})
        by_disclosure.setdefault(d["id"], []).extend(refs)

    for did, info in disclosures.items():
        d = info["d"]
        add({"type": "report", "spec_version": "2.1", "id": sid("report", did), "created_by_ref": SUITE,
             "created": info["published"], "modified": info["published"], "name": d["title"],
             "report_types": ["threat-report"], "published": info["published"],
             "object_refs": sorted(set(by_disclosure[did])),
             "external_references": [{"source_name": SOURCES[info["lane"]]["publisher"], "url": d["url"]}],
             "object_marking_refs": [tlp["id"], statement[info["lane"]]]})
    for lane in used_lanes:
        s = SOURCES[lane]
        add({"type": "marking-definition", "spec_version": "2.1", "id": statement[lane], "created": EPOCH,
             "created_by_ref": SUITE, "name": f"Source terms: {s['publisher']}", "definition_type": "statement",
             "definition": {"statement": s["licence"]}})
    ordered = sorted(objs.values(), key=lambda o: (o["type"], o["id"]))
    bundle_id = f"bundle--{uuid.uuid5(NAMESPACE, 'bundle:' + '|'.join(o['id'] for o in ordered))}"
    return {"type": "bundle", "id": bundle_id, "objects": ordered}


ORG_NOTE = ("An organisation that a publisher names in its disclosure of an influence operation. Undertow records the "
            "name as the publisher gives it; it is not Undertow's finding of who directed the operation.")


@lru_cache(maxsize=1)
def named_organisations() -> frozenset[str]:
    """The organisation names Undertow keeps by hand: config/operations.json and the registers in config/register/.
    A threat-actor is made only for one of these, so free text (or a person's name) can never become one."""
    names = set()
    for o in json.loads((ROOT / "config" / "operations.json").read_text(encoding="utf-8"))["operations"]:
        names.update(g["name"] for g in o.get("orgs") or [])
    for f in sorted((ROOT / "config" / "register").glob("*.json")):
        reg = json.loads(f.read_text(encoding="utf-8"))
        for o in reg.get("operations") or []:
            names.update(g["name"] for g in o.get("orgs") or [])
    return frozenset(names)


def _location(add, cc: str) -> str:
    from tic_doctrine import geo
    lid = sid("location", cc)
    add({"type": "location", "spec_version": "2.1", "id": lid, "created_by_ref": SUITE, "created": EPOCH,
         "modified": EPOCH, "name": geo.name(cc) or cc, "country": cc})
    return lid


# --- a check against the spec's required properties (no external validator: standard library only) ---------

REQUIRED = {
    "identity": ["name"], "campaign": ["name"], "report": ["name", "published", "object_refs"],
    "location": [], "relationship": ["relationship_type", "source_ref", "target_ref"], "intrusion-set": ["name"],
    "attack-pattern": ["name"], "marking-definition": [], "threat-actor": ["name"],
}
SDO_COMMON = ["type", "spec_version", "id", "created", "modified"]
FORBIDDEN = {"indicator", "observed-data", "user-account", "url", "domain-name", "ipv4-addr", "ipv6-addr",
             "email-addr", "sighting"}
RELS = {("campaign", "originates-from", "location"), ("campaign", "targets", "location"),
        ("campaign", "uses", "attack-pattern"), ("campaign", "attributed-to", "intrusion-set"),
        ("campaign", "attributed-to", "threat-actor"), ("threat-actor", "located-at", "location")}


def validate(bundle: dict) -> list[str]:
    import re
    errs = []
    idre = re.compile(r"^[a-z][a-z0-9-]+--[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    tsre = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
    if bundle.get("type") != "bundle" or not idre.match(bundle.get("id", "")):
        errs.append("bundle: type or id invalid")
    ids = {o.get("id") for o in bundle.get("objects", [])}
    seen = set()
    for o in bundle.get("objects", []):
        t, oid = o.get("type"), o.get("id", "")
        if oid in seen:
            errs.append(f"{oid}: duplicate id")
        seen.add(oid)
        if t in FORBIDDEN:
            errs.append(f"{oid}: type {t} is never emitted")
            continue
        if not idre.match(oid) or not oid.startswith(f"{t}--"):
            errs.append(f"{oid}: id must be '{t}--' plus a UUID")
        if t not in REQUIRED:
            errs.append(f"{oid}: unexpected type {t}")
            continue
        common = ["type", "spec_version", "id", "created"] if t == "marking-definition" else SDO_COMMON
        for k in common + REQUIRED[t]:
            if k not in o:
                errs.append(f"{oid}: missing {k}")
        if o.get("spec_version") != "2.1":
            errs.append(f"{oid}: spec_version must be 2.1")
        for k in ("created", "modified", "published"):
            if k in o and not tsre.match(o[k]):
                errs.append(f"{oid}: {k} is not a STIX timestamp")
        if t == "location" and not (o.get("country") or o.get("region") or ("latitude" in o and "longitude" in o)):
            errs.append(f"{oid}: location needs country, region or latitude and longitude")
        if t == "report" and not o.get("object_refs"):
            errs.append(f"{oid}: report needs object_refs")
        for k in ("created_by_ref",):
            if k in o and o[k] not in ids:
                errs.append(f"{oid}: {k} does not resolve")
        for ref in o.get("object_refs", []) + o.get("object_marking_refs", []):
            if ref not in ids:
                errs.append(f"{oid}: reference {ref} does not resolve")
        if t == "relationship":
            src = o.get("source_ref", "").split("--")[0]
            tgt = o.get("target_ref", "").split("--")[0]
            if (src, o.get("relationship_type"), tgt) not in RELS:
                errs.append(f"{oid}: relationship {src} {o.get('relationship_type')} {tgt} not in the mapping")
            for k in ("source_ref", "target_ref"):
                if o.get(k) not in ids:
                    errs.append(f"{oid}: {k} does not resolve")
        if "confidence" in o and not (isinstance(o["confidence"], int) and 0 <= o["confidence"] <= 100):
            errs.append(f"{oid}: confidence must be an integer 0 to 100")
        if t == "identity" and o.get("identity_class") == "individual":
            errs.append(f"{oid}: no identity for a person")
        if t == "threat-actor":
            if o.get("name") not in named_organisations():
                errs.append(f"{oid}: a threat-actor only for a hand-kept organisation name")
            if o.get("resource_level") != "organization" or o.get("threat_actor_types") != ["unknown"]:
                errs.append(f"{oid}: a threat-actor is an organisation of unknown type, nothing more")
            for k in ("roles", "goals", "primary_motivation", "secondary_motivations", "personal_motivations",
                      "sophistication", "aliases"):
                if k in o:
                    errs.append(f"{oid}: {k} is never stated")
    return errs

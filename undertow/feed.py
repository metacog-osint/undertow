"""Build Undertow's contract-v2 feed (tic-feed/2, GeoJSON) from the collected records.

Two units, kept apart (decision 1, Tom, 16 Nov 2026), both kind "observation", tier "routine", status_class "reported":
- a disclosure: one item per network or operation a publisher disclosed, its report of its own enforcement action or
  its own naming (source grade A2);
- reported activity: one item per operation and reporter (activity.py), saying that an independent reporter has
  reported the operation while it runs, with the first and last report and a state of active or quiet (grade B2 or
  B3, by reporter). It adds no origin unless it is a watch row Tom checked whose reporter shows its own evidence.
Undertow states no probability. Geometry
is on the target countries the publisher names (Google names none, and OpenAI's feed summary seldom states one:
countries only named in a stance or summary are listed as such, not mapped), or null with a link to the page.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import CONTRACT, __version__ as KIT_VERSION, geo  # noqa: E402

from . import activity, disarm, eventtime, listings, openai_rss, targets, text  # noqa: E402

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
                           "Information Manipulation Sets it names, read once from the report's text with page numbers."},
    "dfrlab": {"id": "dfrlab-rss", "publisher": "DFRLab (Atlantic Council)", "grade": "B2",
               "licence": ("Atlantic Council (DFRLab): noncommercial use with credit; operation names, dates and links "
                           "only, no DFRLab text republished"),
               "independence_group": "dfrlab", "source_type": "independent research",
               "descriptor": "Investigations by the Atlantic Council's Digital Forensic Research Lab that name an "
                             "operation Undertow tracks. Independent research, not an enforcement action; "
                             "Undertow does not read its attribution."},
    "checkfirst": {"id": "checkfirst-rss", "publisher": "CheckFirst", "grade": "B2",
                   "licence": ("CheckFirst: read, index and cite with credit and a link (its llms.txt; no terms of use "
                               "published); operation names, dates and links only, no CheckFirst text republished"),
                   "independence_group": "checkfirst", "source_type": "independent research",
                   "descriptor": "Investigations by CheckFirst, a Finnish research firm, that name an operation "
                                 "Undertow tracks. Independent research, not an enforcement action; Undertow does "
                                 "not read its attribution."},
    "correctiv": {"id": "correctiv-rss", "publisher": "CORRECTIV", "grade": "B3",
                  "licence": ("CORRECTIV: no terms of use or licence published (all rights reserved); facts only, "
                              "operation names, dates and links, no CORRECTIV text republished"),
                  "independence_group": "correctiv", "source_type": "news media",
                  "descriptor": "Stories by CORRECTIV, a German investigative newsroom, that name an operation "
                                "Undertow tracks. A newsroom often reports other researchers' findings, so it is "
                                "graded B3; Undertow does not read its attribution."},
    "watch": {"id": "undertow-watch-register", "publisher": "Undertow watch register", "grade": "B3",
              "licence": "Each row keeps its reporter's terms (config/register/watch.json); names, dates and links only",
              "independence_group": "watch", "source_type": "independent research",
              "descriptor": "Reported activity a reporter lane does not match by title (unnamed, or naming tracked operations only "
                            "in the report's text), entered by hand from the reporter's "
                            "own publication after an analyst's review."},
}
REQUIREMENT = {"meta": ["UT-PIR-1", "UT-PIR-2"], "google": ["UT-PIR-1"], "openai": ["UT-PIR-1", "UT-PIR-3"],
               "tiktok": ["UT-PIR-1", "UT-PIR-2"], "eeas": ["UT-PIR-1", "UT-PIR-2", "UT-PIR-3"],
               "dfrlab": ["UT-PIR-1"], "checkfirst": ["UT-PIR-1"], "correctiv": ["UT-PIR-1"], "watch": ["UT-PIR-1"]}


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
    if r.get("activity"):
        a = r["activity"]
        who = a["reporter_name"]
        n = a["reports"]
        span = (f"on {a['first_report'][:10]}" if n == 1 else
                f"{n} times between {a['first_report'][:10]} and {a['last_report'][:10]}")
        label = (a.get("operation_in_sentence") or activity.in_sentence(a["operation_name"])
                 if r["publisher"] == "watch" else a["operation_name"])
        bits.append(f"{who} reported on {label} {span}.")
        bits.append(f"State: {a['state']}" + (
            f" (last report within {a['quiet_after_days']} days)." if a["state"] == "active" else
            f" (no report from {who} in more than {a['quiet_after_days']} days; not evidence the operation stopped)."))
        if r["publisher"] == "watch":
            ap = a.get("activity_period")
            if ap:
                bits.append(f"Activity the report covers: {ap['from']} to {ap['to']}.")
            if r.get("targets") or r.get("target_regions"):
                bits.append("Targets as entered from the report: "
                            + ", ".join(_names(r.get("targets") or []) + (r.get("target_regions") or [])) + ".")
            if r.get("named_operations"):
                names = {o["id"]: o["name"] for o in text.operations()}
                bits.append("Operations Undertow tracks that the report names: "
                            + ", ".join(names.get(o, o) for o in r["named_operations"]) + ".")
            if r.get("alignment"):
                bits.append(f"{who} describes it as aligned with {', '.join(_names(r['alignment']))}"
                            + (f' ("{r["origin_wording"]}")' if r.get("origin_wording") else "")
                            + "; recorded as alignment, not as an origin.")
        else:
            named = r.get("countries_named") or []
            read = a.get("reports_read") or 0
            rg = r.get("target_regions") or []
            if named or (rg and not read):
                bits.append("Countries and regions named in the reporter's feed descriptions: "
                            + ", ".join(_names(named) + ([] if read else rg)) + ".")
            if read and (r.get("targets") or rg):
                who_read = activity.by_machine(read, a.get("reports_checked") or 0)
                bits.append((f"Targets as the reports state them, read from each report{who_read}: "
                             if read == a["reports"] else
                             f"Targets as {read} of the {a['reports']} reports state them, read from the "
                             f"report{who_read}, and for "
                             "the others countries named that a platform's or the EEAS's disclosure of this operation "
                             "records as targets: ")
                            + ", ".join(_names(r.get("targets") or []) + rg) + ".")
            elif r.get("targets"):
                bits.append("Marked on the map only where a platform's or the EEAS's disclosure of this operation "
                            f"records a target: {', '.join(_names(r['targets']))}.")
            if r.get("audience"):
                bits.append(f"Audience as the reports describe it: {r['audience']}.")
            if named and not r.get("targets"):
                bits.append("None of them is a target that a disclosure of this operation records, so the item is "
                            "not marked on the map.")
        if r.get("origin"):
            bits.append(f"Origin as {who} states it from its own evidence, checked against the report: "
                        f"{', '.join(_names(r['origin']))}.")
        elif r["publisher"] == "watch" and r.get("origin_reported"):
            bits.append(f"{who} states an origin ({', '.join(_names(r['origin_reported']))}); Undertow does not count "
                        f"it ({r.get('origin_level')}).")
        else:
            bits.append(f"Undertow records that {who} reported the operation, not {who}'s attribution, so this item "
                        "adds no origin and no confidence.")
        bits.append(f"{who} is a reporter, not the platform that acted (grade {a['grade']}). A country named is not "
                    "an origin, and an origin is never a finding of who directed it.")
        return " ".join(bits)
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
    if r.get("audience"):
        bits.append(f"Audience as stated: {r['audience']} (an audience, not a target country, so not marked on the map).")
    if r.get("countries_named") and not (r.get("targets") or r.get("target_regions")):
        bits.append("Countries named in the publisher's description: " + ", ".join(_names(r["countries_named"]))
                    + " (not stated as targets, so not marked on the map).")
    ct = _counts_text(r.get("counts") or {})
    if ct:
        bits.append(f"Counts: {ct}.")
    if r["publisher"] == "meta":
        bits.append(f"Meta lists {r['counts'].get('indicators', 0)} indicators; Undertow keeps the count only.")
    listed = listings.sentence(r.get("orgs"))
    if listed:
        bits.append(listed)
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
    src.setdefault("grade", "A2")
    if r["publisher"] == "watch":
        rp = r["reporter"]
        src.update({"publisher": rp["name"], "grade": rp["grade"], "licence": rp["terms"],
                    "source_type": rp.get("source_type") or src["source_type"],
                    "independence_group": r["independence_group"]})
    src.update({"title": r["disclosure"]["title"], "url": r["url"], "accessed_at": generated})
    if r.get("disclosed_at"):
        src["published_at"] = r["disclosed_at"]
    sid = src["id"]
    # Only stated targets are marked on the map (Tom, 16 Nov 2026). Countries a description merely names (Google's
    # stance, OpenAI's one line, a reporter's story) stay in `countries` and in the summary, never in the geometry,
    # because they often include where the operators are said to be.
    places = r.get("targets") or []
    countries = list(dict.fromkeys((r.get("origin") or []) + places + (r.get("countries_named") or [])
                                   + (r.get("alignment") or [])))
    props = {
        "contract": CONTRACT,
        "id": item_id(r["key"]),
        "subject_id": item_id(r["key"]),   # a hash of the operation's key, with no date or run stamp
        "program": "undertow",
        "title": r["title"],
        "summary": summary(r),
        "kind": "observation",
        "tier": "routine",
        "status": "actual",
        "msg_type": "new",
        "human_review": targets.human_review(r),
        "us_person_data": "organizations" if r.get("orgs") else "none",
        "status_class": "reported",
        "product_category": "current",
        "data_as_of": r.get("disclosed_at") or generated,
        "published_at": generated,
        **({"data_as_of_precision": r["disclosed_precision"]}
           if r.get("disclosed_at") and r.get("disclosed_precision") else {}),
        **eventtime.fields(r),
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
            "listed_by": listings.for_orgs(r.get("orgs")),
            "targets": r.get("targets") or [],
            "target_regions": r.get("target_regions") or [],
            "countries_named": r.get("countries_named") or [],
            **({"audience": r["audience"]} if r.get("audience") else {}),
            **({"target_review": r["target_review"]} if r.get("target_review") else {}),
            "platforms": r.get("platforms") or [],
            "counts": r.get("counts") or {},
            "corroborated_by": r.get("corroborated_by") or [],
            "withheld": r.get("withheld", 0),
        },
    }
    if r.get("languages"):
        props["operation"]["languages"] = r["languages"]
    if r.get("activity"):
        props["activity"] = r["activity"]
    if r.get("confidence"):
        props.update(r["confidence"])
    if r.get("coverage_fraction") is not None:
        props["coverage_fraction"] = r["coverage_fraction"]
    return {"type": "Feature", "geometry": _geometry(places), "properties": props}


def health(lanes: dict, records: list[dict], generated: str | None = None) -> dict:
    """The feed's per-source health record, keyed by the source id the lane's items carry (the key the kit's history
    log and COP's ledger read), in Cordon's and Headwind's shape: state, last_ok, last_error, failures, checked_at,
    detail, plus lane and data_as_of (the newest disclosure date among the lane's items).

    State is "up" when the lane was read on its last check and "failing" when it was not (its last good items stay
    in the feed, marked from_previous on the page). Disclosures come twice a year to quarterly with no fixed date, so
    the kit's "fresh", "late" and "stale" would judge nothing. A failing lane's last_ok is older than its checked_at,
    so the history log ends none of its items."""
    newest: dict[str, str] = {}
    for r in records:
        d = r.get("disclosed_at")
        if d and d > newest.get(r["publisher"], ""):
            newest[r["publisher"]] = d
    out = {}
    for lane, src in SOURCES.items():
        st = lanes.get(lane) or {}
        ok = st.get("status") == "ok"
        failed = st.get("status") == "failed"
        n = st.get("items") or 0
        if ok:
            detail = f"{n} items" + (" (last good copy, not read on this run)" if st.get("from_previous") else "")
        elif failed:
            detail = (f"not read; {n} items from the last good copy" if st.get("from_previous")
                      else "not read; no earlier copy, so no items")
        else:
            detail = "not run yet"
        out[src["id"]] = {
            "state": "up" if ok else "failing" if failed else "never",
            "last_ok": st.get("fetched_at"),
            "last_error": st.get("error") if failed else None,
            "failures": int(st.get("failures") or 0) if (ok or failed) else 0,
            "checked_at": (st.get("failed_at") if failed else st.get("fetched_at")) or generated,
            "detail": detail,
            "lane": lane,
            "data_as_of": newest.get(lane),
        }
    return out


def enforcement_features(base: dict, records: list[dict], generated: str) -> list[dict]:
    """One item per Dismantled period outside its publisher's trailing 8-period range (baseline.RULE). It is tier
    "anomaly", worded as unusual enforcement against the publisher's own record, never as activity, only while the
    publisher's flag rate is within the feed contract's 5% cap for a series (layer `rated_unusual`); otherwise it
    is routine and says why it is not rated unusual. Its time and source are the period's own disclosure; it has no
    place, since an enforcement record is not a target."""
    from undertow import baseline
    out = []
    for pub, layer in (base.get("dismantled") or {}).items():
        rate = layer.get("flag_rate")
        unusual = bool(layer.get("rated_unusual"))
        for p in layer["periods"]:
            if not p.get("outside"):
                continue
            recs = [r for r in records if r.get("publisher") == pub and r.get("lane") == pub
                    and (baseline._period(r) or (None,))[0] == p["key"]]
            if recs:
                last = max(recs, key=lambda r: r.get("disclosed_at") or "")
            elif p.get("source") == baseline.NO_POSTS:
                # A quarter with no posts: the feed that was read is the source.
                feed_ref = {"id": f"{pub}:news-rss", "title": f"{SOURCES[pub]['publisher']} news RSS feed",
                            "url": openai_rss.RSS_URL}
                last = {"disclosure": feed_ref, "url": feed_ref["url"]}
            else:
                continue    # a period read only from the counts register has no disclosure to cite
            t = p["trailing"]
            word = "more" if p["outside"] == "above" else "fewer"
            name = SOURCES[pub]["publisher"]
            key = f"enforcement:{pub}:{p['key']}"
            src = dict(SOURCES[pub])
            src.setdefault("grade", "A2")
            src.update({"title": last["disclosure"]["title"], "url": last["url"], "accessed_at": generated})
            if last.get("disclosed_at"):
                src["published_at"] = last["disclosed_at"]
            origins = [c for c in p["origin"] if c != "none"]
            measured = (f"{name} disclosed {p['items']} takedowns in its {p['period']}, against {t['min']} to "
                        f"{t['max']} (mean {t['mean']}) in its previous {t['periods']} periods ({layer['grain']}).")
            if unusual:
                lead = f"Unusual enforcement against {name}'s own record: {measured}"
            else:
                lead = (f"Outside {name}'s own record, not rated unusual: {measured} The rule puts "
                        f"{layer['outside']} of {name}'s {layer['rated']} rated periods outside their range "
                        f"({rate:.0%}); a period is rated unusual only while the rule puts no more than "
                        f"{baseline.FLAG_RATE_CAP:.0%} of them outside, so this item is routine.")
            props = {
                "contract": CONTRACT, "id": item_id(key), "subject_id": item_id(key), "program": "undertow",
                "title": (f"{name}, {p['period']}: {p['items']} takedowns, {word} than in any of its previous 8 "
                          f"periods ({t['min']} to {t['max']})"),
                "summary": (lead + f" This counts what {name} chose to disclose, not how much influence activity "
                            "there was. Rule: " + baseline.RULE
                            + f" The origins counted are where the operators were, as {name} states them; an origin "
                            "is never a finding of who directed it."),
                "kind": "observation", "tier": "anomaly" if unusual else "routine", "status": "actual",
                "msg_type": "new",
                "human_review": "none", "us_person_data": "none", "status_class": "reported",
                "product_category": "current",
                "data_as_of": last.get("disclosed_at") or generated, "published_at": generated,
                **({"data_as_of_precision": last["disclosed_precision"]}
                   if last.get("disclosed_at") and last.get("disclosed_precision") else {}),
                "countries": origins,
                "pmesii_pt": ["information", "political"], "ie_aspect": ["informational", "human"],
                "ascope": ["people", "organizations"], "continuum": "competition",
                "requirement_ids": REQUIREMENT[pub], "method_version": METHOD, "precision_class": "none",
                "visual": {"type": "page", "url": f"{SITE}/#method"},
                "sources": [src], "actors": [],
                # The operation fields every Undertow item carries, empty where a period has none, so readers of the
                # feed (COP's joins, the page) need no special case.
                "disarm_version": disarm.VERSION, "disarm_technique": [], "disarm_mapping": [],
                "disarm_rules_status": "reviewed" if disarm.reviewed() else "proposed, not yet reviewed",
                "operation": {"key": key, "publisher": pub, "disclosure": last["disclosure"], "operation_name": None,
                              "named_operations": [], "period": p["period"], "origin": [], "origin_wording": None,
                              "origin_level_stated": None, "alignment": [], "sponsor": [], "listed_by": [],
                              "targets": [], "target_regions": [], "countries_named": [], "platforms": [],
                              "counts": {"takedowns": p["items"]}, "corroborated_by": [], "withheld": 0},
                "baseline_ref": {"id": f"undertow-dismantled-{pub}", "type": "rolling",
                                 "window": f"trailing {t['periods']} periods ({layer['grain']})",
                                 **({"flag_rate": rate} if rate is not None else {})},
                "baseline": {"layer": "dismantled", "publisher": pub, "period": p["key"], "period_label": p["period"],
                             "items": p["items"], "trailing": t, "outside": p["outside"], "closed": p["closed"],
                             "origin": p["origin"], "rated_periods": layer["rated"],
                             "outside_periods": layer["outside"], "flag_rate_cap": baseline.FLAG_RATE_CAP,
                             "rule": baseline.RULE},
            }
            out.append({"type": "Feature", "geometry": None, "properties": props})
    return out


def build_feed(records: list[dict], generated: str, health_record: dict | None = None,
               extra: list[dict] | None = None) -> dict:
    feats = [feature(r, generated) for r in records] + list(extra or [])
    feats.sort(key=lambda f: (f["properties"]["data_as_of"], f["properties"]["id"]), reverse=True)
    doc = {
        "type": "FeatureCollection",
        "contract": CONTRACT,
        "contract_rev": "2.1",
        "kit": KIT_VERSION,
        "program": "undertow",
        "generated_at": generated,
        "method_version": METHOD,
        "licence": ("Undertow's own text: CC BY 4.0 (The Intelligence Company). Each item keeps its source's terms: "
                    "Meta MIT; Google facts and counts only; OpenAI RSS quoted with credit; TikTok via the EU Code of "
                    "Conduct Transparency Centre; EEAS reuse with acknowledgement; DFRLab (Atlantic Council) names, dates and links "
                    "only, noncommercial, with credit; CheckFirst and CORRECTIV names, dates and links only, with "
                    "credit. DISARM technique names CC BY-SA 4.0 "
                    "(DISARM Foundation)."),
        "attribution": ("Undertow, The Intelligence Company. Sources: Meta threat-research repository; Google Influence "
                        "Operations Bulletin; OpenAI news RSS; TikTok's reports to the EU Code of Conduct on "
                        "Disinformation; EEAS 4th report on FIMI threats; Atlantic Council's Digital Forensic Research Lab (DFRLab); CheckFirst; CORRECTIV. DISARM Framework v1.6.1, DISARM Foundation, "
                        "CC BY-SA 4.0."),
        "language_key": LANGUAGE_KEY,
        "note": ("Operation level only: no indicator values, account handles, URLs, domains or names of individuals. "
                 "Origin is the publisher's judgment of where the operators were and is never read as sponsorship."),
    }
    if health_record is not None:
        doc["health"] = health_record
    doc["features"] = feats
    return doc

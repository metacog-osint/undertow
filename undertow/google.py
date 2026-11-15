"""Google lane: the Influence Operations Bulletin (formerly the TAG Bulletin), one page per quarter.

Pages are found from blog.google's security RSS and from the URL pattern
blog.google/security/influence-operations-bulletin-qN-YYYY/ for every quarter from FIRST_QUARTER to the current
one (a quarter not yet published answers 404 and is skipped). Tom's decision, 14 Nov 2026: automate; facts and
counts only, no bulletin text republished. robots.txt disallows only search paths.

Each bulletin entry is one sentence pair of a fixed form: "We terminated N YouTube channels [and ...] as part of
our [ongoing] investigation into coordinated influence operations [linked to X]. The campaign was sharing content
in <languages> that was supportive of <...> and critical of <...>." Kept per entry: month, asset counts, the
linked-to country, languages, and the countries the stance names. Not kept: the stance wording itself.
Entries the pattern does not read are kept and counted (`unparsed`), with whatever asset counts can be read.
"""
from __future__ import annotations

import html
import re
from datetime import date

from . import disarm, text

RSS_URL = "https://blog.google/security/rss/"
PAGE_URL = "https://blog.google/security/influence-operations-bulletin-q{q}-{y}/"
FIRST_QUARTER = (2026, 1)
LICENCE = "Google; facts and counts only (no bulletin text republished)"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

PAGE_LINK_RE = re.compile(r"https://blog\.google/security/influence-operations-bulletin-q([1-4])-(\d{4})/")
ENTRY_RE = re.compile(
    r"^We (?P<verb>terminated|blocked|removed|banned|suspended) (?P<assets>.+?) as part of our (?P<ongoing>ongoing )?investigation into "
    r"(?:a )?coordinated influence operations?(?: (?:campaign )?linked to (?P<linked>[^.]+?))?\.\s*(?P<rest>.*)$")
ASSET_RE = re.compile(r"(?P<n>\d[\d,]*)\s+(?P<what>YouTube channels?|Blogger blogs?|Ads accounts?|AdSense accounts?|"
                      r"(?:Google )?Play (?:developers?|(?:developer )?accounts?)|Drive accounts?|Gmail accounts?|Photos accounts?|"
                      r"Google News (?:surfaces? )?(?:and Discover )?(?:domains?)?|domains?|accounts?|channels?|blogs?)", re.I)
DATE_RE = re.compile(r"last updated on (?P<d>[A-Z][a-z]+ \d{1,2}, \d{4})")


def candidate_urls(today: date, rss: bytes | None) -> list[tuple[int, int, str]]:
    found = set()
    y, q = FIRST_QUARTER
    cur = (today.year, (today.month - 1) // 3 + 1)
    while (y, q) <= cur:
        found.add((y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    if rss:
        for m in PAGE_LINK_RE.finditer(rss.decode("utf-8", errors="replace")):
            yq = (int(m.group(2)), int(m.group(1)))
            if yq >= FIRST_QUARTER:
                found.add(yq)
    return [(y, q, PAGE_URL.format(q=q, y=y)) for y, q in sorted(found)]


def page_lines(body: bytes) -> list[str]:
    t = body.decode("utf-8", errors="replace")
    m = re.search(r"<article.*?</article>", t, re.S)
    t = m.group(0) if m else t
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = re.sub(r"<(p|li|h\d|div|br)[^>]*>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace(" ", " ")
    return [re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n") if ln.strip()]


def _assets(s: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in ASSET_RE.finditer(s):
        what = m.group("what").lower()
        n = int(m.group("n").replace(",", ""))
        if "youtube" in what:
            k = "youtube_channels"
        elif "blogger" in what or what.startswith("blog"):
            k = "blogger_blogs"
        elif "adsense" in what:
            k = "adsense_accounts"
        elif "ads" in what:
            k = "ads_accounts"
        elif "play" in what:
            k = "play_accounts"
        elif "domain" in what or "news" in what:
            k = "news_discover_domains" if "eligibility" in s or "Discover" in s else "domains"
        else:
            k = "other_accounts"
        out[k] = out.get(k, 0) + n
    return out


def _clean_country(s: str) -> str:
    s = re.sub(r"\s*\([^)]*\)", "", s).strip()
    return re.sub(r"^the ", "", s)


def _phrase_list(s: str | None) -> list[str]:
    if not s:
        return []
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+(?:of\s+)?", s)
    return [p.strip() for p in parts if p.strip()]


def parse_page(body: bytes, year: int, quarter: int) -> dict:
    lines = page_lines(body)
    m = None
    for ln in lines:
        m = DATE_RE.search(ln)
        if m:
            break
    updated = None
    if m:
        from datetime import datetime
        try:
            updated = datetime.strptime(m.group("d"), "%B %d, %Y").date().isoformat()
        except ValueError:
            updated = None
    month, entries, unparsed, ordinal = None, [], [], {}
    for ln in lines:
        if ln in MONTHS:
            month = f"{year}-{MONTHS.index(ln) + 1:02d}"
            continue
        if month is None or not ln.startswith("We "):
            continue
        ordinal[month] = ordinal.get(month, 0) + 1
        key = f"google:{year}-q{quarter}:{month}:{ordinal[month]:02d}"
        em = ENTRY_RE.match(ln)
        if not em:
            unparsed.append({"key": key, "month": month, "assets": _assets(ln)})
            continue
        rest = em.group("rest")
        linked = em.group("linked")
        origin_cc = []
        firm = None
        if linked:
            cc = text.country_code(_clean_country(linked)) or (text.countries_in(linked) or [None])[0]
            if cc:
                origin_cc = [cc]
        lm = re.search(r"The campaign was linked to (?P<firm>an? [^.]*?(?:firm|company|agency|organi[sz]ation|group))", rest)
        if lm:
            firm = lm.group("firm")
        langs = []
        lg = re.search(r"content in (?P<l>.+?) (?:that|about)\b", rest)
        if lg:
            langs = _phrase_list(lg.group("l"))
        sup = re.search(r"supportive of (?P<s>.+?)(?: and critical of| and about|\.|$)", rest)
        crit = re.search(r"critical of (?P<c>.+?)(?:\.|$)", rest)
        about = re.search(r"content (?:in .+? )?about (?P<a>.+?)\.", rest)
        named = []
        for grp in (sup and sup.group("s"), crit and crit.group("c"), about and about.group("a")):
            for cc in text.countries_in(grp or ""):
                if cc not in named and cc not in origin_cc:
                    named.append(cc)
        leads = re.search(r"received leads from (?P<who>.+?) that", rest)
        entries.append({
            "key": key, "month": month,
            "verb": em.group("verb"),
            "assets": _assets(em.group("assets")),
            "ongoing": bool(em.group("ongoing")),
            "consistent_with_previous": "consistent with our previous reports" in rest,
            "linked_to": _clean_country(linked) if linked else None,
            "origin": origin_cc,
            "linked_org_wording": firm,
            "languages": langs,
            "stance_countries": named,
            "leads_from": leads.group("who") if leads else None,
            "_rest": rest,
        })
    return {"year": year, "quarter": quarter, "updated": updated, "entries": entries, "unparsed": unparsed}


ASSET_WORDS = {"youtube_channels": "YouTube channels", "blogger_blogs": "Blogger blogs", "ads_accounts": "Ads accounts",
               "adsense_accounts": "AdSense accounts", "play_accounts": "Google Play accounts",
               "news_discover_domains": "domains blocked from Google News and Discover", "domains": "domains",
               "other_accounts": "other accounts"}


SINGULAR = {"youtube_channels": "YouTube channel", "blogger_blogs": "Blogger blog", "ads_accounts": "Ads account",
            "adsense_accounts": "AdSense account", "play_accounts": "Google Play account",
            "news_discover_domains": "domain blocked from Google News and Discover", "domains": "domain",
            "other_accounts": "other account"}


def assets_text(a: dict) -> str:
    parts = [f"{n:,} {(SINGULAR if n == 1 else ASSET_WORDS).get(k, k)}" for k, n in a.items()]
    if not parts:
        return "assets"
    return " and ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + " and " + parts[-1]


def build_records(pages: list[dict], urls: dict[tuple[int, int], str]) -> list[dict]:
    out = []
    for pg in pages:
        url = urls[(pg["year"], pg["quarter"])]
        for e in pg["entries"]:
            from tic_doctrine import geo
            where = (f"linked to {geo.name(e['origin'][0]) or e['linked_to']}" if e["origin"]
                     else f"linked to {e['linked_to']}" if e["linked_to"] else "no country named")
            verb = {"blocked": "blocked", "banned": "banned"}.get(e["verb"], "terminated")
            title = f"Google: {assets_text(e['assets'])} {verb}, {where} ({e['month']})"
            if set(e["assets"]) == {"news_discover_domains"}:
                title = f"Google: {assets_text(e['assets'])}, {where} ({e['month']})"
            # DISARM: the stance wording is read for rules but never kept; Google states assets, not behaviours.
            maps = disarm.map_text([e["_rest"]])
            for d in maps:
                d["phrase"] = None    # facts only: the matched Google wording is not republished
            counts = dict(e["assets"])
            out.append({
                "key": e["key"], "lane": "google", "publisher": "google",
                "disclosure": {"id": f"google:{pg['year']}-q{pg['quarter']}",
                               "title": f"Google Influence Operations Bulletin Q{pg['quarter']} {pg['year']}", "url": url},
                "title": title,
                "operation_name": None,
                "named_operations": [],
                "period": e["month"],
                "disclosed_at": f"{pg['updated']}T00:00:00Z" if pg["updated"] else None,
                "disclosed_precision": "day" if pg["updated"] else None,   # the bulletin gives a date, no time
                "origin": e["origin"], "origin_text": e["linked_to"],
                "origin_wording": f"linked to {e['linked_to']}" if e["linked_to"] else None,
                "origin_level": "moderate" if e["origin"] else "none",
                "alignment": [],
                "targets": [], "target_regions": [], "target_text": None,
                "countries_named": e["stance_countries"],
                "languages": e["languages"],
                "platforms": sorted({"YouTube" if k == "youtube_channels" else "Blogger" if k == "blogger_blogs"
                                     else "Google Ads" if k == "ads_accounts" else "Google News and Discover"
                                     if k == "news_discover_domains" else "Google" for k in e["assets"]}),
                "counts": counts,
                "ongoing": e["ongoing"],
                "consistent_with_previous": e["consistent_with_previous"],
                "linked_org_wording": e["linked_org_wording"],
                "leads_from": text.scrub(e["leads_from"])[0] if e["leads_from"] else None,
                "summary": None, "summary_note": None,
                "orgs": [],
                "url": url,
                "withheld": 0,
                "disarm": maps,
            })
    return out

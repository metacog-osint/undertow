"""Reporter lanes: independent researchers and newsrooms that report influence operations while they run.

A reporter is not a platform. It reports operations it investigated, not takedowns of its own. Each lane reads the
reporter's WordPress RSS feed pages (`?paged=N`), never an article page, and keeps an article only when its title or
one-line description names an operation Undertow already tracks (by name or a publisher-given alias in
config/operations.json, case-sensitive as every lane).

Kept per article (a "report" record, held in the snapshot only): the operations named, the publication time, the
link, the countries named (codes) and platforms from a fixed list. Never kept: the reporter's title or description
text (they name individuals, and the scrubber's single-surname gap, UT-ASM-4, would let some through), authors
(`dc:creator` and author categories), attribution wording, and anything from the article page.

Report records are not feed items. activity.py folds them into one "reported activity" item per operation and
reporter (decision 1, 16 Nov 2026). A reporter adds no origin line, so it never changes a confidence level.

New, unnamed activity is not matched here. `triage()` lists influence-worded articles that name no tracked operation
for the analyst to read, on the laptop only (decision 2): see tools/undertow.py triage. Its output holds the reporters'
headlines and is never published.

Terms, read before each lane was built:
- DFRLab (16 Nov 2026): Atlantic Council Terms and Conditions of Use (dfrlab.org/terms-of-use/ answers 404; dfrlab.org
  is an Atlantic Council site): copies for noncommercial use with the Council's notices retained; automated access no
  faster than a person browsing; no harvesting of personal information. robots.txt has an empty Disallow.
- CheckFirst (16 Nov 2026): no terms of use published (privacy policy only, footer "(c) CheckFirst 2026"). Its
  llms.txt says "You are welcome to read, index and cite this site" and asks that findings be attributed to
  CheckFirst with a link to the original publication. robots.txt allows everything but admin and search paths.
- Correctiv (16 Nov 2026): no terms of use or licence found (legal disclosure and imprint only; /en/terms-of-use/,
  /nutzungsbedingungen/ and /en/republishing/ answer 404). robots.txt does not disallow the feed. Its text is
  therefore all rights reserved: the lane keeps facts (operation named, date, link) only, as set for Google.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from . import disarm, text

PAUSE_S = 2.0
OVERLAP_DAYS = 30           # after the first run, read back this far past the newest item seen last time


@dataclass(frozen=True)
class Reporter:
    id: str                 # lane id and publisher key
    name: str               # short name in titles
    credit: str             # the credit line the reporter asks for
    feed_url: str
    link_prefix: str        # every kept link must start with this
    grade: str              # source grade for its reports (decision 1: B2 or B3, by reporter)
    grade_reason: str
    since: str = "2024-01-01"
    max_pages: int = 40


REPORTERS: dict[str, Reporter] = {
    "dfrlab": Reporter(
        "dfrlab", "DFRLab", "Atlantic Council's Digital Forensic Research Lab (DFRLab)",
        "https://dfrlab.org/feed/", "https://dfrlab.org/", "B2",
        "an established research lab that publishes its own investigations with its evidence"),
    "checkfirst": Reporter(
        "checkfirst", "CheckFirst", "CheckFirst",
        "https://checkfirst.network/feed/", "https://checkfirst.network/", "B2",
        "a research firm that publishes its own investigations of information operations with its evidence"),
    "correctiv": Reporter(
        "correctiv", "CORRECTIV", "CORRECTIV",
        "https://correctiv.org/en/feed/", "https://correctiv.org/en/", "B3",
        "an investigative newsroom whose influence-operation stories often report other researchers' findings"),
}

# Platforms as the reporters tag them; any other category (topics, regions, author names) is never kept.
PLATFORMS = {"Facebook": "Facebook", "Instagram": "Instagram", "Telegram": "Telegram", "TikTok": "TikTok",
             "YouTube": "YouTube", "Twitter": "X", "X": "X", "VKontakte": "VKontakte", "VK": "VKontakte",
             "WhatsApp": "WhatsApp", "Threads": "Threads", "Bluesky": "Bluesky", "Reddit": "Reddit",
             "Wikipedia": "Wikipedia", "Rumble": "Rumble", "Odnoklassniki": "Odnoklassniki"}

# Wording that marks an article as about influence operations, for the triage list only.
INFLUENCE = re.compile(
    r"(?i)\b(inauthentic|influence (?:operation|campaign|network)s?|information operations?|FIMI|"
    r"foreign information manipulation|information manipulation|disinformation (?:campaign|network|operation)s?|"
    r"coordinated (?:network|campaign|behaviou?r)|bot ?nets?|bot networks?|troll farms?|propaganda networks?|"
    r"fake (?:accounts|news sites|websites|media)|impersonat\w+|clone sites?|cloned (?:sites|websites|media)|"
    r"election interference|foreign interference)\b")


def page_url(rep: Reporter, n: int) -> str:
    return rep.feed_url if n == 1 else f"{rep.feed_url}?paged={n}"


def _plain(s: str | None) -> str:
    """The description's first paragraph as plain text (the rest is WordPress's 'appeared first on' line)."""
    first = (s or "").split("</p>", 1)[0]
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", first))).strip()


def parse_page(body: bytes) -> list[dict]:
    root = ET.fromstring(body)
    out = []
    for it in root.findall("./channel/item"):
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "").strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            continue
        out.append({"title": (it.findtext("title") or "").strip(), "description": _plain(it.findtext("description")),
                    "categories": [(c.text or "").strip() for c in it.findall("category")],
                    "published": when, "link": (it.findtext("link") or "").strip()})
    return out


def ops_fingerprint() -> str:
    """A hash of the tracked operations' names and aliases: when it changes, the next run reads the whole feed again,
    so an alias added later still finds the older articles that use it."""
    names = sorted((o["id"], o["name"], tuple(o.get("aliases") or [])) for o in text.operations())
    return hashlib.sha256(json.dumps(names, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _slug(link: str) -> str:
    return link.rstrip("/").rsplit("/", 1)[-1]


def build_record(rep: Reporter, it: dict) -> dict | None:
    """A report record for an article that names a tracked operation, else None."""
    if it["published"] < rep.since or not it["link"].startswith(rep.link_prefix):
        return None
    blob = it["title"] + " " + it["description"]
    ops = text.named_operations(blob)
    if not ops:
        return None
    maps = disarm.map_text([text.scrub(blob)[0]])
    for d in maps:
        d["phrase"] = None        # the reporter's wording is not republished; the technique is Undertow's reading
    return {
        "key": f"{rep.id}:{_slug(it['link'])}", "lane": rep.id, "publisher": rep.id,
        "named_operations": ops,
        "disclosed_at": it["published"],
        "target_regions": text.regions_in(blob),
        "countries_named": text.countries_in(blob),
        "platforms": sorted({PLATFORMS[c] for c in it["categories"] if c in PLATFORMS}),
        "url": it["link"],
        "disarm": maps,
    }


def read(rep: Reporter, fetch_page, prev_extra: dict | None, pause: float = PAUSE_S) -> tuple[list[dict], dict, int]:
    """Read feed pages newest first. fetch_page(n) returns the page's bytes or None past the last page (404).

    First run (no complete backfill on record, or the tracked operations changed since): read back to rep.since.
    Later runs: stop once a page reaches OVERLAP_DAYS before the newest item read last time. Returns (records, extra,
    pages read)."""
    prev_extra = prev_extra or {}
    fp = ops_fingerprint()
    backfilled = (prev_extra.get("backfilled_to") or "9999") <= rep.since and prev_extra.get("ops_fingerprint") == fp
    stop_at = rep.since
    if backfilled and prev_extra.get("newest_read"):
        nr = datetime.fromisoformat(prev_extra["newest_read"].replace("Z", "+00:00"))
        stop_at = max(rep.since, (nr - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    items, n, oldest, reached_end = [], 0, None, False
    while n < rep.max_pages:
        n += 1
        if n > 1 and pause:
            time.sleep(pause)
        body = fetch_page(n)
        if body is None:
            reached_end = True
            break
        page = parse_page(body)
        if not page:
            reached_end = True
            break
        items += page
        oldest = min(i["published"] for i in page)
        if oldest < stop_at:
            break
    if not items:
        raise ValueError(f"{rep.name} feed parsed to no items")
    records = [r for r in (build_record(rep, i) for i in items) if r]
    newest = max(i["published"] for i in items)
    complete = backfilled or (oldest is not None and oldest < rep.since) or reached_end
    extra = {"pages_read": n, "items_read": len(items), "newest_read": newest, "oldest_read": oldest,
             "backfilled_to": rep.since if complete else None, "ops_fingerprint": fp}
    return records, extra, n


def merge(rep: Reporter, new: list[dict], previous: list[dict] | None) -> list[dict]:
    """New records replace earlier copies with the same key; earlier records not re-read this run are kept."""
    by = {r["key"]: r for r in previous or [] if r.get("disclosed_at", "") >= rep.since and r.get("url")}
    by.update({r["key"]: r for r in new})
    return sorted(by.values(), key=lambda r: (r["disclosed_at"], r["key"]), reverse=True)


def is_end(exc: Exception) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and exc.code == 404


def triage_candidates(rep: Reporter, items: list[dict], since: str) -> list[dict]:
    """Articles since `since` with influence wording that name no tracked operation. Private: these keep the
    reporter's own headline, which can name individuals, so they go to data/triage.jsonl on the laptop only."""
    out = []
    for it in items:
        if it["published"] < since or not it["link"].startswith(rep.link_prefix):
            continue
        blob = it["title"] + " " + it["description"]
        if text.named_operations(blob):
            continue
        words = sorted({m.group(0).lower() for m in INFLUENCE.finditer(blob)})
        if not words:
            continue
        out.append({"reporter": rep.id, "published": it["published"], "link": it["link"], "title": it["title"],
                    "wording": words, "countries_named": text.countries_in(blob)})
    return out

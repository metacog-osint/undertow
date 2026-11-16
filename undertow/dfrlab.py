"""DFRLab lane: corroboration and link-out from the Atlantic Council's Digital Forensic Research Lab.

DFRLab is an independent research lab, not a platform: it reports operations it investigated, not takedowns of its
own. This lane keeps only DFRLab articles that name an operation Undertow already tracks (by name or a
publisher-given alias in config/operations.json), so each item says "DFRLab reported on this operation on this date"
and links to the article. In the cross-publisher reading it adds DFRLab to an operation's corroborating publishers;
it does not add an origin line, because Undertow does not read DFRLab's attribution wording.

Read: `dfrlab.org/feed/` (WordPress RSS, ten items a page, `?paged=N`), the one-line description and the categories.
Kept per item: the operations named, the publication time, the link, the countries named (codes) and platforms from
a fixed list. Never kept: DFRLab's article title or description text (they name individuals, and the scrubber's
single-surname gap, UT-ASM-4, would let some through), authors (`dc:creator`, and the author categories), and
anything from the article page, which this lane never fetches.

Terms (Atlantic Council Terms and Conditions of Use, read 16 Nov 2026; dfrlab.org/terms-of-use/ answers 404, and
dfrlab.org is an Atlantic Council site): copies for noncommercial use with the Council's notices retained; automated
access no faster than a person browsing; no harvesting of personal information. robots.txt has an empty Disallow.
The lane reads feed pages one at a time with a pause, and after the first run only until it reaches what it read
before.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from . import disarm, text

FEED_URL = "https://dfrlab.org/feed/"
PAGE_URL = "https://dfrlab.org/feed/?paged={n}"
SINCE = "2024-01-01"
MAX_PAGES = 40
OVERLAP_DAYS = 30           # after the first run, read back this far past the newest item seen last time
PAUSE_S = 2.0
LICENCE = ("Atlantic Council (DFRLab): noncommercial use with credit; operation names, dates and links only, no "
           "DFRLab text republished")
CREDIT = "Atlantic Council's Digital Forensic Research Lab (DFRLab)"

# Platforms as DFRLab tags them; any other category (topics, regions, author names) is never kept.
PLATFORMS = {"Facebook": "Facebook", "Instagram": "Instagram", "Telegram": "Telegram", "TikTok": "TikTok",
             "YouTube": "YouTube", "Twitter": "X", "X": "X", "VKontakte": "VKontakte", "VK": "VKontakte",
             "WhatsApp": "WhatsApp", "Threads": "Threads", "Bluesky": "Bluesky", "Reddit": "Reddit",
             "Wikipedia": "Wikipedia", "Rumble": "Rumble", "Odnoklassniki": "Odnoklassniki"}


def page_url(n: int) -> str:
    return FEED_URL if n == 1 else PAGE_URL.format(n=n)


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


def build_record(it: dict) -> dict | None:
    """A record for an article that names a tracked operation, else None."""
    if it["published"] < SINCE or not it["link"].startswith("https://dfrlab.org/"):
        return None
    blob = it["title"] + " " + it["description"]
    ops = text.named_operations(blob)
    if not ops:
        return None
    names = {o["id"]: o["name"] for o in text.operations()}
    op_names = [names[o] for o in ops]
    day = it["published"][:10]
    maps = disarm.map_text([text.scrub(blob)[0]])
    for d in maps:
        d["phrase"] = None        # DFRLab's wording is not republished; the technique is Undertow's reading of it
    return {
        "key": f"dfrlab:{_slug(it['link'])}", "lane": "dfrlab", "publisher": "dfrlab",
        "disclosure": {"id": f"dfrlab:{_slug(it['link'])}", "title": f"DFRLab investigation, {day}", "url": it["link"]},
        "title": f"DFRLab reports on {', '.join(op_names)}",
        "operation_name": None,
        "named_operations": ops,
        "period": it["published"][:7],
        "disclosed_at": it["published"],
        "disclosed_precision": None,
        "origin": [], "origin_text": None, "origin_wording": None, "origin_level": "not read",
        "alignment": [],
        "targets": [], "target_regions": text.regions_in(blob), "target_text": None,
        "countries_named": text.countries_in(blob),
        "platforms": sorted({PLATFORMS[c] for c in it["categories"] if c in PLATFORMS}),
        "counts": {},
        "summary": None, "summary_note": None,
        "orgs": [],
        "url": it["link"],
        "withheld": 0,
        "disarm": maps,
    }


def read(fetch_page, prev_extra: dict | None, pause: float = PAUSE_S) -> tuple[list[dict], dict, int]:
    """Read feed pages newest first. fetch_page(n) returns the page's bytes or None past the last page (404).

    First run (no complete backfill on record, or the tracked operations changed since): read back to SINCE. Later
    runs: stop once a page reaches OVERLAP_DAYS before the newest item read last time. Returns (records, extra,
    pages read)."""
    prev_extra = prev_extra or {}
    fp = ops_fingerprint()
    backfilled = (prev_extra.get("backfilled_to") or "9999") <= SINCE and prev_extra.get("ops_fingerprint") == fp
    stop_at = SINCE
    if backfilled and prev_extra.get("newest_read"):
        from datetime import datetime, timedelta
        nr = datetime.fromisoformat(prev_extra["newest_read"].replace("Z", "+00:00"))
        stop_at = max(SINCE, (nr - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    items, n, oldest, reached_end = [], 0, None, False
    while n < MAX_PAGES:
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
        raise ValueError("DFRLab feed parsed to no items")
    records = [r for r in (build_record(i) for i in items) if r]
    newest = max(i["published"] for i in items)
    complete = backfilled or (oldest is not None and oldest < SINCE) or reached_end
    extra = {"pages_read": n, "items_read": len(items), "newest_read": newest, "oldest_read": oldest,
             "backfilled_to": SINCE if complete else None, "ops_fingerprint": fp}
    return records, extra, n


def merge(new: list[dict], previous: list[dict]) -> list[dict]:
    """New records replace earlier copies with the same key; earlier records not re-read this run are kept."""
    by = {r["key"]: r for r in previous or [] if r.get("disclosed_at", "") >= SINCE}
    by.update({r["key"]: r for r in new})
    return sorted(by.values(), key=lambda r: (r["disclosed_at"], r["key"]), reverse=True)


def is_end(exc: Exception) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and exc.code == 404

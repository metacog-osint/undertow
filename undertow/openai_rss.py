"""OpenAI lane: openai.com/news/rss.xml ONLY.

OpenAI's Terms of Use (effective 1 Jan 2026, read 14 Nov 2026) bar programmatically extracting data from its
websites. The RSS feed is published for programs to read; the report pages are not, so this lane NEVER fetches
a report page (`fetch_allowed` refuses any other openai.com URL, and a test holds it to that). Kept per
operation item: the name OpenAI gives it, the origin wording ("Russia-origin", "likely PRC-origin",
"Iran-linked"), the one-line summary (scrubbed, quoted with credit), the date and the link.

An item is an influence-operation item when its title or summary says "influence". Report round-ups ("Disrupting
malicious uses of AI: October 2025", the 10 Jun 2026 Global Affairs note) are disclosures, not operations, and are
kept as such. Cyber, scam and surveillance-only items are not read.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from . import disarm, text

RSS_URL = "https://openai.com/news/rss.xml"
SINCE = "2024-01-01"
LICENCE = "OpenAI news RSS feed (title and one-line summary quoted with credit; report pages not read)"

ORIGIN_RE = re.compile(r"(?P<likely>likely |suspected )?(?P<place>PRC|China|Chinese|Russia|Russian|Iran|Iranian|Israel|"
                       r"Rwanda|Cambodia|North Korea|Ghana|Philippines|Vietnam)[- ](?P<how>origin|linked|based|aligned)\b"
                       r"|(?:a |an )?(?:covert )?(?P<place2>Iranian|Russian|Chinese|Israeli) (?:covert )?influence operation")
FROM_RE = re.compile(r"\bcampaign from (?P<place>[A-Z][a-z]+)")
ROUNDUP_RE = re.compile(r"^Disrupting (malicious|deceptive) uses of AI(?: by| *[:|]|$)", re.I)
NAME_RE = re.compile(r"[“\"‘']([^”\"’']{3,40})[”\"’']")


def date_precision(published: str) -> str | None:
    """OpenAI's feed dates an item it gives no time as 00:00:00 GMT, and dates the case studies of a monthly report
    the 1st of that month (56 of 1,387 items on 15 Nov 2026 sat at midnight on the 1st, about four times chance):
    'month' for midnight on the 1st, 'day' for midnight on any other date, None for a real time."""
    if not published.endswith("T00:00:00Z"):
        return None
    return "month" if published[8:10] == "01" else "day"


def fetch_allowed(url: str) -> bool:
    """The only openai.com URL this program may fetch is the RSS feed."""
    return url == RSS_URL


def parse_rss(body: bytes) -> list[dict]:
    root = ET.fromstring(body)
    out = []
    for it in root.findall("./channel/item"):
        t = (it.findtext("title") or "").strip()
        d = (it.findtext("description") or "").strip()
        cats = [c.text or "" for c in it.findall("category")]
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "").strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            continue
        out.append({"title": t, "description": d, "categories": cats, "published": when,
                    "link": (it.findtext("link") or "").strip()})
    return out


def classify(item: dict) -> str | None:
    """'operation', 'roundup' or None (not an influence item)."""
    if item["published"] < SINCE:
        return None
    blob = item["title"] + " " + item["description"]
    if ROUNDUP_RE.search(item["title"]) and not re.search(r"covert|Iranian influence operation", item["title"], re.I):
        return "roundup"
    if not re.search(r"\binfluence\b", blob, re.I):
        return None
    if "Global Affairs" in item["categories"]:
        return "roundup"
    return "operation"


def _name(title: str) -> str | None:
    m = NAME_RE.search(title)
    if m and not m.group(1).lower().startswith(("false front", "false-front", "sovereignty")):
        return m.group(1).strip()
    head = title.split(":", 1)[0].strip()
    if ":" in title and re.fullmatch(r"[A-Z0-9][A-Z0-9-]{2,}", head):
        return head
    return None


def build_records(items: list[dict]) -> tuple[list[dict], list[dict]]:
    ops, roundups = [], []
    for it in items:
        kind = classify(it)
        if kind is None:
            continue
        slug = it["link"].rstrip("/").rsplit("/", 1)[-1]
        raw_name = _name(it["title"])
        allow = [raw_name] if raw_name else []     # the operation name OpenAI gives is kept as written
        title, w1 = text.scrub(it["title"], allow)
        summary, w2 = text.scrub(it["description"], allow)
        if kind == "roundup":
            roundups.append({"key": f"openai:{slug}", "title": title, "published": it["published"], "url": it["link"]})
            continue
        blob = it["title"] + " " + it["description"]
        om = ORIGIN_RE.search(blob) or FROM_RE.search(blob)
        origin, wording, level = [], None, "none"
        place = None
        if om:
            place = om.groupdict().get("place") or om.groupdict().get("place2")
            cc = text.country_code(place)
            if cc:
                origin = [cc]
            wording = om.group(0).strip()
            level = "moderate"
        named = [c for c in text.countries_in(re.sub(r"\b\w+-based\b", "", blob)) if c not in origin]
        n_ops = 2 if re.search(r"\btwo\b[^.]{0,40}operations", it["description"]) else 1
        op_name = text.scrub(raw_name, allow)[0] if raw_name else None
        out = {
            "key": f"openai:{slug}", "lane": "openai", "publisher": "openai",
            "disclosure": {"id": f"openai:{it['published'][:10]}", "title": f"OpenAI threat reporting, {it['published'][:10]}",
                           "url": it["link"]},
            "title": f"OpenAI: {title}",
            "operation_name": op_name,
            "named_operations": text.named_operations((op_name or "") + " " + blob),
            "period": it["published"][:7],
            "disclosed_at": it["published"],
            "disclosed_precision": date_precision(it["published"]),
            "origin": origin, "origin_text": place, "origin_wording": wording,
            "origin_level": level,
            "alignment": [],
            "targets": [], "target_regions": text.regions_in(it["description"]), "target_text": None,
            "countries_named": named,
            "platforms": [],
            "counts": {"operations": n_ops} if n_ops > 1 else {},
            "summary": summary or None,
            "summary_note": "OpenAI's one-line summary from its news RSS feed, quoted with credit." if summary else None,
            "orgs": [],
            "url": it["link"],
            "withheld": w1 + w2,
            "disarm": disarm.map_text([summary]),
        }
        ops.append(out)
    return ops, roundups

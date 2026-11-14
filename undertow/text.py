"""Text guards and place matching. Everything a lane keeps from a publisher's words passes scrub() first.

Hard rule (Tom, 14 Nov 2026): operation level only. Undertow never stores indicator values, account handles,
URLs or domains, or the names of individuals. Publishers' summaries sometimes name a politician who was the
subject of a narrative, or a domain the operation ran, so every kept sentence is scrubbed:

- URLs, e-mail addresses, @handles, defanged values ("example[.]com") and bare domains become "[link withheld]".
- A run of two or more capitalised words that are not known places, organisations, platforms, operation names
  or ordinary words is read as a person's name and becomes "[name withheld]". So is one unknown capitalised word
  straight after a title ("Prime Minister X", "journalist X").

The name rule is a heuristic and leans towards withholding: an unfamiliar organisation or outlet of two words
is withheld too (add it to config/operations.json "known_phrases" once checked). A single surname with no title
before it is not caught. Every withheld span is counted per item (`withheld`), so the page can say so.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WITHHELD_NAME = "[name withheld]"
WITHHELD_LINK = "[link withheld]"

URL_RE = re.compile(r"(?i)\b(?:https?|hxxps?)(?::|\[:\])//\S+|\bwww\[?\.\]?\S+")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_.]{2,}")
DEFANGED_RE = re.compile(r"\S*\[\.\]\S*")
TLDS = ("com|net|org|info|news|online|life|today|world|site|top|xyz|io|me|co|uk|de|fr|ru|ua|tr|it|es|pl|ro|md|am|"
        "az|by|kz|cn|tw|in|pk|id|ph|jp|ir|il|eu|us|ca|au|live|press|media|club|space|tv|biz|cc|ai|app|blog|pro")
DOMAIN_RE = re.compile(r"(?i)\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:" + TLDS + r")\b(?:/\S*)?")
BACKTICK_RE = re.compile(r"`[^`]*`")

TITLES = ("President", "Prime Minister", "Minister", "Senator", "Governor", "Chancellor", "Mayor", "MP", "Mr", "Mr.",
          "Ms", "Ms.", "Mrs", "Mrs.", "Dr", "Dr.", "journalist", "journalists", "politician", "candidate", "leader",
          "activist", "blogger", "influencer", "commentator", "opposition leader", "Pope", "King", "Queen")

COMMON = set("""
The A An We Our Us In On At Of For By With From To As This That These Those It Its They Their There Here Although However
Once Earlier Later After Before During Between Since While When Where Which Who Following Throughout Despite Additionally
First Second Third Fourth Finally Also Then Some Many Most Each Both All About Over Under Into Through Against Among Within
Without Such Several Other Another No Not Yes If But And Or Nor So Yet Further Furthermore Moreover Meanwhile Overall
Network Networks Origin Description Accounts Account Removed Followers Follower Indicators Indicator Compromise Domain Domains
Social Media Deep Dive Brute Force Tactics Persist Fluctuate Growing Role Countering Evolving Threat Linked Offshoot Campaigns
Campaign Operation Operations Influence Inauthentic Behavior Behaviour Coordinated Covert Report Reports Bulletin Quarterly
President Prime Minister Ministry Government Governments Party Parties Agency Council Parliament Parliamentary Presidential State States
Federal Republic Kingdom Union Foreign Office Department Army Navy Forces Military Service Services Intelligence Security National
International Institute Foundation University News Times Post Daily Group Groups Company Corporation Inc Ltd Elections Election General
Municipal Conflict War Crisis Code Practice Commitment Measure Measures Chapter Specific Programme Program Centre Center Transparency
Platform Platforms Pages Page Groups Channels Channel Blogs Blog Ads Ad Discover Search Surfaces Sites Site Websites Website
Prime Minister Opposition Communist Democratic Liberal Conservative Labor Labour Socialist Green Greens People People's Popular
Western Eastern Northern Southern Central Global World Europe European Africa African Asia Asian America American Americas Middle East
Sub-Saharan Saharan Region Regions Audience Audiences Diaspora Community Communities Kremlin Russian-aligned Chinese-aligned
January February March April May June July August September October November December
Monday Tuesday Wednesday Thursday Friday Saturday Sunday H1 H2 Q1 Q2 Q3 Q4
AI LLM LLMs IO IOs CIB CIO CIOs FIMI IMS TTP TTPs SLI EU UN NATO OSINT ID IDs
Meta Google OpenAI TikTok YouTube Instagram Facebook Threads WhatsApp Telegram Bluesky Blogger ChatGPT Anthropic Microsoft LinkedIn
X Reddit Twitter VK Rumble Gab Truth Substack Medium Pinterest Snapchat Discord Twitch Kick Viber Line WeChat Weibo
Large Language Models Model Models Generative Artificial Intelligence Deepfake Deepfakes
Mainstream Local Regional Independent Fake Fictitious Fabricated Authentic Real True False Former Current New Old
North South East West Upper Lower Greater Great Little Saint St
Committee Executive Commission Assembly Bureau Directorate Administration Authority Board Movement Front Alliance Bloc
Dollars Euros Rubles Roubles Pounds Lira Hryvnia Yuan Rupees Quetzales Pesos Reais Naira Shillings Dinars Rials
Updating Attribution Dissecting Kill Chain Early-Stage Early Stage Domestic Pakistani Activity Activities Displaying Wide Use
Changing Persistent Based Targeting Operators Operator Beyond Dive Deep Disrupting Disrupted Removing Removed Taking Down
Election Elections Content Farm Farms Spam Scam Cyber Hack Leak Leaks
""".split())


@lru_cache(maxsize=1)
def _places() -> tuple[dict, list]:
    cfg = json.loads((ROOT / "config" / "places.json").read_text(encoding="utf-8"))
    names = {}
    kit = ROOT / "doctrine" / "kit" / "geo" / "countries.json"
    for c in json.loads(kit.read_text(encoding="utf-8"))["countries"]:
        names[c["name"]] = c["cc"]
    names.update(cfg["aliases"])
    return names, cfg["regions"]


@lru_cache(maxsize=1)
def _demonyms() -> frozenset:
    cfg = json.loads((ROOT / "config" / "places.json").read_text(encoding="utf-8"))
    return frozenset(cfg.get("demonyms") or [])


@lru_cache(maxsize=1)
def _operations() -> dict:
    return json.loads((ROOT / "config" / "operations.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def known_phrases() -> list[str]:
    ops = _operations()
    phrases = set(ops.get("known_phrases") or [])
    for o in ops["operations"]:
        phrases.add(o["name"])
        phrases.update(o.get("aliases") or [])
        for org in o.get("orgs") or []:
            phrases.add(org["name"])
    names, regions = _places()
    phrases.update(n for n in names if " " in n)
    phrases.update(r for r in regions if " " in r)
    return sorted(phrases, key=len, reverse=True)


@lru_cache(maxsize=1)
def known_words() -> set[str]:
    words = set(COMMON)
    names, regions = _places()
    for n in list(names) + list(regions) + known_phrases():
        for w in re.split(r"[\s/]+", n):
            if w:
                words.add(w.strip(",.;:()"))
    return words


def _norm(tok: str) -> str:
    t = tok.strip(",.;:!?()[]{}\"“”‘’'")
    for suffix in ("’s", "'s"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    return t


def _is_known(tok: str) -> bool:
    t = _norm(tok)
    if not t:
        return True
    if any(ch.isdigit() for ch in t):
        return True
    if t.isupper() and len(t) <= 6:      # acronyms: organisations and terms, not personal names
        return True
    if t in known_words():
        return True
    if "-" in t and any(p in known_words() or p.isupper() for p in t.split("-")):
        return True
    return False


CAP_RUN_RE = re.compile(r"(?<![\w\[])(?:[A-ZÀ-Þ][\w’'.\-]*)(?:\s+[A-ZÀ-Þ][\w’'.\-]*)+")
TITLE_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(TITLES, key=len, reverse=True)) +
                      r")\s+([A-ZÀ-Þ][\w’'\-]+(?:\s+[A-ZÀ-Þ][\w’'\-]+){0,3})")


def _mask_known(text: str) -> tuple[str, list[str]]:
    kept = []

    def sub(m):
        kept.append(m.group(0))
        return f"\u0001{len(kept) - 1}\u0002"

    for ph in known_phrases():
        text = re.sub(r"(?<![\w])" + re.escape(ph) + r"(?![\w])", sub, text)
    return text, kept


def _unmask(text: str, kept: list[str]) -> str:
    return re.sub("\u0001(\\d+)\u0002", lambda m: kept[int(m.group(1))], text)


def withhold_names(text: str) -> tuple[str, int]:
    """Replace likely personal names with [name withheld]. Returns (text, how many spans were withheld)."""
    count = 0
    masked, kept = _mask_known(text)

    def title_sub(m):
        nonlocal count
        toks = m.group(2).split()
        n = 0
        while n < len(toks) and not _is_known(toks[n]):
            n += 1
        if n == 0:
            return m.group(0)
        count += 1
        trail = re.search(r"[,.;:!?)]+$", toks[n - 1])
        rest = " ".join(toks[n:])
        return f"{m.group(1)} {WITHHELD_NAME}" + (trail.group(0) if trail else "") + (" " + rest if rest else "")

    masked = TITLE_RE.sub(title_sub, masked)

    def run_sub(m):
        nonlocal count
        toks = m.group(0).split()
        out, i = [], 0
        while i < len(toks):
            j = i
            while j < len(toks) and not _is_known(toks[j]):
                j += 1
            if j - i >= 2:
                trail = re.search(r"[,.;:!?)]+$", toks[j - 1])
                out.append(WITHHELD_NAME + (trail.group(0) if trail else ""))
                count += 1
                i = j
            elif j > i:
                out.extend(toks[i:j])
                i = j
            else:
                out.append(toks[i])
                i += 1
        return " ".join(out)

    masked = CAP_RUN_RE.sub(run_sub, masked)
    return _unmask(masked, kept), count


def withhold_links(text: str) -> tuple[str, int]:
    count = 0
    for rx in (BACKTICK_RE, URL_RE, EMAIL_RE, DEFANGED_RE, HANDLE_RE, DOMAIN_RE):
        text, n = rx.subn(WITHHELD_LINK, text)
        count += n
    return text, count


MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)")


def scrub(text: str | None, allow: list[str] | None = None) -> tuple[str, int]:
    """Links, handles and domains first, then names. Returns (clean text, spans withheld).

    allow: phrases kept as written (an operation name the publisher gives, such as OpenAI's "Helgoland Bite")."""
    if not text:
        return "", 0
    t = unicodedata.normalize("NFC", text)
    t = MD_LINK_RE.sub(lambda m: m.group(1), t)       # Markdown links: keep the words, drop the target
    t = re.sub(r"\s+", " ", t).strip()
    t, a = withhold_links(t)
    kept = []
    for ph in sorted(allow or [], key=len, reverse=True):
        if ph and ph in t:
            kept.append(ph)
            t = t.replace(ph, f"\u0003{len(kept) - 1}\u0004")
    t, b = withhold_names(t)
    t = re.sub("\u0003(\\d+)\u0004", lambda m: kept[int(m.group(1))], t)
    t = re.sub(r"(\[link withheld\][\s,;]*){2,}", WITHHELD_LINK + " ", t).strip()
    return t, a + b


# --- places ---------------------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _place_re():
    names, _ = _places()
    alts = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(a) for a in alts) + r")(?![\w])")


def countries_in(text: str | None, demonyms: bool = True) -> list[str]:
    """ISO codes of the countries a text names, in the order first named. demonyms=False skips adjectives
    such as "Russian" (use it where a language list would otherwise read as countries)."""
    if not text:
        return []
    names, _ = _places()
    out = []
    for m in _place_re().finditer(text):
        word = m.group(1)
        if not demonyms and word in _demonyms():
            continue
        cc = names[word]
        if cc not in out:
            out.append(cc)
    return out


def regions_in(text: str | None) -> list[str]:
    if not text:
        return []
    _, regions = _places()
    out = []
    for r in sorted(regions, key=len, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(r) + r"(?![\w])", text) and not any(r in o for o in out):
            out.append(r)
    return out


def country_code(name: str) -> str | None:
    names, _ = _places()
    return names.get(name.strip())


def operations() -> list[dict]:
    return _operations()["operations"]


def named_operations(text: str | None) -> list[str]:
    """Ids of the named operations a text names (by name or a publisher-given alias)."""
    if not text:
        return []
    out = []
    for o in operations():
        for n in [o["name"]] + list(o.get("aliases") or []):
            if re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", text):
                out.append(o["id"])
                break
    return out

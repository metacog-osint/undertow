"""Meta lane: github.com/meta/threat-research (MIT licence).

Reads the README's "Published Threat Indicators" table (period, title, origin, targets, link) and each network's
Markdown file. Keeps per network: title, period, origin, targets, the counts Meta states (accounts, Pages,
followers), Meta's network summary (first paragraphs, scrubbed, quoted under the MIT licence with its notice),
and the indicator COUNT by type. The indicator values themselves (domains, account URLs) are never kept: the
table is read only to count its rows.

The date Meta added each file comes from one call to the GitHub commits API (commit messages read
"Add threat indicators: <file>"); without it the item carries the period only.
"""
from __future__ import annotations

import json
import re

from . import disarm, text

REPO = "meta/threat-research"
README_URL = f"https://raw.githubusercontent.com/{REPO}/main/README.md"
RAW_URL = f"https://raw.githubusercontent.com/{REPO}/main/indicators/{{file}}"
COMMITS_URL = f"https://api.github.com/repos/{REPO}/commits?per_page=100"
PAGE_URL = f"https://github.com/{REPO}/blob/main/indicators/{{file}}"
REPORTS_URL = "https://transparency.meta.com/metasecurity/threat-reporting/"
LICENCE = "MIT (Meta threat-research repository)"
MIT_NOTICE = ("Network summary: Copyright (c) Meta Platforms, Inc. and affiliates, from github.com/meta/threat-research, "
              "MIT License. Quoted with names, links and handles withheld by Undertow.")
SUMMARY_CHARS = 1400

ROW_RE = re.compile(r"^\|\s*(?P<period>H[12] \d{4})\s*\|\s*\[(?P<title>[^\]]+)\]\((?P<link>[^)]+)\)\s*\|"
                    r"\s*(?P<origin>[^|]*)\|\s*(?P<targets>[^|]*)\|\s*$")
COUNT_RE = re.compile(r"(?P<n>\d[\d,]*)\s+(?P<platform>Facebook|Instagram|Threads)?\s*(?P<kind>accounts?|Pages?|Groups?|events?)\b",
                      re.I)
FOLLOW_RE = re.compile(r"[Aa]bout (?P<n>[\d,.]+(?:\s*(?:million|thousand))?) (?:accounts|people) (?:followed|joined)"
                       r" one or more of these (?P<what>[\w ]+?)(?:\.|,| and)")
ORIGIN_RE = re.compile(r"(?:originat\w+ (?:in|from)|operated from|based in) (?P<place>[A-Z][^,.;]*?)(?= and targeting| targeting|[,.;])")


def parse_readme(md: str) -> list[dict]:
    rows = []
    for line in md.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        link = m.group("link").strip()
        file = link.rsplit("/", 1)[-1]
        if not file.endswith(".md"):
            continue
        rows.append({"period": m.group("period"), "title": m.group("title").strip(), "file": file,
                     "origin_text": m.group("origin").strip(), "targets_text": m.group("targets").strip()})
    return rows


def parse_commit_dates(body: bytes) -> dict[str, str]:
    """file name -> date Meta added it, from commit messages 'Add threat indicators: <file>'. Oldest wins."""
    out = {}
    for c in json.loads(body):
        msg = (c.get("commit") or {}).get("message") or ""
        when = ((c.get("commit") or {}).get("committer") or {}).get("date")
        m = re.match(r"Add threat indicators:\s*(\S+\.md)", msg)
        if m and when:
            out[m.group(1)] = when if m.group(1) not in out else min(out[m.group(1)], when)
    return out


def _section(md: str, start: str, stop: str = r"^## ") -> str:
    m = re.search(start, md, re.M)
    if not m:
        return ""
    rest = md[m.end():]
    n = re.search(stop, rest, re.M)
    return rest[: n.start()] if n else rest


def parse_network(md: str) -> dict:
    """Facts from one network file. Indicator values are counted, never returned."""
    summary_md = _section(md, r"^## .*Network Summary\s*$")
    paras = [p.strip() for p in re.split(r"\n\s*\n", summary_md)
             if p.strip() and not p.strip().startswith("#")]
    ioc_md = _section(md, r"^## Indicators of Compromise\s*$")
    by_type: dict[str, int] = {}
    for line in ioc_md.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if len(cells) < 2 or cells[0].lower() in ("indicator type", "") or set(cells[0]) <= set(":- "):
            continue
        kind = re.sub(r"[^a-z0-9]+", "_", cells[0].lower()).strip("_")
        by_type[kind] = by_type.get(kind, 0) + 1
    first = paras[0] if paras else ""
    counts: dict[str, int] = {}
    # Follower sentences ("About 79,400 accounts followed one or more of these ...") are read by FOLLOW_RE only.
    for m in COUNT_RE.finditer(re.sub(r"[^.]*\bfollowed\b[^.]*\.", "", first)):
        n = int(m.group("n").replace(",", ""))
        kind = m.group("kind").lower().rstrip("s")
        key = (m.group("platform") or "").lower() + ("_" if m.group("platform") else "") + kind + "s"
        counts[key] = counts.get(key, 0) + n
    fm = FOLLOW_RE.search(first)
    followers = None
    if fm:
        raw = fm.group("n").replace(",", "")
        mult = 1_000_000 if "million" in raw else 1000 if "thousand" in raw else 1
        followers = int(float(re.sub(r"[^\d.]", "", raw)) * mult)
    om = ORIGIN_RE.search(first)
    return {"paragraphs": paras, "indicators_by_type": by_type, "indicator_count": sum(by_type.values()),
            "counts": counts, "followers": followers, "origin_wording": om.group(0) if om else None}


def _split_places(s: str) -> tuple[list[str], list[str]]:
    return text.countries_in(s), text.regions_in(s)


def build_records(rows: list[dict], networks: dict[str, dict], added: dict[str, str]) -> list[dict]:
    out = []
    for r in rows:
        net = networks.get(r["file"])
        if net is None:
            continue
        title, w1 = text.scrub(r["title"])
        origin_cc, _ = _split_places(r["origin_text"])
        targets, regions = _split_places(r["targets_text"])
        kept, withheld, size = [], w1, 0
        for p in net["paragraphs"]:
            if size >= SUMMARY_CHARS:
                break
            t, w = text.scrub(p)
            withheld += w
            if size + len(t) > SUMMARY_CHARS and kept:
                break
            kept.append(t)
            size += len(t)
        all_sentences = []
        for p in net["paragraphs"]:
            t, _ = text.scrub(p)
            all_sentences += re.split(r"(?<=[.!?])\s+", t)
        wording = net["origin_wording"]
        if wording:
            wording, w = text.scrub(wording)
            withheld += w
        full = " ".join(net["paragraphs"])
        level = "moderate"
        if re.search(r"\b(very )?high confidence\b", full, re.I):
            level = "high"
        orgs = []
        for oid in text.named_operations(full + " " + r["title"]):
            for o in text.operations():
                if o["id"] == oid:
                    for org in o.get("orgs") or []:
                        if "meta" in org.get("named_by", []) and org["name"] in full and org not in orgs:
                            orgs.append({"name": org["name"], "country": org.get("country")})
        if orgs:
            level = "high"   # the publisher names the company it holds responsible (section 4 of the plan)
        platforms = [p for p in ("Facebook", "Instagram", "Threads", "WhatsApp", "TikTok", "X", "Telegram", "YouTube")
                     if re.search(r"(?<![\w])" + re.escape(p) + r"(?![\w])", full)]
        counts = dict(net["counts"])
        if net["followers"] is not None:
            counts["followers"] = net["followers"]
        counts["indicators"] = net["indicator_count"]
        out.append({
            "key": f"meta:{r['file'][:-3]}",
            "lane": "meta", "publisher": "meta",
            "disclosure": {"id": f"meta:{r['period'].replace(' ', '-').lower()}",
                           "title": f"Meta Adversarial Threat Report {r['period']}", "url": REPORTS_URL},
            "title": title,
            "operation_name": None,
            "named_operations": text.named_operations(full + " " + r["title"]),
            "period": r["period"],
            "disclosed_at": added.get(r["file"]),
            "origin": origin_cc, "origin_text": r["origin_text"], "origin_wording": wording,
            "origin_level": level,
            "alignment": [],
            "targets": targets, "target_regions": regions, "target_text": r["targets_text"],
            "countries_named": [],
            "platforms": platforms,
            "counts": counts,
            "indicators_by_type": net["indicators_by_type"],
            "summary": " ".join(kept) or None,
            "summary_note": MIT_NOTICE if kept else None,
            "orgs": orgs,
            "url": PAGE_URL.format(file=r["file"]),
            "withheld": withheld,
            "disarm": disarm.map_text(all_sentences),
        })
    return out

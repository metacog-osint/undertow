"""Record test fixtures from the raw copies a live `collect` kept in data/raw/ (real replies, not made up).

    python tests/make_fixtures.py                 # every lane
    python tests/make_fixtures.py --only dfrlab checkfirst   # reporter lanes only; the other fixtures stay
    python tests/make_fixtures.py --recut         # apply the cuts below to the fixtures already here

Large replies are cut to the parts the parsers read, and the cut is stated in tests/fixtures/MANIFEST.json with
the URL, the fetch time and the SHA-256 of the full reply. The repo is public, so fixtures follow Undertow's own
rules and the sources' terms: Meta's indicator values are replaced by made-up ones of the same type (the leak
tests look for those), and a reporter's items that name no tracked operation lose their title and description.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "tests" / "fixtures"



def index() -> dict[str, dict]:
    out = {}
    for line in (RAW / "index.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        out[r["url"]] = r          # newest wins
    return out


def raw_bytes(rec: dict) -> bytes:
    d = RAW / rec["source_id"]
    for f in d.glob(rec["sha256"][:12] + ".*"):
        b = f.read_bytes()
        return gzip.decompress(b) if f.suffix == ".gz" else b
    raise FileNotFoundError(rec["url"])


def reporter_fixtures(lane, idx, save) -> None:
    """A reporter lane (DFRLab, CheckFirst, CORRECTIV): every feed page the last collect read, cut to title, link,
    pubDate, category and description (no dc:creator, no content:encoded)."""
    from undertow import reporters
    rep = reporters.REPORTERS[lane]
    n = 1
    while reporters.page_url(rep, n) in idx:
        url = reporters.page_url(rep, n)
        body = raw_bytes(idx[url]).decode("utf-8")
        body = re.sub(r"\s*<dc:creator>.*?</dc:creator>", "", body, flags=re.S)
        body = re.sub(r"\s*<content:encoded>.*?</content:encoded>", "", body, flags=re.S)
        save(f"{lane}_feed_{n:02d}.xml", url, cut_reporter_feed(body).encode("utf-8"), REPORTER_CUT)
        n += 1


REPORTER_LANES = ("dfrlab", "checkfirst", "correctiv")


# --- Cuts that keep the public repo inside Undertow's rules and its sources' terms (audit of 25 Nov 2026) ---

IOC_HEAD = "## Indicators of Compromise"
IOC_ROW = re.compile(r"^\|\s*([^|`]+?)\s*\|\s*`([^`]+)`\s*\|\s*$", re.M)
TITLE_GONE = "[fixture: title removed]"
DESC_GONE = "<description><![CDATA[<p>[fixture: description removed]</p>]]></description>"


def synthetic_iocs(md: str, name: str) -> str:
    """Meta's indicator values replaced by made-up ones of the same type. Undertow publishes no indicator value, so
    its public repo keeps none either. Rows, types and order stay, so the counts by type and the leak tests still
    work; an account keeps its platform's host, but the account, domain, URL and IP are invented (IPs from
    192.0.2.0/24, RFC 5737; domains under .invalid)."""
    start = md.find(IOC_HEAD)
    if start < 0:
        return md
    nxt = md.find("\n## ", start + len(IOC_HEAD))
    end = len(md) if nxt < 0 else nxt
    tag = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
    n = 0

    def row(m: re.Match) -> str:
        nonlocal n
        n += 1
        kind, val = m.group(1).strip(), m.group(2)
        if kind == "Domain":
            new = f"fixture-{tag}-{n}[.]invalid"
        elif kind == "Proxy IP":
            new = f"192[.]0[.]2[.]{n}"
        elif kind == "URL":
            new = f"hxxps://fixture-{tag}-{n}[.]invalid/page-{n}"
        elif kind == "Social Media Account":
            mm = re.match(r"((?:hxxps?|https?)://)?([^/]+)/", val)
            scheme, host = ((mm.group(1) or ""), mm.group(2)) if mm else ("https://", "x[.]com")
            new = f"{scheme}{host}/{'@' if '/@' in val else ''}fixture_{tag}_{n}"
        else:
            raise ValueError(f"{name}: unknown indicator type {kind!r}; add a made-up form for it")
        return f"| {kind} | `{new}` |"

    return md[:start] + IOC_ROW.sub(row, md[start:end]) + md[end:]


def cut_reporter_feed(body: str) -> str:
    """A reporter's feed page with every item that names no tracked operation reduced to its link, date and
    categories: title and description replaced (Undertow keeps no reporter's title or description, and CORRECTIV's
    are all rights reserved). Items that name an operation stay whole, because the lane and the scrub tests read
    them. A removed title keeps the influence wording it had, which is all triage reads."""
    from undertow import reporters, text
    parsed = reporters.parse_page(body.encode("utf-8"))
    blocks = list(re.finditer(r"<item>.*?</item>", body, re.S))
    if len(parsed) != len(blocks):
        raise ValueError("feed items and parsed items differ; cut by hand")
    out, last = [], 0
    for m, it in zip(blocks, parsed):
        block = m.group(0)
        blob = it["title"] + " " + it["description"]
        if not text.named_operations(blob):
            words = sorted({w.group(0).lower() for w in reporters.INFLUENCE.finditer(blob)})
            title = TITLE_GONE + (f" ({', '.join(words)})" if words else "")
            block = re.sub(r"<title>.*?</title>", lambda _: f"<title>{xml_escape(title)}</title>", block, count=1, flags=re.S)
            block = re.sub(r"<description>.*?</description>", lambda _: DESC_GONE, block, count=1, flags=re.S)
        out += [body[last:m.start()], block]
        last = m.end()
    return "".join(out) + body[last:]


META_CUT = ("indicator values replaced by made-up ones of the same type (tests/make_fixtures.py synthetic_iocs); "
            "the rest whole. MIT, Copyright (c) Meta Platforms, Inc. and its affiliates: tests/fixtures/LICENSE-meta.txt")
REPORTER_CUT = ("items cut to title, link, pubDate, category and description (dc:creator and content:encoded removed); "
                "items naming no tracked operation keep only link, pubDate and category (cut_reporter_feed)")


def recut() -> int:
    """Apply the cuts above to the fixtures already in tests/fixtures/ (no data/raw needed)."""
    sys.path.insert(0, str(ROOT))
    manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    for name, rec in manifest["files"].items():
        p = OUT / name
        if name.startswith("meta_meta-") or name.startswith("meta_h"):
            p.write_bytes(synthetic_iocs(p.read_text(encoding="utf-8"), name).encode("utf-8"))
            rec["cut"] = META_CUT
        elif any(name.startswith(f"{lane}_feed_") for lane in REPORTER_LANES):
            p.write_bytes(cut_reporter_feed(p.read_text(encoding="utf-8")).encode("utf-8"))
            rec["cut"] = REPORTER_CUT
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"recut {len(manifest['files'])} fixtures in {OUT}")
    return 0


def main() -> int:
    if "--recut" in sys.argv:
        return recut()
    sys.path.insert(0, str(ROOT))
    from undertow import eeas, google, meta, openai_rss, tiktok
    idx = index()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"note": "Real replies recorded from the live collect of 14 Nov 2026 (data/raw), cut where stated.",
                "files": {}}
    only = sys.argv[sys.argv.index("--only") + 1:] if "--only" in sys.argv else None

    def save(name, url, body: bytes, cut: str | None = None):
        (OUT / name).write_bytes(body)
        rec = idx[url]
        manifest["files"][name] = {"url": url, "fetched_at": rec["fetched_at"], "sha256_full": rec["sha256"],
                                   "bytes_full": rec["bytes"], "cut": cut}

    if only:
        manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
        for lane in [x for x in only if x in REPORTER_LANES]:
            for name in [k for k in manifest["files"] if k.startswith(f"{lane}_feed_")]:
                del manifest["files"][name]
                (OUT / name).unlink(missing_ok=True)
            reporter_fixtures(lane, idx, save)
        (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"updated {only}; {len(manifest['files'])} fixtures in {OUT}")
        return 0

    # Meta: README whole, every network file the README lists with made-up indicator values; commits cut to message
    # and date.
    save("meta_readme.md", meta.README_URL, raw_bytes(idx[meta.README_URL]))
    files = [r["file"] for r in meta.parse_readme(raw_bytes(idx[meta.README_URL]).decode("utf-8"))]
    for f in files:
        url = meta.RAW_URL.format(file=f)
        save(f"meta_{f}", url, synthetic_iocs(raw_bytes(idx[url]).decode("utf-8"), f"meta_{f}").encode("utf-8"),
             META_CUT)
    commits = json.loads(raw_bytes(idx[meta.COMMITS_URL]))
    slim = [{"commit": {"message": c["commit"]["message"], "committer": {"date": c["commit"]["committer"]["date"]}}}
            for c in commits]
    save("meta_commits.json", meta.COMMITS_URL, json.dumps(slim, indent=1).encode("utf-8"),
         "kept commit.message and commit.committer.date only (no author names or e-mail addresses)")

    # Google: Q2 and Q3 bulletins, cut to the <article> element; the RSS whole.
    for q in (2, 3):
        url = google.PAGE_URL.format(q=q, y=2026)
        t = raw_bytes(idx[url]).decode("utf-8", errors="replace")
        m = re.search(r"<article.*?</article>", t, re.S)
        save(f"google_q{q}_2026.html", url, m.group(0).encode("utf-8"), "the <article> element only")
    save("google_rss.xml", google.RSS_URL, raw_bytes(idx[google.RSS_URL]))

    # OpenAI: the RSS cut to the influence items, the round-ups and the first 15 other items.
    body = raw_bytes(idx[openai_rss.RSS_URL]).decode("utf-8")
    head, rest = body.split("<item>", 1)
    items = ["<item>" + x for x in ("<item>" + rest).split("<item>")[1:]]
    keep, other = [], 0
    for it in items:
        piece = it.split("</item>")[0] + "</item>"
        parsed = openai_rss.parse_rss(("<rss><channel>" + piece + "</channel></rss>").encode("utf-8"))
        kind = openai_rss.classify(parsed[0]) if parsed else None
        if kind or other < 15:
            keep.append(piece)
            other += 0 if kind else 1
    tail = "</channel></rss>"
    save("openai_rss.xml", openai_rss.RSS_URL, (head + "".join(keep) + tail).encode("utf-8"),
         "the influence items, the report round-ups and the first 15 other items")

    # TikTok: reports 5, 6, 8 and 9, cut to the chapters that hold network entries (Integrity of Services; Crisis and
    # Elections Response).
    for n in (5, 6, 8, 9):
        url = tiktok.REPORT_URL.format(n=n)
        doc = json.loads(raw_bytes(idx[url]))
        doc["chapters"] = [c for c in doc["chapters"] if c.get("name") in ("Integrity of Services",
                                                                             "Crisis and Elections Response")]
        save(f"tiktok_report_{n}.json", url, json.dumps(doc, ensure_ascii=False).encode("utf-8"),
             "chapters 'Integrity of Services' and 'Crisis and Elections Response' only")

    # EEAS: the FIMI page whole.
    save("eeas_fimi_page.html", eeas.FIMI_PAGE, raw_bytes(idx[eeas.FIMI_PAGE]))
    for lane in REPORTER_LANES:
        reporter_fixtures(lane, idx, save)

    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(manifest['files'])} fixtures to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

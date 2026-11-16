"""Record test fixtures from the raw copies a live `collect` kept in data/raw/ (real replies, not made up).

    python tests/make_fixtures.py                 # every lane
    python tests/make_fixtures.py --only dfrlab   # one lane; the other fixtures and their manifest entries stay

Large replies are cut to the parts the parsers read, and the cut is stated in tests/fixtures/MANIFEST.json with
the URL, the fetch time and the SHA-256 of the full reply. The Meta network files are kept whole, indicator tables
included, because the leak tests need real indicator values to look for.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

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


def dfrlab_fixtures(idx, save) -> None:
    """DFRLab: every feed page the last collect read, cut to title, link, pubDate, category and description (no
    dc:creator, no content:encoded)."""
    from undertow import dfrlab
    n = 1
    while dfrlab.page_url(n) in idx:
        body = raw_bytes(idx[dfrlab.page_url(n)]).decode("utf-8")
        body = re.sub(r"\s*<dc:creator>.*?</dc:creator>", "", body, flags=re.S)
        body = re.sub(r"\s*<content:encoded>.*?</content:encoded>", "", body, flags=re.S)
        save(f"dfrlab_feed_{n:02d}.xml", dfrlab.page_url(n), body.encode("utf-8"),
             "items cut to title, link, pubDate, category and description (dc:creator and content:encoded removed)")
        n += 1


def main() -> int:
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
        if "dfrlab" in only:
            for name in [k for k in manifest["files"] if k.startswith("dfrlab_")]:
                del manifest["files"][name]
                (OUT / name).unlink(missing_ok=True)
            dfrlab_fixtures(idx, save)
        (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"updated {only}; {len(manifest['files'])} fixtures in {OUT}")
        return 0

    # Meta: README whole, every network file the README lists, whole; commits cut to message and date.
    save("meta_readme.md", meta.README_URL, raw_bytes(idx[meta.README_URL]))
    files = [r["file"] for r in meta.parse_readme(raw_bytes(idx[meta.README_URL]).decode("utf-8"))]
    for f in files:
        url = meta.RAW_URL.format(file=f)
        save(f"meta_{f}", url, raw_bytes(idx[url]))
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

    # TikTok: reports 8 and 9, cut to the chapters that hold network entries (Integrity of Services; Crisis and
    # Elections Response).
    for n in (8, 9):
        url = tiktok.REPORT_URL.format(n=n)
        doc = json.loads(raw_bytes(idx[url]))
        doc["chapters"] = [c for c in doc["chapters"] if c.get("name") in ("Integrity of Services",
                                                                             "Crisis and Elections Response")]
        save(f"tiktok_report_{n}.json", url, json.dumps(doc, ensure_ascii=False).encode("utf-8"),
             "chapters 'Integrity of Services' and 'Crisis and Elections Response' only")

    # EEAS: the FIMI page whole.
    save("eeas_fimi_page.html", eeas.FIMI_PAGE, raw_bytes(idx[eeas.FIMI_PAGE]))
    dfrlab_fixtures(idx, save)

    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(manifest['files'])} fixtures to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Undertow CLI: collect, build and check.

    python tools/undertow.py collect                 # fetch every live lane, write data/snapshot.json
    python tools/undertow.py collect --only meta     # one or more lanes; the rest keep their last copy
    python tools/undertow.py build                   # build site/ from data/snapshot.json
    python tools/undertow.py check                   # registers, feed linter, STIX check, leak scan

collect never falls back to made-up data. A lane that fails keeps its last good copy (from_previous) or stays
empty, and the snapshot's "lanes" block says which.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from undertow import analysis, disarm, eeas, feed, fetch, google, meta, openai_rss, stix, tiktok  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402
from tic_doctrine.lint import check_header  # noqa: E402

LANES = ["meta", "google", "openai", "tiktok", "eeas"]


def _github_headers() -> dict:
    tok = (os.environ.get("GITHUB_TOKEN") or "").strip()
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _lane_meta(raw_dir, prev, getter):
    body, rec = fetch.fetch("meta-readme", meta.README_URL, raw_dir, "md", getter=getter)
    rows = meta.parse_readme(body.decode("utf-8", errors="replace"))
    if len(rows) < 5:
        raise ValueError(f"README table parsed to {len(rows)} rows")
    recs, networks = [rec], {}
    for r in rows:
        b, rr = fetch.fetch("meta-network", meta.RAW_URL.format(file=r["file"]), raw_dir, "md", getter=getter)
        networks[r["file"]] = meta.parse_network(b.decode("utf-8", errors="replace"))
        recs.append(rr)
    added, note = {}, None
    try:
        b, rr = fetch.fetch("meta-commits", meta.COMMITS_URL, raw_dir, "json", getter=getter, headers=_github_headers())
        added = meta.parse_commit_dates(b)
        recs.append(rr)
    except Exception as exc:  # dates are a nicety; the lane stands without them
        note = f"commit dates not read ({type(exc).__name__}); items carry the period only"
    return {"records": meta.build_records(rows, networks, added), "extra": {"rows": len(rows), "note": note}}, recs


def _lane_google(raw_dir, prev, getter):
    rss, recs = None, []
    try:
        rss, rr = fetch.fetch("google-security-rss", google.RSS_URL, raw_dir, "xml", getter=getter)
        recs.append(rr)
    except Exception:
        rss = None
    today = datetime.now(timezone.utc).date()
    pages, urls, missing = [], {}, []
    for y, q, url in google.candidate_urls(today, rss):
        try:
            b, rr = fetch.fetch("google-iob", url, raw_dir, "html", getter=getter)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                missing.append(f"Q{q} {y}")
                continue
            raise
        recs.append(rr)
        pg = google.parse_page(b, y, q)
        if not pg["entries"] and not pg["unparsed"]:
            raise ValueError(f"Q{q} {y} bulletin parsed to no entries")
        pages.append(pg)
        urls[(y, q)] = url
    if not pages:
        raise ValueError("no bulletin page could be read")
    records = google.build_records(pages, urls)
    for pg in pages:
        n_ok, n_bad = len(pg["entries"]), len(pg["unparsed"])
        cov = round(n_ok / (n_ok + n_bad), 3) if n_ok + n_bad else None
        for r in records:
            if r["disclosure"]["id"] == f"google:{pg['year']}-q{pg['quarter']}":
                r["coverage_fraction"] = cov
    extra = {"rss_read": rss is not None, "not_published": missing,
             "pages": [{"year": p["year"], "quarter": p["quarter"], "url": urls[(p["year"], p["quarter"])],
                        "updated": p["updated"], "entries": len(p["entries"]), "unparsed": p["unparsed"]}
                       for p in pages]}
    return {"records": records, "extra": extra}, recs


def _lane_openai(raw_dir, prev, getter):
    url = openai_rss.RSS_URL
    assert openai_rss.fetch_allowed(url)
    body, rec = fetch.fetch("openai-news-rss", url, raw_dir, "xml", timeout=90, getter=getter)
    items = openai_rss.parse_rss(body)
    if len(items) < 20:
        raise ValueError(f"RSS parsed to {len(items)} items")
    ops, roundups = openai_rss.build_records(items)
    return {"records": ops, "extra": {"rss_items": len(items), "roundups": roundups}}, [rec]


def _lane_tiktok(raw_dir, prev, getter):
    known = sorted(set(tiktok.KNOWN_REPORTS) | {r["id"] for r in (prev.get("extra", {}).get("tiktok") or {}).get("reports", [])})
    reports, recs, probes = [], [], []
    n = known[0]
    misses = 0
    while misses < tiktok.PROBE_AHEAD:
        url = tiktok.REPORT_URL.format(n=n)
        try:
            b, rr = fetch.fetch("disinfocode-tiktok", url, raw_dir, "json", timeout=120, getter=getter)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            b, rr = None, None
        doc = tiktok.is_report(b) if b else None
        if doc is None:
            if n > known[-1]:
                misses += 1
                probes.append(n)
            n += 1
            continue
        recs.append(rr)
        reports.append(tiktok.parse_report(doc))
        n += 1
    if not reports:
        raise ValueError("no TikTok report could be read")
    records = tiktok.build_records(reports)
    if not records:
        raise ValueError("TikTok reports parsed to no networks")
    return {"records": records, "extra": {"reports": [{k: r[k] for k in ("id", "name", "published", "window")}
                                                      | {"networks": len(r["entries"])} for r in reports],
                                           "probed_not_found": probes}}, recs


def _lane_eeas(raw_dir, prev, getter):
    regs = eeas.load_registers()
    body, rec = fetch.fetch("eeas-fimi-page", eeas.FIMI_PAGE, raw_dir, "html", getter=getter)
    page = eeas.check_page(body, regs[-1])
    records = []
    for reg in regs:
        records += eeas.build_records(reg)
    return {"records": records, "extra": {"page": page, "registers": [r["register"] for r in regs],
                                          "report": regs[-1]["report"]}}, [rec]


LANE_FN = {"meta": _lane_meta, "google": _lane_google, "openai": _lane_openai, "tiktok": _lane_tiktok, "eeas": _lane_eeas}


def collect(root: Path = ROOT, getter=None, only: list[str] | None = None) -> dict:
    data_dir = root / "data"
    raw_dir = data_dir / "raw"
    snap_path = data_dir / "snapshot.json"
    prev = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {}
    now = fetch.now_utc()
    snap = {"generated_at": now, "method_version": feed.METHOD, "disarm_version": disarm.VERSION,
            "lanes": {}, "records": {}, "extra": {}}
    for lane in LANES:
        prev_lane = (prev.get("lanes") or {}).get(lane) or {}
        keep = lambda: ((prev.get("records") or {}).get(lane, []), (prev.get("extra") or {}).get(lane, {}))  # noqa: E731
        if only and lane not in only:
            snap["records"][lane], snap["extra"][lane] = keep()
            snap["lanes"][lane] = {**prev_lane, "from_previous": True} if prev_lane else {"status": "not run"}
            continue
        try:
            result, recs = LANE_FN[lane](raw_dir, {"extra": prev.get("extra") or {}}, getter)
            snap["records"][lane] = result["records"]
            snap["extra"][lane] = result["extra"]
            snap["lanes"][lane] = {"status": "ok", "fetched_at": now, "from_previous": False, "items": len(result["records"]),
                                   "fetches": [{k: r[k] for k in ("url", "sha256", "bytes")} for r in recs]}
        except Exception as exc:
            had = bool(prev_lane.get("fetched_at"))
            snap["records"][lane], snap["extra"][lane] = keep() if had else ([], {})
            snap["lanes"][lane] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300], "failed_at": now,
                                   "from_previous": had, "fetched_at": prev_lane.get("fetched_at")}
    data_dir.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return snap


def all_records(snap: dict) -> list[dict]:
    out = []
    for lane in LANES:
        for r in (snap.get("records") or {}).get(lane, []):
            r = {k: v for k, v in r.items() if not k.startswith("_")}
            out.append(r)
    analysis.assess(out)
    return out


def page_data(snap: dict, records: list[dict], feed_doc: dict, events: list[dict]) -> dict:
    """What the page reads: one row per item, plus lane status and the method tables."""
    from tic_doctrine import geo
    rows = []
    by_id = {f["properties"]["id"]: f["properties"] for f in feed_doc["features"]}
    for r in records:
        iid = feed.item_id(r["key"])
        p = by_id[iid]
        rows.append({"id": iid, "publisher": r["publisher"], "title": r["title"], "period": r.get("period"),
                     "disclosed_at": r.get("disclosed_at"), "disclosed_precision": r.get("disclosed_precision"),
                     "origin": r.get("origin") or [],
                     "origin_wording": r.get("origin_wording"), "origin_level": r.get("origin_level"),
                     "alignment": r.get("alignment") or [], "targets": r.get("targets") or [],
                     "target_regions": r.get("target_regions") or [], "countries_named": r.get("countries_named") or [],
                     "operation_name": r.get("operation_name"), "named_operations": r.get("named_operations") or [],
                     "counts": r.get("counts") or {}, "platforms": r.get("platforms") or [],
                     "summary": p["summary"], "publisher_text": r.get("summary"), "publisher_text_note": r.get("summary_note"),
                     "behaviours": r.get("behaviours") or [], "page": r.get("page"),
                     "disarm": p["disarm_mapping"], "confidence": p.get("confidence"),
                     "corroborated_by": r.get("corroborated_by") or [], "withheld": r.get("withheld", 0),
                     "url": r["url"], "disclosure": r["disclosure"], "languages": r.get("languages") or [],
                     "orgs": [o["name"] for o in r.get("orgs") or []]})
    ccs = {c for row in rows for c in row["origin"] + row["targets"] + row["countries_named"] + row["alignment"]}
    return {"generated_at": snap["generated_at"], "method_version": snap["method_version"],
            "disarm_version": snap["disarm_version"], "disarm_rules_status": "reviewed" if disarm.reviewed() else "proposed",
            "lanes": snap["lanes"], "extra": snap.get("extra") or {}, "items": rows, "events": events,
            "country_names": {c: geo.name(c) or c for c in sorted(ccs)},
            "rules": disarm.rules()["rules"], "operations": [{"id": o["id"], "name": o["name"], "aliases": o.get("aliases") or []}
                                                             for o in __import__("undertow.text", fromlist=["x"]).operations()]}


def build_site(root: Path = ROOT, snapshot: dict | None = None) -> dict[str, str]:
    snap_path = root / "data" / "snapshot.json"
    if snapshot is None:
        if not snap_path.exists():
            raise SystemExit("No data/snapshot.json. Run `python tools/undertow.py collect` first; "
                             "Undertow does not build from made-up data.")
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
    snap = snapshot
    records = all_records(snap)
    feed_doc = feed.build_feed(records, snap["generated_at"])
    bundle = stix.build_bundle(records, snap["generated_at"])
    gq = [(p["year"], p["quarter"]) for p in (snap.get("extra", {}).get("google") or {}).get("pages", [])]
    tr = (snap.get("extra", {}).get("tiktok") or {}).get("reports", [])
    ep = ((snap.get("extra", {}).get("eeas") or {}).get("report") or {}).get("published")
    today = datetime.fromisoformat(snap["generated_at"].replace("Z", "+00:00")).date()
    events = analysis.expected_disclosures(records, gq, tr, ep, today)

    def dump(obj) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"

    files = {
        "data/feed.geojson": dump(feed_doc),
        "data/stix.json": dump(bundle),
        "data/events.json": dump({"source": "undertow", "note": "Expected dates on each publisher's past pattern. "
                                  "Dates only, no probabilities; none is a published schedule.", "events": events}),
        "data/snapshot.json": dump(page_data(snap, records, feed_doc, events)),
    }
    src_dir = root / "site_src"
    if src_dir.exists():
        for p in sorted(src_dir.rglob("*")):
            if p.is_file():
                files[p.relative_to(src_dir).as_posix()] = p.read_text(encoding="utf-8")
    for p in sorted((root / "doctrine").glob("*.md")):
        files[f"doctrine/{p.name}"] = p.read_text(encoding="utf-8")
    out_dir = root / "site"
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel, txt in files.items():
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(txt, encoding="utf-8", newline="\n")
    return files


# Hosts a link in the published output may point to: publishers' disclosure pages and the references we cite.
ALLOWED_URL_PREFIXES = (
    "https://github.com/meta/threat-research/", "https://github.com/meta/threat-research",
    "https://raw.githubusercontent.com/meta/threat-research/", "https://api.github.com/repos/meta/threat-research/",
    "https://openai.com/news/rss.xml", "https://blog.google/security/rss/",
    "https://transparency.meta.com/", "https://blog.google/security/", "https://openai.com/index/",
    "https://openai.com/news/", "https://openai.com/global-affairs/", "https://disinfocode.eu/",
    "https://www.eeas.europa.eu/", "https://undertow.theintelligence.company", "https://theintelligence.company",
    "https://github.com/DISARMFoundation/", "https://raw.githubusercontent.com/DISARMFoundation/",
    "https://docs.oasis-open.org/", "https://github.com/metacog-osint/tic-doctrine", "https://creativecommons.org/",
    "https://www.disarm.foundation/", "https://disarm.foundation/",
)
URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>)\]]+")
LEAK_PATTERNS = [(re.compile(r"\[\.\]"), "a defanged value"), (re.compile(r"(?<![\w@])@[A-Za-z0-9_]{3,}(?![\w.])"), "an @handle"),
                 (re.compile(r"hxxp", re.I), "a defanged URL")]


def leak_scan(paths: list[Path]) -> list[str]:
    errs = []
    for p in paths:
        txt = p.read_text(encoding="utf-8")
        for m in URL_IN_TEXT.finditer(txt):
            u = m.group(0)
            if not u.startswith(ALLOWED_URL_PREFIXES):
                errs.append(f"{p.name}: URL outside the allowed publisher pages: {u[:80]}")
        for rx, what in LEAK_PATTERNS:
            for m in rx.finditer(txt):
                errs.append(f"{p.name}: {what}: {txt[max(0, m.start() - 20): m.end() + 20]!r}")
    return errs


def check_all(root: Path = ROOT) -> list[str]:
    errs = registers.check(root / "doctrine")
    regs = registers.ids(root / "doctrine")
    data = root / "site" / "data"
    feed_path = data / "feed.geojson"
    if not feed_path.exists():
        return errs + ["site/data/feed.geojson is missing: run collect and build first"]
    feed_doc = json.loads(feed_path.read_text(encoding="utf-8"))
    errs += [f"feed header: {std}: {msg}" for std, sev, msg in check_header(feed_doc) if sev == "error"]
    for feat in feed_doc.get("features", []):
        p = feat.get("properties") or {}
        fid = p.get("id", "?")
        for std, sev, msg in contract.check(feat, regs):
            if sev == "error":
                errs.append(f"{fid}: {std}: {msg}")
        for t in p.get("disarm_technique") or []:
            if not disarm.name(t):
                errs.append(f"{fid}: DISARM {t} is not in v{disarm.VERSION}")
        if p.get("confidence") == "high":
            errs.append(f"{fid}: confidence High is not possible in this slice (no scored Verdict record)")
    bundle = json.loads((data / "stix.json").read_text(encoding="utf-8"))
    errs += [f"stix: {e}" for e in stix.validate(bundle)]
    errs += leak_scan([data / "feed.geojson", data / "stix.json", data / "events.json", data / "snapshot.json"])
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Undertow: attributed influence-operation takedowns, at operation level.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--only", nargs="*", choices=LANES, help="run only these lanes; keep the rest as they were")
    sub.add_parser("build")
    sub.add_parser("check")
    args = ap.parse_args(argv)
    if args.cmd == "collect":
        snap = collect(only=args.only)
        for lane, st in snap["lanes"].items():
            extra = f" ({st.get('error')})" if st.get("status") == "failed" else ""
            print(f"  {lane:7s} {st.get('status')} {st.get('items', '')}{' [last good copy]' if st.get('from_previous') else ''}{extra}")
        print(f"Collected {sum(len(v) for v in snap['records'].values())} operation records.")
        return 0 if any(s.get("status") == "ok" for s in snap["lanes"].values()) else 1
    if args.cmd == "build":
        files = build_site(ROOT)
        print(f"Built site/ ({len(files)} files).")
        return 0
    if args.cmd == "check":
        errs = check_all(ROOT)
        for e in errs[:60]:
            print("  -", e)
        print(f"Undertow check: {'PASS' if not errs else f'FAIL ({len(errs)} problems)'}")
        return 1 if errs else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

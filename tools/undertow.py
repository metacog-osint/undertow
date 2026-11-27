"""Undertow CLI: collect, build and check.

    python tools/undertow.py collect                 # fetch every live lane, write data/snapshot.json
    python tools/undertow.py collect --only meta     # one or more lanes; the rest keep their last copy
    python tools/undertow.py build                   # build site/ from data/snapshot.json
    python tools/undertow.py check                   # registers, feed linter, STIX check, leak scan
    python tools/undertow.py archive                 # append reporter report records to history/reports.jsonl
    python tools/undertow.py triage [--days 180]     # LAPTOP ONLY: list new, unnamed reported activity for review
    python tools/undertow.py closing [--months 12]   # LAPTOP ONLY: watch rows against later disclosures (UT-IND-3..4)

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

from undertow import (activity, analysis, archive, baseline, disarm, eeas, feed, fetch, google, listings, meta, openai_rss, reporters, targets,  # noqa: E402
                      stix, tiktok)
from tic_doctrine import contract, registers  # noqa: E402
from tic_doctrine.lint import check_header  # noqa: E402

LANES = ["meta", "google", "openai", "tiktok", "eeas", "dfrlab", "checkfirst", "correctiv", "watch"]
REPORTER_LANES = list(reporters.REPORTERS)          # report records; folded into reported-activity items at build
TRIAGE_PATH = ROOT / "data" / "triage.jsonl"         # private: reporters' headlines; never published, never in Actions


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


def _reporter_lane(lane: str):
    rep = reporters.REPORTERS[lane]

    def run(raw_dir, prev, getter):
        recs = []

        def page(n):
            try:
                b, rr = fetch.fetch(f"{lane}-rss", reporters.page_url(rep, n), raw_dir, "xml", getter=getter)
            except Exception as exc:
                if n > 1 and reporters.is_end(exc):
                    return None
                raise
            recs.append(rr)
            return b

        pause = 0 if getter is not None else reporters.PAUSE_S
        new, extra, _ = reporters.read(rep, page, (prev.get("extra") or {}).get(lane), pause=pause)
        records = reporters.merge(rep, new, (prev.get("records") or {}).get(lane))
        return {"records": records, "extra": extra}, recs
    return run


def _lane_watch(raw_dir, prev, getter):
    reg = activity.load_watch()
    errs = activity.check_watch(reg)
    if errs:
        raise ValueError("watch register: " + "; ".join(errs[:5]))
    return {"records": list(reg.get("rows") or []), "extra": {"rows": len(reg.get("rows") or []),
                                                              "reporter_hosts": reg.get("reporter_hosts") or []}}, []


LANE_FN = {"meta": _lane_meta, "google": _lane_google, "openai": _lane_openai, "tiktok": _lane_tiktok, "eeas": _lane_eeas,
           **{lane: _reporter_lane(lane) for lane in REPORTER_LANES}, "watch": _lane_watch}


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
            result, recs = LANE_FN[lane](raw_dir, {"extra": prev.get("extra") or {}, "records": prev.get("records") or {}}, getter)
            snap["records"][lane] = result["records"]
            snap["extra"][lane] = result["extra"]
            snap["lanes"][lane] = {"status": "ok", "fetched_at": now, "from_previous": False, "items": len(result["records"]),
                                   "failures": 0,
                                   "fetches": [{k: r[k] for k in ("url", "sha256", "bytes")} for r in recs]}
        except Exception as exc:
            had = bool(prev_lane.get("fetched_at"))
            snap["records"][lane], snap["extra"][lane] = keep() if had else ([], {})
            snap["lanes"][lane] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300], "failed_at": now,
                                   "from_previous": had, "fetched_at": prev_lane.get("fetched_at"),
                                   "items": len(snap["records"][lane]),
                                   "failures": int(prev_lane.get("failures") or 0) + 1}
    data_dir.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return snap


def _today(snap: dict):
    return datetime.fromisoformat(snap["generated_at"].replace("Z", "+00:00")).date()


def _read_on(snap: dict) -> dict:
    """The day each lane's source was last read (its fetched_at, kept on a last good copy), for the baseline."""
    return {lane: datetime.fromisoformat(st["fetched_at"].replace("Z", "+00:00")).date()
            for lane, st in (snap.get("lanes") or {}).items() if st.get("fetched_at")}


def all_records(snap: dict) -> list[dict]:
    """Disclosures as collected, plus reported-activity records: the reporter lanes' report records grouped by
    (reporter, operation), and the watch register's rows. State (active or quiet) is as of the collect."""
    out = []
    recs = snap.get("records") or {}
    for lane in LANES:
        if lane in REPORTER_LANES or lane == "watch":
            continue
        for r in recs.get(lane, []):
            out.append({k: v for k, v in r.items() if not k.startswith("_")})
    today = _today(snap)
    out += activity.aggregate({lane: recs.get(lane, []) for lane in REPORTER_LANES}, today)
    out += activity.watch_records({"rows": recs.get("watch", [])}, today)
    activity.place(out)
    targets.apply(out)
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
                     "audience": r.get("audience"),
                     "operation_name": r.get("operation_name"), "named_operations": r.get("named_operations") or [],
                     "counts": r.get("counts") or {}, "platforms": r.get("platforms") or [],
                     "summary": p["summary"], "publisher_text": r.get("summary"), "publisher_text_note": r.get("summary_note"),
                     "behaviours": r.get("behaviours") or [], "page": r.get("page"),
                     "disarm": p["disarm_mapping"], "confidence": p.get("confidence"),
                     "corroborated_by": r.get("corroborated_by") or [], "withheld": r.get("withheld", 0),
                     "url": r["url"], "disclosure": r["disclosure"], "languages": r.get("languages") or [],
                     "orgs": [o["name"] for o in r.get("orgs") or []], "grade": p["sources"][0]["grade"],
                     "listed_by": p["operation"]["listed_by"],
                     "reporter": p["sources"][0]["publisher"], "activity": r.get("activity")})
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
    today = _today(snap)
    base = baseline.build(records, today, read_on=_read_on(snap))
    feed_doc = feed.build_feed(records, snap["generated_at"], feed.health(snap.get("lanes") or {}, records, snap["generated_at"]),
                               extra=feed.enforcement_features(base, records, snap["generated_at"]))
    bundle = stix.build_bundle(records, snap["generated_at"])
    gq = [(p["year"], p["quarter"]) for p in (snap.get("extra", {}).get("google") or {}).get("pages", [])]
    tr = (snap.get("extra", {}).get("tiktok") or {}).get("reports", [])
    ep = ((snap.get("extra", {}).get("eeas") or {}).get("report") or {}).get("published")
    events = analysis.expected_disclosures(records, gq, tr, ep, today)

    def dump(obj) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"

    files = {
        "data/feed.geojson": dump(feed_doc),
        "data/stix.json": dump(bundle),
        "data/events.json": dump({"source": "undertow", "note": "Expected dates on each publisher's past pattern. "
                                  "Dates only, no probabilities; none is a published schedule.", "events": events}),
        "data/snapshot.json": dump(page_data(snap, records, feed_doc, events)),
        "data/baseline.json": dump(base),
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
    "https://blog.google/threat-analysis-group/tag-bulletin-",
    "https://openai.com/news/", "https://openai.com/global-affairs/", "https://disinfocode.eu/",
    "https://www.eeas.europa.eu/", "https://undertow.theintelligence.company", "https://theintelligence.company",
    "https://github.com/DISARMFoundation/", "https://raw.githubusercontent.com/DISARMFoundation/",
    "https://docs.oasis-open.org/", "https://github.com/metacog-osint/tic-doctrine", "https://creativecommons.org/",
    "https://www.disarm.foundation/", "https://disarm.foundation/", "https://dfrlab.org/",
    "https://checkfirst.network/", "https://correctiv.org/en/",
)


def allowed_prefixes() -> tuple[str, ...]:
    """The fixed list plus the reporter hosts the watch register lists by hand (a reporter's own site, never an
    operation's)."""
    return (ALLOWED_URL_PREFIXES + tuple(activity.load_watch().get("reporter_hosts") or [])
            + listings.notice_urls())
URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>)\]]+")
LEAK_PATTERNS = [(re.compile(r"\[\.\]"), "a defanged value"), (re.compile(r"(?<![\w@])@[A-Za-z0-9_]{3,}(?![\w.])"), "an @handle"),
                 (re.compile(r"hxxp", re.I), "a defanged URL")]


def leak_scan(paths: list[Path]) -> list[str]:
    errs = []
    allowed = allowed_prefixes()
    for p in paths:
        txt = p.read_text(encoding="utf-8")
        for m in URL_IN_TEXT.finditer(txt):
            u = m.group(0)
            if not u.startswith(allowed):
                errs.append(f"{p.name}: URL outside the allowed publisher pages: {u[:80]}")
        for rx, what in LEAK_PATTERNS:
            for m in rx.finditer(txt):
                errs.append(f"{p.name}: {what}: {txt[max(0, m.start() - 20): m.end() + 20]!r}")
    return errs


def check_all(root: Path = ROOT) -> list[str]:
    errs = (registers.check(root / "doctrine") + baseline.check_register(baseline.load_register())
            + targets.check())
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
    published = [data / "feed.geojson", data / "stix.json", data / "events.json", data / "snapshot.json",
                 data / "baseline.json"]
    if (data / "ended.geojson").exists():  # written by the history step (tic.py history), served beside the feed
        published.append(data / "ended.geojson")
    errs += leak_scan(published)
    errs += [f"watch register: {e}" for e in activity.check_watch(activity.load_watch())]
    errs += [f"listings: {e}" for e in listings.check(root, known=stix.named_organisations())]
    if TRIAGE_PATH.exists():
        # The triage list holds reporters' headlines; none may reach a published file.
        heads = [json.loads(x).get("title") or "" for x in TRIAGE_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
        blob = "\n".join(p.read_text(encoding="utf-8") for p in published)
        errs += [f"triage headline in a published file: {h[:60]!r}" for h in heads if len(h) > 25 and h in blob]
    return errs


def triage(days: int = 60, root: Path = ROOT, getter=None, pause: float | None = None) -> list[dict]:
    """Read each reporter's feed back `days` days and list influence-worded articles that name no tracked operation
    and are not yet on the triage list or in the watch register. Appends them to data/triage.jsonl (git-ignored,
    never published, never run in Actions) and returns them. The analyst reads the list and promotes what matters into
    config/register/watch.json by hand."""
    from datetime import timedelta
    path = root / "data" / "triage.jsonl"
    seen = set()
    if path.exists():
        seen = {json.loads(x)["link"] for x in path.read_text(encoding="utf-8").splitlines() if x.strip()}
    reg = activity.load_watch(root / "config" / "register" / "watch.json")
    for row in reg.get("rows") or []:
        for k in ("first_report", "last_report"):
            if (row.get(k) or {}).get("url"):
                seen.add(row[k]["url"])
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pause = (0 if getter is not None else reporters.PAUSE_S) if pause is None else pause
    found = []
    for lane, rep in reporters.REPORTERS.items():
        items, n = [], 0
        while n < rep.max_pages:
            n += 1
            if n > 1 and pause:
                import time
                time.sleep(pause)
            try:
                body, _ = fetch.fetch(f"{lane}-rss", reporters.page_url(rep, n), None, "xml", getter=getter)
            except Exception as exc:
                if n > 1 and reporters.is_end(exc):
                    break
                print(f"  {lane}: not read ({type(exc).__name__}: {exc})"[:200])
                break
            page = reporters.parse_page(body)
            if not page:
                break
            items += page
            if min(i["published"] for i in page) < since:
                break
        for c in reporters.triage_candidates(rep, items, since):
            if c["link"] not in seen:
                seen.add(c["link"])
                found.append(dict(c, seen_at=fetch.now_utc()))
    if found:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            for c in found:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return found


def closing_list(root: Path = ROOT, months: int = activity.CLOSE_MONTHS) -> dict:
    """Watch rows against the disclosures in data/snapshot.json (UT-IND-3..4). Writes data/closing.json (git-ignored,
    never published) and returns it. Run after each collect that brings a new disclosure; rows are closed by hand."""
    snap = json.loads((root / "data" / "snapshot.json").read_text(encoding="utf-8"))
    recs = snap.get("records") or {}
    disclosures = [r for lane in LANES if lane not in REPORTER_LANES and lane != "watch" for r in recs.get(lane, [])]
    reg = activity.load_watch(root / "config" / "register" / "watch.json")
    out = activity.closing(reg.get("rows") or [], disclosures, months)
    out["snapshot"] = snap.get("generated_at")
    path = root / "data" / "closing.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return out


def tag_backfill(getter=None, raw_dir: Path | None = None, pause: float = 2.0) -> dict:
    """Read Google's TAG Bulletin pages for the quarters before the lane's first, keep counts only (the default
    for ideas#16, 19 Nov 2026). The full replies go to data/raw/ only, never committed."""
    import time
    raw_dir = raw_dir if raw_dir is not None else ROOT / "data" / "raw"
    pages = []
    for i, (y, q) in enumerate(baseline.TAG_QUARTERS):
        if i and pause:
            time.sleep(pause)
        url = baseline.TAG_URL.format(q=q, y=y)
        body, rec = fetch.fetch("google-tag", url, raw_dir, "html", getter=getter)
        parsed = google.parse_page(body, y, q)
        if not parsed["entries"]:
            raise ValueError(f"TAG Q{q} {y} parsed to no entries")
        pages.append(baseline.page_entry(parsed, body, rec["sha256"]))
    reg = {"register": "google-tag-2024-2025",
           "note": ("Counts only, from Google's TAG Bulletin pages (the Influence Operations Bulletin's earlier name), "
                    "read by tools/undertow.py tagbackfill. Per entry: month, the linked-to country code as the lane's "
                    "parser reads it, asset counts, ongoing. No bulletin text kept. Used only by the baseline "
                    "(site/data/baseline.json), not as feed items."),
           "licence": "Google; facts and counts only (14 Nov 2026)",
           "read_at": fetch.now_utc(), "pages": pages}
    errs = baseline.check_register(reg)
    if errs:
        raise ValueError("; ".join(errs))
    baseline.REGISTER.write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return reg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Undertow: attributed influence-operation takedowns, at operation level.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--only", nargs="*", choices=LANES, help="run only these lanes; keep the rest as they were")
    sub.add_parser("build")
    sub.add_parser("check")
    sub.add_parser("archive", help="append the reporter lanes' report records to history/reports.jsonl")
    t = sub.add_parser("triage", help="laptop only: list new, unnamed reported activity into data/triage.jsonl")
    t.add_argument("--days", type=int, default=180)    # 16 Nov 2026: 180 days, to raise the register's volume
    k = sub.add_parser("closing", help="laptop only: watch rows against later disclosures into data/closing.json")
    k.add_argument("--months", type=int, default=activity.CLOSE_MONTHS)
    sub.add_parser("targetreview", help="items whose targets a rule read from prose, not yet read from the report "
                                        "(config/register/targets.json), into data/target-review.json")
    sub.add_parser("tagbackfill", help="laptop only: Google's TAG bulletins Q1 2024-Q4 2025 into a counts-only register")
    args = ap.parse_args(argv)
    if args.cmd == "collect":
        snap = collect(only=args.only)
        for lane, st in snap["lanes"].items():
            extra = f" ({st.get('error')})" if st.get("status") == "failed" else ""
            print(f"  {lane:7s} {st.get('status')} {st.get('items', '')}{' [last good copy]' if st.get('from_previous') else ''}{extra}")
        print(f"Collected {sum(len(v) for v in snap['records'].values())} operation records.")
        return 0 if any(s.get("status") == "ok" for s in snap["lanes"].values()) else 1
    if args.cmd == "archive":
        snap = json.loads((ROOT / "data" / "snapshot.json").read_text(encoding="utf-8"))
        print(f"  history/reports.jsonl: {archive.run(snap, ROOT / 'history', REPORTER_LANES)} new lines")
        return 0
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
    if args.cmd == "targetreview":
        snap = json.loads((ROOT / "data" / "snapshot.json").read_text(encoding="utf-8"))
        rows = targets.keyword_matched(all_records(snap))
        out = ROOT / "data" / "target-review.json"
        out.write_text(json.dumps({"generated_at": snap["generated_at"], "items": rows}, indent=1, ensure_ascii=False),
                       encoding="utf-8")
        for r in rows:
            print(f"  {r['id']} {r['publisher']:10s} {','.join(r['targets'] + r['target_regions'])}: "
                  f"{(r['sentence'] or '')[:120] or str(len(r.get('reports') or [])) + ' report(s) to read'}")
        print(f"{len(rows)} items to review -> {out.relative_to(ROOT)}")
        return 0
    if args.cmd == "tagbackfill":
        if os.environ.get("GITHUB_ACTIONS"):
            print("tagbackfill runs on the laptop only: its register is reviewed before it is committed.")
            return 1
        reg = tag_backfill()
        for pg in reg["pages"]:
            print(f"  Q{pg['quarter']} {pg['year']}: {len(pg['entries'])} entries, {pg['unparsed']} unparsed, "
                  f"updated {pg['updated']}{' (' + pg['updated_note'] + ')' if pg['updated_note'] else ''}")
        print(f"Wrote {baseline.REGISTER.relative_to(ROOT)}; check it, then commit it.")
        return 0
    if args.cmd == "triage":
        if os.environ.get("GITHUB_ACTIONS"):
            print("triage runs on the laptop only: its list holds reporters' headlines and is never published.")
            return 1
        found = triage(days=args.days)
        for c in found:
            print(f"  {c['published'][:10]}  {c['reporter']:10s} {', '.join(c['wording'])}")
            print(f"      {c['title']}")
            print(f"      {c['link']}")
        print(f"{len(found)} new for triage (added to data/triage.jsonl; private, never published). Promote a row by "
              "hand into config/register/watch.json.")
        return 0
    if args.cmd == "closing":
        if os.environ.get("GITHUB_ACTIONS"):
            print("closing runs on the laptop only: watch rows are closed by hand.")
            return 1
        out = closing_list(months=args.months)
        for o in out["open"]:
            print(f"  {o['row']} (first report {o['first_report']}): {len(o['candidates'])} candidate(s)")
            for c in o["candidates"][:10]:
                print(f"      {c['disclosed_at']}  +{c['days_after_first_report']} d  period {c['period'] or '-'}  "
                      f"{c['publisher']} ({c['kind']}), "
                      f"{c['basis']} {', '.join(c['countries'])}: {c['key']}")
        for c in out["closed"]:
            print(f"  closed: {c['row']} -> {c['closed_into']} ({c['kind']}), lead {c['lead_days']} d")
        for p in out["problems"]:
            print(f"  problem: {p}")
        print(f"{len(out['open'])} open, {out['closed_into_takedown']} closed into a takedown, median lead "
              f"{out['median_lead_days'] if out['median_lead_days'] is not None else 'none yet'}; UT-IND-3..4 need 10 "
              "closed rows. Written to data/closing.json (private). Close a row by hand: closed_into in watch.json.")
        return 1 if out["problems"] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

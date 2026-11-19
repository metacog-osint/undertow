"""Offline tests: every lane replays real replies recorded on 14 Nov 2026 (tests/fixtures/MANIFEST.json).

    python -m unittest discover -s tests

The leak tests take the indicator values and handles from Meta's real indicator tables in the fixtures and check
that none of them, and none of the personal names the publishers quote, reaches any published file.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("undertow_cli", ROOT / "tools" / "undertow.py")
cli = importlib.util.module_from_spec(_spec)   # tools/undertow.py (its name clashes with the package)
_spec.loader.exec_module(cli)

from undertow import (activity, analysis, archive, disarm, eeas, feed, google, meta, openai_rss, reporters,  # noqa: E402
                      stix, text, tiktok)
from tic_doctrine import contract, history, registers  # noqa: E402
from tic_doctrine.lint import check_header  # noqa: E402

MANIFEST = json.loads((FIX / "MANIFEST.json").read_text(encoding="utf-8"))
BY_URL = {v["url"]: FIX / name for name, v in MANIFEST["files"].items()}
NAMES_QUOTED = ["Peter Magyar", "George Soros", "Viktor Orbán", "Orbán", "Magyar", "Soros"]
FETCHED: list[str] = []
REPORTER_LANES = list(reporters.REPORTERS)


def reporter_texts() -> list[str]:
    """Every title and description in the recorded reporter feeds (they name individuals)."""
    out = []
    for lane in REPORTER_LANES:
        for fx in sorted(FIX.glob(f"{lane}_feed_*.xml")):
            for it in reporters.parse_page(fx.read_bytes()):
                out += [it["title"], it["description"]]
    return [x for x in out if len(x) > 25]


def getter(url: str, timeout: int = 60) -> bytes:
    FETCHED.append(url)
    if url in BY_URL:
        return BY_URL[url].read_bytes()
    raise urllib.error.HTTPError(url, 404, "not recorded", {}, None)


def meta_indicator_values() -> set[str]:
    vals = set()
    for f in FIX.glob("meta_*.md"):
        for v in re.findall(r"`([^`]+)`", f.read_text(encoding="utf-8")):
            if "[.]" in v or v.startswith("http"):
                vals.add(v)
                clean = v.replace("[.]", ".")
                vals.add(clean)
                host = re.sub(r"^https?://", "", clean).split("/")[0]
                vals.add(host)
                for h in re.findall(r"@([\w.]+)", clean):
                    vals.add(h)
    return {v for v in vals if len(v) >= 6}


class Pipeline(unittest.TestCase):
    """collect -> build on the recorded replies, in a scratch root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="undertow-test-"))
        FETCHED.clear()
        cls.snap = cli.collect(root=cls.tmp, getter=getter)
        cls.files = cli.build_site(root=cls.tmp)
        cls.feed = json.loads(cls.files["data/feed.geojson"])
        cls.stix = json.loads(cls.files["data/stix.json"])
        cls.events = json.loads(cls.files["data/events.json"])
        cls.page = json.loads(cls.files["data/snapshot.json"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_all_lanes_ok(self):
        for lane, st in self.snap["lanes"].items():
            self.assertEqual(st["status"], "ok", f"{lane}: {st.get('error')}")
        counts = {k: len(v) for k, v in self.snap["records"].items()}
        self.assertEqual(counts["meta"], 22)
        self.assertEqual(counts["eeas"], 9)
        self.assertEqual(counts["tiktok"], 25)
        self.assertGreater(counts["google"], 240)     # Q2 158 + Q3 93 recorded; Q1 not recorded
        self.assertGreater(counts["openai"], 20)
        self.assertEqual(counts["dfrlab"], 15)        # report records, folded into reported-activity items at build
        self.assertEqual(counts["checkfirst"], 5)
        self.assertEqual(counts["correctiv"], 3)
        self.assertEqual(counts["watch"], len(activity.load_watch()["rows"]))   # 1 since 16 Nov 2026 (Armenia)

    def test_health_keyed_by_item_source_ids(self):
        h = self.feed["health"]
        item_sources = {f["properties"]["sources"][0]["id"] for f in self.feed["features"]}
        self.assertLessEqual(item_sources, set(h))   # the history log's lane is an item's first source id
        unused = set() if activity.load_watch()["rows"] else {"undertow-watch-register"}
        self.assertEqual(set(h) - item_sources, unused)
        self.assertEqual({v["lane"] for v in h.values()}, set(cli.LANES))
        for sid, e in h.items():
            self.assertEqual(e["state"], "up", sid)
            self.assertEqual(e["last_ok"], e["checked_at"], sid)
            self.assertEqual(e["failures"], 0, sid)
            self.assertIsNone(e["last_error"], sid)
            if sid != "undertow-watch-register":
                self.assertTrue(e["data_as_of"], sid)
        self.assertEqual(history.lanes_ok(h), set(h))

    def test_openai_only_rss_fetched(self):
        openai_urls = [u for u in FETCHED if "openai.com" in u]
        self.assertEqual(set(openai_urls), {openai_rss.RSS_URL})
        self.assertFalse(any("tiktok.com" in u for u in FETCHED))
        self.assertFalse(openai_rss.fetch_allowed("https://openai.com/index/disrupting-ai-enabled-false-front-operations/"))

    def test_feed_lints(self):
        regs = registers.ids(ROOT / "doctrine")
        self.assertEqual([p for p in check_header(self.feed) if p[1] == "error"], [])
        for f in self.feed["features"]:
            errs = [p for p in contract.check(f, regs) if p[1] == "error"]
            self.assertEqual(errs, [], f["properties"]["id"])
        self.assertEqual(self.feed["contract"], "tic-feed/2")

    def test_date_precision(self):
        """A publisher date with no time says so (data_as_of_precision), so no page shows it as the evening before."""
        by_pub = {}
        for f in self.feed["features"]:
            p = f["properties"]
            by_pub.setdefault(p["operation"]["publisher"], []).append(p)
            prec = p.get("data_as_of_precision")
            if p["data_as_of"].endswith("T00:00:00Z") and p["operation"]["publisher"] != "meta":
                self.assertIn(prec, ("day", "month"), p["id"])
            if prec == "month":
                self.assertEqual(p["data_as_of"][8:], "01T00:00:00Z", p["id"])
        self.assertTrue(all(p.get("data_as_of_precision") is None for p in by_pub["meta"]))
        self.assertTrue(all(p["data_as_of_precision"] == "day" for p in by_pub["google"] + by_pub["eeas"]))
        self.assertTrue(any(p.get("data_as_of_precision") == "month" for p in by_pub["openai"]))
        self.assertEqual(openai_rss.date_precision("2026-06-01T00:00:00Z"), "month")
        self.assertEqual(openai_rss.date_precision("2026-10-08T00:00:00Z"), "day")
        self.assertIsNone(openai_rss.date_precision("2024-08-16T11:00:00Z"))

    def test_no_indicator_handle_or_url_in_any_output(self):
        vals = meta_indicator_values()
        self.assertGreater(len(vals), 20)            # the fixtures really hold indicator tables
        for name, body in self.files.items():
            if not name.startswith("data/"):
                continue
            for v in vals:
                self.assertNotIn(v, body, f"{name} holds indicator value {v!r}")
            self.assertNotIn("[.]", body, name)
            self.assertIsNone(re.search(r"(?<![\w@])@[A-Za-z0-9_]{3,}(?![\w.])", body), name)
            for u in re.findall(r"https?://[^\s\"'<>)\]]+", body):
                self.assertTrue(u.startswith(cli.allowed_prefixes()), f"{name}: {u}")

    def test_no_personal_names_in_any_output(self):
        for name, body in self.files.items():
            if name.startswith("data/"):
                for n in NAMES_QUOTED:
                    self.assertNotIn(n, body, f"{name} holds {n!r}")

    def test_check_all_leak_scan_passes(self):
        data = self.tmp / "site" / "data"
        self.assertEqual(cli.leak_scan(sorted(data.glob("*"))), [])

    def test_ids_stable_across_runs(self):
        again = cli.build_site(root=self.tmp)
        f2 = json.loads(again["data/feed.geojson"])
        s2 = json.loads(again["data/stix.json"])
        self.assertEqual([f["properties"]["id"] for f in self.feed["features"]], [f["properties"]["id"] for f in f2["features"]])
        self.assertEqual(self.stix, s2)
        ids = [f["properties"]["id"] for f in self.feed["features"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_stix_valid_and_no_forbidden_objects(self):
        self.assertEqual(stix.validate(self.stix), [])
        types = {o["type"] for o in self.stix["objects"]}
        self.assertTrue({"identity", "report", "campaign", "location", "relationship", "attack-pattern",
                         "intrusion-set", "marking-definition"} <= types)
        self.assertFalse(types & stix.FORBIDDEN)

    def test_stix_threat_actors_only_for_hand_kept_organisations(self):
        tas = [o for o in self.stix["objects"] if o["type"] == "threat-actor"]
        self.assertTrue(tas, "the recorded replies name at least one organisation")
        for t in tas:
            self.assertIn(t["name"], stix.named_organisations())
            self.assertEqual(t["threat_actor_types"], ["unknown"])
            self.assertEqual(t["resource_level"], "organization")
        rels = [o for o in self.stix["objects"] if o["type"] == "relationship" and o["target_ref"].startswith("threat-actor--")]
        self.assertTrue(rels and all(r["source_ref"].startswith("campaign--") for r in rels))

    def test_stix_validator_refuses_a_threat_actor_it_does_not_keep(self):
        b = json.loads(json.dumps(self.stix))
        ta = next(o for o in b["objects"] if o["type"] == "threat-actor")
        ta["name"] = "Jane Example"
        ta["roles"] = ["director"]
        errs = stix.validate(b)
        self.assertTrue(any("hand-kept organisation" in e for e in errs), errs)
        self.assertTrue(any("roles is never stated" in e for e in errs), errs)

    def test_a_free_text_org_never_becomes_a_threat_actor(self):
        recs = json.loads(json.dumps(cli.all_records(self.snap)))
        recs = [r for r in recs if not r.get("activity")] + [r for r in recs if r.get("activity")]
        recs[0]["orgs"] = [{"name": "Jane Example", "country": "RU"}]
        b = stix.build_bundle(recs, "2026-11-16T00:00:00Z")
        self.assertNotIn("Jane Example", [o.get("name") for o in b["objects"]])
        self.assertEqual(stix.validate(b), [])

    def test_standing_listings_show_as_listed_by_and_external_references(self):
        sda = [f["properties"] for f in self.feed["features"]
               if "Social Design Agency" in f["properties"]["operation"]["sponsor"]]
        self.assertTrue(sda, "the recorded replies name the Social Design Agency")
        for p in sda:
            lists = {(x["organisation"], x["list"]) for x in p["operation"]["listed_by"]}
            self.assertIn(("Social Design Agency", "ofac-sdn"), lists)
            self.assertIn("Social Design Agency is listed by", p["summary"])
            self.assertIn("not an origin and changes no confidence", p["summary"])
        rows = [r for r in self.page["items"] if "Social Design Agency" in r["orgs"]]
        self.assertTrue(rows and all(r["listed_by"] for r in rows))
        unlisted = [f["properties"] for f in self.feed["features"] if f["properties"]["operation"]["sponsor"]
                    and not set(f["properties"]["operation"]["sponsor"]) & {"Social Design Agency", "ANO Dialog", "Struktura"}]
        for p in unlisted:
            self.assertEqual(p["operation"]["listed_by"], [])
            self.assertNotIn("is listed by", p["summary"])
        tas = {o["name"]: o for o in self.stix["objects"] if o["type"] == "threat-actor"}
        refs = tas["Social Design Agency"]["external_references"]
        self.assertIn("https://ofac.treasury.gov/recent-actions/20240320", [r["url"] for r in refs])
        for name in ("Haimai", "China Global Television Network"):
            if name in tas:
                self.assertNotIn("external_references", tas[name])
        # A listing adds a reference only: the threat-actor's relationships are still attributed-to and located-at.
        kinds = {o["relationship_type"] for o in self.stix["objects"] if o["type"] == "relationship"
                 and tas["Social Design Agency"]["id"] in (o["source_ref"], o["target_ref"])}
        self.assertLessEqual(kinds, {"attributed-to", "located-at"})

    def test_listings_change_no_confidence_or_origin(self):
        from unittest import mock
        from undertow import listings
        recs = cli.all_records(self.snap)
        with_l = feed.build_feed(recs, self.snap["generated_at"], {})
        with mock.patch.object(listings, "_by_name", return_value={}):
            without = feed.build_feed(recs, self.snap["generated_at"], {})
        a = {f["properties"]["id"]: f["properties"] for f in with_l["features"]}
        b = {f["properties"]["id"]: f["properties"] for f in without["features"]}
        self.assertEqual(set(a), set(b))
        changed = 0
        for k in a:
            for field in ("confidence", "confidence_basis", "actors", "countries", "tier", "kind"):
                self.assertEqual(a[k].get(field), b[k].get(field), f"{k}: {field}")
            self.assertEqual(a[k]["operation"]["origin"], b[k]["operation"]["origin"])
            changed += a[k]["summary"] != b[k]["summary"]
        self.assertGreater(changed, 0)

    def test_stix_disarm_objects_unchanged_with_cc_by_sa(self):
        vendored = {o["id"]: o for o in disarm.bundle()["objects"]}
        for o in self.stix["objects"]:
            if o["type"] == "attack-pattern":
                self.assertEqual(o, vendored[o["id"]])
                self.assertIn(disarm.marking()["id"], o["object_marking_refs"])
        mk = next(o for o in self.stix["objects"] if o["id"] == disarm.marking()["id"])
        self.assertIn("CC-BY-SA-4.0", mk["definition"]["statement"])

    def test_stix_tlp_clear_matches_oasis(self):
        tlp = next(o for o in self.stix["objects"] if o["id"] == "marking-definition--94868c89-83c2-464b-929b-a1a8aa3c8487")
        self.assertEqual(tlp["name"], "TLP:CLEAR")

    def test_mapped_techniques_exist_in_v161(self):
        n = 0
        for f in self.feed["features"]:
            for t in f["properties"]["disarm_technique"]:
                self.assertIsNotNone(disarm.name(t), t)
                n += 1
            for m in f["properties"]["disarm_mapping"]:
                self.assertEqual(m["basis"], "mapped")
        self.assertGreater(n, 20)

    def test_no_high_confidence_and_origin_not_sponsorship(self):
        for f in self.feed["features"]:
            p = f["properties"]
            self.assertNotEqual(p.get("confidence"), "high")
            if p.get("confidence"):
                self.assertEqual(p["confidence_basis"]["rubric"], "tic-confidence-1.0")
                self.assertIn("deception", p["confidence_basis"]["caps"])
            self.assertIn("never a finding of who directed it", p["summary"])
        # EEAS calls Storm-1516 non-attributed: alignment only, no origin, no confidence level.
        storm = next(f["properties"] for f in self.feed["features"] if f["properties"]["operation"]["key"] == "eeas:fimi-4:storm-1516")
        self.assertEqual(storm["operation"]["origin"], [])
        self.assertEqual(storm["operation"]["alignment"], ["RU"])
        self.assertNotIn("confidence", storm)

    def test_doppelganger_corroborated_moderate(self):
        dop = [f["properties"] for f in self.feed["features"] if "doppelganger" in f["properties"]["operation"]["named_operations"]]
        pubs = {p["operation"]["publisher"] for p in dop}
        # "watch": the G7 RRM's Moldova row names Doppelganger (Tom, 18 Nov 2026).
        self.assertEqual(pubs, {"meta", "openai", "eeas", "dfrlab", "correctiv", "watch"})
        self.assertTrue(all(p["confidence"] == "moderate" for p in dop if "activity" not in p))
        self.assertTrue(all("confidence" not in p for p in dop if "activity" in p))
        eeas_dop = next(p for p in dop if p["operation"]["publisher"] == "eeas")
        self.assertEqual(eeas_dop["us_person_data"], "organizations")
        self.assertIn("Social Design Agency", eeas_dop["operation"]["sponsor"])

    def test_reported_activity_one_item_per_operation_and_reporter(self):
        """Decision 1: reporter lanes publish reported-activity items, one per (reporter, operation), kept apart from
        disclosures, graded by the reporter, with first and last report and a state of active or quiet."""
        acts = [f["properties"] for f in self.feed["features"] if "activity" in f["properties"]]
        by = {(p["operation"]["publisher"], p["activity"]["operation"] if p["operation"]["publisher"] != "watch"
               else p["operation"]["key"]): p for p in acts}
        self.assertEqual(len(by), len(acts))
        self.assertEqual({k[0] for k in by} - {"watch"}, {"dfrlab", "checkfirst", "correctiv"})
        self.assertEqual(sum(p["activity"]["reports"] for p in acts if p["operation"]["publisher"] == "dfrlab"), 15)
        self.assertEqual(len([p for p in acts if p["operation"]["publisher"] == "dfrlab"]), 5)
        grades = {"dfrlab": "B2", "checkfirst": "B2", "correctiv": "B3"}
        names = {o["id"]: o["name"] for o in text.operations()}
        for p in acts:
            a = p["activity"]
            if a["reporter"] == "watch":            # hand-kept rows: test_watch_register_checks_and_origin_rule
                continue
            self.assertEqual(p["sources"][0]["grade"], grades[a["reporter"]])
            self.assertIn(a["state"], ("active", "quiet"))
            self.assertNotIn("ended", p["title"] + p["summary"].replace("not evidence the operation stopped", ""))
            self.assertEqual(p["operation"]["origin"], [])
            self.assertNotIn("confidence", p)
            self.assertLessEqual(a["first_report"], a["last_report"])
            self.assertEqual(p["data_as_of"], a["last_report"])
            self.assertEqual(len(a["report_links"]), a["reports"])
            self.assertTrue(p["title"].startswith(names[a["operation"]] + ": "))
            self.assertTrue(all(x["url"].startswith(reporters.REPORTERS[a["reporter"]].link_prefix) for x in a["report_links"]))
            self.assertEqual(p["kind"], "observation")
        storm = by[("correctiv", "storm-1516")]
        self.assertEqual(storm["activity"]["state"], "active")     # 11 Nov 2026, within 180 days of the collect

    def test_reporters_keep_no_reporter_text_and_fetch_only_feeds(self):
        """Reporters' titles and descriptions (which name individuals) and authors never reach a published file, and
        no article page is ever fetched."""
        blob = "\n".join(self.files.values())
        for t in reporter_texts():
            self.assertNotIn(t, blob)
        for name in ["Sandu", "Zelenskyy", "Navalny", "Biden"]:
            self.assertNotIn(name, blob, name)
        for lane in REPORTER_LANES:
            rep = reporters.REPORTERS[lane]
            urls = [u for u in FETCHED if u.startswith(rep.link_prefix.split("/en/")[0])]
            self.assertTrue(urls, lane)
            self.assertTrue(all(u.startswith(rep.feed_url) for u in urls), urls)

    def test_reporters_corroborate_but_never_raise_confidence(self):
        recs = cli.all_records(self.snap)
        with_r = {r["key"]: (r.get("confidence") or {}).get("confidence") for r in recs if not r.get("activity")}
        without = [r for r in recs if not r.get("activity")]
        for r in without:
            r.pop("confidence", None)
        analysis.assess(without)
        self.assertEqual(with_r, {r["key"]: (r.get("confidence") or {}).get("confidence") for r in without})
        storm = next(f["properties"] for f in self.feed["features"] if f["properties"]["operation"]["key"] == "eeas:fimi-4:storm-1516")
        self.assertIn("dfrlab", storm["operation"]["corroborated_by"])
        self.assertIn("correctiv", storm["operation"]["corroborated_by"])
        reps = [o for o in self.stix["objects"] if o["type"] == "report" and "x_tic_activity_state" in o]
        # one report per reporter-lane item; a watch row is a campaign (attributed-to the operations it names)
        self.assertEqual(len(reps), len([f for f in self.feed["features"]
                                         if "activity" in f["properties"] and f["properties"]["activity"]["operation"]
                                         and f["properties"]["operation"]["publisher"] != "watch"]))
        self.assertTrue(all(len(o["object_refs"]) == 1 and o["object_refs"][0].startswith("intrusion-set--") for o in reps))
        self.assertFalse([o for o in self.stix["objects"] if o["type"] == "campaign" and "reported by" in o["name"]])

    def test_events_dates_only(self):
        evs = self.events["events"]
        self.assertTrue(evs)
        for e in evs:
            self.assertRegex(e["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertEqual(e["kind"], "data_release")
            self.assertNotIn("probability", json.dumps(e))
            self.assertIn("not a published date", e["title"])


class HealthAndHistory(unittest.TestCase):
    """A failed lane is marked failing in the feed's health record, so the kit's history log ends none of its items;
    a lane read well ends the items that left it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="undertow-hist-"))
        cli.collect(root=cls.tmp, getter=getter)
        cls.feed1 = json.loads(cli.build_site(root=cls.tmp)["data/feed.geojson"])

        def meta_down(url, timeout=60):
            if "meta/threat-research" in url:
                raise urllib.error.HTTPError(url, 503, "down", {}, None)
            return getter(url, timeout)
        cls.snap2 = cli.collect(root=cls.tmp, getter=meta_down)
        cls.feed2 = json.loads(cli.build_site(root=cls.tmp)["data/feed.geojson"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_failed_lane_is_failing_and_keeps_last_copy(self):
        st = self.snap2["lanes"]["meta"]
        self.assertEqual((st["status"], st["from_previous"], st["failures"], st["items"]), ("failed", True, 1, 22))
        e = self.feed2["health"]["meta-threat-research"]
        self.assertEqual(e["state"], "failing")   # excluded by state, even if both runs fell in the same second
        self.assertIn("503", e["last_error"])
        self.assertNotIn("meta-threat-research", history.lanes_ok(self.feed2["health"]))
        self.assertEqual(len(history.lanes_ok(self.feed2["health"])), len(cli.LANES) - 1)

    def _run(self, feed2):
        t1 = datetime(2026, 11, 16, 2, 30, tzinfo=timezone.utc)
        state, lines = history.update({}, self.feed1, self.feed1["health"], t1)
        self.assertEqual({ln["change"] for ln in lines}, {"new"})
        self.assertEqual(len(lines), len(self.feed1["features"]))
        return history.update(state, feed2, feed2["health"], t1 + timedelta(hours=6))[1]

    def test_failed_lane_ends_nothing(self):
        # As if the failed lane had lost an item too: its items still must not end.
        feed2 = dict(self.feed2)
        gone = next(f for f in feed2["features"] if f["properties"]["sources"][0]["id"] == "meta-threat-research")
        feed2["features"] = [f for f in feed2["features"] if f is not gone]
        self.assertEqual([ln for ln in self._run(feed2) if ln["change"] == "ended"], [])

    def test_read_lane_ends_the_item_that_left(self):
        feed2 = dict(self.feed1)
        gone = next(f for f in feed2["features"] if f["properties"]["sources"][0]["id"] == "google-iob")
        feed2["features"] = [f for f in feed2["features"] if f is not gone]
        ended = [ln for ln in self._run(feed2) if ln["change"] == "ended"]
        self.assertEqual([ln["id"] for ln in ended], [gone["properties"]["id"]])
        self.assertEqual(ended[0]["lane"], "google-iob")


class Lanes(unittest.TestCase):
    def test_dfrlab_reads_until_it_reaches_what_it_read_before(self):
        R = reporters.REPORTERS["dfrlab"]
        pages = {n: (FIX / f"dfrlab_feed_{n:02d}.xml") for n in range(1, 40) if (FIX / f"dfrlab_feed_{n:02d}.xml").exists()}
        read = []

        def fetch_page(n):
            read.append(n)
            return pages[n].read_bytes() if n in pages else None
        recs, extra, n = reporters.read(R, fetch_page, None, pause=0)
        self.assertEqual(extra["backfilled_to"], R.since)
        self.assertLess(extra["oldest_read"], R.since)
        self.assertEqual(len(recs), 15)
        read.clear()
        recs2, extra2, n2 = reporters.read(R, fetch_page, extra, pause=0)
        self.assertLessEqual(n2, 2)                       # incremental: back to 30 days before the newest item
        self.assertEqual(len(reporters.merge(R, recs2, recs)), 15)
        read.clear()
        reporters.read(R, fetch_page, dict(extra, ops_fingerprint="changed"), pause=0)
        self.assertEqual(len(read), n)                    # a new alias reads the whole feed again
        self.assertIsNone(reporters.build_record(R, {"title": "A study of coordinated networks", "description": "",
                                                     "categories": [], "published": "2026-10-01T10:00:00Z",
                                                     "link": "https://dfrlab.org/2026/10/01/x/"}))
        self.assertIsNone(reporters.build_record(R, {"title": "Storm-1516 again", "description": "",
                                                     "categories": [], "published": "2026-10-01T10:00:00Z",
                                                     "link": "https://elsewhere.example/x/"}))

    def test_activity_state_quiet_after_180_days_never_ended(self):
        rec = {"key": "dfrlab:x", "named_operations": ["storm-1516"], "disclosed_at": "2026-01-10T12:00:00Z",
               "url": "https://dfrlab.org/2026/01/10/x/", "countries_named": ["FR"], "target_regions": [],
               "platforms": [], "disarm": []}
        a1 = activity.aggregate({"dfrlab": [rec]}, date(2026, 7, 9))[0]      # 180 days later
        a2 = activity.aggregate({"dfrlab": [rec]}, date(2026, 7, 10))[0]     # 181 days later
        self.assertEqual((a1["activity"]["state"], a2["activity"]["state"]), ("active", "quiet"))
        self.assertTrue(a2["title"].endswith("(quiet)"))
        self.assertEqual(activity.QUIET_DAYS, 180)
        self.assertNotIn("ended", json.dumps(a2))

    def test_only_stated_targets_are_marked_on_the_map(self):
        """Tom, 16 Nov 2026: a reporter item is marked only at countries its reports name that a disclosure of the
        same operation records as targets, never at the operators' country; a description's countries are never
        geometry."""
        from undertow import feed
        rec = {"key": "correctiv:x", "named_operations": ["storm-1516"], "disclosed_at": "2026-11-11T11:25:06Z",
               "url": "https://correctiv.org/en/x/", "countries_named": ["RU", "US"], "target_regions": [],
               "platforms": [], "disarm": []}
        act = activity.aggregate({"correctiv": [rec]}, date(2026, 11, 16))[0]
        disclosure = {"key": "eeas:storm", "named_operations": ["storm-1516"], "targets": ["US", "FR"]}
        activity.place([disclosure, act])
        self.assertEqual(act["targets"], ["US"])
        f = feed.feature(act, "2026-11-16T04:00:00Z")
        self.assertEqual(f["geometry"]["type"], "Point")
        self.assertEqual(f["properties"]["countries"], ["US", "RU"])
        self.assertIn("records a target: United States", f["properties"]["summary"])
        lone = activity.aggregate({"correctiv": [dict(rec, countries_named=["RU"])]}, date(2026, 11, 16))[0]
        activity.place([disclosure, lone])
        g = feed.feature(lone, "2026-11-16T04:00:00Z")
        self.assertIsNone(g["geometry"])
        self.assertEqual(g["properties"]["precision_class"], "none")
        self.assertIn("not marked on the map", g["properties"]["summary"])
        named_only = {k: v for k, v in act.items() if k != "activity"}
        named_only.update(publisher="google", targets=[], countries_named=["RU", "UA"])
        h = feed.feature(named_only, "2026-11-16T04:00:00Z")
        self.assertIsNone(h["geometry"])
        self.assertIn("not stated as targets", h["properties"]["summary"])

    def test_watch_register_checks_and_origin_rule(self):
        """Decision 4: a watch row's origin counts only when Tom checked it and the reporter shows its own evidence."""
        self.assertEqual(activity.check_watch(activity.load_watch()), [])
        live = activity.load_watch()                           # first row: Armenia, promoted by Tom on 16 Nov 2026
        self.assertTrue(all(not r.get("origin") and not r.get("checked_by") for r in live["rows"]))
        self.assertTrue(all(any(r["first_report"]["url"].startswith(h) for h in live["reporter_hosts"])
                            for r in live["rows"]))
        row = {"id": "example-net", "operation": "an unnamed network targeting Moldova",
               "reporter": {"name": "Example Lab", "grade": "B2", "terms": "read 16 Nov 2026"},
               "first_report": {"date": "2026-11-01", "url": "https://lab.example/a/"},
               "countries": ["MD"], "origin": ["RU"], "origin_evidence": "own", "checked_by": "Tom",
               "checked_on": "2026-11-16", "tracked_operation": "storm-1516"}
        reg = {"reporter_hosts": ["https://lab.example/"], "rows": [row]}
        self.assertEqual(activity.check_watch(reg), [])
        bad = json.loads(json.dumps(reg))
        bad["rows"][0]["operation"] = "Maia Sandu smear network"
        bad["rows"][0]["first_report"]["url"] = "https://operation-domain.example/x"
        errs = activity.check_watch(bad)
        self.assertTrue(any("scrubber" in e for e in errs), errs)
        self.assertTrue(any("reporter host" in e for e in errs), errs)
        today = date(2026, 11, 16)
        counted = activity.watch_records(reg, today)[0]
        self.assertEqual(counted["origin"], ["RU"])
        for change in ({"checked_by": None}, {"origin_evidence": "cites-other"}):
            r2 = activity.watch_records({"rows": [dict(row, **change)]}, today)[0]
            self.assertEqual(r2["origin"], [], change)
            self.assertEqual(r2["origin_reported"], ["RU"])
        eeas_storm = {"key": "eeas:x", "publisher": "eeas", "origin": ["RU"], "named_operations": ["storm-1516"]}
        recs = [eeas_storm, counted]
        analysis.assess(recs)
        self.assertEqual(eeas_storm["confidence"]["confidence"], "moderate")    # two lines, still capped
        self.assertEqual(eeas_storm["confidence"]["confidence_basis"]["factors"]["grades"], ["A2", "B2"])
        uncounted = activity.watch_records({"rows": [dict(row, checked_by=None)]}, today)[0]
        recs = [dict(eeas_storm, confidence=None), uncounted]
        analysis.assess(recs)
        self.assertEqual(recs[0]["confidence"]["confidence"], "low")

    def test_watch_label_mid_sentence(self):
        """A watch row's label starts its title capitalised and reads lower-case mid-sentence; acronyms keep theirs.
        Its targets are said to be entered from the report (Tom enters them at triage)."""
        self.assertEqual(activity.in_sentence("Inauthentic networks before X"), "inauthentic networks before X")
        for keep in ("RRN networks", "A", "G7 summit networks", "an unnamed network"):
            self.assertEqual(activity.in_sentence(keep), keep)
        row = {"id": "example-net", "operation": "Inauthentic networks targeting Moldova",
               "reporter": {"name": "Example Lab", "grade": "B2", "terms": "read 16 Nov 2026"},
               "first_report": {"date": "2026-11-01", "url": "https://lab.example/a/"}, "countries": ["MD"]}
        rec = activity.watch_records({"rows": [row]}, date(2026, 11, 16))[0]
        self.assertTrue(rec["title"].startswith("Inauthentic networks targeting Moldova: reported by"))
        self.assertEqual(rec["disclosure"]["title"], "Example Lab reporting on inauthentic networks targeting Moldova")
        s = feed.summary(rec)
        self.assertIn("Example Lab reported on inauthentic networks targeting Moldova on 2026-11-01.", s)
        self.assertIn("Targets as entered from the report: Moldova.", s)
        self.assertNotIn("as the reporter states them", s)

    def test_watch_row_with_several_tracked_operations(self):
        """Tom, 16 Nov 2026: a watch row may name several tracked operations; a reporter's 'state-aligned' is
        alignment, never origin; activity_period says when the activity ran; closing matches any listed operation."""
        row = {"id": "example-vote", "operation": "Pro-Russian disinformation before an example vote",
               "tracked_operations": ["storm-1516", "portal-kombat"],
               "reporter": {"name": "Example Mechanism", "grade": "B2", "terms": "read 16 Nov 2026",
                            "source_type": "government"},
               "first_report": {"date": "2026-10-26", "url": "https://gov.example/report/"},
               "countries": ["MD"], "activity_period": {"from": "2026-01-01", "to": "2026-06-10"},
               "alignment": ["RU"], "attribution_wording": "Russian state-aligned"}
        reg = {"reporter_hosts": ["https://gov.example/"], "rows": [row]}
        self.assertEqual(activity.check_watch(reg), [])
        for bad, word in (({"tracked_operations": ["no-such-op"]}, "not in config"),
                          ({"tracked_operations": "storm-1516"}, "must be a list"),
                          ({"activity_period": {"from": "2026-06", "to": "2026-01"}}, "activity_period"),
                          ({"alignment": ["Russia"]}, "alignment")):
            errs = activity.check_watch({"reporter_hosts": reg["reporter_hosts"], "rows": [dict(row, **bad)]})
            self.assertTrue(any(word in e for e in errs), (bad, errs))
        rec = activity.watch_records(reg, date(2026, 11, 16))[0]
        self.assertEqual(rec["named_operations"], ["storm-1516", "portal-kombat"])
        self.assertEqual(rec["origin"], [])
        self.assertEqual(rec["alignment"], ["RU"])
        self.assertIsNone(rec["activity"]["operation"])
        self.assertEqual(rec["activity"]["operations"], ["storm-1516", "portal-kombat"])
        s = feed.summary(rec)
        self.assertIn("Activity the report covers: 2026-01-01 to 2026-06-10.", s)
        self.assertIn("Operations Undertow tracks that the report names: Storm-1516, Portal Kombat.", s)
        self.assertIn("recorded as alignment, not as an origin", s)
        self.assertIn("adds no origin and no confidence", s)
        old = dict(row, tracked_operation="storm-1516")
        del old["tracked_operations"]
        self.assertEqual(activity.row_operations(old), ["storm-1516"])
        disc = {"key": "meta:x", "publisher": "meta", "disclosed_at": "2026-12-01T00:00:00Z", "period": "2026-11",
                "targets": ["FR"], "named_operations": ["portal-kombat"], "title": "x"}
        cands = activity.closing([row], [disc], months=12)["open"][0]["candidates"]
        self.assertEqual([c["basis"] for c in cands], ["tracked operation"])   # the second listed operation

    def test_triage_lists_unnamed_activity_privately(self):
        """Decision 2: triage lists influence-worded articles naming no tracked operation into data/triage.jsonl,
        which no published file ever holds; check fails if one of its headlines leaks."""
        tmp = Path(tempfile.mkdtemp(prefix="undertow-triage-"))
        try:
            found = cli.triage(days=3650, root=tmp, getter=getter, pause=0)
            self.assertTrue(found)
            self.assertTrue((tmp / "data" / "triage.jsonl").exists())
            for c in found:
                self.assertEqual(text.named_operations(c["title"]), [])
                self.assertTrue(c["wording"])
            self.assertEqual(cli.triage(days=3650, root=tmp, getter=getter, pause=0), [])   # nothing twice
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        import os
        os.environ["GITHUB_ACTIONS"] = "true"
        try:
            n = len(FETCHED)
            self.assertEqual(cli.main(["triage"]), 1)             # refused in Actions: laptop only
            self.assertEqual(len(FETCHED), n)
        finally:
            del os.environ["GITHUB_ACTIONS"]

    def test_closing_lists_candidates_and_measures_closed_rows(self):
        """Tom, 16 Nov 2026 (UT-IND-3..4): open watch rows get the disclosures up to 12 months after their first report
        that share a country or name the tracked operation; closed rows give their lead; a bad closed_into is a
        problem; the command is laptop only."""
        rows = [
            {"id": "open-row", "first_report": {"date": "2026-01-10"}, "countries": ["MD"],
             "tracked_operation": "storm-1516"},
            {"id": "closed-row", "first_report": {"date": "2026-01-10"}, "countries": ["AM"],
             "closed_into": "meta:x"},
            {"id": "bad-row", "first_report": {"date": "2026-01-10"}, "closed_into": "meta:missing"},
        ]
        ds = [
            {"key": "meta:x", "publisher": "meta", "disclosed_at": "2026-04-10T00:00:00Z", "targets": ["AM"]},
            {"key": "google:a", "publisher": "google", "disclosed_at": "2026-03-01T00:00:00Z", "period": "2026-02",
             "targets": [], "countries_named": ["MD", "RU"]},
            {"key": "eeas:s", "publisher": "eeas", "disclosed_at": "2026-03-12T00:00:00Z", "targets": ["DE"],
             "named_operations": ["storm-1516"]},
            {"key": "openai:late", "publisher": "openai", "disclosed_at": "2027-06-01T00:00:00Z", "targets": ["MD"]},
            {"key": "openai:early", "publisher": "openai", "disclosed_at": "2025-12-01T00:00:00Z", "targets": ["MD"]},
        ]
        out = activity.closing(rows, ds)
        cands = out["open"][0]["candidates"]
        self.assertEqual([c["key"] for c in cands], ["eeas:s", "google:a"])     # tracked operation first; in window
        self.assertEqual(cands[0]["kind"], "naming")
        self.assertEqual(cands[1]["basis"], "shared named country (not a target)")
        self.assertEqual(cands[1]["period"], "2026-02")
        self.assertEqual(out["closed"], [{"row": "closed-row", "closed_into": "meta:x", "publisher": "meta",
                                          "kind": "takedown", "disclosed_at": "2026-04-10", "lead_days": 90}])
        self.assertEqual((out["closed_into_takedown"], out["median_lead_days"]), (1, 90))
        self.assertEqual(len(out["problems"]), 1)
        import os
        os.environ["GITHUB_ACTIONS"] = "true"
        try:
            self.assertEqual(cli.main(["closing"]), 1)            # refused in Actions: laptop only
        finally:
            del os.environ["GITHUB_ACTIONS"]

    def test_meta_counts_and_indicator_count(self):
        net = meta.parse_network((FIX / "meta_meta-h2-2026-iran-cib-based-network.md").read_text(encoding="utf-8"))
        self.assertEqual(net["counts"], {"facebook_accounts": 4, "instagram_accounts": 31})
        self.assertEqual(net["followers"], 79400)
        self.assertEqual(net["indicator_count"], 0)
        dop = meta.parse_network((FIX / "meta_meta-h2-2026-russia-cib-based-network-4.md").read_text(encoding="utf-8"))
        self.assertEqual(dop["indicators_by_type"], {"domain": 9, "social_media_account": 5})
        self.assertNotIn("garrygarr950", json.dumps(dop["indicators_by_type"]))

    def test_meta_readme_rows(self):
        rows = meta.parse_readme((FIX / "meta_readme.md").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 22)
        fr = next(r for r in rows if r["file"] == "meta-h2-2026-france-and-spain-cib-based-network.md")
        self.assertEqual(text.countries_in(fr["origin_text"]), ["FR", "ES"])

    def test_google_parse(self):
        pg = google.parse_page((FIX / "google_q3_2026.html").read_bytes(), 2026, 3)
        self.assertEqual(pg["updated"], "2026-10-30")
        self.assertEqual(len(pg["entries"]), 93)
        self.assertEqual(pg["unparsed"], [])
        first = pg["entries"][0]
        self.assertEqual((first["month"], first["assets"], first["origin"]), ("2026-07", {"youtube_channels": 560}, ["AZ"]))
        play = [e for e in pg["entries"] if e["verb"] == "banned"]
        self.assertEqual(play[0]["assets"], {"play_accounts": 1})
        recs = google.build_records([pg], {(2026, 3): "u"})
        self.assertTrue(all(r["summary"] is None for r in recs))           # no bulletin text republished
        self.assertTrue(all(d["phrase"] is None for r in recs for d in r["disarm"]))
        self.assertTrue(all("_rest" not in r for r in recs))

    def test_google_candidates(self):
        c = google.candidate_urls(date(2026, 11, 14), None)
        self.assertEqual([(y, q) for y, q, _ in c], [(2026, 1), (2026, 2), (2026, 3), (2026, 4)])

    def test_openai_classify_and_names(self):
        items = openai_rss.parse_rss((FIX / "openai_rss.xml").read_bytes())
        ops, roundups = openai_rss.build_records(items)
        names = {r["operation_name"] for r in ops}
        self.assertIn("Helgoland Bite", names)
        self.assertIn("STORM-2035", names)
        self.assertFalse(any("distillation" in r["title"] for r in ops))      # cyber, not influence
        self.assertTrue(any("October 2025" in r["title"] for r in roundups))
        dcb = next(r for r in ops if r["operation_name"] == "Data Center Bandwagon")
        self.assertEqual((dcb["origin"], dcb["origin_wording"]), (["CN"], "likely PRC-origin"))

    def test_tiktok_parse(self):
        rep = tiktok.parse_report(json.loads((FIX / "tiktok_report_9.json").read_text(encoding="utf-8")))
        self.assertEqual(rep["window"], ("2026-01-01", "2026-06-30"))
        self.assertEqual(len(rep["entries"]), 17)
        recs = tiktok.build_records([rep])
        hu = next(r for r in recs if r["key"] == "tiktok:r9:hu:107:37070")
        self.assertEqual((hu["removed_month"], hu["targets"]), ("2026-02", ["HU"]))
        ua = next(r for r in recs if r["key"] == "tiktok:r9:ua:45:47114")
        self.assertIn("[name withheld]", ua["summary"])
        self.assertNotIn("Orbán", json.dumps(recs, ensure_ascii=False))
        rep8 = tiktok.parse_report(json.loads((FIX / "tiktok_report_8.json").read_text(encoding="utf-8")))
        by = next(r for r in tiktok.build_records([rep8]) if r["origin"] == ["BY"])
        self.assertEqual(by["targets"], ["UA"])        # "Russian-speaking audience within Ukraine"

    def test_eeas_register_and_page(self):
        reg = eeas.load_registers()[0]
        self.assertEqual(len(reg["operations"]), 9)
        for o in reg["operations"]:
            self.assertTrue(o["page"])
            for b in o["behaviours"]:
                self.assertTrue(b["page"])
            if "aligned" in o["attribution_wording"] and not o.get("orgs"):
                self.assertEqual(o["origin"], [], o["id"])
        pg = eeas.check_page((FIX / "eeas_fimi_page.html").read_bytes(), reg)
        self.assertEqual(pg, {"listed": True, "newer_report": None})
        self.assertEqual(eeas.check_page(b"<a>Read the 5th EEAS Report on FIMI threats</a>", reg)["newer_report"], 5)


class Guards(unittest.TestCase):
    def test_listings_table_passes_its_check(self):
        from undertow import listings
        self.assertEqual(listings.check(known=stix.named_organisations()), [])
        # Organisations only: every listed name is a hand-kept organisation, and the three Russian ones are listed.
        self.assertEqual({e for e in listings._by_name() if listings._by_name()[e]},
                         {"Social Design Agency", "ANO Dialog", "Struktura"})

    def test_listings_check_refuses_bad_rows(self):
        from undertow import listings
        tmp = Path(tempfile.mkdtemp(prefix="undertow-listings-"))
        try:
            (tmp / "config").mkdir()
            good = {"list": "ofac-sdn", "programme": "RUSSIA-EO14024", "listed": "2024-03-20",
                    "notice": "https://ofac.treasury.gov/recent-actions/20240320", "notice_title": "t"}
            rows = [{"name": "Jane Example", "listings": [good]},
                    {"name": "Social Design Agency", "listings": [
                        dict(good, list="xx-list"), dict(good, listed="20 Mar 2024"),
                        dict(good, list="eu-fsf", notice="https://example.org/notice"),
                        dict(good, list="uk-sanctions", notice="https://www.gov.uk/government/news/x", individual="A B"),
                        dict(good), dict(good)]}]
            (tmp / "config" / "operations.json").write_text(
                json.dumps({"operations": [], "organisations": {"entries": rows}}), encoding="utf-8")
            errs = " | ".join(listings.check(tmp, known=frozenset({"Social Design Agency"})))
            for want in ("'Jane Example': not an organisation", "unknown list", "listed must be YYYY-MM-DD",
                         "not on the publisher's own site", "fields not allowed", "list given twice"):
                self.assertIn(want, errs)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_scrub_links_and_handles(self):
        t, n = text.scrub("see http://tiktok[.]com/@garrygarr950, rrn.com.tr, `x[.]com` and @someone_here")
        self.assertNotIn("garrygarr950", t)
        self.assertNotIn("rrn.com.tr", t)
        self.assertNotIn("@someone", t)
        self.assertGreaterEqual(n, 4)

    def test_scrub_names_keeps_orgs_and_places(self):
        t, n = text.scrub("linked Peter Magyar to George Soros; Moldovan President Maia Sandu; ANO Dialog and "
                          "Social Design Agency (SDA) in the United States and Sub-Saharan Africa")
        for name in ("Peter", "Magyar", "Soros", "Maia", "Sandu"):
            self.assertNotIn(name, t)
        for kept in ("ANO Dialog", "Social Design Agency", "United States", "Sub-Saharan Africa", "Moldovan President"):
            self.assertIn(kept, t)
        self.assertEqual(n, 3)

    def test_scrub_allow_keeps_operation_name(self):
        self.assertEqual(text.scrub("Operation “Helgoland Bite”: German", ["Helgoland Bite"])[0],
                         "Operation “Helgoland Bite”: German")

    def test_rules_name_real_v161_techniques(self):
        for r in disarm.rules()["rules"]:
            self.assertIsNotNone(disarm.name(r["technique"]), r["id"])
            re.compile(r["pattern"])
        self.assertEqual(len(disarm.bundle()["index"]), 391)
        self.assertEqual(disarm.bundle()["source_sha256"],
                         "f372a5b70e540022c5ffae41d1e1bd04fb79dd6b94aa0ea2fcce4712d600bf3f")

    def test_rules_each_accepted(self):
        self.assertTrue(disarm.reviewed())
        self.assertEqual({r["review"] for r in disarm.rules()["rules"]}, {"accepted"})
        self.assertEqual(sorted(r["id"] for r in disarm.rules()["rules"] if r.get("changed")), ["dr-04", "dr-10"])

    def test_confidence_rules(self):
        recs = [{"publisher": "meta", "origin": ["RU"], "named_operations": ["x"]},
                {"publisher": "openai", "origin": ["RU"], "named_operations": ["x"]},
                {"publisher": "eeas", "origin": ["RU"], "named_operations": ["x"]},
                {"publisher": "google", "origin": ["IR"], "named_operations": []},
                {"publisher": "tiktok", "origin": ["CN"], "named_operations": ["y"]},
                {"publisher": "eeas", "origin": ["RU"], "named_operations": ["y"]}]
        analysis.assess(recs)
        self.assertEqual([r["confidence"]["confidence"] for r in recs[:3]], ["moderate"] * 3)    # three lines, capped
        self.assertEqual(recs[3]["confidence"]["confidence"], "low")
        self.assertTrue(recs[4]["confidence"]["confidence_basis"]["factors"]["contradicted"])

    def test_doctrine_registers(self):
        self.assertEqual(registers.check(ROOT / "doctrine"), [])

    def test_item_ids_deterministic(self):
        self.assertEqual(feed.item_id("meta:x"), feed.item_id("meta:x"))
        self.assertEqual(stix.sid("campaign", "meta:x"), stix.sid("campaign", "meta:x"))
        self.assertTrue(feed.item_id("meta:x").startswith("UT-META-"))


class Retention(unittest.TestCase):
    """history/reports.jsonl keeps the reporter lanes' report records, append-only."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="undertow-ret-"))
        cls.snap = cli.collect(root=cls.tmp, getter=getter)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.hist = Path(tempfile.mkdtemp(prefix="undertow-hist-"))
        self.addCleanup(shutil.rmtree, self.hist, True)
        self.path = self.hist / "reports.jsonl"

    def test_every_report_record_archived_once(self):
        recs = [r for lane in cli.REPORTER_LANES for r in self.snap["records"][lane]]
        self.assertTrue(recs, "recorded replies give report records")
        n = archive.run(self.snap, self.hist, cli.REPORTER_LANES)
        self.assertEqual(n, len(recs))
        rows = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({r["id"] for r in rows}, {r["key"] for r in recs})
        self.assertEqual(len(rows), len(recs))

    def test_no_reporter_text_in_archive(self):
        archive.run(self.snap, self.hist, cli.REPORTER_LANES)
        for row in map(json.loads, self.path.read_text(encoding="utf-8").splitlines()):
            rec = row["record"]
            for f in ("title", "description", "author", "creator", "summary"):
                self.assertNotIn(f, rec)
            self.assertTrue(all(d.get("phrase") is None for d in rec.get("disarm") or []))

    def test_second_run_writes_nothing_and_change_appends(self):
        archive.run(self.snap, self.hist, cli.REPORTER_LANES)
        before = self.path.read_bytes()
        self.assertEqual(archive.run(self.snap, self.hist, cli.REPORTER_LANES), 0)
        self.assertEqual(self.path.read_bytes(), before)
        lane = next(l for l in cli.REPORTER_LANES if self.snap["records"][l])
        snap = json.loads(json.dumps(self.snap))
        snap["records"][lane][0]["countries_named"] = ["XX"]
        snap["generated_at"] = "2026-11-19T00:00:00Z"
        self.assertEqual(archive.run(snap, self.hist, cli.REPORTER_LANES), 1)
        self.assertTrue(self.path.read_bytes().startswith(before))

    def test_report_gone_from_feed_stays_in_archive(self):
        archive.run(self.snap, self.hist, cli.REPORTER_LANES)
        snap = json.loads(json.dumps(self.snap))
        for lane in cli.REPORTER_LANES:
            snap["records"][lane] = []
        before = self.path.read_bytes()
        self.assertEqual(archive.run(snap, self.hist, cli.REPORTER_LANES), 0)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

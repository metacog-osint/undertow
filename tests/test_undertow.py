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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("undertow_cli", ROOT / "tools" / "undertow.py")
cli = importlib.util.module_from_spec(_spec)   # tools/undertow.py (its name clashes with the package)
_spec.loader.exec_module(cli)

from undertow import analysis, disarm, eeas, feed, google, meta, openai_rss, stix, text, tiktok  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402
from tic_doctrine.lint import check_header  # noqa: E402

MANIFEST = json.loads((FIX / "MANIFEST.json").read_text(encoding="utf-8"))
BY_URL = {v["url"]: FIX / name for name, v in MANIFEST["files"].items()}
NAMES_QUOTED = ["Peter Magyar", "George Soros", "Viktor Orbán", "Orbán", "Magyar", "Soros"]
FETCHED: list[str] = []


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
                self.assertTrue(u.startswith(cli.ALLOWED_URL_PREFIXES), f"{name}: {u}")

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
        self.assertEqual(pubs, {"meta", "openai", "eeas"})
        self.assertTrue(all(p["confidence"] == "moderate" for p in dop))
        eeas_dop = next(p for p in dop if p["operation"]["publisher"] == "eeas")
        self.assertEqual(eeas_dop["us_person_data"], "organizations")
        self.assertIn("Social Design Agency", eeas_dop["operation"]["sponsor"])

    def test_events_dates_only(self):
        evs = self.events["events"]
        self.assertTrue(evs)
        for e in evs:
            self.assertRegex(e["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertEqual(e["kind"], "data_release")
            self.assertNotIn("probability", json.dumps(e))
            self.assertIn("not a published date", e["title"])


class Lanes(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

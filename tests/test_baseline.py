"""Baseline per layer (ideas#16, 19 Nov 2026): offline, from the committed TAG register and made-up records
shaped like the lanes' own (no page is fetched)."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from undertow import baseline  # noqa: E402


def rec(pub, did, when, origin=(), ops=(), disarm=(), lane=None, activity=None, key=None):
    return {"key": key or f"{pub}:{did}:{when}:{len(origin)}:{'-'.join(ops)}", "lane": lane or pub, "publisher": pub,
            "disclosure": {"id": did}, "disclosed_at": when, "origin": list(origin), "named_operations": list(ops),
            "disarm": [{"id": t} for t in disarm], "activity": activity}


class RegisterTest(unittest.TestCase):
    def test_committed_register_is_counts_only(self):
        reg = baseline.load_register()
        self.assertEqual(baseline.check_register(reg), [])
        self.assertEqual([(p["year"], p["quarter"]) for p in reg["pages"]], baseline.TAG_QUARTERS)
        for pg in reg["pages"]:
            self.assertTrue(pg["entries"])
            for e in pg["entries"]:
                self.assertLessEqual(set(e), baseline.ENTRY_FIELDS)
        # Google's Q4 2024 page prints "last updated on February 19, 2024"; the register takes dateModified
        q4 = next(p for p in reg["pages"] if (p["year"], p["quarter"]) == (2024, 4))
        self.assertEqual(q4["updated"], "2025-02-19")
        self.assertTrue(q4["updated_note"])

    def test_check_refuses_text(self):
        reg = {"pages": [{"year": 2024, "quarter": 1, "url": baseline.TAG_URL.format(q=1, y=2024), "updated": None,
                          "updated_note": None, "sha256": "x", "unparsed": 0,
                          "entries": [{"key": "k", "month": "2024-01", "origin": ["Russia"], "assets": {"x": "12"},
                                       "ongoing": False, "stance": "supportive of ..."}]}]}
        errs = " ".join(baseline.check_register(reg))
        self.assertIn("unexpected fields", errs)
        self.assertIn("ISO country codes", errs)
        self.assertIn("counts", errs)
        reg["pages"][0]["url"] = "https://example.org/x"
        self.assertIn("not a TAG bulletin page", " ".join(baseline.check_register(reg)))

    def test_page_entry_date_fallback(self):
        parsed = {"year": 2024, "quarter": 4, "updated": "2024-02-19", "unparsed": [],
                  "entries": [{"key": "google:2024-q4:2024-10:01", "month": "2024-10", "origin": ["RU"],
                               "assets": {"youtube_channels": 3}, "ongoing": True, "_rest": "never kept"}]}
        body = b'<script>{"dateModified": "2025-02-19T20:30:02+00:00"}</script>'
        row = baseline.page_entry(parsed, body, "abc")
        self.assertEqual(row["updated"], "2025-02-19")
        self.assertNotIn("_rest", row["entries"][0])


class DismantledTest(unittest.TestCase):
    def test_grain_trailing_and_ready(self):
        reg = {"pages": [{"year": 2024, "quarter": q, "entries": [{"origin": ["RU"]}] * q} for q in (1, 2, 3, 4)]
               + [{"year": 2025, "quarter": q, "entries": [{"origin": []}] * 2} for q in (1, 2, 3, 4)]
               + [{"year": 2026, "quarter": 1, "entries": [{"origin": ["CN"]}] * 50}]}
        records = [rec("google", "google:2026-q1", "2026-03-31T00:00:00Z", ["IR"], key=f"g{i}") for i in range(3)]
        records += [rec("meta", "meta:h2-2025", "2026-05-19T00:00:00Z", ["RU"]),
                    rec("tiktok", "tiktok:report-8", "2026-03-30T00:00:00Z", ["UA"]),
                    rec("openai", "openai:x", "2024-05-01T00:00:00Z", []),
                    rec("dfrlab", "dfrlab:x", "2026-01-01T00:00:00Z", ["RU"])]
        d = baseline.dismantled(records, reg)
        g = d["google"]["periods"]
        self.assertEqual([p["key"] for p in g][-1], "2026-Q1")
        last = g[-1]
        self.assertEqual(last["items"], 3)              # the lane's reading wins over the register's 50
        self.assertEqual(last["origin"], {"IR": 3})
        self.assertEqual(last["trailing"], {"periods": 8, "min": 1, "max": 4, "mean": 2.2})
        self.assertTrue(last["ready"])
        self.assertFalse(g[-2]["ready"])
        self.assertEqual(g[4]["origin"], {"none": 2})
        self.assertEqual(d["meta"]["periods"][0]["period"], "H2 2025 report")
        self.assertEqual(d["tiktok"]["periods"][0]["period"], "report 8")
        self.assertEqual(d["openai"]["periods"][0]["key"], "2024-Q2")
        self.assertNotIn("dfrlab", d)                   # reporters are never a takedown baseline


class OngoingAndMixTest(unittest.TestCase):
    def test_ongoing_six_month_window_never_ended(self):
        records = [rec("meta", "meta:h1-2026", "2026-06-01T00:00:00Z", ops=["op-a"]),
                   rec("eeas", "eeas:fimi-4", "2026-03-12T00:00:00Z", ops=["op-a", "op-b"]),
                   rec("dfrlab", "-", "2025-01-01T00:00:00Z", ops=["op-b"], lane="dfrlab",
                       activity={"reporter": "dfrlab", "reports": 4, "last_report": "2025-01-10T00:00:00Z"})]
        rows = {o["operation"]: o for o in baseline.ongoing(records, date(2026, 11, 19))}
        self.assertEqual(rows["op-a"]["publishers_acting"], ["eeas", "meta"])
        self.assertEqual(rows["op-a"]["state"], "active")      # 5 months since 1 Jun
        self.assertEqual(rows["op-b"]["reports"], 4)
        self.assertEqual(rows["op-b"]["state"], "quiet")       # 8 months since 12 Mar
        self.assertEqual({o["state"] for o in rows.values()} - {"active", "quiet"}, set())

    def test_technique_mix_per_publisher(self):
        records = [rec("openai", "o", "2025-02-01T00:00:00Z", disarm=["T0085.001"], key="o1"),
                   rec("openai", "o", "2025-03-01T00:00:00Z", key="o2"),
                   rec("google", "google:2026-q1", "2026-03-31T00:00:00Z", key="g1")]
        mix = baseline.technique_mix(records)
        o = next(m for m in mix if m["publisher"] == "openai")
        self.assertEqual((o["half"], o["items"]), ("2025-H1", 2))
        self.assertEqual(o["techniques"], {"T0085.001": {"items": 1, "share": 0.5}})
        self.assertEqual(next(m for m in mix if m["publisher"] == "google")["techniques"], {})

    def test_build_states_the_rule_and_no_warning(self):
        out = baseline.build([rec("openai", "o", "2025-02-01T00:00:00Z")], date(2026, 11, 19))
        txt = json.dumps(out)
        for word in ('"tier"', "warning\""):
            self.assertNotIn(word, txt)
        self.assertEqual(out["rule"], baseline.RULE)
        self.assertIn("never a reading of activity level", out["rule"])
        self.assertEqual(len(out["google_tag_register"]), 8)


def google_recs(year, q, n, updated):
    recs = [dict(rec("google", f"google:{year}-q{q}", f"{updated}T00:00:00Z", ["IR"], key=f"google:{year}-{q}:{i}"),
                 url="https://blog.google/x/", title="t") for i in range(n)]
    for r in recs:
        r["disclosure"]["title"] = f"Google bulletin Q{q} {year}"
    return recs


class DismantledAnomalyTest(unittest.TestCase):
    """A period outside its publisher's trailing 8-period range gets one item; it is tier anomaly (unusual
    enforcement) only while the publisher's flag rate is within the contract's 5%, otherwise routine. The takedown
    items stay routine, and a period inside the range (or without 8 earlier periods) gets no item."""

    TODAY = date(2026, 11, 27)

    def setUp(self):
        self.reg = {"pages": [{"year": 2024, "quarter": q, "entries": [{"origin": ["RU"]}] * (q + 1)}
                              for q in (1, 2, 3, 4)]
                    + [{"year": 2025, "quarter": q, "entries": [{"origin": []}] * 3} for q in (1, 2, 3, 4)]}

    def build(self, records, reg=None, today=None):
        from undertow import feed
        base = {"dismantled": baseline.dismantled(records, self.reg if reg is None else reg, today or self.TODAY)}
        return base["dismantled"]["google"], feed.enforcement_features(base, records, "2026-11-27T00:00:00Z")

    def flagged(self, n):
        layer, feats = self.build(google_recs(2026, 1, n, "2026-03-31"))
        return layer["periods"][-1], feats

    def test_cap_is_the_contracts(self):
        from tic_doctrine import contract
        self.assertEqual(baseline.FLAG_RATE_CAP, contract.FLAG_RATE_CAP)

    def test_above_range_over_the_cap_is_routine(self):
        last, feats = self.flagged(9)                    # trailing range 2 to 5; 1 of 1 rated periods outside
        self.assertEqual((last["outside"], last["trailing"]["min"], last["trailing"]["max"]), ("above", 2, 5))
        self.assertEqual(len(feats), 1)
        p = feats[0]["properties"]
        self.assertEqual((p["tier"], p["kind"], feats[0]["geometry"]), ("routine", "observation", None))
        self.assertTrue(p["id"].startswith("UT-ENFORCEMENT-"))
        self.assertIn("Outside Google's own record, not rated unusual", p["summary"])
        self.assertIn("1 of Google's 1 rated periods outside their range (100%)", p["summary"])
        self.assertNotIn("Unusual enforcement", p["summary"])
        self.assertIn("not how much influence activity there was", p["summary"])
        self.assertEqual(p["baseline_ref"]["flag_rate"], 1.0)
        self.assertEqual(p["data_as_of"], "2026-03-31T00:00:00Z")

    def test_the_live_google_series_is_routine(self):
        """Google's counts as published on 27 Nov 2026: 2024-25 from the TAG register, 2026 from the lane. Q1 (91
        against 27 to 58) and Q2 (158 against 28 to 91) are outside their range, 2 of 3 rated periods (67%), so
        neither is an anomaly, and the kit's linter has no flag-rate note on them."""
        counts = [27, 28, 43, 36, 41, 28, 58, 52]
        reg = {"pages": [{"year": 2024 + i // 4, "quarter": i % 4 + 1, "updated": None,
                          "entries": [{"origin": ["RU"]}] * c} for i, c in enumerate(counts)]}
        recs = (google_recs(2026, 1, 91, "2026-03-31") + google_recs(2026, 2, 158, "2026-06-30")
                + google_recs(2026, 3, 93, "2026-10-30"))
        layer, feats = self.build(recs, reg)
        self.assertEqual((layer["rated"], layer["outside"], layer["flag_rate"], layer["rated_unusual"]),
                         (3, 2, 0.667, False))
        self.assertEqual([f["properties"]["baseline"]["period"] for f in feats], ["2026-Q1", "2026-Q2"])
        self.assertEqual({f["properties"]["tier"] for f in feats}, {"routine"})
        from tic_doctrine import contract
        for f in feats:
            notes = [m for _, _, m in contract.check(f, set()) if "flag_rate" in m or "anomaly" in m]
            self.assertEqual(notes, [])

    def test_anomaly_within_the_cap(self):
        """With 40 quarters of 3 and one of 9, the rule marks 1 of 33 rated periods (3%): tier anomaly."""
        reg = {"pages": [{"year": 2016 + i // 4, "quarter": i % 4 + 1, "updated": None,
                          "entries": [{"origin": []}] * 3} for i in range(40)]}
        layer, feats = self.build(google_recs(2026, 1, 9, "2026-03-31"), reg)
        self.assertEqual((layer["rated"], layer["outside"], layer["rated_unusual"]), (33, 1, True))
        p = feats[0]["properties"]
        self.assertEqual(p["tier"], "anomaly")
        self.assertIn("Unusual enforcement against Google's own record", p["summary"])
        from tic_doctrine import contract
        errs = [m for _, sev, m in contract.check(feats[0], set()) if sev == "error"]
        self.assertFalse([m for m in errs if "anomaly" in m or "baseline_ref" in m], errs)
        self.assertEqual([m for _, _, m in contract.check(feats[0], set()) if "flag_rate" in m], [])

    def test_inside_range_and_below(self):
        last, feats = self.flagged(4)
        self.assertIsNone(last["outside"])
        self.assertEqual(feats, [])
        last, feats = self.flagged(1)
        self.assertEqual(last["outside"], "below")
        self.assertTrue(last["closed"])
        self.assertIn("fewer than in any of its previous 8 periods", feats[0]["properties"]["title"])

    def test_a_period_still_being_filled_is_never_below(self):
        """Google's Q4 2026 bulletin read on 27 Nov with 1 entry so far: the quarter has not ended, so it is not
        rated below its range; read again in January from a page updated on 31 Dec, it is."""
        reg = {"pages": self.reg["pages"] + [{"year": 2026, "quarter": q, "entries": [{"origin": []}] * 3}
                                            for q in (1, 2, 3)]}
        layer, feats = self.build(google_recs(2026, 4, 1, "2026-11-20"), reg)
        last = layer["periods"][-1]
        self.assertEqual((last["key"], last["ready"], last["closed"], last["outside"]), ("2026-Q4", True, False, None))
        self.assertEqual(feats, [])
        # The quarter is over but the page was last updated inside it: still open.
        layer, _ = self.build(google_recs(2026, 4, 1, "2026-12-15"), reg, date(2027, 1, 10))
        self.assertEqual((layer["periods"][-1]["closed"], layer["periods"][-1]["outside"]), (False, None))
        layer, feats = self.build(google_recs(2026, 4, 1, "2026-12-31"), reg, date(2027, 1, 10))
        self.assertEqual((layer["periods"][-1]["closed"], layer["periods"][-1]["outside"]), (True, "below"))
        self.assertEqual(len(feats), 1)
        # Above is rated on an open period: a count only grows.
        layer, feats = self.build(google_recs(2026, 4, 40, "2026-11-20"), reg)
        self.assertEqual((layer["periods"][-1]["closed"], layer["periods"][-1]["outside"]), (False, "above"))

    def test_openai_current_quarter_and_report_grains(self):
        posts = [rec("openai", "o", f"{y}-{m:02d}-15T00:00:00Z", key=f"o{y}{m}{i}")
                 for y in (2024, 2025, 2026) for m in (2, 5, 8, 11) for i in range(3) if (y, m) < (2026, 11)]
        now = [rec("openai", "o", "2026-10-15T00:00:00Z", key="o-now")]
        d = baseline.dismantled(posts + now, {"pages": []}, date(2026, 11, 27))["openai"]["periods"]
        self.assertEqual((d[-1]["key"], d[-1]["ready"], d[-1]["closed"], d[-1]["outside"]),
                         ("2026-Q4", True, False, None))
        d = baseline.dismantled(posts + now, {"pages": []}, date(2027, 1, 2))["openai"]["periods"]
        self.assertEqual((d[-1]["closed"], d[-1]["outside"]), (True, "below"))
        reports = [rec("tiktok", f"tiktok:report-{n}", "2026-01-01T00:00:00Z", key=f"t{n}{i}")
                   for n in range(1, 10) for i in range(5 if n < 9 else 1)]
        t = baseline.dismantled(reports, {"pages": []}, date(2030, 1, 1))["tiktok"]["periods"]
        self.assertEqual((t[-1]["closed"], t[-1]["outside"]), (False, None))   # the latest report: no later one yet
        self.assertTrue(all(x["closed"] for x in t[:-1]))

    def test_openai_quarter_with_no_posts_counts_zero(self):
        """OpenAI's feed is read whole, so a quarter with no influence post is a count of 0 (the live series had
        none in 2025-Q3): every quarter from the first post to the last one ended before the feed was read. Google,
        Meta and TikTok periods exist only where a bulletin or report was published."""
        counts = {"2024-Q2": 5, "2024-Q3": 1, "2024-Q4": 3, "2025-Q1": 3, "2025-Q2": 5, "2025-Q4": 3,
                  "2026-Q1": 3, "2026-Q2": 2, "2026-Q3": 1, "2026-Q4": 1}
        mon = {"1": 2, "2": 5, "3": 8, "4": 11}
        posts = [rec("openai", "o", f"{k[:4]}-{mon[k[-1]]:02d}-15T00:00:00Z", key=f"o{k}{i}")
                 for k, n in counts.items() for i in range(n)]
        others = (google_recs(2026, 1, 3, "2026-03-31") + google_recs(2026, 3, 3, "2026-09-30")
                  + [rec("meta", "meta:h1-2025", "2025-08-01T00:00:00Z", key="m1"),
                     rec("meta", "meta:q1-2026", "2026-05-01T00:00:00Z", key="m2"),
                     rec("tiktok", "tiktok:report-6", "2025-03-01T00:00:00Z", key="t6"),
                     rec("tiktok", "tiktok:report-8", "2026-03-01T00:00:00Z", key="t8")])
        d = baseline.dismantled(posts + others, {"pages": []}, date(2026, 11, 27))
        o = {x["key"]: x for x in d["openai"]["periods"]}
        self.assertEqual(list(o), ["2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4",
                                   "2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"])
        z = o["2025-Q3"]
        self.assertEqual((z["items"], z["origin"], z["source"], z["closed"]), (0, {}, baseline.NO_POSTS, True))
        self.assertEqual({x["source"] for k, x in o.items() if k != "2025-Q3"}, {"lane"})
        self.assertEqual(o["2026-Q3"]["trailing"], {"periods": 8, "min": 0, "max": 5, "mean": 2.5})
        self.assertEqual((d["openai"]["rated"], d["openai"]["outside"]), (2, 0))
        self.assertEqual([x["key"] for x in d["google"]["periods"]], ["2026-Q1", "2026-Q3"])
        self.assertEqual([x["key"] for x in d["meta"]["periods"]], ["2025-H1", "2026-Q1"])
        self.assertEqual([x["key"] for x in d["tiktok"]["periods"]], ["006", "008"])
        for pub in ("google", "meta", "tiktok"):
            self.assertNotIn(baseline.NO_POSTS, {x["source"] for x in d[pub]["periods"]})
        # Quarters after the last post fill only up to the last one ended before the feed was read: a lane
        # showing its last good copy (read 15 Jul 2026) never turns quarters it has not read into zeros.
        early = [p for p in posts if p["disclosed_at"] < "2026-04-01"]
        keys = [x["key"] for x in baseline.dismantled(early, {"pages": []}, date(2026, 11, 27),
                                                      {"openai": date(2026, 7, 15)})["openai"]["periods"]]
        self.assertEqual(keys[-2:], ["2026-Q1", "2026-Q2"])
        self.assertEqual(baseline.dismantled([], {"pages": []}, date(2026, 11, 27))["openai"]["periods"], [])

    def test_a_quarter_with_no_posts_can_be_below(self):
        """Eight quarters of 3 posts, then one with none: rated below, and its item cites the feed that was read."""
        posts = [rec("openai", "o", f"{y}-{m:02d}-15T00:00:00Z", key=f"o{y}{m}{i}")
                 for y in (2024, 2025) for m in (2, 5, 8, 11) for i in range(3)]
        posts.append(dict(rec("openai", "o", "2026-05-15T00:00:00Z", key="o-q2"), url="https://openai.com/index/x/"))
        for r in posts:
            r["disclosure"]["title"] = "t"
            r.setdefault("url", "https://openai.com/index/x/")
        from undertow import feed
        base = {"dismantled": baseline.dismantled(posts, {"pages": []}, self.TODAY)}
        q1 = next(x for x in base["dismantled"]["openai"]["periods"] if x["key"] == "2026-Q1")
        self.assertEqual((q1["items"], q1["source"], q1["outside"]), (0, baseline.NO_POSTS, "below"))
        feats = feed.enforcement_features(base, posts, "2026-11-27T00:00:00Z")
        self.assertEqual(len(feats), 1)
        p = feats[0]["properties"]
        self.assertEqual(p["baseline"]["period"], "2026-Q1")
        self.assertEqual(p["tier"], "routine")
        self.assertIn("0 takedowns, fewer than in any of its previous 8 periods", p["title"])
        self.assertEqual(p["sources"][0]["url"], "https://openai.com/news/rss.xml")
        from tic_doctrine import contract
        self.assertEqual([m for _, sev, m in contract.check(feats[0], set()) if sev == "error"], [])

    def test_not_ready_is_never_flagged(self):
        d = baseline.dismantled([rec("meta", "meta:h2-2025", "2026-05-19T00:00:00Z", ["RU"])] * 3, {"pages": []})
        self.assertEqual([x["outside"] for x in d["meta"]["periods"]], [None])

if __name__ == "__main__":
    unittest.main()

"""Baseline per layer (ideas#16, Tom 19 Nov 2026): offline, from the committed TAG register and made-up records
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

    def test_build_has_no_rating(self):
        out = baseline.build([rec("openai", "o", "2025-02-01T00:00:00Z")], date(2026, 11, 19))
        txt = json.dumps(out)
        for word in ('"tier"', "anomaly\"", "warning\""):
            self.assertNotIn(word, txt)
        self.assertEqual(len(out["google_tag_register"]), 8)


if __name__ == "__main__":
    unittest.main()

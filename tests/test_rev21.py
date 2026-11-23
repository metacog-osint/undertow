"""Feed contract revision 2.1: subject ids, event times, header and health."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from tic_doctrine import __version__ as KIT, contract  # noqa: E402
from undertow import eventtime, feed  # noqa: E402

GENERATED = "2026-11-23T12:00:00Z"


def record(**over):
    r = {"key": "google:2026-q3:2026-07:01", "publisher": "google", "title": "A campaign", "url": "https://blog.google/x",
         "disclosure": {"id": "google:2026-q3", "title": "Bulletin", "url": "https://blog.google/x"},
         "disclosed_at": "2026-10-30T00:00:00Z", "disclosed_precision": "day", "period": "2026-07"}
    r.update(over)
    return r


class EventTimes(unittest.TestCase):
    def test_month(self):
        self.assertEqual(eventtime.fields(record()), {"event_start": "2026-07-01T00:00:00Z",
                         "event_end": "2026-07-01T00:00:00Z", "event_time_precision": "month"})

    def test_half_year_held_at_the_report(self):
        got = eventtime.fields(record(publisher="meta", period="H2 2026", disclosed_at="2026-08-26T10:00:00Z"))
        self.assertEqual((got["event_start"], got["event_end"]), ("2026-07-01T00:00:00Z", "2026-08-01T00:00:00Z"))

    def test_year_and_range(self):
        got = eventtime.fields(record(publisher="eeas", period="2025", disclosed_at="2026-03-12T00:00:00Z"))
        self.assertEqual((got["event_start"], got["event_end"]), ("2025-01-01T00:00:00Z", "2025-12-01T00:00:00Z"))
        got = eventtime.fields(record(publisher="tiktok", period="2026-01 to 2026-06"))
        self.assertEqual((got["event_start"], got["event_end"]), ("2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z"))

    def test_openai_post_month_is_not_an_activity_period(self):
        got = eventtime.fields(record(publisher="openai", period="2024-05", disclosed_at="2024-05-01T00:00:00Z",
                                      disclosed_precision="month"))
        self.assertEqual(got, {"event_start": "2024-05-01T00:00:00Z", "event_time_precision": "month"})

    def test_reporter_has_no_end(self):
        got = eventtime.fields(record(publisher="dfrlab", activity={"first_report": "2024-07-30T12:58:03Z",
                                                                    "last_report": "2026-04-24T22:47:41Z"}))
        self.assertEqual(got, {"event_start": "2024-07-30T12:58:03Z"})

    def test_watch_period_mixed_precision_reads_as_months(self):
        got = eventtime.fields(record(publisher="watch", activity={"first_report": "2026-10-12",
                               "activity_period": {"from": "2026-01-15", "to": "2026-06"}}))
        self.assertEqual(got, {"event_start": "2026-01-01T00:00:00Z", "event_end": "2026-06-01T00:00:00Z",
                               "event_time_precision": "month"})

    def test_unread_period_falls_back_to_the_disclosure(self):
        got = eventtime.fields(record(period="sometime"))
        self.assertEqual(got, {"event_start": "2026-10-30T00:00:00Z", "event_time_precision": "day"})


class Feed(unittest.TestCase):
    def test_item_and_header(self):
        doc = feed.build_feed([record()], GENERATED, feed.health({}, [], GENERATED))
        self.assertEqual((doc["contract_rev"], doc["kit"]), ("2.1", KIT))
        p = doc["features"][0]["properties"]
        self.assertEqual(p["subject_id"], p["id"])
        self.assertEqual(p["id"], feed.item_id("google:2026-q3:2026-07:01"))
        self.assertEqual(p["event_start"], "2026-07-01T00:00:00Z")
        self.assertEqual(contract.check_health(doc["health"], strict=True), [])

    def test_lane_not_run_is_never(self):
        h = feed.health({}, [])
        self.assertEqual({v["state"] for v in h.values()}, {"never"})


if __name__ == "__main__":
    unittest.main()

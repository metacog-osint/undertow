"""Cross-publisher reading: our confidence in each item's origin, and the expected next disclosures.

Three questions are kept apart (doctrine/confidence-mapping.md):
1. Did the takedown happen? The publisher reports its own enforcement action: source grade A2, status_class reported.
2. Where were the operators? The publisher's judgment, kept verbatim with the publisher's stated level.
3. Who directed it? Recorded only when a publisher names an operator. Origin is never read as sponsorship.

Our confidence (tic-confidence-1.0) is about question 2 and counts independent publishers that name the same
operation with the same origin. One publisher: Low. Two: Moderate. High would need three, no contradiction, an
alternative examined and a scored Verdict record, and origin is easy to fake (false flags), which caps it at
Moderate, so there is no High in this slice. An item with no origin stated gets no confidence level.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import confidence  # noqa: E402

GRADE = "A2"
PUBLISHER_GROUP = {"meta": "meta", "google": "google", "openai": "openai", "tiktok": "tiktok", "eeas": "eu-eeas"}


def corroboration(records: list[dict]) -> dict[str, dict]:
    """For each named operation: the publishers that name it and the origins they give."""
    out: dict[str, dict] = {}
    for r in records:
        for op in r.get("named_operations") or []:
            slot = out.setdefault(op, {"publishers": set(), "origins": {}})
            slot["publishers"].add(PUBLISHER_GROUP[r["publisher"]])
            for cc in r.get("origin") or []:
                slot["origins"].setdefault(cc, set()).add(PUBLISHER_GROUP[r["publisher"]])
    return out


def assess(records: list[dict]) -> None:
    """Set r['confidence'] (contract fields) and r['corroborated_by'] in place."""
    corr = corroboration(records)
    for r in records:
        origin = r.get("origin") or []
        mine = PUBLISHER_GROUP[r["publisher"]]
        lines, contradicted, others = {mine}, False, set()
        for op in r.get("named_operations") or []:
            c = corr.get(op) or {}
            for cc in origin:
                lines |= c.get("origins", {}).get(cc, set())
            for cc, pubs in (c.get("origins") or {}).items():
                if origin and cc not in origin and pubs - {mine}:
                    contradicted = True
            others |= (c.get("publishers") or set()) - {mine}
        r["corroborated_by"] = sorted(others)
        if not origin:
            r["confidence"] = None
            continue
        f = confidence.fields(confidence.Evidence(independent_lines=len(lines), contradicted=contradicted,
                                                  grades=[GRADE], ease_of_faking="high", method_scored=False))
        f["confidence_basis"]["scope"] = "origin: where the operators were, as the publishers report it (not who directed it)"
        f["confidence_basis"]["lines"] = sorted(lines)
        r["confidence"] = f


def _d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def expected_disclosures(records: list[dict], google_quarters: list[tuple[int, int]], tiktok_reports: list[dict],
                         eeas_published: str | None, today: date) -> list[dict]:
    """Dates only, no probabilities: when each publisher's next disclosure would fall on its past pattern."""
    ev = []
    if google_quarters:
        y, q = max(google_quarters)
        ny, nq = (y + 1, 1) if q == 4 else (y, q + 1)
        end = date(ny, nq * 3, 1) + timedelta(days=31)
        end = end.replace(day=1) - timedelta(days=1)          # last day of the quarter
        when = end + timedelta(days=31)
        ev.append({"id": f"undertow-google-iob-q{nq}-{ny}", "date": when.isoformat(), "kind": "data_release",
                   "countries": [], "ref": f"google-iob-q{nq}-{ny}",
                   "title": f"Google Influence Operations Bulletin Q{nq} {ny} expected about this date "
                            "(past bulletins appeared 0 to 31 days after the quarter ended; not a published date)",
                   "source": {"publisher": "Google (estimated by Undertow)",
                              "url": "https://blog.google/security/rss/"}})
    meta_dates = sorted(d for d in (_d(r.get("disclosed_at")) for r in records if r["publisher"] == "meta") if d)
    if meta_dates:
        when = meta_dates[-1] + timedelta(days=182)
        ev.append({"id": f"undertow-meta-atr-{when.isoformat()[:7]}", "date": when.isoformat(), "kind": "data_release",
                   "countries": [], "ref": "meta-adversarial-threat-report",
                   "title": "Meta's next Adversarial Threat Report expected about this date (twice a year; the last "
                            f"indicator files were added {meta_dates[-1].isoformat()}; not a published date)",
                   "source": {"publisher": "Meta (estimated by Undertow)",
                              "url": "https://github.com/meta/threat-research"}})
    pubs = sorted(d for d in (_d(r.get("published")) for r in tiktok_reports) if d)
    if pubs:
        when = pubs[-1] + timedelta(days=182)
        n = max(r["id"] for r in tiktok_reports) + 1
        ev.append({"id": f"undertow-code-report-{n}", "date": when.isoformat(), "kind": "data_release", "countries": [],
                   "ref": f"disinfocode-report-{n}",
                   "title": f"Code of Conduct on Disinformation report {n} (TikTok and other signatories) expected about "
                            "this date (semiannual; not a published date)",
                   "source": {"publisher": "EU Code of Conduct Transparency Centre (estimated by Undertow)",
                              "url": "https://disinfocode.eu/reports-archive/"}})
    e = _d(eeas_published)
    if e:
        when = e + timedelta(days=365)
        ev.append({"id": f"undertow-eeas-fimi-{when.year}", "date": when.isoformat(), "kind": "data_release",
                   "countries": [], "ref": "eeas-fimi-5",
                   "title": "5th EEAS report on FIMI threats expected about this date (annual, March; not a published date)",
                   "source": {"publisher": "EEAS (estimated by Undertow)",
                              "url": "https://www.eeas.europa.eu/eeas/information-integrity-and-countering-foreign-information-manipulation-interference-fimi_en"}})
    return sorted([x for x in ev if x["date"] >= today.isoformat()], key=lambda x: (x["date"], x["id"]))

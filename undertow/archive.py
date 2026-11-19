"""Retention archive: per-report records of the reporter lanes, append-only, under history/.

    history/reports.jsonl   one line per reporter report record (operation named, date, link, countries named,
                            platforms, DISARM techniques), when the report is new and again if its content changes

Report records are held in data/snapshot.json, which lives in the Actions cache and the last deployed site only.
This keeps them in git. They hold facts only (the reporters' titles, descriptions and authors are never kept, see
reporters.py), so nothing here is text a reporter owns. Lines are only appended; an unchanged report writes
nothing, so a repeated run adds no lines. Nothing in the live feed or site changes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                          ).hexdigest()[:16]


def last_hashes(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["id"]] = row["hash"]
    return out


def append_reports(path: Path, records: list[dict], seen_at: str) -> int:
    """Append report records (keyed by record key) that are new or changed. Returns the lines written."""
    seen = last_hashes(path)
    lines = []
    for r in sorted(records, key=lambda r: r["key"]):
        body = {k: v for k, v in r.items() if not k.startswith("_")}
        h = digest(body)
        if seen.get(r["key"]) == h:
            continue
        seen[r["key"]] = h
        lines.append(json.dumps({"id": r["key"], "seen_at": seen_at, "hash": h, "record": body},
                                sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    return len(lines)


def run(snap: dict, hist_dir: Path, lanes: list[str]) -> int:
    recs = [r for lane in lanes for r in (snap.get("records") or {}).get(lane, [])]
    return append_reports(hist_dir / "reports.jsonl", recs, snap["generated_at"])

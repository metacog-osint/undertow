"""Private archive (19 Nov 2026, retention rule): update.yml sends the raw replies to the PRIVATE repo
metacog-osint/tic-archive after the deploy (tools/tic_archive.py). Live views are untouched: no program code changed."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "tools"))   # after ROOT: tools/<program>.py must not shadow the package
import tic_archive as ta  # noqa: E402

NOW = datetime(2026, 11, 19, 6, 0, tzinfo=timezone.utc)
PROGRAM = "undertow"
WF = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
_START = WF.index("- name: Private archive (raw replies, to tic-archive)")
_NEXT = re.search(r"\n      [-#]", WF[_START + 1:])     # the raw step only, not the lanes after it
STEP = WF[_START:_START + 1 + _NEXT.start()] if _NEXT else WF[_START:]


def put(files: dict, **kw):
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw"
        for rel, text in files.items():
            (raw / rel).parent.mkdir(parents=True, exist_ok=True)
            (raw / rel).write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        store = ta.DirStore(Path(td) / "store")
        arch = ta.Archive(store, PROGRAM, "raw")
        doc = arch.put(raw, now=NOW, **kw)["doc"]
        arch.restore(Path(td) / "out")
        out = {p.relative_to(Path(td) / "out").as_posix(): p.read_bytes()
               for p in (Path(td) / "out").rglob("*") if p.is_file()}
        return doc, out


def step_args(flag):
    """Values given to one tic_archive.py flag in the workflow step."""
    toks = STEP.replace("\\n", " ").split()
    return [toks[i + 1].strip("'\"") for i, t in enumerate(toks) if t == flag]


class Workflow(unittest.TestCase):
    def test_step_after_deploy_with_private_token_and_loud_failure(self):
        self.assertLess(WF.index("- name: Deploy site/ to Cloudflare Pages"), WF.index(STEP[:40]))
        self.assertIn("GH_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", STEP)
        self.assertNotIn("github.token", STEP)
        self.assertIn(f"--program {PROGRAM} --lane raw --src data/raw", STEP)
        self.assertIn("exit 1", STEP)
        self.assertNotIn("|| true", STEP)

    def test_raw_never_published_by_this_repo(self):
        for chunk in WF.split("uses: actions/upload-artifact")[1:]:
            self.assertNotIn("data/raw", chunk.split("path:", 1)[1].split("\n", 1)[0])
        self.assertNotIn("data/raw", WF.split("cache/save", 1)[1].split("- name:", 1)[0] if "cache/save" in WF else "")


class OperationLevelOnly(unittest.TestCase):
    """19 Nov 2026: Meta indicator values and reporter text stay unstored, in the private archive too."""

    def test_every_reporter_lane_and_meta_networks_excluded(self):
        from undertow import reporters
        ex = step_args("--exclude")
        self.assertIn("meta-network/*", ex)
        for lane in reporters.REPORTERS:
            self.assertIn(f"{lane}-rss/*", ex, f"reporter lane {lane} would reach the archive")

    def test_lane_source_ids_match_the_excludes(self):
        src = (ROOT / "tools" / "undertow.py").read_text(encoding="utf-8")
        self.assertIn('fetch.fetch("meta-network"', src)
        self.assertIn('fetch.fetch(f"{lane}-rss"', src)

    def test_archive_keeps_platform_replies_only(self):
        doc, out = put({"meta-readme/a.md": "| network |", "meta-network/b.md": "indicator 203.0.113.9",
                        "meta-commits/c.json": "[]", "google-iob/d.html": "<p>bulletin</p>",
                        "openai-news-rss/e.xml": "<rss/>", "disinfocode-tiktok/f.json": "{}",
                        "eeas-fimi-page/g.html": "<html/>", "dfrlab-rss/h.xml": "<rss>reporter</rss>",
                        "checkfirst-rss/i.xml": "<rss/>", "correctiv-rss/j.xml": "<rss/>", "index.jsonl": "{}\n"},
                       exclude=step_args("--exclude"))
        self.assertEqual(sorted(out), ["disinfocode-tiktok/f.json", "eeas-fimi-page/g.html", "google-iob/d.html",
                                       "index.jsonl", "meta-commits/c.json", "meta-readme/a.md",
                                       "openai-news-rss/e.xml"])
        self.assertFalse(any(b"203.0.113.9" in v or b"reporter" in v for v in out.values()))


if __name__ == "__main__":
    unittest.main()

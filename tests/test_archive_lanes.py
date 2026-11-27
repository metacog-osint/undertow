"""Private archive lanes: every file a run of update.yml leaves outside the tracked code (data/, history/, site/)
lands in the private archive (tools/tic_archive.py, metacog-osint/tic-archive) and restores byte for byte. A file
that a later run removes or replaces stays restorable from the snapshot that held it. Operation level only holds in
the archive too: the snapshot, history/ and site/ lanes hold no Meta indicator value and no reporter text.

The test makes a real offline run in a temporary folder (collect from the recorded replies, build, the retention
archive, the kit's history log as the workflow calls it), then runs the workflow's own tic_archive.py commands, read
from update.yml, against a local DirStore. Nothing reaches GitHub: GhStore is replaced by the DirStore and any
subprocess call during an archive command fails the test."""
from __future__ import annotations

import fnmatch
import gzip
import hashlib
import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.append(str(ROOT / "tools"))   # after ROOT: tools/<program>.py must not shadow the package
import tic_archive as ta  # noqa: E402
from undertow import archive  # noqa: E402

spec = importlib.util.spec_from_file_location("undertow_cli_lanes", ROOT / "tools" / "undertow.py")
undertow_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(undertow_cli)
from test_undertow import getter, meta_indicator_values, reporter_texts  # noqa: E402

WF = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
PROGRAM = "undertow"
RUN_OUTPUTS = ("data", "history", "site")          # what a run writes beside the tracked code
RUN_INPUTS = ("doctrine", "site_src")              # tracked code the offline run is given
NEW_STEP = "Private archive (history, run snapshot and site, to tic-archive)"
FIRST, SECOND = "20261127T060000Z", "20261127T120000Z"


def steps() -> dict[str, str]:
    """The workflow's steps by name (unnamed `uses:` steps by their action)."""
    out = {}
    for chunk in re.split(r"(?m)^      - ", WF.split("\n    steps:\n", 1)[1])[1:]:
        m = re.match(r"name: (.+)|uses: (\S+)", chunk)
        out[(m.group(1) or m.group(2)).strip()] = chunk
    return out


STEPS = steps()


def step(prefix: str) -> str:
    (name,) = [n for n in STEPS if n.startswith(prefix)]
    return STEPS[name]


def archive_calls(text: str, cmd: str) -> list[list[str]]:
    """Every `python tools/tic_archive.py <cmd> ...` in a step, as argv after the script name."""
    flat = re.sub(r"\\\n\s*", " ", text)
    calls = []
    for m in re.finditer(r"python tools/tic_archive\.py (" + cmd + r")\b([^;|&\n]*)", flat):
        args = re.sub(r"\s\d?>>?\s*(\"[^\"]*\"|\S+)", " ", m.group(2))     # a shell redirection is not an argument
        calls.append([m.group(1), *shlex.split(args)])
    return calls


def arg(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, t in enumerate(argv) if t == flag]


def put_calls() -> list[list[str]]:
    return [c for name in STEPS if name.startswith("Private archive") for c in archive_calls(STEPS[name], "put")]


def tree(root: Path) -> dict[str, str]:
    """{posix path relative to root: sha256} for every file."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def run_archive(argv: list[str], cwd: Path, store: Path, stamp: str = FIRST) -> int:
    """One tic_archive.py command as the workflow gives it, in cwd, against a DirStore at store."""
    def no_subprocess(*a, **k):
        raise AssertionError("an archive command tried to run a subprocess (gh): nothing may leave the test")

    old = os.getcwd()
    os.chdir(cwd)
    try:
        env = {k: v for k, v in os.environ.items() if k != "GH_TOKEN"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(ta, "GhStore", lambda *a, **k: ta.DirStore(store)), \
                mock.patch.object(ta, "utc_stamp", lambda now=None: stamp), \
                mock.patch.object(subprocess, "run", no_subprocess):
            return ta.main(argv)
    finally:
        os.chdir(old)


def lane_paths(argv: list[str]) -> tuple[str, str]:
    """(lane, the run-tree folder its restored paths are relative to) for a single-source put."""
    (src,) = arg(argv, "--src")
    assert "=" not in src, "named sources: extend lane_paths"
    return arg(argv, "--lane")[0], src


class RunTree:
    """A real offline run, made once: collect, build, the retention archive and the kit's history log."""
    tmp: Path | None = None

    @classmethod
    def make(cls) -> Path:
        if cls.tmp is not None:
            return cls.tmp
        tmp = Path(tempfile.mkdtemp(prefix="undertow-lanes-"))
        for d in RUN_INPUTS:
            shutil.copytree(ROOT / d, tmp / d)
        snap = undertow_cli.collect(root=tmp, getter=getter)
        undertow_cli.build_site(root=tmp)
        # A closed day of the history log, as an older run leaves it.
        day = tmp / "history" / "log" / "2026" / "11" / "20.jsonl.gz"
        day.parent.mkdir(parents=True, exist_ok=True)
        day.write_bytes(gzip.compress(b'{"format":"tic-history/1","change":"new","id":"undertow:old"}\n', 9, mtime=0))
        # The retention archive (history/reports.jsonl), as `tools/undertow.py archive` writes it.
        if archive.run(snap, tmp / "history", undertow_cli.REPORTER_LANES) < 1:
            raise RuntimeError("the reporter archive wrote no lines from the recorded replies")
        # The kit's history log exactly as the History step calls it.
        (kit,) = re.findall(r"python (doctrine/kit/tic\.py history [^|;\n]*)", re.sub(r"\\\n\s*", " ", step("History")))
        r = subprocess.run([sys.executable, *shlex.split(kit)], cwd=tmp, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"kit history failed: {r.stderr[-400:]}")
        cls.tmp = tmp
        return tmp


def tearDownModule():
    if RunTree.tmp is not None:
        shutil.rmtree(RunTree.tmp, ignore_errors=True)


class TestWorkflowLanes(unittest.TestCase):
    def test_lanes_are_raw_history_state_site(self):
        lanes = {arg(c, "--lane")[0]: c for c in put_calls()}
        self.assertEqual(set(lanes), {"raw", "history", "state", "site"})
        for c in lanes.values():
            self.assertEqual(arg(c, "--program"), [PROGRAM])
        self.assertEqual(arg(lanes["history"], "--src"), ["history"])
        self.assertEqual(arg(lanes["state"], "--src"), ["data"])
        # data/raw has its own lane, with Meta's network files and the reporter pages left out; the laptop's triage
        # list (reporters' headlines) never goes anywhere.
        self.assertEqual(arg(lanes["state"], "--exclude"), ["raw/*", "triage.jsonl"])
        self.assertEqual(arg(lanes["site"], "--src"), ["site"])
        # Copies of public files: archived as they are, so they match the public copy by hash.
        for lane in ("history", "state", "site"):
            self.assertFalse([t for t in lanes[lane] if t.startswith("--redact")], lane)
            self.assertFalse(arg(lanes[lane], "--include"), lane)

    def test_step_after_the_deploy_and_loud_on_failure(self):
        names = list(STEPS)
        new = names.index(NEW_STEP)
        self.assertEqual(new, len(names) - 1)
        self.assertGreater(new, names.index("Deploy site/ to Cloudflare Pages"))
        self.assertGreater(new, names.index("Private archive (raw replies, to tic-archive)"))
        text = STEPS[NEW_STEP]
        self.assertIn("if: ${{ !cancelled() }}", text)
        self.assertIn("GH_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", text)
        self.assertNotIn("github.token", text)
        self.assertNotIn("|| true", text)
        self.assertIn('[ -z "$GH_TOKEN" ]', text)
        self.assertEqual(text.count("exit 1"), 2)            # token missing; any lane failed
        self.assertEqual(text.count("|| failed=1"), 3)       # each lane tried even if another failed

    def test_each_lane_only_after_the_step_that_writes_it(self):
        text = STEPS[NEW_STEP]
        self.assertIn("HISTORY: ${{ steps.history.outcome }}", text)
        self.assertIn("CHECKED: ${{ steps.recheck.outcome }}", text)
        # The deploy step's outcome is success also when it skipped the deploy (no Cloudflare secrets), so the
        # site lane reads the step's own output, which only a real deploy writes (TestDeployOutput).
        self.assertIn("DEPLOYED: ${{ steps.deploy.outputs.deployed }}", text)
        self.assertNotIn("steps.deploy.outcome", text)
        self.assertIn("id: history", step("History"))
        self.assertIn("id: recheck", step("Check again"))
        self.assertIn("id: deploy", STEPS["Deploy site/ to Cloudflare Pages"])
        flat = re.sub(r"\\\n\s*", " ", text)
        for var, value, lane in (("HISTORY", "success", "history"), ("CHECKED", "success", "state"),
                                 ("DEPLOYED", "true", "site")):
            self.assertRegex(flat, rf'if \[ "\${var}" = "{value}" \]; then\s+python tools/tic_archive\.py put '
                                   rf'--program undertow --lane {lane} ')

    def test_what_the_workflow_keeps_for_a_while_is_inside_the_archived_folders(self):
        # The Actions cache (evicted after 7 days unused) holds this path; the state lane takes it.
        save = STEPS["Keep this run's snapshot for the next run"]
        (cached,) = re.findall(r"(?m)^\s+path: (\S+)\s*$", save)
        (restored,) = re.findall(r"(?m)^\s+path: (\S+)\s*$", STEPS["Last run's snapshot from the Actions cache (none on the first run)"])
        self.assertEqual(cached, "data/snapshot.json")
        self.assertEqual(restored, cached)
        self.assertTrue(cached.startswith("data/") and not cached.startswith("data/raw"))
        self.assertIn("git add history\n", step("History"))
        self.assertIn("pages deploy site --project-name", step("Deploy site/"))


def run_script(text: str) -> str:
    """A step's `run: |` block as the shell gets it."""
    block = text.split("run: |\n", 1)[1]
    return "".join(line[10:] if line.startswith(" " * 10) else line.lstrip(" ")
                   for line in block.splitlines(keepends=True))


def run_step(text: str, td: Path, env: dict[str, str], stubs: str) -> subprocess.CompletedProcess:
    """Run a step's shell in `td` with bash -e, as Actions does, after the shell functions in `stubs`."""
    script = td / "step.sh"
    script.write_text(run_script(text), encoding="utf-8", newline="\n")
    cmd = f'set -e; {stubs} . "{script.as_posix()}"'
    return subprocess.run(["bash", "-c", cmd], env={**os.environ, **env}, capture_output=True, text=True, cwd=td)


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class TestDeployOutput(unittest.TestCase):
    """The deploy step's own shell, with npx and sleep replaced: `deployed=true` reaches $GITHUB_OUTPUT only when
    wrangler deployed, so a run without the Cloudflare secrets never archives a site that was not published."""

    def run_deploy(self, token: str, account: str, npx_exit: int) -> tuple[int, str, int]:
        """(exit code, what the step wrote to $GITHUB_OUTPUT, how many times npx ran)."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            calls, out = td / "npx-calls", td / "github-output"
            out.write_text("", encoding="utf-8")
            env = {"CLOUDFLARE_API_TOKEN": token, "CLOUDFLARE_ACCOUNT_ID": account, "GITHUB_SHA": "0" * 40,
                   "GITHUB_OUTPUT": out.as_posix()}
            # Shell functions stand in for npx (counted, its exit code chosen here) and sleep (no wait).
            stubs = f'npx() {{ echo x >> "{calls.as_posix()}"; return {npx_exit}; }}; sleep() {{ :; }};'
            r = run_step(STEPS["Deploy site/ to Cloudflare Pages"], td, env, stubs)
            n = len(calls.read_text().splitlines()) if calls.exists() else 0
            return r.returncode, out.read_text(encoding="utf-8"), n

    def test_no_secrets_skips_and_writes_no_output(self):
        for token, account in (("", ""), ("t", ""), ("", "a")):
            code, out, npx = self.run_deploy(token, account, 0)
            self.assertEqual((code, npx), (0, 0))
            self.assertNotIn("deployed=true", out)

    def test_a_real_deploy_writes_the_output(self):
        code, out, npx = self.run_deploy("t", "a", 0)
        self.assertEqual((code, npx), (0, 1))
        self.assertEqual(out.strip(), "deployed=true")

    def test_three_failed_deploys_write_no_output(self):
        code, out, npx = self.run_deploy("t", "a", 1)
        self.assertEqual((code, npx), (1, 3))
        self.assertNotIn("deployed=true", out)


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class TestRestoreStepAnnotations(unittest.TestCase):
    """The restore on a cache miss, its own shell with python replaced: a failed restore falls through to a first
    run, so the step stays green and prints no ::error:: line (a red annotation on a green run)."""

    STEP = "No cache entry, so the snapshot from the private archive"

    def run_restore(self, token: str, restore: str) -> tuple[subprocess.CompletedProcess, Path]:
        td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, td, True)
        (td / "runner-temp").mkdir()
        env = {"GH_TOKEN": token, "RUNNER_TEMP": (td / "runner-temp").as_posix()}
        return run_step(step(self.STEP), td, env, f"python() {{ {restore} }};"), td

    @staticmethod
    def lines(r: subprocess.CompletedProcess) -> list[str]:
        return (r.stdout + r.stderr).splitlines()

    def test_a_failed_restore_is_a_warning_not_an_error(self):
        r, td = self.run_restore("t", 'echo "::error::tic-archive: restore undertow/state: no release" >&2; return 1;')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse([ln for ln in self.lines(r) if ln.startswith("::error::")], self.lines(r))
        self.assertIn("::warning::tic-archive: restore undertow/state: no release", self.lines(r))
        self.assertTrue(any("No snapshot in the Actions cache or the private archive" in ln for ln in self.lines(r)))
        self.assertFalse((td / "data").exists())

    def test_no_token_is_a_warning_and_no_restore(self):
        r, _ = self.run_restore("", 'echo called >&2; return 1;')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("called", r.stdout + r.stderr)
        self.assertFalse([ln for ln in self.lines(r) if ln.startswith("::error::")])

    def test_a_restore_without_the_snapshot_file_is_not_copied(self):
        r, td = self.run_restore("t", 'mkdir -p "$RUNNER_TEMP/archive-state"; return 0;')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((td / "data").exists())

    def test_a_good_restore_is_copied_into_data(self):
        r, td = self.run_restore("t", 'mkdir -p "$RUNNER_TEMP/archive-state"; '
                                      'echo "{}" > "$RUNNER_TEMP/archive-state/snapshot.json"; return 0;')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((td / "data" / "snapshot.json").read_text(encoding="utf-8").strip(), "{}")
        self.assertTrue(any("restored the newest copy" in ln for ln in self.lines(r)))


class TestEveryRunFileIsArchived(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_root = RunTree.make()
        cls.work = Path(tempfile.mkdtemp(prefix="undertow-store-"))
        cls.store = cls.work / "store"
        cls.before = {top: tree(cls.run_root / top) for top in RUN_OUTPUTS}
        cls.results = {}
        for argv in put_calls():
            cls.results[arg(argv, "--lane")[0]] = run_archive(argv, cls.run_root, cls.store, FIRST)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def restore_all(self, dest: Path, snapshots: dict[str, str] | None = None) -> dict[str, str]:
        """Every lane restored, mapped back to run-tree paths: {path: sha256}."""
        got = {}
        for argv in put_calls():
            lane, src = lane_paths(argv)
            cmd = ["restore", "--program", PROGRAM, "--lane", lane, "--dest", str(dest / lane)]
            if snapshots and lane in snapshots:
                cmd += ["--snapshot", snapshots[lane]]
            self.assertEqual(run_archive(cmd, self.run_root, self.store), 0, lane)
            for rel, sha in tree(dest / lane).items():
                path = f"{src}/{rel}"
                self.assertNotIn(path, got, "two lanes hold the same file")
                got[path] = sha
        return got

    def snapshot_names(self, stamp: str) -> dict[str, str]:
        out = {}
        for tag in self.store.iterdir():
            for p in tag.iterdir():
                if p.name.startswith(stamp) and p.name.endswith(".files.json"):
                    out[tag.name[len(PROGRAM) + 1:].rsplit("-", 2)[0]] = p.name
        return out

    def test_the_offline_run_writes_only_the_known_folders(self):
        self.assertEqual({p.name for p in self.run_root.iterdir()}, set(RUN_INPUTS) | set(RUN_OUTPUTS))
        self.assertTrue(self.before["data"] and self.before["history"] and self.before["site"])

    def test_every_put_succeeded(self):
        self.assertEqual(self.results, {"raw": 0, "history": 0, "state": 0, "site": 0})

    def test_every_file_of_the_run_restores_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as td:
            got = self.restore_all(Path(td), self.snapshot_names(FIRST))
        # Files the raw lane leaves out on purpose (operation level only): Meta's per-network files (indicator
        # values) and the reporter pages (reporter text). Every other file of the run is in the archive.
        (raw_put,) = [c for c in put_calls() if arg(c, "--lane") == ["raw"]]
        raw_excluded = arg(raw_put, "--exclude")
        left_out = {f"data/{rel}" for rel in self.before["data"]
                    if rel.startswith("raw/") and any(fnmatch.fnmatch(rel[4:], g) for g in raw_excluded)}
        self.assertTrue(any(p.startswith("data/raw/meta-network/") for p in left_out), "the run read Meta's networks")
        self.assertTrue(any(p.startswith("data/raw/dfrlab-rss/") for p in left_out), "the run read a reporter feed")
        want = {f"{top}/{rel}": sha for top, files in self.before.items() for rel, sha in files.items()
                if f"{top}/{rel}" not in left_out}
        self.assertEqual(sorted(set(want) - set(got)), [], "files of the run missing from the archive")
        self.assertEqual(sorted(set(got) - set(want)), [], "the archive holds files the run did not write")
        self.assertEqual({p: s for p, s in got.items() if want[p] != s}, {}, "restored bytes differ")
        # The files other programs read from the site are among them, and so is the snapshot the cache holds.
        for p in ("site/data/feed.geojson", "site/data/ended.geojson", "site/data/events.json", "site/data/stix.json",
                  "site/data/snapshot.json", "site/data/baseline.json", "data/snapshot.json", "data/raw/index.jsonl",
                  "history/state.json", "history/reports.jsonl", "history/log/2026/11/20.jsonl.gz"):
            self.assertIn(p, got)

    def test_no_indicator_value_or_reporter_text_in_the_new_lanes(self):
        """The history, state and site lanes are copies of operation-level files: none holds a Meta indicator value
        or a reporter's title or description, the same rule the raw lane's excludes hold."""
        vals, texts = meta_indicator_values(), reporter_texts()
        self.assertGreater(len(vals), 20)
        self.assertTrue(texts)
        with tempfile.TemporaryDirectory() as td:
            for argv in put_calls():
                lane, _ = lane_paths(argv)
                if lane == "raw":
                    continue
                dest = Path(td) / lane
                self.assertEqual(run_archive(["restore", "--program", PROGRAM, "--lane", lane, "--dest", str(dest)],
                                             self.run_root, self.store), 0, lane)
                for p in dest.rglob("*"):
                    # site/ outside site/data is a copy of the tracked site_src/ and doctrine/ (the page's own text
                    # names hosts such as tiktok.com); the data files are what the run wrote.
                    if not p.is_file() or (lane == "site" and not p.relative_to(dest).as_posix().startswith("data/")):
                        continue
                    body = p.read_bytes()
                    body = gzip.decompress(body) if p.name.endswith(".gz") else body
                    txt = body.decode("utf-8", errors="replace")
                    for v in vals:
                        self.assertNotIn(v, txt, f"{lane}: {p.relative_to(dest)} holds an indicator value")
                    for t in texts:
                        self.assertNotIn(t, txt, f"{lane}: {p.relative_to(dest)} holds reporter text")

    def test_removed_or_replaced_files_stay_restorable(self):
        root = self.run_root
        old = {p: (root / p).read_bytes() for p in ("history/log/2026/11/20.jsonl.gz", "data/snapshot.json",
                                                     "site/data/ended.geojson")}
        try:
            # The next run: a closed log day no longer in the public tree (a cap), a new snapshot, a new deploy.
            (root / "history/log/2026/11/20.jsonl.gz").unlink()
            (root / "data/snapshot.json").write_bytes(old["data/snapshot.json"].replace(b"{", b'{"run": 2, ', 1))
            (root / "site/data/ended.geojson").write_bytes(old["site/data/ended.geojson"] + b"\n")
            for argv in put_calls():
                if arg(argv, "--lane")[0] != "raw":
                    self.assertEqual(run_archive(argv, root, self.store, SECOND), 0)
            first, second = self.snapshot_names(FIRST), self.snapshot_names(SECOND)
            self.assertEqual(set(first), {"raw", "history", "state", "site"})
            self.assertEqual(set(second), {"history", "state", "site"})
            with tempfile.TemporaryDirectory() as td:
                now = self.restore_all(Path(td) / "now")
                then = self.restore_all(Path(td) / "then", first)
            self.assertNotIn("history/log/2026/11/20.jsonl.gz", now)
            for p, data in old.items():
                self.assertEqual(then[p], hashlib.sha256(data).hexdigest(), p)
                if (root / p).exists():
                    self.assertEqual(now[p], hashlib.sha256((root / p).read_bytes()).hexdigest(), p)
                    self.assertNotEqual(now[p], then[p], p)
        finally:
            for p, data in old.items():
                (root / p).parent.mkdir(parents=True, exist_ok=True)
                (root / p).write_bytes(data)


class TestSnapshotRestoreFromTheArchive(unittest.TestCase):
    """The run snapshot is read back from the private archive when the Actions cache has none."""

    def test_only_on_a_cache_miss_and_into_a_temporary_folder_first(self):
        names = list(STEPS)
        text = step("No cache entry, so the snapshot from the private archive")
        i = names.index("No cache entry, so the snapshot from the private archive")
        self.assertEqual(names[i - 1], "Last run's snapshot from the Actions cache (none on the first run)")
        self.assertLess(i, names.index("Live collection (a failed lane keeps its last good copy and says so on the page)"))
        self.assertIn("if: steps.state.outputs.cache-matched-key == ''", text)
        self.assertIn("GH_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", text)
        self.assertNotIn("github.token", text)
        self.assertNotIn("exit 1", text)        # a miss everywhere is a first run, as before, never a stop
        (call,) = archive_calls(text, "restore")
        self.assertEqual(arg(call, "--program"), [PROGRAM])
        self.assertEqual(arg(call, "--lane"), ["state"])
        self.assertEqual(arg(call, "--dest"), ["$RUNNER_TEMP/archive-state"])        # not data/ itself
        self.assertLess(text.index("python tools/tic_archive.py restore"),
                        text.index('cp -R "$RUNNER_TEMP/archive-state/." data/'))

    def test_restore_gives_back_the_snapshot_the_cache_holds(self):
        run_root = RunTree.make()
        (call,) = archive_calls(step("No cache entry, so the snapshot from the private archive"), "restore")
        (state_put,) = [c for c in put_calls() if arg(c, "--lane") == ["state"]]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            self.assertEqual(run_archive(state_put, run_root, td / "store"), 0)
            fresh = td / "next-run"
            fresh.mkdir()
            runner_temp = td / "runner-temp"
            argv = [t.replace("$RUNNER_TEMP", str(runner_temp)) for t in call]
            self.assertEqual(run_archive(argv, fresh, td / "store"), 0)
            shutil.copytree(runner_temp / "archive-state", fresh / "data")       # cp -R .../archive-state/. data/
            want = {rel: sha for rel, sha in tree(run_root / "data").items() if not rel.startswith("raw/")}
            self.assertEqual(tree(fresh / "data"), want)
            self.assertEqual(set(want), {"snapshot.json"})

    def test_triage_list_never_reaches_the_state_lane(self):
        (state_put,) = [c for c in put_calls() if arg(c, "--lane") == ["state"]]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "data" / "raw").mkdir(parents=True)
            (td / "data" / "snapshot.json").write_text("{}\n", encoding="utf-8")
            (td / "data" / "triage.jsonl").write_text('{"title": "a reporter headline"}\n', encoding="utf-8")
            (td / "data" / "raw" / "index.jsonl").write_text("{}\n", encoding="utf-8")
            self.assertEqual(run_archive(state_put, td, td / "store"), 0)
            self.assertEqual(run_archive(["restore", "--program", PROGRAM, "--lane", "state", "--dest", str(td / "out")],
                                         td, td / "store"), 0)
            self.assertEqual(set(tree(td / "out")), {"snapshot.json"})


if __name__ == "__main__":
    unittest.main()

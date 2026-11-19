# Undertow (`[local path]`)

Influence operations for The Intelligence Company (`tic-feed/2`, program id `undertow`, prefix `UT`): covert
influence operations that Meta, Google, OpenAI, TikTok and the EEAS have publicly disrupted or named, at
**operation level only**, tagged with DISARM v1.6.1 techniques and exported as STIX 2.1; kept apart, reports by
independent researchers (DFRLab, CheckFirst, CORRECTIV) and the G7 RRM. Measurements and publishers' reports only:
no probability. Spec: `[local path]` section 6; row in
`_ideas\new-programs.md`. Site https://undertow.theintelligence.company; repo `metacog-osint/undertow`, **public**
(since 15 Nov 2026).

**Slimmed 18 Nov 2026** from 32.6 KB. Full earlier text (shas, run ids, counts, decision narrative):
`.claude/notes-archive-2026-11-18.md`. **Current state and open items: `.claude/HANDOFF.md`**, read it first.
`.claude/` is kept out of git by `.git/info/exclude`. Keep this file under 12 KB; state goes in the handoff.

## Commands
```bash
python tools/undertow.py collect [--only meta]  # lanes into data/snapshot.json; others keep their last copy
python tools/undertow.py build | check          # site/; registers, linter, STIX check, leak scan
python tools/undertow.py triage [--days 180]    # LAPTOP ONLY -> data/triage.jsonl
python tools/undertow.py closing [--months 12]  # LAPTOP ONLY -> data/closing.json
python -m unittest discover -s tests            # offline, recorded real replies (tests/make_fixtures.py re-records)
python tools/serve.py                           # http://127.0.0.1:8781 with _headers; launch entry `undertow-site`
python doctrine/kit/tic.py kitcheck             # also: tic.py lint site/data/feed.geojson --doctrine doctrine
```
Standard library only (Python 3.12+). `collect` never makes up data: a failed lane keeps its last good copy
(`from_previous`) or stays empty, and the snapshot's `lanes` says which. Run `closing` after each collect that
brings a new disclosure (about monthly). `triage` and `closing` refuse when `GITHUB_ACTIONS` is set.

## Deploy and workflow
- **Pushing `main` deploys.** `update.yml` runs on every push to main, cron `41 */6 * * *` (fallback) and
  dispatch (hub's tic-dispatch at :30 past 02, 08, 14, 20 UTC): tests, kitcheck, cached snapshot, collect, build,
  check, history, check, `wrangler pages deploy`. Secret `CLOUDFLARE_PAGES_TOKEN`, variable `CLOUDFLARE_ACCOUNT_ID`
  (set with `--body`; a PowerShell pipe's BOM broke Headwind's).
- The workflow commits `history/` to main after each run (its token starts no run): **fetch before working**.
- Each commit and push needs Tom's yes. Push by named commit (`git push origin <sha>:refs/heads/main`) after listing
  what is ahead; ask for each push by its sha (auto mode refused pushes until Tom said "Push <sha>").
- Pages project `undertow` (`undertow-cm3.pages.dev`), Squarespace CNAME. History (kit `tic-history/1`) writes
  `history/` (published items only) and `site/data/ended.geojson`; a failing lane ends nothing.
- `feed.health()` is **keyed by the source id items carry** (`google-iob`, `eeas-fimi-4`, ...), not lane name.
  State `up` or `failing` only: disclosures have no rhythm for fresh/late/stale.

## Lanes
| Lane | Module | Source, how read, what is kept |
|---|---|---|
| `meta` | `meta.py` | `github.com/meta/threat-research`: README table, each network's Markdown, one GitHub API commits call for when each file was added (`GITHUB_TOKEN` if set, never recorded; can postdate the report). Kept: title, period, origin, targets, counts, summary (≤1,400 chars, scrubbed), indicator **counts** only |
| `google` | `google.py` | `blog.google/security/influence-operations-bulletin-qN-YYYY/` from Q1 2026 plus its RSS; 404 = not yet out. Facts and counts only; stance read for DISARM, never kept. Keys positional (`google:2026-q3:2026-07:01`): an edited bulletin logs ended+new |
| `openai` | `openai_rss.py` | `openai.com/news/rss.xml` ONLY (`fetch_allowed()` refuses other openai.com URLs; a test holds it). "influence" in title or summary = operation; round-ups are disclosures. Since 1 Jan 2024 |
| `tiktok` | `tiktok.py` | `disinfocode.eu/reports/tiktok/<n>/json`, probing two ahead. NEVER tiktok.com. Commitment 14 TTP 6, crisis and elections chapters, merged on (origin, accounts, followers) |
| `eeas` | `eeas.py` | `config/register/eeas-fimi-4.json`: 9 sets of the 4th FIMI report (12 Mar 2026), from the PDF (sha256 recorded), cited to printed pages; each run watches for a 5th |
| `dfrlab`, `checkfirst`, `correctiv` | `reporters.py` | Reporter lanes (below). Grades B2, B2, B3 (a newsroom often reports others' findings) |
| `watch` | `activity.py` | `config/register/watch.json`, hand-kept; `check_watch()` refuses a bad row |

**Reporter lanes** (`REPORTERS`): WordPress RSS pages (`?paged=N`, 2 s apart), never an article page. Kept only when
title or description names an operation in `config/operations.json` (case-sensitive): operations, time, link,
countries named, platforms from a fixed list. **Never kept:** the reporter's title or description (they name
individuals), `dc:creator`, author categories, attribution. First run back to 2024-01-01; later runs stop 30 days
before the newest item read last time; a change to names or aliases (`ops_fingerprint`) re-reads the whole feed.

**Reported activity** (`activity.py`, Tom 16 Nov): one item per (reporter, operation), key `<lane>:activity:<op>`;
state **active** (last report within `QUIET_DAYS` = 180) or **quiet**, never "ended". Title says "reported by", since
a name match means the reporter wrote about the operation, not that it found it running. `data_as_of` is the last
report. STIX: a `report` on the operation's intrusion-set, no campaign.

**Watch register** rules: Tom promotes triage rows by hand. Each row's URL must be on a host in its
`reporter_hosts` (also extends the leak scan). `tracked_operations` (list; old single `tracked_operation` still
reads) become `named_operations`: corroboration and a STIX campaign `attributed-to` each intrusion set, never origin
or confidence. Optional `activity_period` {from, to} (when the activity ran, not the report date), `alignment`
(a reporter's "state-aligned"/"Kremlin-aligned" is alignment, never origin), `label_starts_with_name`. A row from a
reporter with its own lane counts in that lane's independence group; its STIX campaign carries the row's grade.
G7 RRM (B2, government) and VIGINUM enter only as rows.

## Hard rules and how they are held
- **Operation level only.** No indicator values, account handles, URLs or domains, or names of individuals in any
  output. `text.scrub()` on every kept sentence (links, handles, defanged values, bare domains -> "[link withheld]";
  two+ unknown capitalised words, or one after a title -> "[name withheld]"; misses a lone surname, UT-ASM-4).
  Wrongly withheld organisation -> `known_phrases` in `config/operations.json`. `check` scans published files for
  defanged values, @handles and URLs outside `ALLOWED_URL_PREFIXES`. Tests assert no Meta indicator value leaks.
- `data/raw/` (full replies) is never cached, committed or published; only `data/snapshot.json` is cached.
  `data/triage.jsonl` is never published. `tests/fixtures/` holds full replies (see the handoff: repo now public).
- **Never fetch tiktok.com or OpenAI's report pages.**
- **Origin is never sponsorship.** Three questions kept apart (`doctrine/confidence-mapping.md`). EEAS's
  "Russia-aligned"/"Chinese-aligned" for non-attributed operations (Storm-1516, Operation Overload, Portal Kombat,
  Spamouflage, HaiEnergy) is `alignment`, and those items carry no confidence. An operator is recorded only where the
  publisher names it, as a reported `responsible` actor, with `us_person_data: organizations`.
- A reporter lane never adds an origin. A watch row's origin counts only when `checked_by` is set and
  `origin_evidence` is "own" ("cites-other" repeats a platform's attribution).
- **Confidence** (tic-confidence-1.0, origin only): independent publishers naming the same operation (name or
  publisher alias) with the same origin. One is Low, two Moderate. **No High** (origin easy to fake; no scored
  Verdict record).
- **DISARM** (`config/disarm_rules.json`): 17 phrase rules, each one v1.6.1 technique, basis `mapped`; reviewed by
  Tom 14 Nov 2026, each rule `review: accepted` 19 Nov (a rule without it turns the table "proposed"). A technique
  is Undertow's reading of the publisher's words, not the publisher's claim. Bundle cut
  vendored in `config/disarm/DISARM-1.6.1-cut.json` with its CC BY-SA 4.0 marking.
- **STIX:** UUIDv5 ids from `uuid5(DNS, "undertow.theintelligence.company")` and a stable key; timestamps from the
  disclosure, so rebuilds are byte-identical. TLP:CLEAR from OASIS `cti-stix-common-objects`. A `threat-actor`
  (types ["unknown"], resource_level "organization", nothing more) only for a name hand-kept in
  `config/operations.json` or `config/register/` (`stix.named_organisations()`; `validate()` refuses any other).
  Never emitted: indicator, observed-data, cyber-observables, identity for a person.
- **Standing listings** (`undertow/listings.py`, `organisations.entries[].listings`): each row read from the list
  publisher's own notice (Headwind's list ids). `check` refuses unknown lists, non-ISO dates, notices off the
  publisher's site, extra fields such as a person's name. Shown as `listed_by`; never changes confidence or origin
  (a test builds with and without).
- **Only stated targets are marked on the map** (Tom, 16 Nov). Google and OpenAI name no target, so they are off
  the map; countries their text names stay in `countries`/`countries_named`, labelled not targets. A reporter's item
  is marked where a disclosure of the same operation records a target (`activity.place`).
- **Dates:** `data_as_of` is the publisher's date; `data_as_of_precision` `day` (Google, EEAS, TikTok report 8,
  OpenAI at midnight) or `month` (OpenAI case studies dated midnight on the 1st, `openai_rss.date_precision`).
- **Baseline** (Tom 16 Nov): name-matched lead time set aside (platforms coin most names in the disclosure). The
  baseline is the watch register's closing: `UT-IND-3` lead days to the takedown a row is `closed_into`; `UT-IND-4`
  share closed within 12 months. `UT-IND-1..2`: corroboration; target-country quarterly count. **No anomaly rule and
  no warning tier before 10 closed rows**; even then described, never rated. Every item: kind observation, tier
  routine, `reported`, grade A2.
- Never edit `doctrine/kit/` (sync: `python <tic-doctrine>/tools/sync.py [local path]`, Tom's yes) or
  `site_src/tic-*` (copies of the hub's `site/shared/` files).

## Outputs (`site/data/`) and suite use
`feed.geojson` (~1.9 MB; the hub reads it whole), `stix.json`, `events.json` (expected disclosures, each "not a
published date"), `snapshot.json` (the page), `ended.geojson` (COP). Registry row in tic-doctrine
`vocab/programs.json`; hub Programs menu after Context; COP halos target countries (Information preset, `#CD00A0`).
COP's joins: sanctions (`tools/undertow_sanctions.py`) and elections (`tools/undertow_elections.py`, uses
`activity_period` or `operation.period`, never a report date, so keep both filled). Election dates: hand-entered in
Verdict's calendar, kind `election` (ElectionGuide is non-commercial). Press join waits for a narrative lane.

## Sources and terms (read 14 Nov 2026 unless marked)
- Meta MIT (quote with "Copyright (c) Meta Platforms, Inc. and affiliates ... MIT License"). Google: ToS ambiguous;
  Tom: automate, facts and counts only. OpenAI: Terms bar extraction; RSS only, with credit. TikTok via
  disinfocode.eu: no terms found; tiktok.com never read. EEAS: reuse with acknowledgement. DISARM: CC BY-SA 4.0.
- DFRLab (16 Nov): Atlantic Council terms, noncommercial, no faster than a person; credit "Atlantic Council's
  Digital Forensic Research Lab". CheckFirst: `llms.txt` welcomes citing with attribution. CORRECTIV: no terms found,
  all rights reserved, facts only. G7 RRM (canada.ca): non-commercial with full title, author and URL.
- Not built: Alliance4Europe (feed still since Sep 2025); Ukraine's CCD (a party to the war). VIGINUM: SGDSN terms
  unread. No new reporter lane until one shows current, on-topic output.

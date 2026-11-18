# Undertow (`D:\Projects\undertow`)

Influence operations for The Intelligence Company (`tic-feed/2`, program id `undertow`, prefix `UT`): covert
influence operations that Meta, Google, OpenAI, TikTok and the EEAS have publicly disrupted or named, at
**operation level only**, tagged with DISARM v1.6.1 techniques and exported as STIX 2.1. Roadmap step 12. Name,
lanes and terms decisions: Tom, 14 Nov 2026 (spec: `D:\Projects\_ideas\drafts\2026-11-14-influence-ops-step12.md`,
section 6; programme row in `_ideas\new-programs.md`). Measurements and publishers' reports only: no probability.

## State, 16 Nov 2026 (about 10 AM CST): live

- **Repo:** `metacog-osint/undertow` (private, Tom's decision), branch `main`. Commits:
  - `3b4a72a`: the first live slice (14 Nov).
  - `305cb68`: house bar v1.11.
  - `d18db9a`: DISARM table reviewed by Tom.
  - `79f99a1`: house bar v1.12, from the house-bar rollout session.
  - `28fb96d`: house bar v1.13, from the session that listed Wake.
  - `e70194d`: EEAS register, second machine reading.
  - `d2d0b8f`: date precision and kit 0.5.6.
  - `393758e`: health record and history log.
  - `e73b0e7`: STIX threat-actors for five hand-kept named organisations.
  - `a3e1a65`: the DFRLab lane (corroboration and link-out).
  - The reported-activity slice (16 Nov 2026, below), after the history rewrite:
    - `229716f`: CheckFirst and CORRECTIV lanes, reported-activity items, watch register and the laptop-only triage
      list.
    - `a3e59cf`: only stated targets on the map.
    - `79cd60e`: the watch register's first row (Armenia, DFRLab).
    - `606105f`: the baseline (watch-register closing, `UT-IND-3..4`), the `closing` list, triage at 180 days.
    - `origin/main` was `f282823` at about 10 AM CST on 16 Nov, ahead of `606105f` only by the workflow's history
      commits.
  - The workflow commits `history/` to main after each run, so fetch before working.
  - Each commit and push needs Tom's yes. Push by named commit (`git push origin <sha>:refs/heads/main`) after
    listing what is ahead, and ask for each push by its sha (the auto-mode check refused pushes until Tom said
    "Push <sha>").
- **Site:** https://undertow.theintelligence.company. Cloudflare Pages project `undertow` (`undertow-cm3.pages.dev`);
  Tom added the Squarespace CNAME, and the domain has been active with HTTPS and HSTS since 4:21 PM CST on 14 Nov.
  `.github/workflows/update.yml` runs on every push to `main`, on cron `41 */6 * * *` and on workflow_dispatch:
  tests, kitcheck, the last snapshot from the Actions cache, collect, build, check, history (below), check again, then
  `wrangler pages deploy site --project-name undertow`. It uses secret `CLOUDFLARE_PAGES_TOKEN` and repo variable
  `CLOUDFLARE_ACCOUNT_ID` (set with `--body`; a PowerShell pipe's BOM broke Headwind's). Every run on 14 and 15 Nov
  passed (43643868752, 43645582544, 43662903183, 43670100913, 43688512599, 43729348150, 43750332277,
  43758431795, 43765391411).
- **tic-dispatch:** the hub's Worker (`dispatch/dispatch.js`) starts `update.yml` at :30 past 02, 08, 14 and 20 UTC.
  The dispatch token reaches Undertow: the first dispatched run started at 20:30 UTC on 15 Nov 2026 (43758431795,
  passed). The cron `41 */6` stays as a fallback.
- **Suite:**
  - Registry row in tic-doctrine `vocab/programs.json`: live since kit 0.5.3; 0.5.6 makes its terms line say what
    Undertow quotes with credit.
  - Hub listing (hub `67b65f1`): the house bar's Programs menu after Context, the product lists, the drawing node
    at [780, 426] and the first guide question. Its feed is about 1.9 MB and the hub reads it whole.
  - COP layer (COP `a790f20`): halos on target countries under the Information preset, colour `#CD00A0`, on
    `tools/gate.py`'s open list through `ID_PREFIXES`, six source rows and MCP rule 8. COP `46d2fe8` shows date-only
    times as dates.
- **Tom's other open step:** send the permission emails to TikTok and OpenAI
  (`_ideas\drafts\2026-11-14-undertow-permission-emails.md`). Claude never sends them.

## Commands

```bash
python tools/undertow.py collect               # fetch every live lane into data/snapshot.json
python tools/undertow.py collect --only meta   # one or more lanes; the rest keep their last copy
python tools/undertow.py build                 # build site/ from data/snapshot.json
python tools/undertow.py check                 # registers, feed linter, STIX check, leak scan
python tools/undertow.py triage [--days 180]   # LAPTOP ONLY: new, unnamed reported activity -> data/triage.jsonl
python tools/undertow.py closing [--months 12] # LAPTOP ONLY: watch rows against later disclosures -> data/closing.json
python -m unittest discover -s tests           # 51 offline tests on recorded real replies
python tests/make_fixtures.py                  # re-record fixtures from the raw copies of the last collect
python tools/serve.py                          # site/ on http://127.0.0.1:8781 with _headers (CSP); launch entry `undertow-site`
python doctrine/kit/tic.py lint site/data/feed.geojson --doctrine doctrine
python doctrine/kit/tic.py kitcheck            # the vendored kit is intact
```

`collect` never falls back to made-up data. A lane that fails keeps its last good copy (`from_previous`) or stays
empty, and `lanes` in the snapshot says which. Standard library only (Python 3.12+).

## Lanes (first collect 14 Nov 2026; 16 Nov: 434 feed items, 425 disclosures plus 9 reported-activity items)

| Lane | Module | Source and how it is read | Items |
|---|---|---|---|
| `meta` | `meta.py` | `github.com/meta/threat-research` (MIT). Read: the README table (period, title, origin, targets, link), each network's Markdown file from raw.githubusercontent, and one GitHub API call (`/commits?per_page=100`) for when each file was added (commit messages "Add threat indicators: <file>"; `GITHUB_TOKEN` used if set, never recorded). Kept: title, period, origin, targets, Meta's counts (accounts, Pages, followers), Meta's network summary (first paragraphs up to 1,400 characters, scrubbed, quoted with the MIT notice) and the indicator **count** by type | 22 (H2 2026 10, H1 2026 6, H2 2025 6) |
| `google` | `google.py` | Influence Operations Bulletin pages, `blog.google/security/influence-operations-bulletin-qN-YYYY/`, every quarter from Q1 2026 to the current one, plus any in `blog.google/security/rss/`. A 404 means not yet published. Facts and counts only: month, asset counts, linked-to country, languages, countries the stance names. The stance wording is read for DISARM rules and never kept (the matched phrase is null). Unparsed entries are kept and counted | 342 (Q1 91, Q2 158, Q3 93) |
| `openai` | `openai_rss.py` | `openai.com/news/rss.xml` ONLY. `fetch_allowed()` refuses any other openai.com URL, and a test holds it. An item is an operation when its title or summary says "influence" (not Global Affairs); round-ups are disclosures. Kept: operation name, origin wording, the one-line summary (scrubbed, quoted with credit). Since 1 Jan 2024 | 27 operations, 6 round-ups |
| `tiktok` | `tiktok.py` | EU Code of Conduct Transparency Centre JSON, `disinfocode.eu/reports/tiktok/<n>/json`: reports 8 (Jul-Dec 2025) and 9 (Jan-Jun 2026), probing two numbers ahead. NEVER tiktok.com. Networks come from Commitment 14 TTP 6, the crisis chapter and the elections chapter, merged on (origin, accounts, followers). TikTok's description is quoted with credit | 25 (report 8: 8, report 9: 17) |
| `eeas` | `eeas.py` | `config/register/eeas-fimi-4.json`: the nine Information Manipulation Sets of the 4th EEAS FIMI report (12 Mar 2026), entered once from the PDF (sha256 recorded), each row and quote cited to its printed page. Each run reads the EEAS FIMI page to confirm the report is listed and to notice a 5th | 9 |
| `dfrlab` | `reporters.py` | Reporter lane (below). `dfrlab.org/feed/`. Grade B2 | 15 reports -> 5 activity items |
| `checkfirst` | `reporters.py` | Reporter lane. `checkfirst.network/feed/` (10 a page). Grade B2 | 5 reports -> 2 items |
| `correctiv` | `reporters.py` | Reporter lane. `correctiv.org/en/feed/` (100 a page; English stories back to 2015). Grade B3 (a newsroom often reports others' findings) | 3 reports -> 2 items |
| `watch` | `activity.py` | `config/register/watch.json`, hand-kept; `check_watch()` refuses a bad row | 1 row (Armenia, 16 Nov) |

**Reporter lanes** (`undertow/reporters.py`, `REPORTERS`): WordPress RSS pages (`?paged=N`, 2 s apart), never an
article page. Kept only when the title or one-line description names an operation in `config/operations.json`
(case-sensitive, as every lane): operations, time, link, countries named, platforms from a fixed list. **Never
kept:** the reporter's title or description (they name individuals), `dc:creator`, author categories, attribution.
First run reads back to 2024-01-01; later runs stop 30 days before the newest item read last time; a change to the
operations' names or aliases (`ops_fingerprint`) reads the whole feed again. The lanes' report records stay in the
snapshot; the feed shows them only as reported-activity items.

## Reported activity (16 Nov 2026, Tom's "Yes, all five" to `_ideas\drafts\2026-11-16-undertow-emerging-ops.md`)
- **Unit (decision 1):** `undertow/activity.py`. One item per (reporter, operation), apart from disclosures: key
  `<lane>:activity:<op>`, the reporter, first and last report, count, every report link, and state **active**
  (last report within `QUIET_DAYS` = 180) or **quiet**, never "ended". 180, not 90, because DFRLab's 15 reports span
  30 months. Title "<op>: reported by <reporter>, last on <date> (active)", because a name match says the reporter
  wrote about the operation, not that it found it running (CheckFirst's two Portal Kombat matches are a dataset
  launch and an OpenCTI connector). `data_as_of` is the last report. STIX: a `report` on the operation's
  intrusion-set, no campaign. Adding the unit ended DFRLab's 15 per-article items (live for one day) in the history
  log and replaced them with 5.
- **Curation (decision 2):** tracked operations are matched automatically. New activity: `python tools/undertow.py
  triage` on the laptop only (it refuses when `GITHUB_ACTIONS` is set) writes influence-worded articles naming no
  tracked operation to `data/triage.jsonl` (git-ignored, never published; `check` fails if one of its headlines
  reaches a published file). Tom promotes rows by hand into `config/register/watch.json`; each row's URL must be on a
  host in its `reporter_hosts`, which also extends the leak scan's allowed prefixes. First run, 16 Nov (120 days): 3
  entries, one real (DFRLab, 12 Oct 2026, coordinated inauthentic networks before Armenia's elections), two
  CheckFirst event posts. **First row (Tom's "Armenia entry, as proposed", 16 Nov 2026):**
  `armenia-election-war-fears-2026`, "Inauthentic networks amplifying fears of war before Armenia's elections"
  (DFRLab's framing, no names), DFRLab B2, first report 2026-10-12, target Armenia only (Azerbaijan is named in the
  report but not entered as a target), no origin, `checked_by` empty, no tracked operation (so no STIX report: there
  is no intrusion-set to report on). `reporter_hosts`: `https://dfrlab.org/`. Item `UT-WATCH-c12152a686`, active,
  marked at Armenia.
- **Watch register widened (Tom's "Yes, as recommended", 16 Nov 2026, to
  `_ideas\drafts\2026-11-16-undertow-watch-candidates.md`):**
  - A row may list several `tracked_operations` (the older single `tracked_operation` still reads,
    `activity.row_operations`). They become the item's `named_operations`: corroboration and a STIX campaign
    `attributed-to` each intrusion set ("the publisher names this operation"), never origin or confidence. `closing`
    matches any of them.
  - Optional fields:
    - `activity_period` {from, to}: when the activity ran, which is not the report date. It goes in the summary.
    - `alignment`: a reporter's "state-aligned" or "Kremlin-aligned" is recorded as alignment, never origin, as
      the EEAS's wording is.
    - `label_starts_with_name`: the label keeps its capital mid-sentence.
  - A row from a reporter with its own lane counts in that lane's independence group (`dfrlab`, not `watch:dfrlab`).
  - The STIX campaign of a watch row carries the row's own grade, where it used to carry the lane's B3.
  - **Hand-entered reporter:** the G7 Rapid Response Mechanism (Global Affairs Canada), B2, source_type government.
    canada.ca terms, read 16 Nov 2026: non-commercial reproduction with the full title, the author and the URL.
    `reporter_hosts` now also holds `https://checkfirst.network/` and `https://international.canada.ca/`.
  - **Rows on 16 Nov 2026 (5):**
    - Armenia, DFRLab: gained `activity_period` 2026-01 to 2026-06; the election was 7 Jun 2026.
    - Armenia, CheckFirst, 10 Jun: Operation Overload, Portal Kombat, Storm-1516.
    - Bulgaria, DFRLab, 9 Jun: Portal Kombat; the vote was 19 Apr.
    - Roska Bridge, CheckFirst, 2 Jul: Portal Kombat; targets DE, FR, UA, US.
    - Armenia, G7 RRM, 26 Oct: the three operations, alignment RU.
  - **Waiting:**
    - The RRM's Poland statement: the page names no operation as read, though a search summary said the Pravda
      Network. Tom reads it first.
    - The RRM's Moldova report: not read yet.
    - VIGINUM's Rokh Solis: SGDSN's terms are unread because its site shows a browser check.
- **Reporters (decision 3):** DFRLab, CheckFirst, CORRECTIV. Not Alliance4Europe (feed still since Sep 2025) or
  Ukraine's CCD (a party to the war). VIGINUM and Canada's RRM only as hand-entered watch rows.
- **Origin (decision 4):** a reporter lane never adds an origin. A watch row's origin counts only when `checked_by`
  is set and `origin_evidence` is "own"; "cites-other" repeats a platform's attribution, the same line twice. Grades
  of the counted lines go into the confidence basis; still capped Moderate. `analysis.group()` gives a watch row its
  reporter's own independence group.
- **Terms (decision 5):** read before building (below).
- **Baseline (Tom's "Yes, all four", 16 Nov 2026, to `_ideas\drafts\2026-11-16-undertow-baseline-numbers.md`):**
  - Name-matched lead time is set aside. 2 of 22 named takedown events had an earlier report, both Doppelganger and
    left-censored, because platforms coin most names in the disclosure.
  - The baseline is the watch register's closing. New indicators in `doctrine/indicators.json`:
    - `UT-IND-3`: lead days from first report to the takedown a row is `closed_into`.
    - `UT-IND-4`: the share of rows closed within 12 months.
  - `UT-IND-1..2` keep their own meanings (corroboration; target-country quarterly count). Earlier notes tied lead
    time to them by mistake.
  - No anomaly rule and no warning tier before 10 closed rows; even then the measures are described, never rated.
  - `python tools/undertow.py closing [--months 12]` (laptop only; refuses in Actions; writes git-ignored
    `data/closing.json`) lists, per open row, disclosures up to 12 months after its first report that share a
    country (a stated target, else a country the description names, labelled "not a target") or name its tracked
    operation. Each candidate shows its period. Closed rows show their lead, and a `closed_into` that is not a dated
    disclosure on file is a problem (exit 1).
  - Run it after each collect that brings a new disclosure, about monthly.
  - First run, 16 Nov: the Armenia row has four Google Q3 2026 candidates (bulletin of 30 Oct, periods Jul to Sep
    2026, Armenia named in the stance, not a target). They acted before DFRLab's 12 Oct report, so none is a lead
    in the baseline's sense. Tom decides whether any closes the row.
  - Triage's default window is 180 days (was 60).
  - Volume: hand-entered VIGINUM and RRM rows as they publish. No new reporter lane until one shows current,
    on-topic output.
- **Cross-suite joins** (Tom's "Yes, as recommended", 16 Nov 2026, to
  `_ideas\drafts\2026-11-16-undertow-cross-suite-joins.md`):
  - **Standing listings (built 16 Nov 2026, not committed):** `config/operations.json` `organisations.entries`, one
    entry per hand-kept organisation, each `listings` row read from the publisher's own notice on 16 Nov 2026: list
    (Headwind's ids `ofac-sdn`, `eu-fsf`, `uk-sanctions`, `france-gels`, `canada-sema`), programme, listing date,
    notice URL and title, and where in the notice. SDA, ANO Dialog and Struktura: EU 28 Jul 2023 (Implementing Reg.
    2023/1563, entries 245-247), OFAC 20 Mar 2024 (SDA, Struktura; RUSSIA-EO14024) and 4 Sep 2024 (ANO Dialog), UK
    28 Oct 2024 (Financial Sanctions Notice, RUS2292-2294), Canada 21 Feb 2025 (SOR/2025-33, items 690-692). France's
    register only restates the EU act ((UE) 2023/1563), so no France row. Struktura's identity: the EU's entry 246
    gives "Struktura" as an alias and its TIN is the tax ID in OFAC's entry (`identity_note`). Haimai and CGTN are on
    none of the five lists. `undertow/listings.py`: `for_org`, `sentence`, `notice_urls` (the leak scan allows these
    exact addresses), `check` (run by `check`: hand-kept organisation, known list, ISO date, notice on the list
    publisher's own site, no extra fields such as a person's name). Shown as `operation.listed_by` on items whose
    publisher names the organisation (3 on 16 Nov), a "<org> is listed by EU (2023-07-28), ..." sentence in the
    summary, a "Listed by" row on the page, and STIX `external_references` on the threat-actor (no relationship).
    Confidence and origin unchanged (a test builds the feed with and without listings).
  - **Sanctions join:** in COP (branch `undertow/sanctions-join`, `tools/undertow_sanctions.py`), published off.
  - **Elections:** ElectionGuide's calendar is "for non-commercial use" and its Data Use Policy was not found, so
    fallback (a): hand-entered national elections in Verdict's calendar, kind `election`. Tom chose all 40 stated
    target countries (18 Nov 2026). 48 votes, 1 Nov 2024 to 31 Dec 2027, each from the electoral body's own page,
    8 entered unverified (Verdict branch `calendar/elections`; research and the not-yet-set dates in
    `D:\Projects\_ideas\drafts\2026-11-18-election-research\`). A re-read in Chrome on 18 Nov afternoon verified
    BG's runoff (cik.bg decision 441-PVR), MT (electoral.gov.mt voting notice), CO's runoff (Registraduría) and
    TD (ange.td calendar); `reread_patch.py` there. Still unverified: RU (cikrf.ru, kremlin.ru and pravo.gov.ru
    show error pages), CM (decree 2026/345 not on prc.cm), FR's two rounds (convocation decree not yet in the JO). The join is COP's `tools/undertow_elections.py`
    (branch `undertow/election-join`, published off): it uses `activity.activity_period` or the disclosure's
    `operation.period`, never a report date, so keep both filled.
  - **Press join:** set aside until a narrative lane exists.

Outputs in `site/data/`:
- `feed.geojson`: 425 items, 1.9 MB, linter PASS.
- `stix.json`: a STIX 2.1 bundle.
- `events.json`: Verdict calendar format; expected next disclosures, dates only, each titled "not a published date".
- `snapshot.json`: what the page reads.

The page also serves `doctrine/method.md` and `doctrine/confidence-mapping.md`.

**Dates (15 Nov 2026, kit 0.5.6):** `data_as_of` is the publisher's date. Where the publisher gives no time, the item
carries `data_as_of_precision`:
- `day`: Google's bulletins, the EEAS report, TikTok's report 8 and OpenAI posts dated midnight.
- `month`: OpenAI's case studies, which its feed dates at midnight on the 1st (`openai_rss.date_precision`). On
  15 Nov, 56 of OpenAI's 1,387 feed items sat at midnight on the 1st, about four times chance.

15 Nov count: 23 month, 361 day and 41 exact (Meta's commit times, TikTok's report 9 and two OpenAI posts). The
page shows "June 2026 (month only)" or "2026-10-30 (date only)", and COP shows the date or month in UTC. A lane that
fails keeps its last good records, which lack the field until the lane next succeeds.

## Health record and history log (built 15 Nov 2026, Tom's "Yes, build item 1")
- **Health:** the feed carries a `health` block (`feed.health()`), one entry per source, **keyed by the source id the
  items carry** (`meta-threat-research`, `google-iob`, `openai-news-rss`, `disinfocode-tiktok`, `eeas-fimi-4`), not by
  lane name: the kit's history log and COP's ledger take an item's lane from its first source id. Shape as Cordon's
  and Headwind's: state, last_ok, last_error, failures (consecutive, kept in the snapshot's `lanes`), checked_at,
  detail, plus lane and data_as_of (newest disclosure among the lane's items). State is `up` when read on this run
  and `failing` otherwise; the kit's fresh/late/stale would judge nothing, because disclosures have no fixed rhythm.
- **History:** `update.yml` runs `tic.py history site/data/feed.geojson --dir history --ended
  site/data/ended.geojson` after `check`, commits only `history/` to main with the workflow's token (which starts no
  run), then runs `check` again so `ended.geojson` is in the leak scan before the deploy. Copied from Headwind's
  step. `permissions: contents: write`. A failing lane ends nothing. `history/` holds published feed items only,
  never `data/raw` or the snapshot. The first run writes about 2.6 MB (425 `new` lines and the state).
- **Left for COP (its own worktree, on Tom's yes):** source rows `checkfirst-rss`, `correctiv-rss` and
  `undertow-watch-register` in `config/sources.json` (as `dfrlab-rss`, COP `4d76f56`, on COP's main since 16 Nov);
  check that COP's Undertow layer reads reported-activity items (they carry an `activity` block and no origin). And
  add Undertow's `ended` address
  (`https://undertow.theintelligence.company/data/ended.geojson`) to COP's `config/programs.json`, and consider
  `source_health: true`, so COP greys a failing lane's kept items as it does Headwind's.

## Hard rules and how they are held
- **Operation level only.** No indicator values, account handles, URLs or domains, or names of individuals in any
  output.
  - `text.scrub()` runs on every kept sentence. Links, handles, defanged values and bare domains become
    "[link withheld]".
  - A run of two or more unknown capitalised words, or one word after a title, becomes "[name withheld]". The
    heuristic misses a single surname with no title before it (assumption UT-ASM-4, "strained").
  - If a checked organisation or outlet is withheld by mistake, add it to `config/operations.json` `known_phrases`.
  - `check` scans every published file for defanged values, @handles and URLs outside the publishers' own pages
    (`ALLOWED_URL_PREFIXES` in `tools/undertow.py`).
  - The tests take every indicator value in Meta's real tables and assert that none reaches any output.
- **The raw copies (`data/raw/`, git-ignored) and `tests/fixtures/` hold publishers' full replies, Meta's indicator
  tables included** (the leak tests need real values). Both stay private: never publish `tests/` or `data/`, and
  the workflow caches only `data/snapshot.json`.
- **Never fetch tiktok.com or OpenAI's report pages.**
- **Origin is never read as sponsorship.** Three questions are kept apart (`doctrine/confidence-mapping.md`).
  - EEAS's "Russia-aligned" or "Chinese-aligned" for operations it calls non-attributed (Storm-1516, Operation
    Overload, Portal Kombat, Spamouflage, HaiEnergy) is recorded as `alignment`, never as origin, and those items
    carry no confidence level.
  - An operator is recorded only where the publisher names it (SDA, ANO Dialog, Struktura, Haimai, CGTN), as a reported
    `responsible` actor. Such items carry `us_person_data: organizations` because the linter requires it whenever an
    organisation is named (none is a US organisation).
- **Our confidence follows tic-confidence-1.0 and is about origin only.** It counts independent publishers naming
  the same operation (`config/operations.json`, by name or a publisher-given alias) with the same origin.
  - One publisher is Low; two is Moderate.
  - Origin is easy to fake (cap Moderate), and there is no scored Verdict record, so there is **no High**.
- **DISARM** (`config/disarm_rules.json`): 17 phrase rules, each mapping to one v1.6.1 technique, with basis `mapped`
  (the matched phrase is kept, except for Google).
  - **Reviewed by Tom on the evening of 14 Nov 2026 CST** (`review.status` "reviewed", `reviewed_on` 2026-11-15
    UTC), from `_ideas\drafts\2026-11-14-undertow-disarm-review.md`. 15 rules were approved as written. dr-04 lost
    the bare "AI-generated content" alternative, and dr-10 lost "standalone websites".
  - Every item's `disarm_rules_status` reads "reviewed". A technique is still Undertow's reading of the publisher's
    words, not the publisher's claim.
  - On 15 Nov, 56 of 425 items carry a technique. `basis: reported` is unused.
  - DISARM's STIX bundle is vendored as a cut in `config/disarm/DISARM-1.6.1-cut.json`, with its CC BY-SA 4.0
    marking.
- **EEAS register** (`config/register/eeas-fimi-4.json`): entered by the build session on 14 Nov. On 15 Nov a
  **second machine reading, not a person's check**, compared every row with printed pp. 28-34 and p. 14 of the PDF
  (sha256 matched); `checked_by` says so. On Tom's yes:
  - Four quotes went back to the report's exact words.
  - RRN/Media Brands' region "Africa" became "North Africa".
  - Five targets were added from pp. 32 and 34: Doppelgänger UA, Storm-1516 PL, Portal Kombat Africa, and
    Spamouflage the US and the European Union.
  - The origin bases for Doppelgänger and Paperwall were reworded to cite what the pages say.
  - Full list: `_ideas\drafts\2026-11-15-undertow-eeas-check.md`.
  - Tom has not read the rows himself.
- **STIX:**
  - Ids are UUIDv5 from namespace `uuid5(DNS, "undertow.theintelligence.company")` and a stable key. Timestamps come
    from the disclosure, so a rebuild is byte-identical unless the data change.
  - TLP:CLEAR is copied from OASIS `cti-stix-common-objects`.
  - A named organisation (16 Nov 2026, second slice, Tom's "continue working on open items"): `threat-actor` with
    `threat_actor_types` ["unknown"] and `resource_level` "organization", nothing more (no roles, goals, motivations,
    sophistication or aliases), `attributed-to` from each campaign whose own publisher names it, and `located-at`
    its country. Made only for a name hand-kept in `config/operations.json` or `config/register/`
    (`stix.named_organisations()`), and `validate()` refuses any other name, so free text or a person's name can
    never become one. Five on 16 Nov: Social Design Agency, ANO Dialog, Struktura (RU), Haimai and China Global
    Television Network (CN). CGTN comes from the EEAS's "linked to Chinese state-controlled media" (Falsos Amigos);
    the relationship says only that the publisher names the organisation.
  - Never emitted: indicator, observed-data, cyber-observables, a threat-actor for anything but a hand-kept
    organisation, or an identity for a person.

## Kit, house bar, layout
- Doctrine kit **0.5.6** vendored (tic-doctrine `5643761` since the history rewrite; `37a1dad` before it), synced on
  15 Nov with `python <tic-doctrine>/tools/sync.py D:/Projects/undertow`. Kit 0.5.6 adds `data_as_of_precision` and
  Undertow's corrected terms line. **The suite is at 0.5.9** (`5eec41a`, 16 Nov: 0.5.7 optional subdivisions, 0.5.8
  Launch's history source, 0.5.9 Relief live); none of the three changes Undertow's own entry, so a sync is
  housekeeping, on Tom's yes. Never edit `doctrine/kit/` here.
- House bar: `site_src/tic-nav.js` **v1.13** (v1.12 made it sticky with a minimize button, `79f99a1`; v1.13 added
  Wake, `28fb96d`) and `tic-time.js` v1.3, copied from the hub's `site/shared/` by the sessions that rolled the bar
  out. Copy bar files from the hub; never edit them here.
- Registers:
  - Requirements and intelligence needs: `UT-REQ-1`, `UT-PIR-1..3`, `UT-EEI-1..2`.
  - Indicators `UT-IND-1..4` are registered and unused (3 and 4, the watch-register baseline, since 16 Nov 2026);
    assumptions are `UT-ASM-1..4`.
  - There is no warning problem, because there is no baseline of disclosures.
  - Every item is kind observation, tier routine, `reported`, grade A2.

## Known limits
- **Only stated targets are marked on the map** (Tom, 16 Nov 2026, "Mark only target countries on the map"). Google
  and OpenAI name no target, so all their items (342 and 27 on 16 Nov) have no geometry and list under Off the map
  in COP; before, 249 Google and 15 OpenAI items were drawn on the countries their stance or summary names, which
  can include the operators' country. Those countries stay in `countries` and `countries_named` and the summary
  says they are not targets. A reporter's item is marked at countries its reports name that a disclosure of the
  same operation records as targets (`activity.place`): on 16 Nov, 5 of 9 (CORRECTIV's Storm-1516 at the US only,
  no longer Russia), 4 off the map. On 16 Nov, 47 of 434 items have geometry. On the page Google counts under
  "none named" in the origin-by-target matrix.
- Meta's "added" date is when the file entered the repository. The H2 2025 files were all added on 19 May 2026, so
  that date is later than the report.
- OpenAI's RSS gives no target and no Breakout category; its origin wording is only what the one line says.
- TikTok's Code reports are semiannual and partial (Europe and crises only), 3 to 8 months behind tiktok.com's
  monthly list.
- Google items are keyed by position (`google:2026-q3:2026-07:01`), so if Google edits a bulletin, that month's keys
  shift. Other lanes key on content.
- No anomaly rule yet: no baseline of disclosures. On 15 Nov, only Google's bulletins (TAG Bulletin pages answer
  back to Q3 2020) looked long enough for one; Meta has three README periods and OpenAI about ten report dates.
- History log: Google's keys are positional (above), so if Google edits a bulletin, that month logs as ended and new.

## Sources and terms (read 14 Nov 2026 unless marked)
- Meta threat-research: MIT (LICENSE and README). Summaries are quoted with "Copyright (c) Meta Platforms, Inc. and
  affiliates ... MIT License".
- Google: the ToS are ambiguous on scraping; robots.txt disallows only search paths. Tom: automate, facts and
  counts only.
- OpenAI: the Terms of Use (1 Jan 2026) bar programmatic extraction from its websites. The RSS feed is read and
  nothing else; titles and one-line summaries are quoted with credit.
- TikTok via disinfocode.eu: the Centre states no terms (none found), and robots.txt has an empty `Disallow:`.
  tiktok.com is never read (its terms bar automated extraction). TikTok's descriptions are quoted with credit.
- EEAS: reuse is authorised provided the source is acknowledged (legal notice, as recorded in the plan).
- DISARM v1.6.1: CC BY-SA 4.0 (LICENSE.md and the bundle marking; the README's CC-BY-4.0 line is the outlier).
- DFRLab (read 16 Nov 2026): Atlantic Council Terms and Conditions of Use (dfrlab.org/terms-of-use/ is a 404; the
  site is the Council's). Copies for noncommercial use with the Council's notices; automated access no faster than a
  person; no harvesting of personal information. robots.txt: empty `Disallow:`. Undertow keeps names, dates and
  links only and credits "Atlantic Council's Digital Forensic Research Lab".
- CheckFirst (read 16 Nov 2026): no terms of use published (privacy policy only). Its `llms.txt`: "welcome to read,
  index and cite this site", attributing findings to CheckFirst with a link. robots.txt allows all but admin and
  search. Names, dates and links only, credited "CheckFirst".
- CORRECTIV (read 16 Nov 2026): no terms of use or licence found (legal disclosure and imprint only;
  `/en/terms-of-use/`, `/nutzungsbedingungen/` and `/en/republishing/` answer 404), so all rights reserved. robots.txt
  does not disallow the feed. Facts only (operation named, date, link), as Tom set for Google.
- `config/operations.json` gained the alias "Pravda Network" (DFRLab's capitalisation of "Pravda network") for
  Portal Kombat, 16 Nov 2026.

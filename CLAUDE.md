# Undertow (`D:\Projects\undertow`)

Influence operations for The Intelligence Company (`tic-feed/2`, program id `undertow`, prefix `UT`): covert
influence operations that Meta, Google, OpenAI, TikTok and the EEAS have publicly disrupted or named, at
**operation level only**, tagged with DISARM v1.6.1 techniques and exported as STIX 2.1. Roadmap step 12. Name,
lanes and terms decisions: Tom, 14 Nov 2026 (spec: `D:\Projects\_ideas\drafts\2026-11-14-influence-ops-step12.md`,
section 6; programme row in `_ideas\new-programs.md`). Measurements and publishers' reports only: no probability.

## State, 15 Nov 2026 (about 3:30 PM CST): live

- **Repo:** `metacog-osint/undertow` (private, Tom's decision), branch `main`. Commits:
  - `3b4a72a`: the first live slice (14 Nov).
  - `305cb68`: house bar v1.11.
  - `d18db9a`: DISARM table reviewed by Tom.
  - `79f99a1`: house bar v1.12, from the house-bar rollout session.
  - `28fb96d`: house bar v1.13, from the session that listed Wake.
  - `e70194d`: EEAS register, second machine reading.
  - `d2d0b8f`: date precision and kit 0.5.6.
  - Then this notes rewrite.
  - Each commit and push needs Tom's yes. Push by named commit (`git push origin <sha>:refs/heads/main`) after
    listing what is ahead, and ask for each push by its sha (the auto-mode check refused pushes until Tom said
    "Push <sha>").
- **Site:** https://undertow.theintelligence.company. Cloudflare Pages project `undertow` (`undertow-cm3.pages.dev`);
  Tom added the Squarespace CNAME, and the domain has been active with HTTPS and HSTS since 4:21 PM CST on 14 Nov.
  `.github/workflows/update.yml` runs on every push to `main`, on cron `41 */6 * * *` and on workflow_dispatch:
  tests, kitcheck, the last snapshot from the Actions cache, collect, build, check, then
  `wrangler pages deploy site --project-name undertow`. It uses secret `CLOUDFLARE_PAGES_TOKEN` and repo variable
  `CLOUDFLARE_ACCOUNT_ID` (set with `--body`; a PowerShell pipe's BOM broke Headwind's). Every run on 14 and 15 Nov
  passed (43643868752, 43645582544, 43662903183, 43670100913, 43688512599, 43729348150, 43750332277).
- **tic-dispatch:** the hub's Worker (`dispatch/dispatch.js`) starts `update.yml` at :30 past 02, 08, 14 and 20 UTC.
  **Tom's step, still open on 15 Nov:** add `undertow` to the dispatch token's repository access. Until then those
  starts fail (404) and the cron is the clock; no dispatched run had happened by 1:48 PM CST on 15 Nov.
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
python -m unittest discover -s tests           # 29 offline tests on recorded real replies
python tests/make_fixtures.py                  # re-record fixtures from the raw copies of the last collect
python tools/serve.py                          # site/ on http://127.0.0.1:8781 with _headers (CSP); launch entry `undertow-site`
python doctrine/kit/tic.py lint site/data/feed.geojson --doctrine doctrine
python doctrine/kit/tic.py kitcheck            # the vendored kit is intact
```

`collect` never falls back to made-up data. A lane that fails keeps its last good copy (`from_previous`) or stays
empty, and `lanes` in the snapshot says which. Standard library only (Python 3.12+).

## Lanes (first collect 14 Nov 2026; 15 Nov: 425 items)

| Lane | Module | Source and how it is read | Items |
|---|---|---|---|
| `meta` | `meta.py` | `github.com/meta/threat-research` (MIT). Read: the README table (period, title, origin, targets, link), each network's Markdown file from raw.githubusercontent, and one GitHub API call (`/commits?per_page=100`) for when each file was added (commit messages "Add threat indicators: <file>"; `GITHUB_TOKEN` used if set, never recorded). Kept: title, period, origin, targets, Meta's counts (accounts, Pages, followers), Meta's network summary (first paragraphs up to 1,400 characters, scrubbed, quoted with the MIT notice) and the indicator **count** by type | 22 (H2 2026 10, H1 2026 6, H2 2025 6) |
| `google` | `google.py` | Influence Operations Bulletin pages, `blog.google/security/influence-operations-bulletin-qN-YYYY/`, every quarter from Q1 2026 to the current one, plus any in `blog.google/security/rss/`. A 404 means not yet published. Facts and counts only: month, asset counts, linked-to country, languages, countries the stance names. The stance wording is read for DISARM rules and never kept (the matched phrase is null). Unparsed entries are kept and counted | 342 (Q1 91, Q2 158, Q3 93) |
| `openai` | `openai_rss.py` | `openai.com/news/rss.xml` ONLY. `fetch_allowed()` refuses any other openai.com URL, and a test holds it. An item is an operation when its title or summary says "influence" (not Global Affairs); round-ups are disclosures. Kept: operation name, origin wording, the one-line summary (scrubbed, quoted with credit). Since 1 Jan 2024 | 27 operations, 6 round-ups |
| `tiktok` | `tiktok.py` | EU Code of Conduct Transparency Centre JSON, `disinfocode.eu/reports/tiktok/<n>/json`: reports 8 (Jul-Dec 2025) and 9 (Jan-Jun 2026), probing two numbers ahead. NEVER tiktok.com. Networks come from Commitment 14 TTP 6, the crisis chapter and the elections chapter, merged on (origin, accounts, followers). TikTok's description is quoted with credit | 25 (report 8: 8, report 9: 17) |
| `eeas` | `eeas.py` | `config/register/eeas-fimi-4.json`: the nine Information Manipulation Sets of the 4th EEAS FIMI report (12 Mar 2026), entered once from the PDF (sha256 recorded), each row and quote cited to its printed page. Each run reads the EEAS FIMI page to confirm the report is listed and to notice a 5th | 9 |

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
  - Never emitted: indicator, observed-data, cyber-observables, threat-actor, or an identity for a person.

## Kit, house bar, layout
- Doctrine kit **0.5.6** (tic-doctrine `37a1dad`), synced on 15 Nov with `python <tic-doctrine>/tools/sync.py
  D:/Projects/undertow`. Kit 0.5.6 adds `data_as_of_precision` and Undertow's corrected terms line. Never edit
  `doctrine/kit/` here.
- House bar: `site_src/tic-nav.js` **v1.13** (v1.12 made it sticky with a minimize button, `79f99a1`; v1.13 added
  Wake, `28fb96d`) and `tic-time.js` v1.3, copied from the hub's `site/shared/` by the sessions that rolled the bar
  out. Copy bar files from the hub; never edit them here.
- Registers:
  - Requirements and intelligence needs: `UT-REQ-1`, `UT-PIR-1..3`, `UT-EEI-1..2`.
  - Indicators `UT-IND-1..2` are registered and unused; assumptions are `UT-ASM-1..4`.
  - There is no warning problem, because there is no baseline of disclosures.
  - Every item is kind observation, tier routine, `reported`, grade A2.

## Known limits
- Google names no target. Its items' geometry is on the countries the stance names (`countries_named`), and on the
  page they count under "none named" in the origin-by-target matrix.
- Meta's "added" date is when the file entered the repository. The H2 2025 files were all added on 19 May 2026, so
  that date is later than the report.
- OpenAI's RSS gives no target and no Breakout category; its origin wording is only what the one line says.
- TikTok's Code reports are semiannual and partial (Europe and crises only), 3 to 8 months behind tiktok.com's
  monthly list.
- Google items are keyed by position (`google:2026-q3:2026-07:01`), so if Google edits a bulletin, that month's keys
  shift. Other lanes key on content.
- No anomaly rule, no history log (`tic.py history`) and no `health` block in the feed yet.

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

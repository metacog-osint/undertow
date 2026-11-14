# Undertow (`[local path]`)

Influence operations for The Intelligence Company (`tic-feed/2`, program id `undertow`, prefix `UT`): covert
influence operations that Meta, Google, OpenAI, TikTok and the EEAS have publicly disrupted or named, at
**operation level only**, tagged with DISARM v1.6.1 techniques and exported as STIX 2.1. Roadmap step 12. Name,
lanes and terms decisions: Tom, 14 Nov 2026 (spec: `[local path]`,
section 6; programme row in `_ideas\new-programs.md`). Measurements and publishers' reports only: no probability.

**State, 14 Nov 2026 (built by a side session, about 3:30 PM CST): first live slice, local only.** All five lanes
collect live; `check` PASS (registers, tradecraft linter, STIX check, leak scan); 28 offline tests pass; the page
was looked at in the browser pane at desktop width and 375 px, light and dark, with the CSP served by
`tools/serve.py` (no console errors, no CSP violations, no sideways scroll). `git init` done, **nothing committed**
(each commit needs Tom's yes). **Not done, each needs Tom's own yes:** the GitHub repo (private, Tom's decision),
first commit and push, the Cloudflare Pages project `undertow`, secrets, DNS (`undertow.theintelligence.company`),
the `tic-dispatch` entry, house bar, registry row and COP layer. The permission emails to TikTok and OpenAI
(`_ideas\drafts\2026-11-14-undertow-permission-emails.md`) are Tom's to send.

## Commands

```bash
python tools/undertow.py collect               # fetch every live lane into data/snapshot.json
python tools/undertow.py collect --only meta   # one or more lanes; the rest keep their last copy
python tools/undertow.py build                 # build site/ from data/snapshot.json
python tools/undertow.py check                 # registers, feed linter, STIX check, leak scan
python -m unittest discover -s tests           # 28 offline tests on recorded real replies
python tests/make_fixtures.py                  # re-record fixtures from the raw copies of the last collect
python tools/serve.py                          # site/ on http://127.0.0.1:8781 with _headers (CSP); launch entry `undertow-site`
python doctrine/kit/tic.py lint site/data/feed.geojson --doctrine doctrine
```

`collect` never falls back to made-up data. A lane that fails keeps its last good copy (`from_previous`) or stays
empty, and `lanes` in the snapshot says which. Standard library only (Python 3.12+).

## Lanes (first collect 14 Nov 2026, 3:22 PM CST; last 3:27 PM CST, 21:27 UTC)

| Lane | Module | Source and how it is read | Items |
|---|---|---|---|
| `meta` | `meta.py` | `github.com/meta/threat-research` (MIT): README table (period, title, origin, targets, link) and each network's Markdown file from raw.githubusercontent; one GitHub API call (`/commits?per_page=100`) for when each file was added (commit messages "Add threat indicators: <file>"; `GITHUB_TOKEN` used if set, never recorded). Kept: title, period, origin, targets, Meta's counts (accounts, Pages, followers), Meta's network summary (first paragraphs up to 1,400 characters, scrubbed, quoted with the MIT notice), the indicator **count** by type | 22 (H2 2026 10, H1 2026 6, H2 2025 6) |
| `google` | `google.py` | Influence Operations Bulletin pages, `blog.google/security/influence-operations-bulletin-qN-YYYY/`, every quarter from Q1 2026 to the current one plus any in `blog.google/security/rss/`; a 404 is "not yet published" (Q4 2026 on 14 Nov). Facts and counts only: month, asset counts, linked-to country, languages, countries the stance names. The stance wording is read for DISARM rules and never kept (matched phrase is null). Unparsed entries are kept and counted | 342 (Q1 91, Q2 158, Q3 93; 0 unparsed) |
| `openai` | `openai_rss.py` | `openai.com/news/rss.xml` ONLY. `fetch_allowed()` refuses any other openai.com URL and a test holds it. An item is an operation when its title or summary says "influence" (not Global Affairs); round-ups ("Disrupting malicious uses of AI: October 2025") are disclosures. Kept: operation name (quoted name kept as written), origin wording, one-line summary (scrubbed, quoted with credit). Since 1 Jan 2024 | 27 operations, 6 round-ups |
| `tiktok` | `tiktok.py` | EU Code of Conduct Transparency Centre JSON, `disinfocode.eu/reports/tiktok/<n>/json`, reports 8 ("March 2026", Jul-Dec 2025) and 9 ("September 2026", Jan-Jun 2026), probing two numbers ahead (10 and 11 answered 404). NEVER tiktok.com. Networks from Commitment 14 TTP 6, the crisis chapter and the elections chapter, merged on (origin, accounts, followers) | 25 (report 8: 8, report 9: 17) |
| `eeas` | `eeas.py` | `config/register/eeas-fimi-4.json`: the nine Information Manipulation Sets of the 4th EEAS FIMI report (12 Mar 2026), entered once by this session from the PDF (sha256 recorded), each row and quote cited to its printed page. Each run reads the EEAS FIMI page to confirm the report is listed and to notice a 5th | 9 |

Outputs in `site/data/`: `feed.geojson` (425 items, 1.9 MB, linter PASS), `stix.json` (STIX 2.1 bundle: 425
campaigns, 20 reports, 63 locations, 23 intrusion-sets, 16 DISARM attack-patterns, 524 relationships),
`events.json` (Verdict calendar format: Google Q4 2026 bulletin about 31 Jan 2027, Meta's next report about 25 Feb
2027, EEAS 5th report about 12 Mar 2027, Code report 10 about 25 Mar 2027; dates only, kind `data_release`, each
titled "not a published date"), `snapshot.json` (what the page reads). The page also serves `doctrine/method.md`
and `doctrine/confidence-mapping.md`.

## Hard rules and how they are held
- **Operation level only.** No indicator values, account handles, URLs or domains, or names of individuals in any
  output. `text.scrub()` runs on every kept sentence: links, handles, defanged values and bare domains become
  "[link withheld]"; a run of two or more unknown capitalised words, or one after a title, becomes "[name
  withheld]" (10 spans withheld in the 14 Nov collect, e.g. Viktor Orbán in TikTok's text, the names of Pages in
  Meta's Taiwan network). The heuristic misses a single surname with no title before it (assumption UT-ASM-4,
  "strained"). Add a checked organisation or outlet to `config/operations.json` `known_phrases` when it is
  withheld by mistake. `check` scans every published file for defanged values, @handles and URLs outside the
  publishers' own pages (`ALLOWED_URL_PREFIXES` in `tools/undertow.py`); the tests take every indicator value in
  Meta's real tables and assert none reaches any output.
- **The raw copies (`data/raw/`, git-ignored) and `tests/fixtures/` hold publishers' full replies, Meta's indicator
  tables included** (the leak tests need real values). Both stay private: never publish `tests/` or `data/`, and
  the workflow caches only `data/snapshot.json`.
- **Origin is never read as sponsorship.** Three questions kept apart (`doctrine/confidence-mapping.md`). EEAS's
  "Russia-aligned" or "Chinese-aligned" for operations it calls non-attributed (Storm-1516, Operation Overload,
  Portal Kombat, Spamouflage, HaiEnergy) is recorded as `alignment`, never origin, and those items carry no
  confidence level. An operator is recorded only where the publisher names it (SDA, ANO Dialog, Struktura, Haimai,
  CGTN), as a reported `responsible` actor; such items carry `us_person_data: organizations` because the linter
  requires it whenever an organisation is named (none of them is a US organisation).
- **Our confidence, tic-confidence-1.0, about origin only:** independent publishers naming the same operation
  (`config/operations.json`, name or publisher-given alias) with the same origin. One is Low, two Moderate; origin
  is easy to fake (cap Moderate) and there is no scored Verdict record, so **no High**. 14 Nov: 301 Low, 6
  Moderate (Doppelganger by Meta, OpenAI and EEAS; IUVM by Meta and OpenAI), 118 none (no origin stated).
  STIX `confidence`: Low 15, Moderate 50.
- **DISARM**: `config/disarm_rules.json`, 17 phrase rules (the plan's 11 candidates plus 6), each to one v1.6.1
  technique; basis `mapped`, phrase kept (not for Google). **The table is "proposed": the plan says Tom reviews it
  before use**, and every item says so (`disarm_rules_status`) and the page says to read techniques as
  provisional. To approve: set `review.status` to `reviewed` with name and date. 56 of 425 items carry a technique.
  `basis: reported` is unused: the EEAS report cites T0075/T0076/T0079 for narratives in general, not per IMS.
  DISARM's STIX bundle is vendored as a cut in `config/disarm/DISARM-1.6.1-cut.json` (the DISARM identity, its
  "CC-BY-SA-4.0 DISARM Foundation" marking, the 17 used attack-patterns unchanged, and an index of all 391 ids;
  full bundle sha256 recorded, fetched at tag v1.6.1).
- **STIX**: ids UUIDv5 from namespace `uuid5(DNS, "undertow.theintelligence.company")` and a stable key;
  timestamps from the disclosure, so a rebuild is byte-identical except when the data change. TLP:CLEAR copied
  from OASIS `cti-stix-common-objects` (`config/stix_markings.json`, checked 14 Nov). Never emitted: indicator,
  observed-data, cyber-observables, threat-actor, an identity for a person. `stix.validate()` checks required
  properties, id form, timestamps, references and the four allowed relationship types.

## Kit, house bar, layout
- Doctrine kit **0.5.0** (tic-doctrine `origin/main` at `0ffc003`, the newest released; the local `main` checkout
  in `[local path]` is at 0.4.9, so the kit was exported from `origin/main` with `git archive` and
  synced from there; that checkout was not touched). `python doctrine/kit/tic.py kitcheck` passes.
- House bar: `tic-nav.js` **v1.10** and `tic-time.js` v1.3 copied from the hub's `site/shared/` (the brief said
  v1.9; the hub had moved to v1.10). Undertow is not in the Programs menu yet (`data-current="undertow"` is set
  for when it is); adding it is a hub change for Tom's yes.
- Registers: `UT-REQ-1`, `UT-PIR-1..3`, `UT-EEI-1..2`; no warning problem (no baseline of disclosures);
  `UT-IND-1..2` registered, unused; `UT-ASM-1..4`. Every item is kind observation, tier routine, `reported`, grade A2.
- `.github/workflows/update.yml`: written, never run. Every 6 h (cron fallback; meant for `tic-dispatch`),
  tests, kitcheck, snapshot from the Actions cache, collect, build, check, save, `wrangler pages deploy site
  --project-name undertow`. Needs `CLOUDFLARE_PAGES_TOKEN` and repo variable `CLOUDFLARE_ACCOUNT_ID` (set with
  `--body`, not a PowerShell pipe: a BOM broke Headwind's). No API key is needed.

## Known limits
- Google names no target: its items' geometry is on the countries the stance names (`countries_named`), and on
  the page they count under "none named" in the origin-by-target matrix. 106 Google entries name no country.
- Meta's "added" date is when the file entered the repository. The H2 2025 files were all added 19 May 2026, so
  that date is later than the report.
- OpenAI's RSS gives no target and no Breakout category; its origin wording is only what the one line says (the
  8 Oct 2026 "false front" item names none).
- TikTok's Code reports are semiannual and partial (Europe and crises only), 3 to 8 months behind tiktok.com's
  monthly list.
- Items are keyed by position for Google (`google:2026-q3:2026-07:01`): if Google edits a bulletin, keys from that
  month shift. Other lanes key on content (Meta file name, OpenAI slug, TikTok origin/accounts/followers, EEAS id).
- No anomaly rule, no history log (`tic.py history`) yet, no `health` block in the feed.
- EEAS register rows were entered by this session and are `checked_by: null`; a person should read them against
  pp. 28-34 of the PDF.

## Sources and terms (read 14 Nov 2026 unless marked)
- Meta threat-research: MIT (LICENSE and README). Summaries quoted with "Copyright (c) Meta Platforms, Inc. and
  affiliates ... MIT License".
- Google: ToS ambiguous on scraping; robots.txt disallows only search paths. Tom: automate, facts and counts only.
- OpenAI: Terms of Use (1 Jan 2026) bar programmatic extraction from its websites; the RSS feed is read, nothing else.
- TikTok via disinfocode.eu: the Centre states no terms (none found); robots.txt `Disallow:` empty. tiktok.com
  never read (its terms bar automated extraction).
- EEAS: reuse authorised provided the source is acknowledged (legal notice, as recorded in the plan).
- DISARM v1.6.1: CC BY-SA 4.0 (LICENSE.md and bundle marking; the README's CC-BY-4.0 line is the outlier).

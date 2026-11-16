# Undertow method (`undertow-1.0`)

## Purpose
Undertow records influence operations that platforms and governments have publicly disrupted or named: who
published the takedown, when, where the publisher says the operators worked, whom they targeted, at what scale, and
which DISARM techniques the publisher's own description shows. It is the suite's influence-operations layer.
**Operation level only.** It never stores indicator values, account handles, URLs or domains, or the names of
individuals. It states no probability.

## Lanes (first live slice, 14 Nov 2026)

| Lane | Source | Read how | Cadence | Kept |
|---|---|---|---|---|
| `meta` | Meta threat-research repository on GitHub (MIT) | README table and each network's Markdown file; one GitHub API call for the dates files were added | Twice a year | Title, period, origin, targets, Meta's counts, Meta's network summary (scrubbed, quoted under MIT), the indicator **count** by type |
| `google` | Google Influence Operations Bulletin | Quarterly pages found from blog.google's security RSS and the URL pattern, Q1 2026 onward | Quarterly | Month, counts of channels, blogs, accounts and domains, the linked-to country, languages, countries named in the stance. No bulletin text. Unparsed entries kept and counted |
| `openai` | OpenAI news RSS feed only | `openai.com/news/rss.xml`; report pages never fetched (OpenAI's terms bar programmatic extraction) | Irregular | Operation name, origin wording, the one-line summary (scrubbed, quoted with credit) |
| `tiktok` | TikTok's reports to the EU Code of Conduct on Disinformation | Transparency Centre JSON, `disinfocode.eu/reports/tiktok/<n>/json`; never tiktok.com (TikTok's terms bar automated extraction) | Semiannual | Origin, target audience, accounts, followers, the month where the elections chapter gives it, TikTok's description (scrubbed) |
| `eeas` | EEAS 4th report on FIMI threats (March 2026) | Named Information Manipulation Sets entered once into `config/register/eeas-fimi-4.json`, each row cited to its printed page; the FIMI page is read each run for a newer report | Annual | Name, aliases EEAS gives, attribution wording, operators EEAS names, alignment, targets, counts, short behaviour quotes with pages |
| `dfrlab` | Atlantic Council's Digital Forensic Research Lab (from 16 Nov 2026) | `dfrlab.org/feed/` RSS pages, one at a time with a pause; never the article pages | Several a month | Reporter lane (below). Grade B2 |
| `checkfirst` | CheckFirst, a Finnish research firm (from 16 Nov 2026) | `checkfirst.network/feed/` RSS pages, as DFRLab's | A few a month | Reporter lane. Grade B2 |
| `correctiv` | CORRECTIV, a German investigative newsroom, English feed (from 16 Nov 2026) | `correctiv.org/en/feed/` RSS pages, as DFRLab's | Several a week, few on influence operations | Reporter lane. Grade B3: a newsroom often reports other researchers' findings |
| `watch` | Undertow's watch register, `config/register/watch.json` (from 16 Nov 2026) | Entered by hand from the private triage list (below) | When Tom promotes a row | Reported activity that names no tracked operation |

**Reporter lanes** keep an article only when its title or one-line description names an operation already listed in
`config/operations.json` (by name or a publisher-given alias, case-sensitive). They keep the operations named, the
date, the link, countries named and platforms from a fixed list. They never keep the reporter's title, text, authors
or attribution, because headlines name individuals. A match on a name says that the reporter wrote about the
operation, not that it found the operation running.

## What an item is
Two units, kept apart (Tom, 16 Nov 2026). Both are kind `observation`, tier `routine`, `status_class: reported`.

- **A disclosure:** one item per network or operation a platform or government disclosed. Source grade **A2**: the
  publisher is reliable on its own enforcement actions; the takedown is probably true and cannot be confirmed from
  outside. Disclosures arrive 1 to 8 months after the activity.
- **Reported activity:** one item per operation and reporter. It says that an independent reporter has reported the
  operation while it runs: the reporter, the first and last report, the number of reports and their links, and a
  state. The state is **active** while the last report is no more than 180 days old, and **quiet** after that.
  It is never "ended": a reporter falling silent is not evidence that an operation stopped. 180 days, because
  DFRLab's 15 reports on tracked operations span 30 months. Graded by the reporter, B2 or B3.

**Two ways in.**
1. Tracked operations are matched automatically by the reporter lanes.
2. New, unnamed activity goes to a **private triage list**. `python tools/undertow.py triage` runs on Tom's laptop
   only (it refuses to run in GitHub Actions). It reads each reporter's feed back 60 days and writes
   influence-worded articles that name no tracked operation to `data/triage.jsonl`, which is git-ignored and never
   published. `check` fails if any of its headlines reaches a published file. Tom promotes what matters by hand into
   the **watch register**: a cited row with the operation as the reporter frames it (never a person's name), the
   countries, the first report and the reporter's attribution wording. A row can later be closed into a disclosure
   when a platform names the network.

**Origin from a reporter.** A reporter lane never adds an origin. A watch row's origin counts toward our origin
confidence only when Tom has checked the row and the reporter shows its own evidence for the origin
(`origin_evidence: own`). A reporter repeating a platform's or government's attribution (`cites-other`) is the same
line counted twice, so it does not count. The cap stays Moderate.

No anomaly rule and no warning tier yet. The first baseline will match each later takedown to its earlier reports,
measuring lead time and reporting rate (`UT-IND-1..2`). Part of that lead time is the referral pipeline: platforms
often act because researchers send them what they found, so lead time is not an independent warning signal.

## Three questions kept apart
1. **Did the takedown happen?** The publisher's own report of its own action: A2, `reported`.
2. **Where were the operators?** The publisher's judgment, kept verbatim (`origin_wording`) with the publisher's
   stated level (`origin_level_stated`: high, moderate or none; see `confidence-mapping.md`).
3. **Who directed it?** Recorded only when a publisher names an operator (`sponsor`, as reported actors).
   **Origin is never read as sponsorship.** "Aligned with Russia" (EEAS on Storm-1516 and Operation Overload, which
   it calls non-attributed) is recorded as alignment, never as origin.

Our confidence follows tic-confidence-1.0 and is about question 2 only: see `confidence-mapping.md`.

## Text guards (`undertow/text.py`)
Every sentence kept from a publisher passes `scrub()`: URLs, e-mail addresses, @handles, defanged values and bare
domains become "[link withheld]"; a run of two or more capitalised words that are not known places,
organisations, platforms, operation names or ordinary words, or one after a title ("Prime Minister X"), becomes
"[name withheld]". The rule leans towards withholding. A single surname with no title before it is not caught; that
is assumption UT-ASM-4, marked strained. The count of withheld spans is on every item. The build's `check` scans
every published file for defanged values, handles and URLs outside the publishers' own disclosure pages.

## DISARM (`config/disarm_rules.json`)
DISARM Framework v1.6.1 (CC BY-SA 4.0). A technique is attached only when a rule in the published table matches the
publisher's own words; the matched phrase is kept (for Google, not kept: facts only). `basis: mapped` means it is
Undertow's reading, not the publisher's claim; `basis: reported` is for a publisher that cites an id for one
operation (none in this slice). A behaviour no rule matches stays as text. **The rule table was reviewed by Tom on 14
Nov 2026** (15 rules as drafted, two narrowed so that an unnamed medium is not read as images and a standalone
website is not read as a news site); every item says so (`disarm_rules_status`).

## Outputs
- `data/feed.geojson`: tic-feed/2. Geometry on the target countries the publisher names; Google and OpenAI name
  none, so their geometry is on the countries named in the stance or summary (`countries_named`), and null when none
  is named.
- `data/stix.json`: a STIX 2.1 bundle with deterministic UUIDv5 ids. Report per disclosure, campaign per network,
  a report per reported-activity item on the operation's intrusion-set (no campaign, origin or relationship),
  location with `originates-from` and `targets`, DISARM's own attack-pattern objects (unchanged, with DISARM's CC
  BY-SA marking) with `uses`, intrusion-set with `attributed-to` for named operations, TLP:CLEAR and a statement
  marking per source licence. Never: indicator, observed-data, cyber-observables, an identity for a person.
- `data/events.json`: expected next disclosures for Verdict's calendar, on each publisher's past pattern. Dates
  only, no probabilities; none is a published schedule.

## What the method does not do
- It does not judge whether an operation worked, how far it reached, or who sponsored it.
- It does not read OpenAI's report pages or tiktok.com, so OpenAI's Breakout Scale and TikTok's monthly list are
  missing. Permission emails to both are drafted for Tom.
- TikTok's Code of Conduct reports cover only networks that touched Europe or a crisis, 3 to 8 months behind TikTok's
  own monthly list.
- Google names no target; the countries its stance names are not targets.

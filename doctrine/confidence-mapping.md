# Confidence mapping (Undertow, `undertow-1.0`)

Published as the plan's section 4 promised (the private planning notes).

## Three questions, kept apart
1. **Did the takedown happen?** The publisher reports its own enforcement action. Source grade **A2** (reliable on
   its own actions; probably true, not independently confirmable). `status_class: reported`.
2. **Where were the operators?** (origin) The publisher's judgment.
3. **Who directed it?** (sponsor) A separate, stronger claim. **Origin is never read as sponsorship.** "Operated
   from Russia" is not "Russian state". A sponsor is recorded only when the publisher names one.

## The publisher's stated level (`origin_level_stated`)
The publisher's wording is kept verbatim (`origin_wording`, STIX `x_tic_attribution_wording`) and sorted:

| Publisher's words | Publisher's stated level |
|---|---|
| "high confidence", "very high confidence", or a named state body or company that runs it | High |
| "originated in", "operated from", "-origin", "we assess that this network operated from" | Moderate |
| "linked to" (Google) | Moderate for origin; nothing for sponsor |
| "could not attribute", "unattributed", "non-attributed", or only "aligned" | None |

## Our confidence (tic-confidence-1.0)
Our confidence is not the publisher's level. It is about origin only, and the lines of evidence are **independent
publishers naming the same operation with the same origin** (a named operation in `config/operations.json`, matched
by its name or an alias the publisher gives).

- One publisher: **Low**.
- Two independent publishers: **Moderate**.
- High needs three, no contradiction, an alternative examined and a scored Verdict record. Origin is also easy to
  fake (false flags), which caps it at **Moderate** (`ease_of_faking: high`). **No High in this slice.**
- A different origin for the same operation from another publisher is a contradiction (`contradicted: true`).
- An item with no origin stated carries no confidence level.

Each item's `confidence_basis` gives the rubric, the publishers counted (`lines`), the caps applied and what would
raise it.

## To STIX
STIX 2.1 Appendix A: `confidence` on the campaign uses the None/Low/Med/High scale: Low 15, Moderate 50 (High 85,
unused). The DNI (ICD 203) scale in Appendix A is a likelihood scale and is not used, since these items carry no
probability. The Admiralty grade goes in `x_tic_source_grade` ("A2"); a consumer that needs a number can use
Appendix A's Admiralty credibility row (2 -> 70).

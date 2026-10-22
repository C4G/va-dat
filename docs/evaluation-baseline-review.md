# Approved decisions for the supplied Human audit

The approved Evaluation baseline is retained locally under
`vision_aid/evaluation/baselines/f8e9c83d5de8155cd81c4d9c15180c6e38640a5aba7323d35040b81e39aa6c9a.json`.
The JSON is untracked and is not distributed with the repository.
It contains one classification and reason for each of the 86 original Human
findings and an explicit Programmatic decision for each of the 198 applicable
page review rows. Its selection key is the SHA-256 checksum of the supplied
`Pristine Accessibility Defect Report.xlsx`, not a model, snapshot, or run.

The review used the original Defect report and URL list, the existing semantic,
forms, and nontext rules, and the actual saved HTML and Programmatic findings for
all 17 pages. An initial decision record was saved outside the repository before
opening either old model-specific review. Further direct inspections and the
comparison below refined that record. Earlier reviews were never authoritative.

The final classifications are **18 Programmatic, 63 LLM, and 5 not testable**.
None of the original findings is too ambiguous to classify. Source identities,
original text, and repeated job titles remain separate. The seven Globals repeat
on 17 pages, producing 82 Programmatic, 111 LLM, and 5 not-testable page rows.
Combined results still count each original once.

## Existing rules and complete matches

The JSON records exact rule identifiers and the relevant DOM path in the saved
checker evidence. These descriptions resolve to each run's own finding IDs.
Every selector was checked against both saved evidence sets; each resolves to
exactly one finding, with no reuse between Human findings on the same page.

| Original source rows | Human defect | Approved existing evidence |
| --- | --- | --- |
| 2 | Missing main region, Global | `LAND_001` on each page's body |
| 3 | Header logo's empty alternative, Global | `NON_TEXT_002` on the linked header logo |
| 4 | Unnamed navigation, Global | Both `LAND_005` header navigation findings jointly |
| 8 | Missing skip link, Global | `NAV_001` on each page's body |
| 9, 18, 24, 29 | Multiple h1 headings | All `HEAD_002` findings on the relevant page |
| 38 | Careers heading structure | `HEAD_001` on Open Positions h4, jointly with both `HEAD_002` findings on Hello! and Open Positions h1 |
| 46, 49, 54, 59, 64, 69, 74, 79, 84 | Job-page h1-to-h6 hierarchy | `HEAD_001` on the exact reported job heading |

Careers is a joint match: the skipped h4 and repeated level-one structure expose
both Open Positions headings and the reported hierarchy. A shared criterion or
one partial structural finding alone would not be enough.

These decisions select 118 actual Programmatic findings per Full evaluation to
cover the 82 applicable Programmatic page rows. The header logo match does not
claim the distinct unlinked footer logo. No complete Programmatic cross-catch was
established for an LLM-classified finding; each deliberate absence has a reason.
For example, required-attribute findings do not cover missing asterisk
instructions or autocomplete tokens, and missing iframe titles do not cover
company heading markup. Multiple h1 findings do not establish that every
paragraph heading is unnecessary or that repeated Presto wording is descriptive.

## Semantic and unavailable evidence

The 63 Human findings assigned to the LLM require judgment about meaning, intended structure, or
accessibility patterns absent from existing rules. The JSON gives an individual
reason for every original finding, including these distinctions:

- The forms checker has no autocomplete rule. Contact's missing tokens remain
  LLM responsibility.
- The nine job back links contain U+F104; Careers' same-page link contains U+F107.
  `LINK_001` treats these private-use glyphs as nonempty text. Their missing
  descriptions require LLM judgment. Every job back link was located directly.
- Unlinked images with `alt=""` are outside the existing missing-alt and
  linked-image rules. This includes the footer logo, Careers image, Mail images,
  and Contact's Mobile/Mail/Laptop images.
- Footer lists and intended headings, quotations, decorative text glyphs,
  descriptive titles/links, and inappropriate paragraph headings require
  semantic judgment. The unnamed Lottie wrapper under Our DNA is not an img
  missing an alt attribute.
- Home and Clients carousel configuration explicitly enables autoplay and
  infinite rotation with navigation disabled and no pause control. That static
  evidence supports an LLM assessment of missing movement controls.
- The KAI video markup lacks a captions track, and the page contains no transcript
  or transcript link. Existing Programmatic rules do not check those omissions.
- Contact's exact company/location names appear in strong elements in the outer
  page next to the maps. Their missing heading markup is assessable without
  loading the external iframe documents.

The five not-testable originals remain in the Overall denominator:

| Source row | Reason |
| --- | --- |
| 12, 22 | The Human audit reports inaccurate alternative Sheets; the saved pages instead contain Sheetz with a matching Sheetz_Gas-Logo filename. The reported wording is absent, and original image appearance is not saved to establish a different inaccuracy. |
| 16 | Video/source markup does not record whether playback works. |
| 31 | The four labels have matching for/id associations. Hidden-label CSS alone does not establish the specifically reported JAWS announcement failure; the necessary browser/accessibility-tree evidence is absent. |
| 33 | The initial form does not record submitted errors or focus movement. |

## Differences from earlier reviews

Compared with Haiku's previous review:

- Contact autocomplete and the Senior Java Engineer back link move from
  Programmatic to LLM because existing rules do not detect those defects.
- Careers heading structure moves from LLM to Programmatic with the joint match
  described above.
- The Associate Solution/ML Engineer, first Senior .NET Engineer, and Azure Cloud
  Architect back links move from not testable to LLM. All three links exist in
  the saved HTML with private-use arrows.

Compared with Luna's previous review, Contact's company/location headings move
from not testable to LLM. Their exact names are present outside the iframes.
The other final classifications agree after inspection. Neither previous review
has saved catches on any of the five final not-testable originals, so this group
introduces no incompatible LLM matches during correction.

## Comparable saved results

Applying the approved decisions to the saved evidence produces these combined
counts, with every compatible LLM decision and qualification retained:

| Saved Full evaluation | Measure | Previous review | Shared baseline |
| --- | --- | --- | --- |
| Haiku `20261018T152533-610e4938` | LLM | 22/59, 37.3% | 21/63, 33.3% |
| Haiku | Programmatic | 17/19, 89.5% | 18/18, 100.0% |
| Haiku | Overall | 39/86, 45.3% | 39/86, 45.3% |
| Luna `20261011T015629-880f3e7c` | LLM | 28/62, 45.2% | 28/63, 44.4% |
| Luna | Programmatic | 18/18, 100.0% | 18/18, 100.0% |
| Luna | Overall | 46/86, 53.5% | 46/86, 53.5% |

Haiku gains five LLM responsibilities and loses Careers heading structure to the
Programmatic denominator, increasing its LLM denominator by four. Its previous
LLM catch for Careers remains a valid cross-catch but no longer enters the LLM
numerator. Luna gains one LLM responsibility, Contact company/location headings,
without an additional saved catch. Both runs now have five not-testable originals
and the same source denominators. Overall is unchanged because source credit
moves between responsibilities while each original still counts once.

The Programmatic counts come from resolved, validated evidence. All 17 pages
have identical checker evidence across the two runs, and every approved expected
catch resolves to the appropriate run's findings. A missing or non-unique
expectation prevents reporting rather than receiving assumed credit.

## Verification

Verification used the existing evaluator CLI against temporary copies of the
ignored source evidence. The initial Home preview test failed because no approved local
baseline was saved. Adding the approved JSON made it pass. The external
verification suite then passed all four scenarios:

1. Home preparation automatically selects this audit's baseline and populates
   the independently expected 5 Programmatic, 9 LLM, and 2 not-testable rows.
2. Single-page `run` previews prepare all 17 audited URLs with their own local
   findings and repeated Globals. Their 198 rows have the counts above, and the
   freshly produced checker evidence equals the saved evidence.
3. Single-page `report` succeeds for all 34 temporary saved children, 17 per model,
   while preserving their LLM IDs/reasoning, Human evidence, snapshots, raw model
   responses, normalized findings, and original execution metadata. Each page's
   Programmatic numerator equals its independently expected denominator. Both
   runs resolve 118 distinct actual Programmatic IDs, and the runs' ID sets are
   disjoint.
4. Public preparation rejects the wrong audit checksum, an omitted original
   decision, an omitted page decision, and an expected element absent from actual
   evidence. Errors identify the affected identity or unresolved evidence.

The original saved reviews and reports were not changed by this verification.
It made no model requests or downloads and did not change checker behavior.
Baseline JSON remains local and is excluded from package data. New checkouts
prepare a CSV review or select an approved local file with `--baseline PATH`.
Combined reporting uses the same saved-decision contract.

### Actual saved-run correction

During the original implementation, the now-retired `correct-all` command applied the approved
baseline to both original completed Full evaluations. All 36 regenerated reports
are standalone and usable offline. The two evaluations validate 396 child review
rows in total and retain 86 unique originals each, with the corrected counts in
the table above.

Comparison with the pre-correction inventory confirmed unchanged original
execution evidence, model configuration, completion, usage, pricing, costs, and
all LLM match IDs, reasoning, and notes. The interrupted Haiku attempt also
remains unchanged. Verified original backups contain 344 Haiku files and 342 Luna
files at `.model-evaluation/full-runs/review-history/<run-id>/original`, with
SHA-256 inventories beside them. The local verification records are
`.scratch/evaluation-baseline/verification/before.json`, `after.json`, and
`backup-and-html.json`.

## Manual maintenance

When Programmatic rules change, prepare a new baseline CSV review and
deliberately re-review the affected original Human defects and page matches.
Approve that review through the evaluator CLI into a new baseline file before
preparing new runs. The current authoring workflow is documented in the README.
Discovering a new rule or observing a different catch must not silently change a
classification. An unresolved expectation requires investigation, not a guessed
match or a removed responsibility.

Runs copy the approved decisions into their own evidence. Editing the reusable
JSON does not rewrite historical decisions. Changed-page-evidence policy remains
a separate, deferred task.

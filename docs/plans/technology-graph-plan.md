# Technology Graph plan

Status: in progress. Updated November 1, 2026. **The "Current plan" section below is the plan of record; where later sections disagree with it, it wins.** Later sections describe the earlier design and are kept for history. Hosted deployment and account creation still require separate authorization.

## Current plan (November 1, 2026)

### Goals

- a) Lists of breakthroughs we may see in the future, the milestones that say they have been achieved, and attribution of where each came from.
- b) Progress towards them that we add to over time, as papers and links.
- c) A UI to view it all, modelled on a strategy-game tech tree.
- d) A polished UI that works on mobile, with motion, in the style of the Silicon Data pitch in am-live (`docs/sponsor-segments/silicon-data/silicon-data-segment.html`).
- e) An arbitrary paper (for example from arXiv) can be added once and count as progress for several breakthroughs.

### Terms

- **Breakthrough**: a leaf of the tree, one proposed future capability (ID like `CSC-02`). Stored in the `breakthroughs` table and served at `/api/breakthroughs/<ID>`. The ingestion pipeline still writes `final-innovations.json` with an `innovations` list; the atlas reads that format unchanged.
- **Milestone**: one of a breakthrough's completion criteria, numbered 1…n.
- **Progress**: one source (paper or link) judged against a milestone, one row in `progress`.

Older sections use "milestone" for what is now a breakthrough.

### Cost rule

Reuse existing data and structures. This plan adds **one new table (`progress`)**, **no model passes over existing data**, and **one model call per paper added**. Any further table or model pass needs an explicit decision. (Since added by decision: one prerequisite call per field.)

### Starting point

- `ingestion/` produces each field's `final-innovations.json`: 31 of 66 fields are complete (334 breakthroughs); see `docs/ingestion-status-2026-11-01.md`.
- `atlas/` is the v1 prototype: SQLite importer (`runs`, `fields`, `breakthroughs`, `assets`, `documents`), read-only server and API, and a static UI loading 4 fields (SWE, CSC, CPE, ROB). See `atlas/README.md`.

### Steps

1. **Load all completed fields (goal a).** Point the existing importer at every completed field and remove the hard-coded four-field copy. Milestones are each record's existing `completion_criteria` items, numbered 1…n and served as-is. Sources are each record's existing `sources` and saved copies. New fields are imported the same way as ingestion finishes them.
2. **Add the `progress` table and backfill it (goal b).** Columns: breakthrough ID; criterion number (nullable); URL; saved-copy SHA-256 (row in the existing `assets` table); source date; verdict `advances` / `meets` / `contradicts` (nullable); quote; model; date added. Backfill by copying, with no model calls: each `current_state` paragraph and its cited `source_urls` becomes one row with criterion and verdict left empty, attributed to the research model and research date. Criterion status is computed from rows: `meets` → met, `advances` → in progress. Tests sit with the existing ones in `atlas/tests`.
3. **`atlas add <url>` (goals b and e).** (1) Save the paper into `assets` with a local PDF and a Wayback link; skip the download if the URL or hash already exists. (2) Rank all criteria against the abstract by word-overlap scoring computed in memory (nothing stored, no model) and keep the top ~20. (3) One model call (Codex, GPT-6.1 Terra, strict JSON schema) returns a `progress` row for each criterion the paper touches; code checks that each quote appears in the paper and rejects rows that fail. One paper touching three breakthroughs is three rows. `--breakthrough ID` forces a target the ranking missed.
4. **Tech-tree UI (goals c and d).** React + Vite + Framer Motion, reading the existing server API plus one progress endpoint. Style from the Silicon Data pitch: Outfit, DM Sans and JetBrains Mono, self-drawing SVG lines, the same easing. One lane per field; each breakthrough is a node with a segmented bar per criterion (met / in progress / none); lines from the existing `related_concepts` references; nodes within a lane ordered by progress. Node detail is the existing record view plus a timeline of progress rows with their papers and quotes. Mobile: a vertical path per field, swiped between fields, tap to open. An original design in the strategy-game genre, not a copy of any game's artwork.

### Core architecture: a fixed core, and edits over time (November 2, 2026)

The atlas must change over time the way a wiki does: every part can be corrected or extended, and every change is attributed and can be undone. The design separates a small core that never changes from everything else, which changes only through edits.

**The core (fixed):**

1. **Permanent IDs.** A field, breakthrough or milestone keeps its ID forever. Records are retired or merged, never deleted, and IDs are never reused. Links, progress and history all refer to IDs.
2. **A small set of record kinds:** field; breakthrough; milestone; link between breakthroughs (`needs`, `discussed together`); progress (a source judged against a milestone); source (saved copy and its SHA-256). A new kind is a rare, deliberate decision.
3. **Saved, fingerprinted sources.** Every claim points to a saved source or to an edit.
4. **Every change is an edit.** An edit records the record ID, what changed, the author (a person, or a model with its prompt and call record), the time, the reason, and the evidence. The current state of any record is its first version plus its edits in order.

**Everything else changes through edits:**

- Content: titles, descriptions, milestones, verdicts.
- Structure: new fields and breakthroughs, splits and merges, adding or removing links.
- Process: prompts, models, and the rules for what counts as a link. Because each edit names its model and prompt, a process change never corrupts history: edits made under an old rule can be found and redone on their own.

**How the existing pieces fit:**

- Ingestion research is the first edit to each breakthrough, by the research model.
- `atlas.add` writes progress edits; `atlas.prerequisites` writes link edits; a person's corrections are edits recorded the same way.
- The SQLite database is a view rebuilt from the core, as it already is from the ingestion files. It is not the source of truth.

**Open decision: where the core lives.**

- **Git files** (one JSON file per record, edits as commits): history, diff, attribution and revert come from git, with no new table. Suits one editor or a few trusted ones.
- **An edits table:** needed if people will edit through a website, together with accounts, permissions and review, which the later-collaboration scope below still defers.

The answer depends on who edits. Until it is decided, new derived data (such as prerequisite links) is not treated as final.

### Prerequisite order (started November 2, 2026)

True prerequisite order ("A must be achieved before B") is wanted. `atlas/prerequisites.py` (`python3 -m atlas.prerequisites FIELD … | --all`) makes one model call per field that sees the field's breakthroughs in full and a one-line catalog of all breakthroughs, and returns, per breakthrough, what it needs and what needs it, from any field. A link means B is expected to come first on the way to A (A builds on B, uses it as a component, assumes its result, or B is the expected route); merely helpful, topical, or same-capability pairs are not links. Code rejects unknown IDs, self-links, links with neither side in the field, and links that close a loop. Each call's prompt and response are kept under `atlas/data/prerequisites/`.

Status: run on Quantum Computing (5 links, including from CPE-01 and CSC-02) and Computer Science (no new links). Links are currently stored inside the dependent breakthrough's record, so a changed re-import of that field drops them; under the core architecture they become link edits. Remaining: decide where the core lives, run the other fields, and compute tree columns from the longest prerequisite chain. Until then the tree orders nodes by progress.

This plan supersedes the deprecated paid-report plan in `archive/AI_Takeoff_Project_Plan.md` (dated forecasts, PDF product, blog/thread funnel). That plan is history only and is not a goal, input, or constraint for this project.

## Product and immediate objective

Build a **Technology Graph** for exploring proposed capabilities, their relationships, and dated evidence of progress. Fields and branches organize navigation. Milestones replace the idea of leaves (superseded: a leaf is now a *breakthrough*, and *milestone* means one of its completion criteria; see Terms above): a milestone can have multiple upstream inputs, cross-field connections, and alternative research routes. The product is not constrained to a strict tree.

Connections are directed and typed, with a mechanism, rationale, source support where available, and explicit uncertainty. A possible enabling component, accelerator, alternative approach, or feedback relationship is not proof of necessity or sufficiency. Prerequisite groups should express multiple inputs and alternative routes without implying that satisfying the group automatically completes a milestone.

The highest-priority delivery is one complete workflow: **source intake and archiving → milestone or progress proposal → machine acceptance → accepted change visible in an attractive graph**. Build the graph, progress model, intake, and frontend first. Keep future collaboration possible without building a public CMS now.

## Starting point and provenance

The current local application uses SQLite and provides the original 660 entries, proposed graph connections, a bounded webpage audit, and separate proposal-source/progress/context roles. The hosted architecture and intake pipeline below are proposed work, not current capabilities.

The user clarified how the original corpus was created: Grok 4.5 online was prompted, for each of 66 fields, with `name 10 <field> discoveries that would be revolutionary if we actually discovered them. Include sources.` The responses were copied into Markdown. This is user-reported provenance, not independently verified authorship of the underlying scientific ideas.

Consequences for the product:

- Treat the 660 entries as generated candidates, not validated scientific consensus or a canonical list of open problems. Importing them does not validate them.
- Preserve original wording, stable IDs, supplied references, audit findings, and revision history. The supplied references are field-level bibliographies; exact innovation-specific proposal attribution remains unconfirmed. Some pages are dead, and public archives do not always contain a copy.
- The existing partial-progress audit checks narrower findings. It is not complete verification that each original proposal is well-defined, unresolved, revolutionary, correctly attributed, or supported by consensus.
- The Atlas research pipeline (below) replaces the editorial pass: each field's problems are researched afresh from sources, and every original entry receives an explicit decision (covered, added or not added). Original wording is preserved alongside. There is no obligation to retain ten milestones per field.
- A source re-check of Biomedical Engineering found that 4 of its 5 original citation links appear fabricated (no live page, no archive copy, unregistered DOI) and the fifth is a real document at a different URL (`research/source-recheck/field-09/existence.json`). The original bibliographies should be treated as unreliable across all fields.

## Atlas research pipeline (adopted October 31, 2026)

The new Atlas is a separate project in `Atlas/`, with its own database (`Atlas/db/atlasdb.sqlite3`, not yet populated). The existing TechTree app and its database are unchanged. Current pipeline: `Atlas/research/fields_v5/` (`prompts/`, `tools/run_pipeline.py`, `tools/archive_and_accept.py`); `fields_v3/` and `fields_v4/` hold the experiments that led to it, including failed runs, kept as records. Step-by-step instructions: `Atlas/research/fields_v5/Field_Onboarding_Runbook.md`.

| Step | Model | What it does |
|---|---|---|
| 1a Research | Grok 4.7, high (`~/.grok/bin/grok`), web search and fetch, no schema | Finds the field's open problems from primary sources and writes plain-text notes with citations, completion criteria, current state, dependencies and approaches. |
| 1b Format | GPT-6.1 Terra, high (Codex CLI bundled in ChatGPT.app), strict JSON schema, no web | Converts the notes to JSON without adding content. |
| 2 Reconcile and merge | GPT-6.1 Sol, medium (Codex), web search, strict JSON schema | Decides each original entry (V2-ids) as COVERED, ADDED or NOT_ADDED, adds sourced problems the research missed, and adds dependencies from existing problems to added ones. Existing problems are otherwise copied unchanged. |
| 3 Archive and machine acceptance | Script, no model | Saves every cited source and runs the acceptance rules below. |

Design decisions:

- Schemas follow OpenAI strict structured-output rules, so key presence, types, enums, id/URL/DOI/PMID patterns, word limits, item counts and conditional rules (for example, a `sourced` claim needs 1–5 citations) are enforced at generation time rather than validated afterwards. Grok's `--json-schema` constrains every intermediate message, so Grok is used only for unstructured research and Codex does all schema-bound steps.
- Each problem records `identified_dependencies` (on problems already in the list, by id), `unidentified_dependencies` (described in words with free-text likely fields, to be matched later) and `approaches` (routes to solving it, not dependencies). Dependencies within a field are as important as those across fields.
- The 66 fields are arbitrary navigation labels, not matching keys. Unidentified dependencies will be resolved later by semantic search across all problems (embeddings to shortlist candidates, a model to judge them); unmatched clusters indicate shared capabilities nobody has listed. This runs once more fields are done.
- There is no human review. Each final list records a `review_process` (researched_by, formatted_by, reconciled_by, accepted_by) naming the model and effort behind each step. Sol is not described as a reviewer because it does not re-check content it copies.
- Machine acceptance gives each problem one of four statuses: `accepted` (every claim has a citation whose quote is found in a local copy), `accepted_with_exceptions` (the recognized-as-goal claim, which answers "why is this a major item?", is verified with a local PDF and an Internet Archive link, but another claim is only registered or unverified), `pending` (the goal claim is waiting on an access exception) or `rejected` (schema or dependency fault, placeholder text, a quote missing from a readable copy, an unregistered DOI/PMID, or an unfixable goal claim). Capture failures are classified (paywalled, bot_blocked, rate_limited, transient, dead_link, archive_refused, render_failed, quote_mismatch, unregistered_id) and queued for retry, legal-copy lookup (Europe PMC), manual copy, dead, or content problem in `Atlas/archive/exceptions.json`. Unauthorised sources (such as Sci-Hub) and bot-protection workarounds are not used.
- Model runs vary: research for the same field produced substantially different problem lists across runs, and merge decisions on borderline originals can change between runs.

Status: Biomedical Engineering has a final list in the current format (14 problems; 13 machine-accepted, 1 rejected because its only source was blocked and unarchived; 55 of 57 quotes verified in saved copies). Robotics has final lists in the earlier `related_problems` format and needs a re-run. CLI cost estimates for Grok research are about $2–2.60 per field; Codex steps run on the ChatGPT plan.

## Scope now and later

**Core scope:** a polished graph and accessible list, milestone details, dated progress, source intake and capture, validated agent-assisted imports/API, review decisions, accepted changes, and reversible history. Suggestions and proposed changes remain separate from accepted records.

**Later collaboration:** permanent milestone pages; attributed edits, history, diffs and revert; discussions, disputes, watchlists, community proposals, review permissions and moderation. Do not build public accounts, a general CMS, reputation systems, or discussion features now. No MediaWiki/Wikibase migration is decided or needed for the core delivery.

Optional images, icons, other user-added attachments, and replaceable visual themes can follow. No image or icon asset production is required now. Source captures remain core intake work.

## Proposed architecture and responsibilities

| Component | Proposed responsibility |
|---|---|
| Cloudflare Workers | Application/API boundary, validated intake, review actions, and orchestration of source capture and processing. |
| D1 | Authoritative structured records: graph, claims, progress, provenance, capture metadata, workflow states, review decisions, and revisions. D1 is the SQLite-based deployment target; migration behavior must be tested rather than assumed identical to the local runtime. |
| R2 | Available source PDFs and webpage captures where permitted, plus future attachments/assets. D1 links each record to its stored object and capture metadata. |
| React/TypeScript frontend | Proposed modern, strategy-game-like graph exploration and review interface, backed by the API. |
| Agents and validated imports | Assist extraction, matching, scope checks and proposed edits. They do not bypass validation or editorial acceptance. |

Evaluate the rendering library against the real 660-entry dataset before choosing it. Compare approaches for layout, interaction, label legibility, progressive disclosure, mobile use and accessibility; do not select a library solely from a small demonstration.

Retain a repeatable, validated SQLite-to-D1 import with stable IDs and explicit schema versions. Preserve original records and history, distinguish original audit labels from new role decisions, and reconcile counts and references before accepting a migration.

## Structured data model

| Entity | Essential information and relationships |
|---|---|
| Milestone | Stable ID, capability statement, field memberships, attributed significance, completion criteria, original wording/provenance, current revision, editorial status and achievement status. |
| Field | Navigation grouping, name and display information; it does not constrain graph connectivity. |
| Directed connection / prerequisite group | Endpoints, type, mechanism, alternatives or grouped inputs, rationale, uncertainty, supporting claims and review state. |
| Progress event | Demonstrated result, event date and its precision/source, publication date separately, conditions, scope, limitations and remaining gap. |
| Progress–milestone link | Which part of each milestone the event advances or completes, criterion-level justification, and a separate reviewed completion decision. One event can link to several milestones. |
| Source / capture | Original and resolved URL, author, title, publisher, available dates, retrieval timestamp, object reference, content hash, capture outcome and failure details. |
| Claim–evidence link | Exact supporting passage/locator, interpretation, scope and limits, source role, and separate source-origin provenance. |
| Intake / proposed change / review decision | Submission identity, processing state, candidate matches, proposed additions/edits, reviewer decision, reason and accepted revision references. |
| Revision / attribution | Previous and new state, actor, reason, timestamp and source references; changes remain inspectable and reversible. |

Editorial review status and scientific achievement status are independent. “Accepted for publication in the graph” does not mean “achieved.” Do not invent completion percentages, solution dates, or a universal result from a narrower experiment. Completing an upstream milestone never automatically completes downstream milestones.

## Intake and review workflow

1. **Submit.** Accept a new milestone proposal or dated progress marker through an initially agent-assisted validated import/API. Assign a stable submission ID and retain the input and attribution.
2. **Capture sources immediately.** Attempt permitted PDF/webpage capture at intake and retain source metadata and capture outcomes. Capture now, before link rot, rather than deferring archiving until publication.
3. **Extract claims.** Separate capability, significance, demonstrated findings, conditions, limitations and proposed connection mechanisms. Link passages and locators to the specific claims they support.
4. **Verify scope.** Check the actual source, distinguish its statements from interpretation, and identify unsupported qualifiers. Keep a planned experiment, research goal or background discussion separate from a demonstrated result.
5. **Deduplicate and match.** Compare against existing proposals, progress events and sources. Offer candidate matches with reasons; do not silently overwrite, merge, or attach a result to every related milestone.
6. **Propose graph changes.** Prepare inspectable milestone, progress-link and connection changes. State remaining gaps and any proposed completion decision explicitly.
7. **Machine acceptance.** Accept or reject automatically against the acceptance rules, recording the reasons, the rules, and the models behind each step. There is no human review step. Acceptance does not turn a hypothesis into an established prerequisite.
8. **Publish the accepted revision.** Make the accepted change visible in the graph, detail panel and chronological progress view. Preserve history and a path to revert.

Processing must be retryable and idempotent: repeated submission, capture, extraction or import attempts must not create duplicate accepted events or apply the same change twice. Failed and incomplete stages remain visible and resumable.

### Intake requirements by kind

**Milestone proposals:** state a specific capability, credible and attributed significance, assessable completion criteria, likely duplicates, and suggested dependencies or alternative routes. The model's assertion that an idea is revolutionary is not sufficient significance evidence.

**Progress markers:** state what was demonstrated, when, under which conditions, and with what limits. Propose links to each affected milestone, describe the part advanced and remaining gap, and justify any claim of completion against that milestone's criteria. A single source can advance several milestones without establishing all of them in full.

## Evidence roles, archiving and recovery

Keep these roles distinct at claim level:

- **Proposal/significance:** where the capability proposal or its claimed importance is actually supported and attributed. Field-level bibliography candidates remain labeled as such; show an honest unconfirmed state when exact attribution is unknown.
- **Progress:** actual scoped results advancing or completing specified criteria. Goals, background, inaccessible pages and unsupported claims do not masquerade as demonstrated progress.
- **Connection support:** evidence or rationale for a proposed relationship, with its own scope and uncertainty. Progress on two nodes alone does not establish a dependency between them.

“From the original notes” versus “newly found” is source origin, not source role. The same source may serve several roles only where separate passages or findings justify those uses.

Every cited source is now captured locally in `Atlas/archive/` (`sources/<sha256>.<ext>`, with one `captures.jsonl` line per attempt), as private research copies not for redistribution or public display, falling back to an Internet Archive copy when the live page is unreadable. Which saved copies may be shown publicly is decided only if the Atlas is published. Later, store captures in R2. Link each capture in D1 to its original/resolved URL, authorship and publication metadata, retrieval time, hash, and exact supporting passage/locator. Distinguish publication, event and retrieval dates. Do not fabricate unavailable metadata. The UI should offer both **original source** and **saved source** access, with the version and any capture limitations visible.

A successful capture does not establish evidence validity; a failed capture does not disprove a claim. Record blocked, incomplete and failed attempts separately from the scope assessment, and retain those outcomes in intake/review. A public archive may corroborate a source version but must not be the sole retained copy. A hash establishes the integrity of the retained bytes, not the authenticity or truth of the original source.

Back up the database and referenced objects together, with a manifest that can reconcile object references and hashes. Retain off-device backups and test restoration of both records and objects, not merely restoration of database rows.

## Frontend direction

Use a polished strategy-game-like presentation: dark canvas, recognizable field colors, deliberate typography, milestone shapes, and readable typed connections. Styling should be replaceable without changing scientific meaning.

Core interactions are pan/zoom; search and filters; selection with immediate upstream/downstream context; progressive detail and clustering; a detail panel showing claims, evidence roles and limits; and chronological progress. Avoid opening the entire graph as an unreadable mass of labels. Keep direction and connection meaning clear as the view changes.

Provide a usable mobile/list alternative with access to the same milestones, sources, proposed relationships and progress. Do not require precise pointer gestures or visual graph interpretation to reach the evidence.

## Delivery sequence and acceptance

| Milestone | Deliverable | Acceptance criteria |
|---|---|---|
| 1. First complete slice | Intake plus source archive, milestone/progress proposal, review, and accepted change visible in an attractive graph. | A milestone proposal and a dated progress marker each complete the flow; original/saved source and passage are inspectable; failed capture has a visible outcome; retry creates no duplicate; revision can be reversed. No public CMS required. |
| 2. Full-corpus migration and exploration | Repeatable import and graph/list usability on the real 660-entry corpus. | IDs, originals, source roles and history reconcile; generated candidates are not promoted to consensus; navigation, focus and labels remain usable across fields and on mobile. Renderer choice is supported by this evaluation. |
| 3. Broader intake reliability and evidence | Milestone proposals and multi-milestone progress links, matching, capture recovery and review decisions. | Duplicate/match ambiguity is visible; partial versus completed criteria are explicit; suggestions cannot bypass review; unsupported claims and incomplete captures remain inspectable. |
| 4. Hosted deployment readiness | Workers/D1/R2 configuration, migration rehearsal, recovery and operational checks. | Structured records and object references reconcile after import and restore; accepted changes remain attributable and reversible; hosted permissions and processing behavior are verified before release. Deployment requires later authorization. |
| Atlas A. Research all fields | Run the v5 pipeline on all 66 fields, with archive and machine acceptance. | Every field has a final list, a review_process record and an acceptance report; failed runs are recorded, not repaired by hand. |
| Atlas B. atlasdb import | Tables for problems, criteria, claims, sources, citations, dependencies, approaches, originals and decisions, runs; repeatable import keyed by run. | Re-import of the same run changes nothing; every identified dependency resolves; every citation links to its capture. |
| Atlas C. Cross-field matching | Semantic search over all problems to resolve unidentified dependencies; cluster the rest into shared capabilities. | Each unidentified dependency is matched, partly matched or left unresolved with candidates recorded. |
| Later | Wikipedia-like collaboration and richer presentation. | Scope separately after graph, progress and intake prove useful. No public accounts/CMS/reputation/discussion work is included now. |

Testing should be proportional to these outcomes: migration/preservation and references; matching and idempotency; claim/source-role boundaries; completion decisions and reversible revisions; graph scale, navigation and mobile/list access; and database-plus-object backup/restore. Use meaningful end-to-end checks for the first slice rather than building a large workflow framework before the product works.

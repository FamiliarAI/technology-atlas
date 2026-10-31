# Technology Graph plan

Status: planning only. Consolidated October 31, 2026. This document authorizes no implementation, migration, deployment, account creation, or research run.

This plan supersedes the deprecated paid-report plan in `archive/AI_Takeoff_Project_Plan.md` (dated forecasts, PDF product, blog/thread funnel). That plan is history only and is not a goal, input, or constraint for this project.

## Product and immediate objective

Build a **Technology Graph** for exploring proposed capabilities, their relationships, and dated evidence of progress. Fields and branches organize navigation. Milestones replace the idea of leaves: a milestone can have multiple upstream inputs, cross-field connections, and alternative research routes. The product is not constrained to a strict tree.

Connections are directed and typed, with a mechanism, rationale, source support where available, and explicit uncertainty. A possible enabling component, accelerator, alternative approach, or feedback relationship is not proof of necessity or sufficiency. Prerequisite groups should express multiple inputs and alternative routes without implying that satisfying the group automatically completes a milestone.

The highest-priority delivery is one complete workflow: **source intake and archiving → milestone or progress proposal → review → accepted change visible in an attractive graph**. Build the graph, progress model, intake, and frontend first. Keep future collaboration possible without building a public CMS now.

## Starting point and provenance

The current local application uses SQLite and provides the original 660 entries, proposed graph connections, a bounded webpage audit, and separate proposal-source/progress/context roles. The hosted architecture and intake pipeline below are proposed work, not current capabilities.

The user clarified how the original corpus was created: Grok 4.5 online was prompted, for each of 66 fields, with `name 10 <field> discoveries that would be revolutionary if we actually discovered them. Include sources.` The responses were copied into Markdown. This is user-reported provenance, not independently verified authorship of the underlying scientific ideas.

Consequences for the product:

- Treat the 660 entries as generated candidates, not validated scientific consensus or a canonical list of open problems. Importing them does not validate them.
- Preserve original wording, stable IDs, supplied references, audit findings, and revision history. The supplied references are field-level bibliographies; exact innovation-specific proposal attribution remains unconfirmed. Some pages are dead, and public archives do not always contain a copy.
- The existing partial-progress audit checks narrower findings. It is not complete verification that each original proposal is well-defined, unresolved, revolutionary, correctly attributed, or supported by consensus.
- A later editorial pass may keep, rewrite, merge by reference, or set aside a candidate after actual source reading. A rewrite preserves the original wording and records the reason and attribution for the change. There is no obligation to retain ten milestones per field.

No new research or corpus-wide revalidation is initiated by this plan.

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
7. **Review.** Accept, request changes, reject, or set aside with a reason. Record the actor/time and preserve the proposal and supporting material. Acceptance does not turn a hypothesis into an established prerequisite.
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

Store available PDFs and webpage captures in R2 where permitted. Link each capture in D1 to its original/resolved URL, authorship and publication metadata, retrieval time, hash, and exact supporting passage/locator. Distinguish publication, event and retrieval dates. Do not fabricate unavailable metadata. The UI should offer both **original source** and **saved source** access, with the version and any capture limitations visible.

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
| Later | Wikipedia-like collaboration and richer presentation. | Scope separately after graph, progress and intake prove useful. No public accounts/CMS/reputation/discussion work is included now. |

Testing should be proportional to these outcomes: migration/preservation and references; matching and idempotency; claim/source-role boundaries; completion decisions and reversible revisions; graph scale, navigation and mobile/list access; and database-plus-object backup/restore. Use meaningful end-to-end checks for the first slice rather than building a large workflow framework before the product works.

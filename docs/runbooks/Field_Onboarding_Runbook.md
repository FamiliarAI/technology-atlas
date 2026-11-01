# Field Onboarding Runbook

Updated November 1, 2026. Scope: the verified Chemistry workflow, now authorized for all 66 historical fields with three fields active at a time.

This is the agreed workflow for the rebuild. See the [ingestion pipeline](../../ingestion/README.md) for implementation and commands. `ingestion.batch` coordinates the full sequence through `ingestion.field_workflow`; `ingestion.final_rewrite` implements step 5. The legacy `ingestion.pipeline run` command does not orchestrate this entire sequence. The [project plan](../plans/technology-graph-plan.md) retains historical context. Do not treat an evidence-review run as completion of this workflow.

## Process at a glance

1. Independent original research: Grok discovers concepts without seeing the historical list.
2. Compare against the original list: in the same Grok conversation, research additions and modifications and return the complete reconciled list.
3. Structure that reconciled research, then capture its cited sources as preparation for review.
4. Review every item in the reconciled list.
5. Produce the final structured output incorporating review corrections, with a change log and explicit unresolved issues.

Source capture is part of step 3, not a separate selection or review pass. The structured list before review is provisional; review recommendations alone are not the final output.

## Outcome

Produce a source-supported shortlist of potential revolutionary innovations or discoveries for one selected field. Select for transformative impact before detailed evidence processing, using the achieved historical breakthroughs in the research prompt as calibration. Each included problem should explain what remains unsolved, why it matters, what would count as solving it, and what the cited evidence actually supports. Someone should be able to inspect the supporting passages and saved sources.

Aim for ten independently researched concepts; explain any shortfall rather than pad the list. Then reconcile with the original list in a second research pass. Preserve every concept from the first pass, allowing modifications and additions with no ten-item cap. Concepts are the primary output; supporting claims and source-access issues must not be mistaken for a verdict on the concept. Preserve each field’s complete output and verification independently. The authorized batch runs three fields concurrently and refills a slot when a field finishes.

## Execute the authorized 66-field batch

```bash
python3 -m ingestion.batch prepare --as-of 2026-11-01
python3 -m ingestion.batch run
```

Use the canonical roster and original lists restored from Git, not a manually reconstructed field list. Inspect `ingestion/runs/all-fields/progress.md` for current state. A field is complete only after all five steps, final validation, and its verified external backup. Once all 66 are complete, merge the per-field records with code into one field-separated `ingestion/runs/all-fields/final-innovations.json`. An incomplete field must not disappear from the progress report or be counted complete. Resume with the same command; do not restart successful research. If Grok access is exhausted, stop new scheduling and ask the user to switch accounts.

## 1. Independent original research (Grok)

Record the field, its boundaries, and the research date. If no field has been selected, ask which one to start with.

Do not give Grok the original list in this step; preserve independent discovery. Research candidates using primary sources where available. Compare candidates for revolutionary impact, overlap, and obvious omissions. Inspect the plain-language shortlist before proceeding to structured records; an important unsolved problem alone does not qualify. Distinguish an open problem from an already demonstrated result or a speculative aspiration. Keep uncertainty explicit; a source describing a goal does not establish field-wide consensus.

For each candidate, keep a short problem statement, completion criteria, current state, significance, and citations. Record the research tool/model used. Keep raw research outputs so later corrections can be traced.

Use the already authorized tool/account configuration. Do not introduce paid API use or switch accounts implicitly. If Grok access or credits run out, stop that step and ask the user to switch accounts; never request credentials.

## 2. Compare against the original list (same Grok conversation)

Resume the exact Grok session from step 1, passing both its new list and the original list recovered from history. Save the original list with its Git revision. Reuse the earlier conversation and research context; do not assume hidden reasoning traces are preserved.

Use [the reconciliation prompt](../../ingestion/prompts/reconcile.md). Ask Grok to compare concepts, modify or clarify the new entries, and add worthwhile omissions. It may search for new evidence supporting additions and modifications. It must preserve every first-pass concept and its stable ID; do not delete concepts or merge away first-pass entries. There is no ten-item cap. Weak sourcing calls for research or an explicit uncertainty, not automatic removal. Original entries are candidates, not established facts: reassess their sources and revolutionary impact.

Return a complete revised set of plain-language research notes in the same format as step 1: title, ID, significance, missing breakthrough, proposed completion criteria, current state, and actual supporting URLs/passages. Include a short change log and a disposition for every original entry: covered by an identified concept, added, or not added with a reason. Do not return only a comparison or recommendations.

Record and resume the explicit session ID, never whichever session happens to be latest. Retain the session's working directory. Before using this flow, verify a disposable two-turn conversation retains both its ID and first-turn information. The resume spike passed after restoring the original working directory: the resumed call retained the same session ID and recalled first-turn information. The current runner retains each field's `grok-workspace` directory and passes the successful first research session ID explicitly to reconciliation with `--resume`; it also rejects a returned conversation ID that differs from the requested session. Do not silently substitute a fresh conversation.

## 3. Structure the reconciled research

Convert step 2's complete research notes into structured records without new selection or research. Preserve all concept IDs, original-entry dispositions, source links, uncertainty, and the change log. Validate the structure and check that no first-pass concept was lost.

Download the cited sources for the reconciled list. Capture failures update source status; they do not trigger another whole-list rewrite. Exercise a failed download and recovery on one item when implementing capture, then reuse that behavior across the field.

For each source used to support a claim:

- Record its title, authors/date when available, original and resolved URL, DOI/other identifier when present, and retrieval date.
- Save the best available original artifact: the paper PDF when available, otherwise usable HTML or XML. Record its path and content hash. Do not manufacture a PDF merely to satisfy a format requirement.
- Open the saved artifact and check that it is the intended source and contains the relevant material. A PDF header, filename, or successful HTTP response is insufficient.
- Link the claim to the supporting passage and page/section in that specific saved artifact. State limits on what the passage establishes.

Label publisher PDFs, webpage snapshots, abstracts, and locally rendered documents accurately. An abstract is a partial copy; a rendering that omits figures or tables is incomplete. Retain original XML/HTML when making a derivative rendering.

A Wayback snapshot is a best-effort additional backup. Its absence does not block a supported claim. Keep source copies private and excluded from Git; verify the ignore rule before adding any. Use legitimate access and record blocks rather than bypassing them.

## 4. Review every concept

Review every concept in the reconciled, structured list, including unchanged first-pass concepts as well as modifications and additions. For the current Chemistry run, this means all thirteen concepts; do not reuse earlier first-pass reviews as substitutes. Make one LLM review call per concept, using its current structured record and relevant saved evidence. Assess the concept’s revolutionary significance, scope, missing breakthrough, completion criteria, and current state. Return concrete proposed corrections for the final rewrite. Assess each material claim by reading its evidence in context. Automated quote matching and identifier checks are aids, not scientific judgments. Tolerate PDF line wrapping, hyphen spacing, presentation ligatures (ff/fi/fl/ffi/ffl/st), and quotation typography. Single/double delimiters may match around the same quoted span; do not conflate lexical apostrophes, primes, mathematical notation, changed words, numbers or negation. Retain the original quote and artifact; normalize only for comparison.

| Dimension | States | Meaning |
|---|---|---|
| Evidence support | Supported / Contradicted / Unresolved | Record a short reason. Supported means the inspected evidence supports the stated scope; it does not certify scientific truth. |
| Source capture | Saved / Partial / Missing | Record what was retained and any missing material or failed operation. |

Keep each complete review prompt within the total input budget, not just a per-artifact text cap. Remove exact repeated excerpt text and JSON escape overhead first; if shortening is still required, retain every source/artifact reference and explicitly mark partial excerpts and omitted characters. Missing material limits the assessment; it is not evidence that a result is absent. Original source files remain unchanged.

A saved paper can contradict a claim. A supported claim can still have an outstanding capture task. Missing evidence or failed extraction means unresolved, not contradicted.

Compare duplicate candidates and inspect obvious gaps in the field list. Narrow or correct claims where the evidence warrants it. One bad optional citation does not invalidate adequate support from another source; remove or flag the bad citation with a reason.

Keep claim-level evidence results visible separately from the concept assessment. Do not label an entire concept unsupported merely because a supporting claim needs correction or a source could not be downloaded. Separate collection incomplete and review failed from evidence/scope uncertainty; one invalid quote must not discard valid assessments of other claims. Treat explicitly proposed completion criteria as proposals grounded in the goal, without demanding published consensus. Assess dated results at their stated dates and record recent-literature queries, cutoff and limitations separately. Do not silently promote candidates because a script finished.

## 5. Produce the final structured output after review

Rewrite each innovation independently with one LLM call. Supply only that concept's reconciled research, structured record, validated review, and source references. Do not send full source documents again or ask for new research: step 4 already inspected the evidence. Measure and record each input's size before execution, then run the independent calls in parallel with the chosen worker limit.

Each final record has six sections:

1. **Concept:** title and a plain-language explanation.
2. **Significance:** why it would be revolutionary, its direct consequences, and possibilities that require further breakthroughs.
3. **Missing breakthrough:** what remains unsolved and the barriers.
4. **Current state:** demonstrated results, dates, and limitations.
5. **Completion criteria:** what would count as achieving the breakthrough, with proposed criteria labeled as proposals.
6. **Related concepts:** overlaps and distinctions without merging away identities.

Integrate the reviewer's useful explanations, distinctions, and limitations into those sections; consolidation must not discard that detail. Put source citations near the statements they support and uncertainty where it matters. Keep the full review, original research, and change history linked as audit metadata rather than repeating proposed-correction and evidence-review sections in the main entry. Preserve every concept and stable ID, qualify unsupported assertions, and record which corrections were applied or left unresolved and why.

Prepare and inspect input sizes before making model calls:

```bash
python3 -m ingestion.final_rewrite ingestion/runs/CHEMREV --prepare-only
python3 -m ingestion.final_rewrite ingestion/runs/CHEMREV --workers 13
```

The worker default is 3; the current Chemistry run authorizes 13 independent calls. This command is step 5 only, not a replacement for the preceding research, capture, and review stages. It produces `final-innovations.json` and `final-innovations.md` after validating the individual records and merging them deterministically. No LLM merge call is needed. Chemistry's consolidated output must contain all thirteen reconciled entries.

Check the final schema, concept-ID preservation, original-entry dispositions, and source/artifact references. These are code checks, not another routine LLM review. A failed or missing record must remain visible rather than silently producing a shortened final list. If a correction needs new research or a replacement source, recover only that item, capture the evidence, and update its review and final record; do not rerun the whole field. Preserve the prior outputs. Reviews that only produce recommendations are not a completed pipeline.

The field is complete when:

- The final revised list explains each concept, its completion criteria, current state, and significance, with inspectable supporting passages.
- Every first-pass concept is retained, every original entry has a disposition, and review recommendations are applied or explicitly left unresolved with reasons. Overlaps and obvious omissions have been considered.
- Capture status and remaining recovery actions are visible independently of evidence support.
- Saved evidence for included claims can be reopened. Copy the field outputs and source files to a backup outside the project, then verify their hashes and reopen a source from that backup.

Report the result briefly: the field, concepts retained/modified/added, corrections applied, where the outputs are, and remaining evidence or capture issues. A completed review does not mean every candidate is supported or every source is fully captured. If the result is empty or inadequate, state that and identify what is missing before expanding.

No prescribed report template or commit per field is required. When committing, inspect the staged changes and exclude private source copies. Do not push or publish without authorization.

Before automating further, use this field to check three behaviors: a source supports the actual claim, a failed download can be recovered without losing earlier work, and repeating a completed step does not duplicate results. Add tests for those behaviors when implementing the tools; documentation-only changes need a consistency check.

## Recovery: only repeat what failed

Keep a brief issue entry beside the affected source or claim: what failed, what was tried, and the next action. Preserve usable earlier captures. A failed retry must not replace the best saved copy.

| Failure | Recovery |
|---|---|
| Timeout, rate limit, or temporary server failure | Retry the failed operation once after the indicated wait. If it still fails, record the next action and continue with other sources. |
| Paywall, bot block, or dead URL | Look for a legitimate repository/author copy or existing archive. Use a relevant provider such as Europe PMC when appropriate. If unavailable, request a legitimate manual copy or find an alternative supporting source. |
| Paper PDF download fails | Record that failure even if a landing-page snapshot exists. Follow declared and ordinary PDF links; keep usable HTML/XML and mark capture partial if relevant full text is missing. |
| Rendering fails | Keep usable original HTML/XML. Retry rendering only if a readable derivative is actually needed. |
| Wayback save fails | Keep the local artifact; record the backup failure and continue. |
| Quote, identifier, or extraction check fails | Inspect source identity, version, passage, and extraction. Leave support unresolved until assessed; correct the citation or claim when justified. |
| Named papers lack citation URLs | Repair an explicit source ledger from saved research before formatting; identify actual documents, map URLs to claims, and record gaps. Do not repeat whole-field discovery. |
| Model service explicitly refuses a request for safety reasons | Preserve the refusal and mark that review unfinished. Do not automatically resend the same input or switch models to get around it. Continue unrelated fields. A permitted narrower review must disclose its reduced evidence scope; it is not equivalent to the refused full-source review. |
| Research, formatting, or another pipeline step fails | Preserve successful outputs and resume only the failed step. Confirm the earlier process has stopped before retrying. |

Manual copies may be linked by URL or another source identifier; a DOI is not required. Verify identity and relevant content, then reassess only the affected claims. Corrected claims and replacement citations form a new revision with a short explanation; preserve the raw outputs and previous evidence.

Do not build a scheduler, extensive queues, OCR, or a catalog of fallback providers until a real case requires them. After the bounded retry, the issue remains open until an explicit next action is taken.

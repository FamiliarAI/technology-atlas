# Field Onboarding Runbook

Updated October 31, 2026. Scope: one field first.

This is the workflow for the rebuild. The former `fields_v5` scripts remain in Git history at `7bc3997`; they have not been restored or updated to implement this workflow. Restore only the pieces needed for the next step. The [project plan](../plans/technology-graph-plan.md) retains historical implementation details.

## Outcome

Produce a useful, source-supported list of open problems for one selected field. Each included problem should explain what remains unsolved, why it matters, what would count as solving it, and what the cited evidence actually supports. Someone should be able to inspect the supporting passages and saved sources.

Do not require ten problems, exhaustive coverage, or reconciliation with all historical entries. Use old research as candidate material when useful, and reassess its claims. Complete and inspect this field before expanding to others.

## 1. Choose the field and research it

Record the field, its boundaries, and the research date. If no field has been selected, ask which one to start with.

Research candidates using primary sources where available. Compare candidates for importance, overlap, and obvious omissions. Distinguish an open problem from an already demonstrated result or a speculative aspiration. Keep uncertainty explicit; a source describing a goal does not establish field-wide consensus.

For each candidate, keep a short problem statement, completion criteria, current state, significance, and citations. Record the research tool/model used. Keep raw research outputs so later corrections can be traced.

Use the already authorized tool/account configuration. Do not introduce paid API use or switch accounts implicitly. If Grok access or credits run out, stop that step and ask the user to switch accounts; never request credentials.

## 2. Save the evidence

First exercise capture and review on one problem, including a failed download and recovery. Then apply it to the rest of the field. One problem tests capture; the complete field tests research quality.

For each source used to support a claim:

- Record its title, authors/date when available, original and resolved URL, DOI/other identifier when present, and retrieval date.
- Save the best available original artifact: the paper PDF when available, otherwise usable HTML or XML. Record its path and content hash. Do not manufacture a PDF merely to satisfy a format requirement.
- Open the saved artifact and check that it is the intended source and contains the relevant material. A PDF header, filename, or successful HTTP response is insufficient.
- Link the claim to the supporting passage and page/section in that specific saved artifact. State limits on what the passage establishes.

Label publisher PDFs, webpage snapshots, abstracts, and locally rendered documents accurately. An abstract is a partial copy; a rendering that omits figures or tables is incomplete. Retain original XML/HTML when making a derivative rendering.

A Wayback snapshot is a best-effort additional backup. Its absence does not block a supported claim. Keep source copies private and excluded from Git; verify the ignore rule before adding any. Use legitimate access and record blocks rather than bypassing them.

## 3. Assess support separately from capture

Assess each material claim by reading its evidence in context. Automated quote matching and identifier checks are aids, not scientific judgments.

| Dimension | States | Meaning |
|---|---|---|
| Evidence support | Supported / Contradicted / Unresolved | Record a short reason. Supported means the inspected evidence supports the stated scope; it does not certify scientific truth. |
| Source capture | Saved / Partial / Missing | Record what was retained and any missing material or failed operation. |

A saved paper can contradict a claim. A supported claim can still have an outstanding capture task. Missing evidence or failed extraction means unresolved, not contradicted.

Compare duplicate candidates and inspect obvious gaps in the field list. Narrow or correct claims where the evidence warrants it. One bad optional citation does not invalidate adequate support from another source; remove or flag the bad citation with a reason.

Keep unresolved candidates visible separately. Include a problem in the supported list only when its material claims have adequate support. Do not silently promote candidates because a script finished.

## 4. Recover only what failed

Keep a brief issue entry beside the affected source or claim: what failed, what was tried, and the next action. Preserve usable earlier captures. A failed retry must not replace the best saved copy.

| Failure | Recovery |
|---|---|
| Timeout, rate limit, or temporary server failure | Retry the failed operation once after the indicated wait. If it still fails, record the next action and continue with other sources. |
| Paywall, bot block, or dead URL | Look for a legitimate repository/author copy or existing archive. Use a relevant provider such as Europe PMC when appropriate. If unavailable, request a legitimate manual copy or find an alternative supporting source. |
| Paper PDF download fails | Record that failure even if a landing-page snapshot exists. Keep usable HTML/XML; mark capture partial if relevant full text is missing. |
| Rendering fails | Keep usable original HTML/XML. Retry rendering only if a readable derivative is actually needed. |
| Wayback save fails | Keep the local artifact; record the backup failure and continue. |
| Quote, identifier, or extraction check fails | Inspect source identity, version, passage, and extraction. Leave support unresolved until assessed; correct the citation or claim when justified. |
| Research, formatting, or another pipeline step fails | Preserve successful outputs and resume only the failed step. Confirm the earlier process has stopped before retrying. |

Manual copies may be linked by URL or another source identifier; a DOI is not required. Verify identity and relevant content, then reassess only the affected claims. Corrected claims and replacement citations form a new revision with a short explanation; preserve the raw outputs and previous evidence.

Do not build a scheduler, extensive queues, OCR, or a catalog of fallback providers until a real case requires them. After the bounded retry, the issue remains open until an explicit next action is taken.

## 5. Inspect the field and stop

The field review is complete when:

- The supported list explains each problem, its completion criteria, current state, and significance, with inspectable supporting passages.
- Duplicates and obvious omissions have been considered; unresolved and excluded candidates have short reasons.
- Capture status and remaining recovery actions are visible independently of evidence support.
- Saved evidence for included claims can be reopened. Copy the field outputs and source files to a backup outside the project, then verify their hashes and reopen a source from that backup.

Report the result briefly: the field, supported and unresolved problem counts, where the outputs are, and remaining issues. A completed review does not mean every candidate is supported or every source is fully captured. If the result is empty or inadequate, state that and identify what is missing before expanding.

No prescribed report template or commit per field is required. When committing, inspect the staged changes and exclude private source copies. Do not push or publish without authorization.

Before automating further, use this field to check three behaviors: a source supports the actual claim, a failed download can be recovered without losing earlier work, and repeating a completed step does not duplicate results. Add tests for those behaviors when implementing the tools; documentation-only changes need a consistency check.

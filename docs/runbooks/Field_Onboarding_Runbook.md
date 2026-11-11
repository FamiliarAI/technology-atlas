# Field Onboarding Runbook

Updated November 11, 2026. `ingestion.batch` coordinates the field workflow with three active fields and three review or rewrite workers per field. See the [pipeline README](../../ingestion/README.md) for caching, source recovery and test details, and the [review](../ingestion-review-2026-11-11.md) for the changes behind this workflow.

## Run and resume

Use the canonical roster and original lists restored from Git. For a new batch only:

```bash
python3 -m ingestion.batch prepare --as-of 2026-11-01
```

Run or resume all fields, or select prefixes:

```bash
python3 -m ingestion.batch run
python3 -m ingestion.batch run --fields MLC CLM VIR
```

`--fields PREFIX…` selects work without changing the roster. Inspect `ingestion/runs/all-fields/batch.json`, `progress.md` and each field's `workflow-receipt.json`. Resolve field roots from the manifest. Completed fields reuse validated outputs and backups; failed fields stay visible. Successful stages are cached, so resume rather than restarting discovery.

The signed-in CLI providers and ordered lists are in `ingestion/config.json`:

| Stage | Ordered models |
| --- | --- |
| Research and reconcile | Grok `grok-4.7` high → Codex `gpt-6.1-terra` high → Codex `gpt-6.1-sol` high → Claude `opus` |
| Format | Codex `gpt-6.1-terra` high → Codex `gpt-6.1-sol` high → Claude `opus` |
| Review and rewrite | Codex `gpt-6.1-sol` medium → Claude `opus` |

Fallback occurs only on classified provider exhaustion or timeout. Other failures stay with the same model: format and review allow one retry; research and reconcile do not. A failed rewrite can be recovered or retried on resume. A safety refusal is final for every model and is never a reason to try another model.

Grok exhaustion is recorded in `batch.json` at `providers.grok.exhausted_at`. All fields skip Grok for 24 hours and can use the remaining list. A timeout does not start that cooldown. Do not switch accounts automatically or request credentials. If no entry can run a stage, new field scheduling stops; wait for a reset or add capacity. Exit status 2 reports that condition; 1 reports an incomplete selected field or import error.

## 1. Independent research

Record the field, boundaries and research date. Discover potentially revolutionary concepts without supplying the historical list. Aim for ten independently researched concepts, explaining a shortfall rather than padding. Use primary sources where available and the research prompt's historical breakthroughs to calibrate impact.

For each concept, retain its stable ID, significance, missing breakthrough, proposed completion criteria, current state and citations. Distinguish an unsolved problem, a demonstrated result and a speculative aspiration. A source describing a goal does not establish consensus. Preserve raw research and model attribution.

## 2. Reconcile with the original list

Compare the full first-pass list with the original list recovered from Git. Research modifications and worthwhile additions. Preserve every first-pass concept and stable ID; there is no ten-item cap. Original entries are candidates to reassess, not established facts.

When Grok did the research and its session is available, resume that explicit session in the same working directory. The runner verifies the returned session ID. Otherwise use a fresh conversation containing the complete first pass and original list, with wording that explains the missing prior turn. Fresh reconciliation is the same pass without the earlier tool history. The receipt records `resume` or `fresh`.

Return the complete revised research notes, a change log, and a disposition for every original entry: covered by identified concepts, added, or not added with a reason. Weak sourcing calls for research or explicit uncertainty, not silent removal.

## 3. Structure and capture

Format the reconciled notes without new selection or research. Preserve concept IDs, source links, uncertainty, original-entry dispositions and the change log. Validate that formatting neither loses nor invents concepts.

Download and index cited sources with original/resolved URLs, identity metadata, retrieval information, paths and hashes. Retain original PDFs or usable HTML/XML/text. Follow PDF links; when nothing was captured and a DOI exists, try one Europe PMC open-copy lookup. Record failures and partial captures without rewriting the whole list.

Open saved artifacts and verify identity and relevant passages. A successful download or PDF header is insufficient. Abstracts, truncated extraction and extraction warnings remain partial. PDF extraction repairs surrogate text; no OCR or PDF rendering is performed. Source text is limited to 120,000 characters per artifact, with truncation recorded. Keep private source copies under Git-ignored `ingestion/runs/`.

For an inaccessible source, supply a legitimate alternate URL or manual copy with the README's `alternative` or `attach` command. Keep the original citation URL as the key; a DOI is not required for manual recovery. Preserve good copies and failed-operation history. An existing archive can be supplied; a fresh Wayback save is deferred and is not a support gate.

## 4. Review every concept

Make one review call per reconciled concept using its structured record and saved evidence. Assess revolutionary significance, scope, overlap, missing breakthrough, completion criteria and current state, then propose concrete corrections. Keep concept assessment separate from claim-level evidence support and source-capture status.

| Dimension | States |
| --- | --- |
| Evidence support | Supported / Contradicted / Unresolved, with reasons |
| Source capture | Saved / Partial / Missing, with limits and recovery actions |

Supported means the inspected evidence supports the stated scope; it does not certify scientific truth. A saved source can contradict a claim. Missing evidence means unresolved, not contradicted. Proposed completion criteria need not represent published consensus. Record uncertainty and assess dated results at their stated dates.

Validate quotations against the specific supplied artifact. Matching tolerates ordinary PDF wrapping and typography, without changing words, numbers or negation. Keep raw output and audits of normalized references. Capture metadata corrections cannot repair an unmatched passage or change a scientific judgment.

The complete review prompt is capped at 900,000 UTF-8 bytes, including retry space. Deduplicate exact excerpts and avoid JSON escape overhead before shortening text. Preserve source/artifact references and mark omitted text as partial; full saved files remain unchanged. Missing passages limit the assessment and do not establish absence of evidence.

## 5. Rewrite and finish the field

Rewrite each reviewed concept independently using its reconciled research, structured record, validated review, source metadata and concept roster. Do not send full source documents again or request new research. Input sizes are recorded. To prepare without calls or run only this stage:

```bash
python3 -m ingestion.final_rewrite ingestion/runs/all-fields/MLC --prepare-only
python3 -m ingestion.final_rewrite ingestion/runs/all-fields/MLC --workers 3
```

Each final record has six sections: **concept, significance, missing breakthrough, current state, completion criteria, and related concepts**. Integrate review corrections and limitations, cite supported statements, label proposed criteria and retain unresolved issues. Keep full reviews and change history linked as audit metadata. Each record retains the models used for research, reconcile, format, review and rewrite.

Validate records, IDs, original-entry dispositions and source references, then merge deterministically into `final-innovations.json` and `final-innovations.md`. There is no LLM merge pass.

Only a recorded safety refusal at review or rewrite withholds a concept. Keep its `{id, title, stage, reason}` in the final `withheld` list and omit it from `innovations`. Preserve the refusal under `workflow-blocked/`; do not narrow, filter, retry or reroute it to another model. The marker blocks the stage even if metadata changes. Other review or rewrite failures block completion; a refusal at a field-wide stage blocks that stage. Preserve every non-withheld concept and every original-entry disposition.

The batch validates final records, reviews and source hashes, then verifies an external backup by checking all file hashes and reopening saved sources. It imports each finished field into `atlas/core` in the controller thread, one at a time, checks the core, rebuilds SQLite and commits with the field and model names. Existing core fields are left alone; a failed check or rebuild rolls back the import. Inspect `import_error` separately from field completion. There is no requirement to finish every field before importing one.

Report the field, retained and withheld concepts, corrections, output locations and remaining evidence or capture issues. Completion does not imply every claim is supported or every source is fully captured.

## Recovery and checks

Repeat only the failed operation. Preserve successful captures, cached stages, attempts and raw outputs. Cache keys include the prompt/input and the selected model and effort; resumed reconciliation also includes its session ID. All configured entries' caches are checked before new calls. Prompt changes invalidate affected caches. Restore settings, caches, attempts and sources together from backup.

For documentation-only changes, check consistency against the implementation. Run ingestion tests with dependencies installed in the same Python environment:

```bash
python3 -m pip install -r ingestion/requirements.txt
python3 -m unittest discover -s ingestion/tests -v
```

The tests use temporary data and synthetic evidence, without live model or publisher calls.

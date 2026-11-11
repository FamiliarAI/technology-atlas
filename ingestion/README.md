# Field ingestion

Tools for the [field onboarding runbook](../docs/runbooks/Field_Onboarding_Runbook.md), adapted from the archived `fields_v5` pipeline at Git commit `7bc3997`. The agreed sequence is independent Grok research → same-thread comparison with the original list and further research → structuring and source capture → review of every concept → final structured rewrite.

The current full workflow is `ingestion.field_workflow`, coordinated across fields by `ingestion.batch`.

From the repository root, use Python 3.10+ with `python3 -m pip install -r ingestion/requirements.txt`. The existing signed-in Grok CLI and Codex CLI bundled with ChatGPT are configured in `config.json`. No API key is needed. Model configuration is separate from the prompts. Do not switch accounts automatically; if Grok access is exhausted, ask the user to switch accounts.

## All 66 fields: complete workflow

```bash
python3 -m ingestion.batch prepare --as-of 2026-11-01
python3 -m ingestion.batch run
```

Preparation restores the canonical 66-field roster and each original Markdown/JSON list from Git revision `7bc3997d0e1ee3ccdb4073402fb9744827173dda`, preserving their paths and hashes under `ingestion/runs/all-fields/originals/`. The batch runs three fields at a time and starts the next when a field finishes. Each field follows all five steps, with up to three independent concept calls inside a field. Grok research and reconciliation use the same persistent session and working directory. The existing Chemistry run is reused only after its final output and backup verify.

Progress is recorded in `ingestion/runs/all-fields/batch.json` and `progress.md`; each field has a `workflow-receipt.json`. The final per-field outputs are `final-innovations.json` and `final-innovations.md`. A field counts as complete only after its records, reviews, saved-source hashes, and external backup validate. Backups default to `../2026_Takeoff_backups/all-fields/`. Completion is tracked per field, with each field retaining its own final outputs and original-entry dispositions.

Rerun the same `batch run` command to resume. Verified completed fields are skipped; cached successful stages are reused. Failed fields remain visibly incomplete while other fields proceed. Grok account exhaustion stops new field scheduling and requires the user to switch accounts; credentials are never requested. The command exits nonzero for an incomplete batch (1) or an account switch requirement (2). Runtime receipts—not the presence of these commands—establish actual completion.

## Final structured rewrite (step 5)

Use one independent LLM rewrite per innovation. Its input contains only that concept's reconciled research, structured record, validated review, and source references—not full source documents again. Measure the prepared inputs before running calls:

```bash
python3 -m ingestion.final_rewrite ingestion/runs/CHEMREV --prepare-only
python3 -m ingestion.final_rewrite ingestion/runs/CHEMREV --workers 13
```

`--prepare-only` prepares and measures inputs without model calls. The worker default is 3; 13 parallel calls are authorized for this Chemistry run. The command consumes the existing reconciled research and validated reviews; it does not rerun research, capture, or review.

Each record has six sections: **concept, significance, missing breakthrough, current state, completion criteria, and related concepts**. Incorporate the reviewer's detailed explanations, distinctions, and limitations into those sections, with citations beside the supported statements. Keep uncertainty explicit and preserve stable IDs. Link the full review, source references, and change history as audit metadata, rather than repeating the review's headings in the final entry.

Validate each record, then merge deterministically into `final-innovations.json` and readable `final-innovations.md`; there is no LLM merge pass. The Chemistry output must retain all thirteen entries and account for the review corrections. A missing or invalid record is an incomplete step, not permission to omit a concept. The presence of this command or documentation does not certify a completed run; inspect the generated outputs and validation results before reporting completion.

## Sources and recovery

Downloads retain original PDF/HTML/XML/text and content hashes. The downloader follows a page's declared PDF links and ordinary links whose URL path ends in `.pdf` (including query strings), without recursively crawling linked pages; a failed PDF download remains visible even when the landing page was saved. PDF text is extracted with page markers. Valid UTF-16 surrogate pairs become Unicode characters, and lone surrogates become U+FFFD so the extracted text can be encoded as UTF-8. Parser warnings, including skipped form content, are retained as extraction issues so incomplete text cannot be certified as a full capture. No PDF rendering, OCR or automatic legal-copy provider search is performed. An abstract, unreadable PDF, truncated extraction or uncertain identity is never silently treated as a complete source. Extraction is limited to 120,000 characters per artifact and explicitly marks truncation. The per-field workflow also caps the complete review prompt at 900,000 UTF-8 bytes, including JSON and instructions, with space reserved for a bounded retry message. Small inputs are unchanged. Oversized inputs first use UTF-8 JSON and exact-text references to avoid repeated excerpts, then share the remaining text budget fairly across sources and their artifacts. All source identities, hashes and paths remain represented. Shortened excerpts report retained/omitted character counts, a truncation flag and an extraction-limit reason; full source files stay untouched, and limited excerpts cannot certify full capture.

`captures.json` records each operation and its attempts. Transient downloads get one retry; a Retry-After longer than 60 seconds is deferred with the wait recorded. A normal rerun reuses successful operations and leaves failed ones alone.

For an inaccessible source, find a legitimate repository/author/archived copy, then supply that URL or a manual file. Use the original citation URL as the stable key; no DOI is required.

```bash
python3 -m ingestion.pipeline alternative ingestion/runs/FLD "https://publisher.example/paper" "https://repository.example/paper.pdf"
python3 -m ingestion.pipeline attach ingestion/runs/FLD "https://publisher.example/paper" /absolute/path/paper.pdf
```

Alternative URLs are captured and their declared PDF links followed. Add `--retry` to `alternative` to retry that failed alternative. A fresh Wayback save is deferred; an existing accessible archive URL can be supplied as an alternative. Neither is a support gate.

A new copy must pass source-identity and passage review. The pipeline accepts a `sha256:` prefix only when the remaining hash exactly identifies a supplied artifact, and maps a resolved artifact URL back to its parent source-record key only when both the artifact hash and resolved URL uniquely match supplied metadata. It does not infer that different papers are equivalent. Per-field reviews retain the raw output and an audit of normalized references. Full-copy labels are capped at partial when extraction is truncated or has recorded issues. These metadata corrections preserve raw model output and never change claim judgments or repair unmatched passages. The reviewer may link any supplied source for a problem to another of that problem's claims when the saved passage supports it; each new link remains explicit in the assessment. Original access failures remain recorded even after an alternate copy supports the claim. Good copies are never replaced by failed retries.

## Inspect and back up

All runtime files, including copied sources and model prompts containing source text, live under Git-ignored `ingestion/runs/`. Tests use temporary directories and synthetic evidence; they do not call the real models or remote publishers.

Before treating the field as complete, inspect supported claims and unresolved cases, then create an external backup:

```bash
python3 -m ingestion.pipeline backup ingestion/runs/FLD ../2026_Takeoff_backups/FLD-20261031
```

The destination must be new and outside this project. The backup verifies every file hash and reopens every archived source. Its `backup-verification.json` records the check. Copy that directory back to a fresh run location to restore it; retain field settings, workflow caches, attempts, reconciled outputs and sources together. No command publishes or commits research.

## Tests

```bash
python3 -m unittest discover -s ingestion/tests -v
```

Coverage includes stage resumption, idempotency, failed-download recovery, preservation of good copies, artifact-bound passages, unsupported scope, missing evidence, capture completeness, manual attachments, UTF-8-safe PDF extraction, per-field batch completion, locks, subprocess failure/timeout, and backup readback. The suite tests orchestration and assessment boundaries; a real field is still needed to evaluate research quality and live account/provider behavior.

Explicit provider safety refusals are recorded in `workflow-blocked/` by stage and input hash. They bypass automatic retries, and identical inputs are not resent on resume. Other fields can continue, but the affected field remains incomplete until its review requirement is resolved. Normal Markdown heading variants are accepted without rewriting the saved research.

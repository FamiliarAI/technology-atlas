# Field ingestion

`ingestion.batch` coordinates `ingestion.field_workflow` across three fields at a time, refilling each slot when a field finishes. Review and rewrite each use three concept workers per field. See the [field onboarding runbook](../docs/runbooks/Field_Onboarding_Runbook.md) for research and evidence rules.

## Run and resume

From the repository root, install the dependencies in the Python environment used to run the pipeline:

```bash
python3 -m pip install -r ingestion/requirements.txt
```

The signed-in Grok, Codex and Claude CLIs are configured in `ingestion/config.json`; prompts are separate. The runner removes API-key environment overrides and does not switch accounts automatically.

For a new batch, prepare the canonical 66-field roster and original Markdown/JSON lists from Git revision `7bc3997d0e1ee3ccdb4073402fb9744827173dda`:

```bash
python3 -m ingestion.batch prepare --as-of 2026-11-01
python3 -m ingestion.batch run
```

For the existing batch, rerun `run` without preparing it again. To run only selected field prefixes:

```bash
python3 -m ingestion.batch run --fields MLC CLM VIR
```

`--fields PREFIX…` limits work to those prefixes; it does not change the roster. Unknown prefixes are rejected. Verified completed fields reuse their outputs and backup and still get an import check. Failed fields remain visible while other fields proceed.

Live status is in `ingestion/runs/all-fields/batch.json` and `progress.md`. Each field has a `workflow-receipt.json`, final JSON and Markdown, and a verified external backup. Use the manifest's field roots; Chemistry uses `ingestion/runs/CHEMREV/`. Backups default to `../2026_Takeoff_backups/all-fields/`.

Exit status is 1 if a selected field is incomplete or has an import error, and 2 if a stage runs out of usable fallback entries. In the latter case, the controller stops scheduling new fields; wait for a reset or add capacity. A selected subset can succeed while the overall batch remains incomplete.

## Stages and models

| Stage | Work | Ordered model list |
| --- | --- | --- |
| Research | Independent discovery without the original list; web tools enabled | Grok `grok-4.7` high → Codex `gpt-6.1-terra` high → Codex `gpt-6.1-sol` high → Claude `opus` |
| Reconcile | Compare the first pass with the original list; further research with web tools | Grok `grok-4.7` high → Codex `gpt-6.1-terra` high → Codex `gpt-6.1-sol` high → Claude `opus` |
| Format | Structure reconciled notes, original-entry dispositions and change log | Codex `gpt-6.1-terra` high → Codex `gpt-6.1-sol` high → Claude `opus` |
| Capture | Download and index cited sources; no model call | None |
| Review | One evidence review and proposed corrections per concept | Codex `gpt-6.1-sol` medium → Claude `opus` |
| Rewrite | One final record per reviewed concept, then deterministic merge | Codex `gpt-6.1-sol` medium → Claude `opus` |
| Finish | Validate, verify external backup, import into `atlas/core`, check, rebuild and commit | None |

A stage advances to the next model **only on classified provider exhaustion or timeout**. An unclassified error or invalid output does not trigger fallback. Format and review allow one same-model retry; Codex formatting output exhaustion lowers effort to medium for that retry. Research and reconcile have no same-model retry. A failed rewrite can recover a valid saved result or retry on a later run.

A safety refusal is final for every model. It is recorded under `workflow-blocked/` and checked before cache reuse or calls, even if the input metadata changes. The refused stage is never automatically retried, filtered or rerouted.

Grok exhaustion is shared across fields and saved as `providers.grok.exhausted_at` in `batch.json`. Grok is skipped for 24 hours after that timestamp; the next configured model can continue. A timeout permits fallback but does not start the cooldown. Grok calls have a 2,400-second timeout; other calls default to 3,600 seconds.

Reconciliation resumes the explicit Grok research session in its original `grok-workspace` only when Grok supplied that session and is available. Otherwise it starts a fresh conversation with the full first-pass list and original list. This is the same reconciliation pass; only tool history is absent. The attempt receipt records `resume` or `fresh`.

## Final output and withheld concepts

Each final record contains **concept, significance, missing breakthrough, current state, completion criteria, and related concepts**, with citations, corrections and unresolved issues. Rewrite inputs include the concept's research, structured record, validated review, source metadata and concept roster; full source documents are not sent again. Records retain stage model names in `models: {research, reconcile, format, review, rewrite}`; attempt receipts record provider and model.

Only a recorded safety refusal at review or rewrite makes a concept withheld. The final `withheld` list records `{id, title, stage, reason}`; the concept is excluded from `innovations` without narrowing or sending it to another model. Other review or rewrite failures block the field. A refusal at a field-wide stage blocks that stage. All non-withheld concept IDs and every original-entry disposition must survive validation.

To prepare rewrite inputs without calls, or rerun only the rewrite stage:

```bash
python3 -m ingestion.final_rewrite ingestion/runs/all-fields/MLC --prepare-only
python3 -m ingestion.final_rewrite ingestion/runs/all-fields/MLC --workers 3
```

This produces `final-innovations.json` and `final-innovations.md`; it does not perform the batch's backup or import. The batch validates records, reviews and saved-source hashes, then copies and verifies the field outside the project. The controller imports finished fields into `atlas/core` one at a time, checks the core, rebuilds SQLite and creates a Git commit naming the field and models. Existing core fields are left alone. A failed check or rebuild rolls back the import; an import error is recorded separately. Each field can land independently.

## Caching and recovery

Successful stages use content-verified `workflow-cache/<stage>-<fingerprint>.json` entries. Fingerprints include prompt/input, schema where applicable, and the selected entry's `{model, effort}`; resumed reconciliation also includes its session ID. Every model entry's cache is checked before any new call, including during cooldown. Prompt changes invalidate affected caches. Attempts and logs are retained.

`final-rewrite-cache/` stores validated records by prompt, schema and `{model, effort}`. The rewriter can also recover a matching prior result that passes current validation. Resume with the same settings and original list to reuse successful work.

`captures.json` makes downloads idempotent: normal reruns reuse successful operations and leave failed ones alone. Transient downloads get one retry; waits over 60 seconds are deferred. Capture follows PDF links without recursively crawling pages. If no bytes were retained and a DOI is available, the workflow tries one Europe PMC open-copy lookup and records it in `source-recovery.json`.

Saved PDF/HTML/XML/text artifacts retain hashes. PDF extraction preserves page markers, repairs surrogate pairs and replaces lone surrogates. Extraction issues and the 120,000-character artifact limit remain explicit. Review prompts are capped at 900,000 UTF-8 bytes, including retry space; repeated excerpts are deduplicated before text is shortened. Shortened text is marked partial; original files remain unchanged. Missing evidence means unresolved, not contradicted. No OCR or PDF rendering is performed.

For a legitimate alternate or manual copy, keep the original citation URL as the key:

```bash
python3 -m ingestion.pipeline alternative ingestion/runs/FLD "https://publisher.example/paper" "https://repository.example/paper.pdf"
python3 -m ingestion.pipeline attach ingestion/runs/FLD "https://publisher.example/paper" copies/paper.pdf
```

Use `alternative --retry` to retry a failed alternative. New copies still require identity and passage review. Raw reviews and reference-normalization audits are retained; metadata repairs do not change scientific judgments. Failed retries do not replace good copies.

Runtime files and source copies stay under Git-ignored `ingestion/runs/`. For a separate manual backup:

```bash
python3 -m ingestion.pipeline backup ingestion/runs/FLD ../2026_Takeoff_backups/FLD-recovery
```

The destination must be new and outside the project. Backup checks all file hashes and reopens archived sources, recording `backup-verification.json`. Restore the whole directory, including settings, caches, attempts and sources, together.

## Tests

With the dependencies installed in the same Python environment:

```bash
python3 -m unittest discover -s ingestion/tests -v
```

Tests use temporary directories and synthetic evidence rather than live models or publishers. They cover stage/cache reuse, fallback and cooldown, terminal refusals, withheld concepts, source recovery and extraction, review validation, batch completion, serialized import and backup verification. Live research quality and provider behavior still require real runs.

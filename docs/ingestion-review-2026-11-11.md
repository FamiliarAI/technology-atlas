# Ingestion pipeline review and change plan

November 11, 2026. Read-only review by Opus, edited by Fable. It feeds Track A of the [project plan](plans/technology-graph-plan.md). Line numbers are as of commit `6d40448`.

## How the pipeline works

`batch.run` (`ingestion/batch.py`) runs three fields at a time and calls `run_field` (`ingestion/field_workflow.py`). Per field:

| Stage | Model today | Calls | Notes |
|---|---|---|---|
| Research | Grok grok-4.7, high, web tools | 1 | 750k–1.04M tokens, 15–20 minutes |
| Reconcile | the same Grok session, resumed | 1 | 470k–900k tokens; session ID is in the cache key |
| Format | Codex Terra, high | 1 (+1 retry at medium) | |
| Capture | none | 0 | HTTP downloads, Europe PMC lookup |
| Review | Codex Sol, medium | 1 per concept (+ retries), 3 in parallel | |
| Final rewrite | Codex Sol (under the `review` config key) | 1 per concept, 3 workers | `ingestion/final_rewrite.py` |
| Backup | none | 0 | external copy |

About 3 + 2N calls per field; N averages 10.8.

- **Caching:** `workflow-cache/<stage>-<fingerprint>` and `final-rewrite-cache/`. The fingerprint includes the prompt text and the `{"model","effort"}` dict. `captures.json` makes capture idempotent.
- **Quota:** only Grok exhaustion is detected (`AccountExhausted`, by regex). The batch then stops scheduling fields. Codex has no exhaustion detection.
- **Refusal guard:** a marker per stage name under `workflow-blocked/`, checked first in `stage()`. Only OpenAI's refusal text is recognised.

## Findings

1. **Machine Learning was never refused.** MLC-11 fails before any model call: `pypdf` extracted lone UTF-16 surrogates from one PDF and `build_review_input` fails on `.encode('utf-8')` (`field_workflow.py:143`). It is a bug, not a provider refusal. CLM-02 and VIR-01 are real refusals.
2. **About 720 of `pipeline.py`'s 1,036 lines are a dead earlier pipeline:** the `Pipeline` class, `validate_ledger`, `validate_handoff`, `salvage_review`, `init_field`, the `init/run/repair-sources/revise` commands, the Grok branch of `Models.call`, `schemas.LEDGER` and `FIELD_REVIEW`, `prompts/source_ledger.md`, `prompts/field_review.md`, `sources.invalidate_summaries`, and 20 of the 53 tests in `test_pipeline.py`. **Keep:** `Models` (Codex), `passage_matches`, `execute`, `backup`, `locked`, and the `attach` and `alternative` commands; `atlas/add.py`, `atlas/prerequisites.py` and `atlas/labels.py` depend on some of these.
3. **One-off code:** `write_aggregate`; the Chemistry special case and `prepare`/`REVISION` in `batch.py`; the `--workers 13` limit in `final_rewrite.py`; the `self.models.__class__ is Models` test seam.
4. **Duplicated:** Grok invocation, subprocess and environment scrubbing, two locks, `max_output_tokens` recovery, and prior-output recovery each exist twice (`pipeline.py` and `field_workflow.py` or `final_rewrite.py`).
5. **Misleading:** Codex failure messages mention Grok credits; the README and runbook document the dead pipeline, the 66-field gate, a ban on fresh reconcile conversations and "no fallback providers"; the status document's roster is stale.
6. **Grok cannot carry the remaining research.** At the observed limit of about 600k tokens per rolling 24 hours, Grok cannot finish one field's research and reconcile (1.5–1.9M tokens) in a day. Codex Terra will do most of it in practice.
7. **Not covered by tests:** surrogate text, `run_field` end to end, a withheld concept, Codex exhaustion, and import into the atlas.

## What is left

| Group | Reusable work | Calls left |
|---|---|---|
| Machine Learning | research, reconcile, format, 10 of 11 reviews | fix the bug, then 1 review and 11 rewrites |
| Clinical Medicine | 14 of 15 reviews | 14 rewrites, CLM-02 withheld |
| Virology | 10 of 11 reviews | 10 rewrites, VIR-01 withheld |
| 32 other fields | none usable | a full run each: about 850 calls in all |

## Design decisions

- **Cache keys do not change.** A stage's fingerprint stays the `{model, effort}` of the entry actually used, and every entry's cache is checked before any call. Prompt files are not edited until MLC, CLM and VIR are finished: any text change would invalidate their cached stages and re-research them under new concept IDs. Wording needed only for a fresh reconcile is appended in code, on that path only.
- **Fallback happens only on positive exhaustion or timeout**, detected from the provider's error events and never from model text. Any other failure keeps today's same-model retry. A safety refusal is terminal for every model: the marker check stays first.
- **Grok exhaustion is remembered** in `batch.json` (`providers.grok.exhausted_at`) and Grok is skipped for 24 hours, so each field does not spend six minutes rediscovering it.
- **Reconcile** resumes the Grok session only if Grok did the research and is still available; otherwise it is a fresh call. `reconcile.md` already embeds the full first pass, so a fresh call loses only the tool history. This is the same pass, not a new kind. The mode is recorded.
- **Withheld concepts.** Only a recorded safety refusal makes a concept withheld; every other review failure still blocks the field. The final file lists `withheld: [{id, title, stage, reason}]`. The concept is never narrowed, filtered or sent to another model.
- **Import** into `atlas/core` runs in the controller thread, one field at a time, because `sources.jsonl` is rewritten on each import.
- **Model names.** Every stage receipt records provider and model; each final record gets `models: {research, reconcile, format, review, rewrite}`.

Config shape:

```json
"providers": {"grok": {"bin": "~/.grok/bin/grok"},
              "codex": {"bin": "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"},
              "claude": {"bin": "claude"}},
"stages": {
  "research":  [{"provider": "grok", "model": "grok-4.7", "effort": "high", "timeout_s": 2400},
                {"provider": "codex", "model": "gpt-6.1-terra", "effort": "high", "search": true},
                {"provider": "codex", "model": "gpt-6.1-sol", "effort": "high", "search": true},
                {"provider": "claude", "model": "opus"}],
  "reconcile": "same list as research",
  "format":    ["terra high", "sol", "opus"],
  "review":    ["sol medium", "opus"],
  "rewrite":   ["sol medium", "opus"]}
```

The existing `research`, `format`, `review`, `grok` and `codex` keys stay until `atlas/add.py`, `prerequisites.py` and `labels.py` are moved over.

## Steps

| # | Step | Done when | Who |
|---|---|---|---|
| 1 | Fix the surrogate bug in `sources.extract` (pair surrogates, replace lone ones), with a test | MLC-11's review input builds without a call; tests pass | Codex Sol |
| 2 | Remove the dead pipeline, its 20 tests and its README section | no references remain; atlas imports work; active prompt files' SHA-256 unchanged; tests pass | Codex Sol |
| 3 | Drop the 66-field gate (`write_aggregate` and its branch) | an incomplete batch writes no aggregate; tests updated | Codex Sol |
| 4 | Withheld concepts | tests show a refused concept is withheld, other failures block, the marker is respected | Opus |
| 5 | Import each finished field into `atlas/core` and run the check | a test shows import is idempotent and serialized | Opus |
| 6 | Record provider and model in receipts and records | cache keys unchanged: CLM, VIR and MLC caches still hit in a dry run | Opus |
| 7 | Fallback lists, the Grok cooldown, fresh reconcile | tests cover exhaustion, timeout, refusal-is-terminal and cache reuse | Opus |
| 8 | Documents: runbook, README, status | they describe the pipeline as it is | Codex Sol |
| 9 | Run Machine Learning, then Clinical Medicine and Virology, then the 32 fields | each field lands in `atlas/core` | the pipeline |

## Refused and deferred

- Refused: narrowing, filtering or re-routing CLM-02 or VIR-01; falling back on unclassified failures.
- Decided by the owner on November 11:
  - **Old run folders removed.** `BIO`, `CE`, `CHE`, `CHEM`, `CPE`, `EE`, `MATH`, `MATSCI`, `ME`, `PHY` and `batch-20261101T050201Z` under `ingestion/runs/` (189 MB) were moved to the Trash after checking that no field root, saved copy or record refers to them. `all-fields/` and `CHEMREV/` remain.
  - **Model names are backfilled** into the 31 imported fields as part of step 6, from each attempt's `model.json` (Codex) and `stdout.log` `modelUsage` (Grok). This is an attributed edit to `atlas/core`, not a content change.
  - **The pipeline commits `atlas/core` after each import** (step 5), using `atlas.core.commit`, with the field and the models in the message.

## Not verified

The Claude CLI flags, Codex's quota error wording, and Codex web-search behaviour for research. These must be checked by a real call before step 7 is called done.

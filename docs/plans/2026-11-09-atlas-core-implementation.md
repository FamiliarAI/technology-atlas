# Atlas core implementation plan

**Goal:** make `atlas/core/` (files in git) the source of truth for the atlas, with the SQLite database rebuilt from it.

**Design:** [2026-11-09-atlas-core-design.md](2026-11-09-atlas-core-design.md). Read it first.

**Stack:** Python 3.10+ standard library only, `unittest`. No new dependencies, no new tables, no model calls in this plan.

**Where to work:** the main checkout, branch `atlas-core`. A separate worktree will not work: the real data (`ingestion/runs/`, `atlas/data/`) is ignored by git and only exists here.

**Rules for every task:** write the test first; keep the existing terse style of `atlas/store.py`; do not touch `ingestion/`; do not change the server API or `atlas/web`; do not run any model call; do not commit (the orchestrator reviews and commits).

## File formats (the contract between tasks)

`atlas/core/<PREFIX>/field.json`

```json
{"id": "QUA", "name": "Quantum Computing", "color": "hsl(…)", "as_of": "2026-11-01", "boundaries": …,
 "created_at": "…", "imported_from": {"run_hash": "<sha256 of final-innovations.json>", "imported_at": "…"},
 "original_dispositions": […], "reconciliation_change_log": […]}
```

`color` is fixed at import (today's value from `store.color`) so adding fields never recolours old ones.

`atlas/core/<PREFIX>/<ID>.json` — the ingestion record, with these changes only:

- added `"field": "QUA"` and `"status": "active"` (the other value is `"retired"`, with `"merged_into": "<ID>"`);
- each `completion_criteria` item gains `"id": "m1"` (assigned in order at import, never renumbered) and `"label"` (text before the first `:` in the criterion if that is 80 characters or fewer, else the first 8 words);
- `"sources"` becomes an ordered list of URLs; the details move to `sources.jsonl`;
- `"provenance"` paths become relative to the repository root;
- `"prerequisites"` keeps today's shape: `[{"id", "reason", "model", "field"}]`.

`atlas/core/sources.jsonl` — one line per URL, sorted by URL:

```json
{"url": "…", "title": "…", "status": "saved", "copies": [{"sha256": "…", "format": "html", "kind": "source", "resolved_url": "…", "retrieved_at": "…", …}]}
```

The URL is the source's ID. `copies` is the union, by `sha256`, of every artifact any breakthrough recorded for that URL, with `path` and `absolute_path` removed. Where breakthroughs disagree on title or status, the first seen (fields in sorted order) wins.

`atlas/core/progress.jsonl` — one line per judgement, in the order added:

```json
{"breakthrough": "QUA-01", "milestone": "m1", "url": "…", "copy": "<sha256>", "source_date": "2024-08-27", "verdict": "advances", "quote": "…", "by": "gpt-6.1-terra", "added_at": "…"}
```

All JSON is written with `indent=1, ensure_ascii=False`, a trailing newline, and stable key order, so diffs are small. No absolute path appears anywhere under `atlas/core/`.

**Finding saved copies:** files are named `<sha256>.<ext>`. A resolver indexes `ingestion/runs/**/sources/` and `atlas/data/added/sources/` by file stem. Nothing in `atlas/core/` stores a path to them.

## Task 1 — core module, import and check (Codex, GPT-6.1 Sol)

Files: create `atlas/core.py`, `atlas/tests/test_core.py`.

`atlas/core.py` provides:

- `CORE = ROOT / 'atlas/core'`
- `import_field(folder, core=CORE, color=None)` — reads `<folder>/final-innovations.json` and writes the field's files in the formats above, merging its sources into `sources.jsonl`. Raises if `core/<PREFIX>/` already exists (re-importing over edited pages is deferred work). Applies the validity checks `store.import_fields` applies today (prefix match, unique IDs, six non-empty sections).
- `load(core=CORE)` — returns `{'fields': {id: dict}, 'breakthroughs': {id: dict}, 'sources': {url: dict}, 'progress': [dict]}`.
- `write_breakthrough(item, core=CORE)`, `write_sources(sources, core=CORE)`, `write_progress(rows, core=CORE)` — the only writers; they produce the stable formatting.
- `check(data)` — returns a list of problem strings, empty when sound: breakthrough ID matches its file and field; milestone IDs unique within a breakthrough; every `prerequisites` ID exists and `prerequisites` has no loop; every `merged_into` exists; every `sources` URL is in `sources.jsonl`; every progress row names an existing breakthrough, milestone and source URL, and a valid verdict; no string value starts with `/Users/` or `/private/`.
- `python3 -m atlas.core import` imports every field `store.completed_fields()` lists that is not yet in core, then also carries over, from the existing `atlas/data/atlas.sqlite3` if present: `prerequisites` already stored in breakthrough payloads, and progress rows with a verdict (converting `criterion` n to milestone `m<n>`, `model` to `by`, `asset` to `copy`; adding a source line for a URL not yet known). `python3 -m atlas.core check` prints problems and exits non-zero if any.

Tests (use the SWE fixture pattern in `atlas/tests/test_atlas.py` `setUp`): import writes the files and a second import raises; milestone IDs and labels; sources merged across two breakthroughs citing one URL; no absolute paths; `load` round-trips what the writers wrote byte-for-byte; `check` reports each kind of problem on a deliberately broken copy.

Then run `python3 -m atlas.core import` on the real data.

Done when: `python3 -m unittest discover -s atlas/tests` passes; `atlas/core/` has 31 field folders and 334 breakthrough files; `progress.jsonl` has 4 lines; QUA files hold the 5 prerequisite links; `python3 -m atlas.core check` prints nothing.

## Task 2 — rebuild the database from core (Opus 5.5)

Files: modify `atlas/store.py`, `atlas/tests/test_atlas.py`, `atlas/README.md`.

- Replace `import_fields` with `rebuild(core=CORE, path=DB)`: run `core.check` and stop on any problem; build a fresh database at a temporary path beside `path`, then replace `path` atomically. Same six tables, same columns.
- `breakthroughs.payload` is the core record with `sources` expanded back to `[{url, title, status, artifacts}]` from `sources.jsonl`, so `server.py` and the UI are untouched. Retired breakthroughs are not loaded.
- `assets`: one row per copy found by the resolver, hash verified as today; a copy whose file is missing is skipped and counted in the printed summary, not an error (the files are private and may be absent on another computer). `documents`: from `provenance`, as today.
- `runs`: one row per field from `imported_from` (payload: the `field.json` text). `fields`: from `field.json`.
- `progress`: the derived `research:` rows exactly as `backfill_progress` makes them now, plus one row per `progress.jsonl` line with the same `added:<copy>:<breakthrough>:<n>` ID as today, where n is the milestone's position.
- `python3 -m atlas.store` runs `rebuild` and prints counts.
- Rewrite the tests that exercised importing from ingestion so they import into a temporary core, then rebuild. Keep the behaviours that still apply (allowlisted, integrity-checked downloads; explicit-mention connections; progress summary; backfill without status). Add: deleting the database and rebuilding gives byte-identical table contents; a `check` problem stops the rebuild and leaves the old database in place.

Parity proof (write the script to the scratch directory, do not add it to the repo): before rebuilding, copy the current `atlas/data/atlas.sqlite3`. After, compare every breakthrough payload old against new, ignoring only: the added `field`, `status`, milestone `id` and `label` keys; `path`/`absolute_path` in artifacts; `provenance` path form. For `sources`, report (do not fail on) entries whose title, status or artifact list changed because of the merge by URL, with counts. Compare progress row sets and the catalog's `connections`.

Done when: all tests pass; the parity script reports 334 of 334 payloads equal under those rules and lists any source-merge differences; the 4 verdicts and 5 links are present after `rm atlas/data/atlas.sqlite3 && python3 -m atlas.store`; the server starts and `/api/catalog` and `/api/breakthroughs/QUA-01` respond.

## Task 3 — writers go through core (Codex, GPT-6.1 Sol)

Files: modify `atlas/add.py`, `atlas/prerequisites.py`, `atlas/tests/test_atlas.py`, `atlas/README.md`.

- `atlas.add`: still reads candidates from the database. Instead of writing `progress` and `assets` rows, it adds the source line if the URL is new (or adds the new copy to its `copies`), replaces any earlier `progress.jsonl` lines for that URL with the new ones, then calls `store.rebuild`. Signature gains `core=CORE`.
- `atlas.prerequisites`: still builds its prompt from the database. Instead of updating payloads, it rewrites the `prerequisites` list in the affected breakthrough files with `core.write_breakthrough`, then calls `store.rebuild`.
- Both `main()` functions finish with `git add atlas/core && git commit` unless `--no-commit` is given. Message: what was added, then a `Model:` line and the call-record folder. Library functions never run git; tests never commit.
- Update the two existing tests for these modules to assert on core files and on the rebuilt database.

Done when: all tests pass; with a stubbed `call`, adding a URL twice leaves one set of lines; links written by `prerequisites` survive `rm` of the database and a rebuild.

## Task 4 — verify and review (orchestrator)

Run the full test suite, the parity script, `atlas.core check`, and the server by hand; read the diff; update the main plan's status lines. Commit `atlas/core/` as its own commit ("Import 31 fields into atlas/core"), separate from the code.

## Deferred, deliberately

- Re-importing a field whose pages have been edited (the "research proposes a diff" flow).
- The weekly paper finder.
- Importing a field without its refused concept; that is an ingestion change.

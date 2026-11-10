# Technology Atlas v1

Local, read-only exploration of the reviewed breakthroughs from **every field the ingestion batch marks complete** (31 fields, 334 breakthroughs as of November 1, 2026). Existing research is imported unchanged; no new model calls or research reruns are required.

## Run

From the repository root, using Python 3.10 or later (standard library only):

```bash
python3 -m atlas.store
python3 -m atlas.server --port 8765
```

Open **http://127.0.0.1:8765**. The server binds only to this computer. It is not a hosted service and is not accessible from another device through that localhost address.

`python3 -m atlas.store` rebuilds `atlas/data/atlas.sqlite3` from the records in `atlas/core/` (files in Git; see the [core design](../docs/plans/2026-11-09-atlas-core-design.md)). It runs `python3 -m atlas.core check` first and stops on any problem, leaving the existing database in place; otherwise it builds a new database beside the old one and swaps it in. Deleting the database and rebuilding gives the same contents. New completed fields enter the core with `python3 -m atlas.core import`, then rebuild.

Saved source copies are not in Git. The rebuild finds each copy by its SHA-256 file name under any `sources/` folder in `ingestion/runs/` or `atlas/data/added/`, verifies its hash, and prints how many copies are missing; a missing copy is skipped (its download is unavailable), a changed one stops the rebuild.

## Tech tree (React)

The tech tree lives in `atlas/web` (React, Vite, Framer Motion; type and palette from the Silicon Data pitch, fonts bundled locally). Build it once, then open **http://127.0.0.1:8765/tree/**:

```bash
cd atlas/web && npm install && npm run build
```

The build goes to `atlas/static/tree/` (ignored by Git) and is served by `atlas.server`. For live editing, run `npm run dev` with the server on port 8765; Vite proxies `/api`.

- Desktop: one lane per field, read left to right; each breakthrough is a card with a segmented bar (one segment per milestone: met, in progress, none). Cards within a lane are ordered by progress. Hovering a card draws its `related_concepts` links. These are not prerequisites; prerequisite order is deferred (see the project plan).
- Phone (≤ 760px): one field at a time as a vertical path; swipe sideways or use the field chips to change field.
- Detail panel (bottom sheet on phones): milestones with their status and the progress rows judged against each, research sources not yet tied to a milestone, related breakthroughs, and a link to the full record at `/#ID`.
- API addition: `GET /api/progress` returns each breakthrough's milestone status list and progress row count.

## Included

- Field filters, full-text search, graph overview, and a mobile-friendly library.
- Each record's completion criteria shown as numbered milestones.
- Every breakthrough's six final sections, source references, unresolved issues, and review change history.
- Deep links such as `http://127.0.0.1:8765/#SWE-01`.
- Explicit related-concept references from the reviewed material, with the original explanations accessible in the detail view. Hover or keyboard-focus a map node to reveal its references; click or press Enter for its record. Drag the map to pan and use the zoom controls to inspect it.
- Original publisher/repository links and local saved-copy downloads. Copies may be partial; the interface preserves capture status and evidence limitations.
- Review and research provenance downloads, import timestamps, and final-set SHA-256 fingerprints.
- A SQLite view rebuilt atomically from `atlas/core/`, with stable IDs; Git holds the history of every record.

The graph is a map of explicit discussion references, **not a dependency graph**. No cross-field semantic matching pass has been performed. Connections do not establish causality, prerequisites, or achievement. Reviewed concepts are proposals, not completed breakthroughs or forecasts.

## Adding progress

```bash
python3 -m atlas.add https://arxiv.org/abs/2408.13687
python3 -m atlas.add <url> --breakthrough CSC-02   # also judge every milestone of CSC-02
python3 -m atlas.add <url> --no-commit            # write and rebuild, leave changes uncommitted
```

1. Saves the source into `atlas/data/added/sources/<sha256>.<ext>` (page plus any declared PDF, using the ingestion capture code). A URL already saved by the research reuses that copy. A Wayback save is requested; the archive copy is at `https://web.archive.org/web/<url>`.
2. Ranks every milestone against the source's opening text by IDF-weighted word overlap, in memory, and keeps the top 20 (plus all of `--breakthrough`'s milestones).
3. Makes one model call (the ingestion `format` model, strict JSON schema) that returns a row per milestone the source bears on: verdict `advances`/`meets`/`contradicts` and an exact quote. Prompt, schema, logs and response are kept in `atlas/data/added/calls/`.
4. Writes the URL and saved-copy hash to `atlas/core/sources.jsonl`, merging copies by hash and keeping existing source metadata. Writes rows whose milestone was a candidate and whose quote is found in the saved copy to `atlas/core/progress.jsonl`, using stable milestone IDs; prints the rest as rejected. Re-adding a URL replaces all its earlier judgement lines, including when the new result is empty.
5. Rebuilds the database from core, including saved-copy assets, then commits `atlas/core/` with the URL, model and call-record folder in the message. `--no-commit` skips Git while still writing core and rebuilding.

## Prerequisite order

```bash
python3 -m atlas.prerequisites SWE CSC
python3 -m atlas.prerequisites --all
python3 -m atlas.prerequisites SWE --no-commit
```

Each field gets one model call using its database records and a catalog of every active breakthrough. Checked links are written through the core writer to the dependent breakthrough's JSON file as `prerequisites: [{id, reason, model, field}]`. Unknown IDs, self-links, duplicates, links outside the requested field and loops are rejected. Re-running a field replaces links produced by that field's earlier call, preserving links from other fields. Source lists in these files remain URL lists.

The database is rebuilt after each field. The command then commits `atlas/core/` once, with the fields, model and call-record folders (`atlas/data/prerequisites/`) in the message. `--no-commit` skips Git while keeping the file writes and rebuilds. The library functions `atlas.add.add` and `atlas.prerequisites.run` accept `core=` and `path=` and never run Git.

## Data and integrity

`atlas/data/atlas.sqlite3` is generated locally and ignored by Git. Tables:

- `runs`: one row per field: the hash and import time of the ingestion output it was imported from, and its `field.json`.
- `fields`: navigation groups (one per field), with the colour fixed at import.
- `breakthroughs`: the core records of active breakthroughs (retired ones are left out), with each source URL expanded back to `{url, title, status, artifacts}` from `sources.jsonl`.
- `assets`: saved source copies found on this computer, and their hashes.
- `documents`: research, structured-record, and review provenance files inside the repository.
- `progress`: one row per source per milestone it bears on (breakthrough, criterion number, URL, saved-copy hash, source date, verdict `advances`/`meets`/`contradicts`, quote, model, date added). Each `current_state` paragraph's cited sources are derived with criterion and verdict left empty (`research:` IDs); each line of `atlas/core/progress.jsonl` becomes an `added:` row. Milestone status is computed from rows: `meets` → met, `advances` → in progress.

The database is a disposable view. Progress judgements and prerequisite links are saved in `atlas/core/` and survive deleting and rebuilding the database.

Saved copies must match their hash at rebuild. Every subsequent download checks the bytes again. Downloads use attachment disposition and `nosniff`, including saved HTML, so source-page scripts are not executed as application content. The API never accepts arbitrary filesystem paths. Local paths in records are redacted from browser API responses.

The database references original private files rather than copying all source documents again. Keep the database and the referenced ingestion directories together when backing up or moving this prototype. The existing per-field backups remain the authoritative recovery copies for research. The app does not modify those files.

API:

- `GET /api/catalog`
- `GET /api/breakthroughs/<ID>`
- `GET /api/assets/<SHA256>` — verified attachment download
- `GET /api/documents/<ID>:<provenance-kind>` — verified attachment download

No write/intake endpoints, authentication system, public redistribution, or hosted deployment are included in this first exploration prototype. A dated-progress submission flow and reviewed cross-field matching remain subsequent product work.

## Validation

```bash
python3 -m unittest discover -s atlas/tests -v
node --check atlas/static/app.js
```

`test_core.py` covers importing into and checking `atlas/core/`; `test_atlas.py` covers the rebuild (identical tables after deleting and rebuilding, a check problem or changed copy leaving the old database in place, missing copies skipped), relationship extraction, download allowlisting/integrity, progress, and the add and prerequisite passes.

`tests/browser-smoke.js` contains a Playwright function that can be supplied as the `code` argument to the connected browser's `browser_run_code_unsafe` tool. Its file loader may restrict paths outside the browser workspace. It exercises filtering, searching, empty-state reset, six-section details, related-record navigation, source downloads, deep links, mobile overflow, and keyboard dismissal against the running local app. It is not required to run the application.

Manual visual inspection was performed at 1440px desktop and 390px mobile widths. All 39 imported breakthrough objects were compared with their source final JSON, and a repeat import returned no changes.

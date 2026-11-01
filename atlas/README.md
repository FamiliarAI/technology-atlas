# Technology Atlas v1

Local, read-only exploration of the reviewed innovations from **every field the ingestion batch marks complete** (31 fields, 334 innovations as of November 1, 2026). Existing research is imported unchanged; no new model calls or research reruns are required.

## Run

From the repository root, using Python 3.10 or later (standard library only):

```bash
python3 -m atlas.store
python3 -m atlas.server --port 8765
```

Open **http://127.0.0.1:8765**. The server binds only to this computer. It is not a hosted service and is not accessible from another device through that localhost address.

`python3 -m atlas.store` reads `ingestion/runs/all-fields/batch.json` and imports each field with status `complete` from its manifest `root` (Chemistry lives in `ingestion/runs/CHEMREV/`). Re-run it as more fields complete; unchanged fields are skipped. The private runtime data is intentionally excluded from Git. Restore it from the verified field backups if moving to another computer.

## Included

- Field filters, full-text search, graph overview, and a mobile-friendly library.
- Each record's completion criteria shown as numbered milestones.
- Every innovation's six final sections, source references, unresolved issues, and review change history.
- Deep links such as `http://127.0.0.1:8765/#SWE-01`.
- Explicit related-concept references from the reviewed material, with the original explanations accessible in the detail view. Hover or keyboard-focus a map node to reveal its references; click or press Enter for its record. Drag the map to pan and use the zoom controls to inspect it.
- Original publisher/repository links and local saved-copy downloads. Copies may be partial; the interface preserves capture status and evidence limitations.
- Review and research provenance downloads, import timestamps, and final-set SHA-256 fingerprints.
- SQLite import with exact original JSON snapshots, stable IDs, preserved earlier versions, atomic updates, and no duplicate records when the same run is imported again.

The graph is a map of explicit discussion references, **not a dependency graph**. No cross-field semantic matching pass has been performed. Connections do not establish causality, prerequisites, or achievement. Reviewed concepts are proposals, not completed breakthroughs or forecasts.

## Data and integrity

`atlas/data/atlas.sqlite3` is generated locally and ignored by Git. Tables:

- `runs`: immutable full field snapshots, content hash, and import timestamp. These retain original dispositions and all final metadata.
- `fields`: navigation groups (one per completed field) and their current snapshot.
- `innovations`: complete final records, unchanged from the ingestion outputs.
- `assets`: allowlisted saved source files and their hashes.
- `documents`: allowlisted research, structured-record, and review provenance files.

Imported source artifacts must exist inside their field directory and match their saved hash. Every subsequent download checks the bytes again. Downloads use attachment disposition and `nosniff`, including saved HTML, so source-page scripts are not executed as application content. The API never accepts arbitrary filesystem paths. Local paths in records are redacted from browser API responses.

The database references original private files rather than copying all source documents again. Keep the database and the referenced ingestion directories together when backing up or moving this prototype. The existing per-field backups remain the authoritative recovery copies for research. The app does not modify those files.

API:

- `GET /api/catalog`
- `GET /api/innovations/<ID>`
- `GET /api/assets/<SHA256>` — verified attachment download
- `GET /api/documents/<ID>:<provenance-kind>` — verified attachment download

No write/intake endpoints, authentication system, public redistribution, or hosted deployment are included in this first exploration prototype. A dated-progress submission flow and reviewed cross-field matching remain subsequent product work.

## Validation

```bash
python3 -m unittest discover -s atlas/tests -v
node --check atlas/static/app.js
```

Five behavioral tests cover lossless/idempotent import, retained prior revisions, transactional rollback on altered source bytes, provenance-preserving relationship extraction, and download allowlisting/integrity.

`tests/browser-smoke.js` contains a Playwright function that can be supplied as the `code` argument to the connected browser's `browser_run_code_unsafe` tool. Its file loader may restrict paths outside the browser workspace. It exercises filtering, searching, empty-state reset, six-section details, related-record navigation, source downloads, deep links, mobile overflow, and keyboard dismissal against the running local app. It is not required to run the application.

Manual visual inspection was performed at 1440px desktop and 390px mobile widths. All 39 imported innovation objects were compared with their source final JSON, and a repeat import returned no changes.

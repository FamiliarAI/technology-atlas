# Technology Graph plan

Status: in progress. Updated November 11, 2026. Earlier designs (the hosted architecture, the v5 research pipeline, the 660-entry migration) were removed from this file on November 11; they are in git history before that date. Hosted deployment and account creation still require separate authorization.

## Current plan (November 1, 2026)

### Goals

- a) Lists of breakthroughs we may see in the future, the milestones that say they have been achieved, and attribution of where each came from.
- b) Progress towards them that we add to over time, as papers and links.
- c) A UI to view it all, modelled on a strategy-game tech tree.
- d) A polished UI that works on mobile, with motion, in the style of the Silicon Data pitch in am-live (`docs/sponsor-segments/silicon-data/silicon-data-segment.html`).
- e) An arbitrary paper (for example from arXiv) can be added once and count as progress for several breakthroughs.

### Terms

- **Breakthrough**: a leaf of the tree, one proposed future capability (ID like `CSC-02`). Stored in the `breakthroughs` table and served at `/api/breakthroughs/<ID>`. The ingestion pipeline still writes `final-innovations.json` with an `innovations` list; the atlas reads that format unchanged.
- **Milestone**: one of a breakthrough's completion criteria, numbered 1…n.
- **Progress**: one source (paper or link) judged against a milestone, one row in `progress`.

### Cost rule

Reuse existing data and structures. This plan adds **one new table (`progress`)**, **no model passes over existing data**, and **one model call per paper added**. Any further table or model pass needs an explicit decision. (Since added by decision: one prerequisite call per field.)

### Starting point

- `ingestion/` produces each field's `final-innovations.json`: 31 of 66 fields are complete (334 breakthroughs); see `docs/ingestion-status-2026-11-01.md`.
- `atlas/` is the v1 prototype: SQLite importer (`runs`, `fields`, `breakthroughs`, `assets`, `documents`), read-only server and API, and a static UI loading 4 fields (SWE, CSC, CPE, ROB). See `atlas/README.md`.

### Steps

1. **Load all completed fields (goal a).** Point the existing importer at every completed field and remove the hard-coded four-field copy. Milestones are each record's existing `completion_criteria` items, numbered 1…n and served as-is. Sources are each record's existing `sources` and saved copies. New fields are imported the same way as ingestion finishes them.
2. **Add the `progress` table and backfill it (goal b).** Columns: breakthrough ID; criterion number (nullable); URL; saved-copy SHA-256 (row in the existing `assets` table); source date; verdict `advances` / `meets` / `contradicts` (nullable); quote; model; date added. Backfill by copying, with no model calls: each `current_state` paragraph and its cited `source_urls` becomes one row with criterion and verdict left empty, attributed to the research model and research date. Criterion status is computed from rows: `meets` → met, `advances` → in progress. Tests sit with the existing ones in `atlas/tests`.
3. **`atlas add <url>` (goals b and e).** (1) Save the paper into `assets` with a local PDF and a Wayback link; skip the download if the URL or hash already exists. (2) Rank all criteria against the abstract by word-overlap scoring computed in memory (nothing stored, no model) and keep the top ~20. (3) One model call (Codex, GPT-6.1 Terra, strict JSON schema) returns a `progress` row for each criterion the paper touches; code checks that each quote appears in the paper and rejects rows that fail. One paper touching three breakthroughs is three rows. `--breakthrough ID` forces a target the ranking missed.
4. **Tech-tree UI (goals c and d).** React + Vite + Framer Motion, reading the existing server API plus one progress endpoint. Style from the Silicon Data pitch: Outfit, DM Sans and JetBrains Mono, self-drawing SVG lines, the same easing. One lane per field; each breakthrough is a node with a segmented bar per criterion (met / in progress / none); lines from the existing `related_concepts` references; nodes within a lane ordered by progress. Node detail is the existing record view plus a timeline of progress rows with their papers and quotes. Mobile: a vertical path per field, swiped between fields, tap to open. An original design in the strategy-game genre, not a copy of any game's artwork.

### Core architecture: a fixed core, and edits over time (November 2, 2026)

The atlas must change over time the way a wiki does: every part can be corrected or extended, and every change is attributed and can be undone. The design separates a small core that never changes from everything else, which changes only through edits.

**The core (fixed):**

1. **Permanent IDs.** A field, breakthrough or milestone keeps its ID forever. Records are retired or merged, never deleted, and IDs are never reused. Links, progress and history all refer to IDs.
2. **A small set of record kinds:** field; breakthrough; milestone; link between breakthroughs (`needs`, `discussed together`); progress (a source judged against a milestone); source (saved copy and its SHA-256). A new kind is a rare, deliberate decision.
3. **Saved, fingerprinted sources.** Every claim points to a saved source or to an edit.
4. **Every change is an edit.** An edit records the record ID, what changed, the author (a person, or a model with its prompt and call record), the time, the reason, and the evidence. The current state of any record is its first version plus its edits in order.

**Everything else changes through edits:**

- Content: titles, descriptions, milestones, verdicts.
- Structure: new fields and breakthroughs, splits and merges, adding or removing links.
- Process: prompts, models, and the rules for what counts as a link. Because each edit names its model and prompt, a process change never corrupts history: edits made under an old rule can be found and redone on their own.

**How the existing pieces fit:**

- Ingestion research is the first edit to each breakthrough, by the research model.
- `atlas.add` writes progress edits; `atlas.prerequisites` writes link edits; a person's corrections are edits recorded the same way.
- The SQLite database is a view rebuilt from the core, as it already is from the ingestion files. It is not the source of truth.

**Decided November 9, 2026: the core lives in git files.** The owner and the owner's agents edit; everyone else reads. Records are files under `atlas/core/`, edits are commits, and the database is rebuilt from them. Record kinds, layout, the one-time import of existing data and the growth flow are in the [core design](2026-11-09-atlas-core-design.md). An edits table, accounts and web editing are not built. Built November 9: `python3 -m atlas.core import` slotted the 31 complete fields in, `python3 -m atlas.store` rebuilds the database from the files, and `atlas.add` and `atlas.prerequisites` write to the files and commit ([implementation plan](2026-11-09-atlas-core-implementation.md)).

### Prerequisite order (started November 2, 2026)

True prerequisite order ("A must be achieved before B") is wanted. `atlas/prerequisites.py` (`python3 -m atlas.prerequisites FIELD … | --all`) makes one model call per field that sees the field's breakthroughs in full and a one-line catalog of all breakthroughs, and returns, per breakthrough, what it needs and what needs it, from any field. A link means B is expected to come first on the way to A (A builds on B, uses it as a component, assumes its result, or B is the expected route); merely helpful, topical, or same-capability pairs are not links. Code rejects unknown IDs, self-links, links with neither side in the field, and links that close a loop. Each call's prompt and response are kept under `atlas/data/prerequisites/`.

Status: run on Quantum Computing (5 links, including from CPE-01 and CSC-02) and Computer Science (no new links). Links are stored in the dependent breakthrough's file in `atlas/core/` and survive a rebuild. Remaining: run the other fields, and compute tree columns from the longest prerequisite chain. Until then the tree orders nodes by progress.

This plan supersedes the deprecated paid-report plan in `archive/AI_Takeoff_Project_Plan.md` (dated forecasts, PDF product, blog/thread funnel). That plan is history only and is not a goal, input, or constraint for this project.

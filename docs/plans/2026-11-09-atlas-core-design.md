# Atlas core design

Decided November 9, 2026. This settles the "where the core lives" question in the [project plan](technology-graph-plan.md).

## Decisions

- **Who edits:** the owner and the owner's agents. Everyone else reads. No accounts, permissions or web editing.
- **Where records live:** files in git, under `atlas/core/`. Git is the history, attribution and undo.
- **The SQLite database** is a view rebuilt from `atlas/core/`. It keeps its current tables.
- **Count:** no new tables, one new folder, one optional new kind of model call (the paper finder).

## Record kinds

There are six kinds. Adding a seventh is a rare, deliberate decision.

| Kind | Permanent ID | Holds | Comes from |
|---|---|---|---|
| Field | `QUA` | name, colour | `fields` table |
| Breakthrough | `QUA-01` | title, concept, significance, missing breakthrough, current state, related-concepts text, unresolved issues, home field | each record in `final-innovations.json` |
| Milestone | `QUA-01.m1` | one completion criterion, a short label, its source URLs | each `completion_criteria` item |
| Link | from + to + type | type `needs` or `related`, the reason, who said so | prerequisite links; IDs mentioned in `related_concepts` |
| Source | hash of the URL | URL, title, date, saved copies with their SHA-256 | each record's `sources`; the `assets` table |
| Progress | source + milestone | verdict `advances` / `meets` / `contradicts`, exact quote, who judged, when | judged rows of the `progress` table |

Rules:

- An ID is never reused. A record is retired or merged (`status: retired`, `merged_into`), never deleted; its file stays.
- A milestone's ID is assigned once and does not change when milestones are inserted, split or reordered. Milestone status is computed from progress: `meets` → met, `advances` → in progress.
- A breakthrough has one home field. Anything cross-field is a link. Fields are navigation labels.
- Every progress row and link names who made it: a person, or a model and its saved call record.

## Layout

```
atlas/core/
  QUA/
    field.json        the Field
    QUA-01.json       one Breakthrough, with its Milestones and its outgoing "needs" Links
  sources.jsonl       one line per Source
  progress.jsonl      one line per Progress judgement, append-only
```

- Milestones and `needs` links sit inside their breakthrough's file, so each breakthrough has one page with one history.
- `related` links are derived at rebuild from the IDs mentioned in the related-concepts text, as the importer does now.
- Sources and progress are line-per-record files because they only grow by appending and one paper can bear on several breakthroughs.
- Saved PDFs and pages stay out of git. `sources.jsonl` records their SHA-256.
- No absolute local paths are written into `atlas/core/`.

## History and undo

- One edit is one commit. The message gives the reason; git gives author and time. An agent's commit names its model and prompt.
- Undo is `git revert`. A page's history is `git log` on its file.

## Slotting in existing data

One script, run once, no model calls:

1. Each complete field gets `field.json`; each breakthrough gets its file, text copied unchanged.
2. Each `completion_criteria` item becomes `m1`, `m2`, … in order. Its label is the criterion's own opening phrase, taken by code.
3. The 5 existing prerequisite links become `needs` links.
4. The distinct source URLs (1,008 on November 9) become lines in `sources.jsonl`.
5. The 4 judged progress rows go into `progress.jsonl`. Unjudged rows are each breakthrough's own citations; they are derived at rebuild and not stored.

Done when: the database rebuilt from `atlas/core/` has the same 334 breakthroughs with identical content as the current one, and the 4 verdicts and 5 links survive deleting and rebuilding the database.

## How it grows

- **A paper:** `atlas add <url>` as now (save a copy, rank milestones, one model call, check each quote against the saved copy), writing a Source line and Progress lines to `atlas/core/` and committing.
- **Finding papers:** URLs pasted by the owner, or an optional weekly finder (Grok searching recent papers per field) that feeds `atlas add`.
- **A field:** when ingestion finishes a field it is imported as new files. Fields arrive one at a time; there is no "all 66 complete" gate. A field imports without a concept the provider refused to review; the refusal guard is not bypassed.
- **A correction:** edit the breakthrough's file, run the check, commit with the reason.
- **Re-running research** on an imported field never overwrites its files. It produces a diff to accept or reject.

## Check

One script, run on every rebuild: IDs are unique; links resolve; `needs` has no loops; every progress row points at an existing milestone and source; no retired ID is reused.

## Code changes

- New: the one-time import script and the check script.
- `atlas/store.py` rebuilds from `atlas/core/` instead of the ingestion output.
- `atlas/add.py` and `atlas/prerequisites.py` write to `atlas/core/`.
- Server, API and tree UI are unchanged.

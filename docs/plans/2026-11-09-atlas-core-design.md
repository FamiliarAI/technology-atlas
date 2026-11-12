# Atlas core design

Decided November 9, 2026. Corrected November 11 to match the code as built, and updated November 11 for the change to a map: the atlas no longer publishes order claims, and a paper can be a step toward a whole breakthrough. This settles the "where the core lives" question in the [project plan](technology-graph-plan.md). For every field of every record, see the [data reference](../data-reference.md).

## Decisions

- **Who edits:** the owner and the owner's agents. Everyone else reads. No accounts, permissions or web editing.
- **Where records live:** files in git, under `atlas/core/`. Git is the history, attribution and undo.
- **The SQLite database** is a view rebuilt from `atlas/core/`. It has five tables: `fields`, `breakthroughs`, `assets`, `documents` and `progress`.
- **Count:** no new tables, one new folder, one optional new kind of model call (the paper finder).

## Record kinds

There are six kinds. Adding a seventh is a rare, deliberate decision.

| Kind | Permanent ID | Holds | Comes from |
|---|---|---|---|
| Field | `QUA` | name, colour, evidence date, scope boundaries, where it was imported from, the research run's dispositions and change log, and any withheld concepts | the field's `final-innovations.json` |
| Breakthrough | `QUA-01` | title, concept, significance, missing breakthrough, current state, related-concepts text, unresolved issues, home field | each record in `final-innovations.json` |
| Milestone | `QUA-01.m1` | one completion criterion: its text, a short label, its source URLs | each `completion_criteria` item |
| Link | from + to | a `needs` link: the prerequisite's ID, the reason, the model that proposed it. Kept in the records and checked, but not published in the site data. | `atlas.prerequisites`, one call per field |
| Source | the URL itself | URL, title, capture status, saved copies with their SHA-256 | each record's `sources` |
| Progress | source + milestone, or source + breakthrough | verdict `advances` / `meets` / `contradicts`, exact quote, the source's date, the saved copy judged, who judged, when. `milestone: null` means a step toward the breakthrough as a whole; it can only advance or contradict. | `atlas.add`, one call per paper |

Rules:

- An ID is never reused. A record is retired or merged (`status: retired`, `merged_into`), never deleted; its file stays. This is a rule for editors: the check confirms that `merged_into` resolves but does not detect a reused ID. No record has been retired yet.
- A milestone's ID is assigned once and does not change when milestones are inserted, split or reordered. Milestone status is computed from progress: `meets` → met, `advances` → in progress. A whole-breakthrough row changes no milestone's status; it counts as movement, and its `advances` rows are counted as the breakthrough's `overall` steps.
- A breakthrough has one home field. Anything cross-field is a link. Fields are navigation labels.
- Every progress row and link names who made it: a person, or a model and its saved call record.

## Layout

```
atlas/core/
  QUA/
    field.json        the Field
    QUA-01.json       one Breakthrough, with its Milestones and its outgoing "needs" Links
  sources.jsonl       one line per Source
  progress.jsonl      one line per Progress judgement, in the order added
```

- Milestones and `needs` links sit inside their breakthrough's file, so each breakthrough has one page with one history.
- There is one kind of link, `needs`. The links remain in the records but are not published: the site data has no `prerequisites`, `needs`, `unlocks` or claims file. A breakthrough's `related_concepts` section is kept as text; no `related` links are derived or stored. (The first design derived them at rebuild; that was dropped with the old catalog's `connections`.)
- Sources and progress are line-per-record files because one paper can bear on several breakthroughs. `sources.jsonl` is kept sorted by URL and rewritten whole on each import. `progress.jsonl` is rewritten by `atlas.add`: adding a URL again replaces that URL's earlier rows, so git history, not the file, is the record of past judgements.
- Saved PDFs and pages stay out of git. `sources.jsonl` records their SHA-256.
- No absolute local paths are written into `atlas/core/`.

## History and undo

- One edit is one commit. The message gives the reason; git gives author and time. An agent's commit names its model and prompt.
- Undo is `git revert`. A page's history is `git log` on its file.

## Slotting in existing data

This section records the first import on November 9 (31 fields, 334 breakthroughs). Later fields arrive through the ingestion pipeline, which imports and commits each one. One script, run once, no model calls:

1. Each complete field gets `field.json`; each breakthrough gets its file, text copied unchanged.
2. Each `completion_criteria` item becomes `m1`, `m2`, … in order. Its label is the criterion's own opening phrase, taken by code.
3. The 5 existing prerequisite links become `needs` links.
4. The distinct source URLs (1,008 on November 9) become lines in `sources.jsonl`.
5. The 4 judged progress rows go into `progress.jsonl`. Unjudged rows are each breakthrough's own citations; they are derived at rebuild and not stored.

Done when: the database rebuilt from `atlas/core/` has the same 334 breakthroughs with identical content as the current one, and the 4 verdicts and 5 links survive deleting and rebuilding the database.

## How it grows

- **A paper:** `atlas add <url>` as now (save a copy, rank milestones, one model call, check each quote against the saved copy), writing a Source line and Progress lines to `atlas/core/` and committing. The model gives each row a milestone number, or 0 for a step toward the breakthrough as a whole; such a row is stored with `milestone: null` and cannot be `meets`.
- **Finding papers:** URLs pasted by the owner, or an optional weekly finder (Grok searching recent papers per field) that feeds `atlas add`.
- **A field:** when ingestion finishes a field it is imported as new files and committed, with the models used recorded on each breakthrough (`models`). Fields arrive one at a time; there is no "all 66 complete" gate. A field imports without a concept the provider refused to review; the concept is listed under `withheld` in `field.json` and the refusal guard is not bypassed.
- **A correction:** edit the breakthrough's file, run the check, commit with the reason.
- **Re-running research** on an imported field never overwrites its files: importing a field that is already in the core raises an error. Producing a diff to accept or reject is planned for after v1 and is not built.

## Check

`python3 -m atlas.core check`, also run on every rebuild: each breakthrough's ID matches its file and field; milestone IDs are unique within a breakthrough; every `needs` link and `merged_into` resolves; `needs` has no loops; every cited URL is in `sources.jsonl`; every progress row points at an existing breakthrough, at one of its milestones or at none (`milestone: null`), and at a known source, and has a valid verdict (`meets` only with a milestone); no value is an absolute local path.

## Code changes

As planned on November 9; all done. The server and site have since been rebuilt (see the [site design](2026-11-11-site-design.md)).

- New: the one-time import script and the check script.
- `atlas/store.py` rebuilds from `atlas/core/` instead of the ingestion output.
- `atlas/add.py` and `atlas/prerequisites.py` write to `atlas/core/`.
- Server, API and tree UI are unchanged.

# Data reference

November 11, 2026. Every term and data field of the Technology Atlas: what it holds, which code writes it and which code or page reads it. Checked against the code and the files in `atlas/core/` on branch `v1`. Where an older document disagrees with the code, this page follows the code and says so.

## 1. Orientation

The atlas is a map of breakthroughs people should work towards ([project plan](plans/technology-graph-plan.md)). Each breakthrough has milestones that show how close it is. Each milestone is a test: "this breakthrough counts as achieved when these milestones are met." Research papers are added as steps toward one milestone, or toward the breakthrough as a whole.

The atlas makes no order claims. The links were removed on November 11, 2026. They are in git history.

There are no dates in v1.

Data flows one way:

```
research pipeline (ingestion/)  →  atlas/core/ files in git (source of truth)
  →  SQLite view atlas/data/atlas.sqlite3 (rebuilt, never edited)
  →  site data files under /data/ (built on request or exported)
  →  website (atlas/web) and static export
```

Counts on November 11: 66 fields, 742 breakthroughs, 2,800 milestones, 1,676 sources, 4 judged progress rows, 2 withheld concepts.

## 2. Glossary

**Field.** A discipline and the folder that holds its breakthroughs. Its ID is a prefix of 2 to 8 capitals: `QUA` (Quantum Computing), `CHEMREV` (Chemistry). Fields are navigation labels.

**Region.** One of eight groups of neighbouring fields, such as "Computing and Information". Regions are a constant (`REGIONS` in `atlas/store.py`), not core data. A field missing from the constant falls into "Engineering and Energy".

**Breakthrough.** One proposed future capability, with a permanent ID `<FIELD>-<NN>`, such as `QUA-01` ("Distance-scalable universal fault-tolerant quantum computation"). One file per breakthrough. The ID pattern in code is `^[A-Z]{2,8}-\d{2}$`.

**Concept.** The pipeline's word for a breakthrough before it reaches the atlas. In `ingestion/` the same thing is also called a *problem* (`candidates.problems[]`), a *candidate* and an *innovation* (`final-innovations.json` → `innovations[]`). Once imported it is a breakthrough. Do not confuse it with the `concept` section, which is the breakthrough's opening description.

**Milestone.** One of a breakthrough's completion criteria: one condition a qualifying result must show. Stored as an item of `completion_criteria` with `id` (`m1`, `m2`, …), a short `label` and the full criterion `text`. Its full name is `QUA-01.m1`; in the files the breakthrough ID and the milestone ID are stored separately. A milestone's status is computed, never stored: `met` if any progress row for it says `meets`, `in_progress` if any says `advances`, otherwise `none`. Synonyms in code: *criterion* (the 1-based position, used by the database, the model call in `atlas.add` and the site's evidence rows; 0 in the model call means the breakthrough as a whole), *completion criterion*.

**Label.** A milestone's short pass condition, such as "Universal encoded gates whose error per operation falls with code distance". At import, code takes the criterion's text before its first colon (or its first eight words if that is over 80 characters), which often yields a phrase like "Proposed demonstration" (`NEP-01.m1`). `python3 -m atlas.labels` replaces these with model-written labels; that rewrite is in progress across all fields.

**Claim.** Inside the pipeline, one cited statement in the research record (`candidates.problems[].claims[]`), which the review then checks. The atlas once also used the word for its predictions, including *order* claims (`needs` links); those links were removed on November 11, 2026 and are in git history.

**Source.** A paper or page, identified by its URL. One line in `atlas/core/sources.jsonl`. Example: `https://arxiv.org/abs/2610.24077`.

**Copy.** A saved file of a source (PDF, HTML, XML or text), identified by its SHA-256. Recorded in the source's `copies`; the file itself is outside git, under a `sources/` folder in `ingestion/runs/` or `atlas/data/added/`, named `<sha256>.<ext>`. The pipeline and the database call copies *artifacts*; the database table is `assets`; a progress row calls its copy `copy` (core) or `asset` (database).

**Progress row.** One source judged against one milestone, or against the breakthrough as a whole, with an exact quote from the saved copy. Its verdict is one of:

- `meets`: the source reports a result that satisfies the milestone as written.
- `advances`: a concrete result that moves measurably towards the milestone without satisfying it.
- `contradicts`: a result showing the milestone's approach fails or is further away than assumed.

A row with `milestone` null is a **whole-breakthrough step**: a partial step toward the breakthrough that bears on no single milestone. It may only `advance` or `contradict`; `meets` needs a milestone. It changes no milestone's status. It does count as movement (`moved_at`, recent changes), and the catalog counts its `advances` rows as `overall`.

Judged rows live in `atlas/core/progress.jsonl`. The database adds unjudged *research citation* rows (no milestone, no verdict) for every source cited in a breakthrough's `current_state`.

**Withheld concept.** A concept the reviewing or rewriting model's provider refused for safety reasons. It is left out of the atlas, not narrowed or sent to another model, and recorded in its field's `withheld` list. There are two: `CLM-02` and `VIR-01`. Their IDs are not reused.

**Constellation, star.** The site's words for a field and a breakthrough on the star chart. *Figure lines* join a constellation's stars and mean only "same field". Star positions are computed in the browser (`atlas/web/src/sky.js`) and are not data.

**Model names.** As recorded in the files: `grok-4.7-build` (Grok; the config asks for `grok-4.7` and the provider reports `grok-4.7-build`), `gpt-6.1-terra` (Codex Terra), `gpt-6.1-sol` (Codex Sol), `opus` (Claude Opus). By `models.research`, Grok researched 39 fields and Terra 27. `atlas.add` judgements use the config's `format` model (`gpt-6.1-terra`); labels use `gpt-6.1-sol`. Fable writes design and review, not data.

## 3. Records in `atlas/core/`

Layout:

```
atlas/core/
  QUA/field.json      one field
  QUA/QUA-01.json     one breakthrough, with its milestones
  sources.jsonl       one line per source, sorted by URL
  progress.jsonl      one line per judged progress row
```

All files are UTF-8 JSON. Breakthrough and field files are written with one-space indentation by `atlas.core._json`. "Required" means present in every record today and assumed by code; optional keys give the count of records that have them.

Common writers and readers, used in the tables below:

- `import_field` = `atlas.core.import_field`, run by `ingestion.batch` (`import_to_atlas`) or `python3 -m atlas.core import`.
- `final_rewrite` = `ingestion.final_rewrite.run`, which writes `final-innovations.json` in the field's run folder.
- `load`/`check` = `atlas.core.load` and `atlas.core.check`.
- `rebuild` = `atlas.store.rebuild`, which builds the database.
- `site_view` = `atlas.store.site_view` and the data-file builders after it (section 5).

### 3.1 `field.json` (66 files)

| Field | Type | Required? | What it contains | Written by | Read by |
|---|---|---|---|---|---|
| `id` | string | yes | Field ID, equal to the folder name. `"QUA"` | `import_field` (from the run's `prefix`) | `check`; `rebuild` → `fields.id` |
| `name` | string | yes | Display name. `"Quantum Computing"` | `import_field` (from the run's `field`) | `rebuild` → `fields.name`; catalog, field file |
| `color` | string | yes | CSS colour fixed at import, such as `"hsl(145 60% 74%)"`; four early fields have hex colours. Never recoloured. | `import_field` via `atlas.core.next_color` | `rebuild` → `fields.color`; `next_color`. Not in the site data (colour on the site means progress only). |
| `as_of` | string | yes | Date the field's batch was prepared. `"2026-11-01"` for all 66. | `import_field` (copied from the run's `field.json`) | Nothing. The site's `as_of` is the constant `AS_OF` in `store.py`. |
| `boundaries` | string | yes | The field's scope as given to the research prompt. In 65 of 66 fields this is the prompt's fixed instruction, "<Name>: fundamental discoveries and enabling technologies within this field. Include cross-field consequences…"; only `CHEMREV` has a real scope. | `import_field` (from the run's `field.json`) | `rebuild` → `fields.boundaries`; field file `boundaries`, which is empty when the text is that instruction (`store.scope`) → Field page "scope" |
| `created_at` | string | yes | ISO time the final record was merged. | `import_field` (from `final-innovations.json`) | `rebuild`: `added_at` of research citation rows |
| `imported_from` | object | yes | `run_hash`: SHA-256 of the `final-innovations.json` bytes imported; `imported_at`: ISO time of import. | `import_field` | Nothing in code; an audit trail. |
| `original_dispositions` | list | yes (660 items) | What happened to each entry of the field's original (pre-pipeline) list: `original_number` (int), `original_title`, `status` (`covered` 256, `added` 159, `not_added` 245), `concept_ids` (list of breakthrough IDs), `reason`. | Format stage (`FORMAT_SCHEMA` in `ingestion/field_workflow.py`) → `final_rewrite` → `import_field` | Nothing in `atlas/`; `ingestion.batch` validates it. |
| `reconciliation_change_log` | list | yes (487 items) | Changes made when the first-pass research was reconciled with the original list: `concept_ids`, `change`, `reason`. | Format stage `change_log` → `import_field` | Nothing in `atlas/`. |
| `withheld` | list | optional (35 of 66) | Withheld concepts: `id`, `title`, `stage` (`"review-CLM-02"`; a rewrite refusal would read `"final-rewrite-<ID>"`), `reason` (the provider's refusal text). Non-empty only in `CLM` and `VIR`. The 31 fields imported first have no key, which means none. | `final_rewrite` → `import_field` | `ingestion.batch.import_message`. Copied to the `fields.withheld` column and served in the field file and the catalog (section 5). |

### 3.2 Breakthrough file `<FIELD>/<ID>.json` (742 files)

Six *sections* hold the research text. Each section is a list of paragraphs, and every paragraph has the same shape:

| Paragraph key | Type | What it contains |
|---|---|---|
| `text` | string | One paragraph of prose. |
| `source_urls` | list of strings | URLs this paragraph cites. Each must appear in the breakthrough's `sources`. Often empty. |

Milestones (items of `completion_criteria`) are paragraphs with two more keys, `id` and `label`.

| Field | Type | Required? | What it contains | Written by | Read by |
|---|---|---|---|---|---|
| `id` | string | yes | Breakthrough ID, equal to the file name. Permanent. | Research stage (`PREFIX-NN` headings) → `final_rewrite` | `check`; everything |
| `title` | string | yes | One-line name. | `final_rewrite` (rewrite model) | Catalog, field file, search, b file; page titles; prompts in `atlas.labels`, `atlas.add` |
| `field` | string | yes | Home field ID; must match the folder. | `import_field` | `check`; `rebuild` → `breakthroughs.field` |
| `status` | string | yes | `"active"` (all 742) or `"retired"`. Retired records are skipped by `rebuild` and by `atlas.labels`. | `import_field` | `rebuild`; `atlas.labels`; b file `status` |
| `merged_into` | string | optional (0) | For a retired record, the ID it was merged into. | Manual edit (none yet) | `check` (must resolve) |
| `concept` | paragraphs | yes (1,729) | What the breakthrough is. The first paragraph is the summary used everywhere. | `final_rewrite` | b file; field file `summary`; search `summary`; Breakthrough page; prompts |
| `significance` | paragraphs | yes (2,324) | Why it would matter. | `final_rewrite` | b file → `Record.jsx` |
| `missing_breakthrough` | paragraphs | yes (2,551) | What is still missing today. | `final_rewrite` | b file → `Record.jsx` |
| `current_state` | paragraphs | yes (3,583) | The state of the art, with citations. | `final_rewrite` | b file → `Record.jsx`; `rebuild` derives research citation rows from its `source_urls` |
| `completion_criteria` | list | yes (2,800; 2 to 6 per breakthrough) | The milestones, in order. Each item: `text`, `source_urls`, `id` (`m1`… assigned once at import, never renumbered), `label`. | `final_rewrite` (text, source_urls); `import_field` (`id`, first `label`); `atlas.labels.relabel` (`label` only, byte-preserving edit) | `check` (IDs unique); `site_view` (statuses, labels); b file; prompts in `atlas.add`, `atlas.labels` |
| `related_concepts` | paragraphs | yes (3,493) | Prose naming related concepts, often by ID. No link is derived from it. | `final_rewrite` | b file → `Record.jsx` |
| `unresolved_issues` | list of strings | yes (4,740 strings) | Evidence gaps the review left open. | `final_rewrite` | b file → `Record.jsx`; field file `issue_count` |
| `change_log` | list | yes (6,644 items) | Changes the review made: `change`, `reason`. | `final_rewrite` | b file → `Record.jsx` |
| `sources` | list of strings | yes (1,820 URLs) | Every URL the record cites; each is a line in `sources.jsonl`. Median 2 per breakthrough. | `import_field` (reduces the pipeline's source objects to URLs) | `check`; `rebuild` expands each URL back to `{url, title, status, artifacts}` |
| `provenance` | object | yes | Repository-relative paths of the pipeline files behind the record: `research` (`reconciled-research.md`), `structured_record` (`reconciled-structured.json`), `review` (the concept's `validated.json`). All under git-ignored `ingestion/runs/`. | `final_rewrite.make_input` → `import_field` (made relative) | `rebuild` → `documents` table (local downloads only). Not in the site data. |
| `models` | object | yes | Model that ran each pipeline stage: `research`, `reconcile`, `format`, `review` (missing in 2 records, `CLM-05` and `CLM-13`, for which the pipeline recorded no review model), `rewrite`. Example (`QUA-01`): research and reconcile `grok-4.7-build`, format `gpt-6.1-terra`, review and rewrite `gpt-6.1-sol`. | `final_rewrite` (`attempt_model` per stage) | b file `models` (not displayed by the site today) |

The pipeline's intermediate structures (research claims with citations, review verdicts per claim with evidence passages) do not enter the atlas. Their shapes are `CANDIDATES` and `REVIEW` in `ingestion/schemas.py`, `FORMAT_SCHEMA` and `REVIEW_SCHEMA` in `ingestion/field_workflow.py`, and `FINAL_SCHEMA` in `ingestion/final_rewrite.py`, which is the shape of each breakthrough before import adds `field`, `status`, milestone `id` and `label`, and reduces `sources` to URLs.

### 3.3 `sources.jsonl` line (1,676 lines)

One JSON object per line, sorted by URL, no duplicate URLs.

| Field | Type | Required? | What it contains | Written by | Read by |
|---|---|---|---|---|---|
| `url` | string | yes | The cited URL, as the research wrote it. The key. | `import_field` (`_merge_source`); `atlas.add` | `check`; `rebuild`; b file `sources[].url` |
| `title` | string | yes | Title from the research; empty in 158 lines. `atlas.add` uses the URL as title for a new source. | same | b file `sources[].title` (the site shows the host name when empty) |
| `status` | string | yes | `saved` (1,274: at least one non-empty copy) or `not_captured` (402). | Capture stage (`ingestion/field_workflow.py`); `atlas.add` writes `saved` | b file `sources[].status` |
| `copies` | list | yes (2,284 items; empty when not captured) | Saved copies, merged by hash. Keys below. Local paths (`path`, `absolute_path`) are dropped at import. | Capture stage → `import_field`; `atlas.add` appends `{sha256, format, kind}` | `rebuild` → `assets`; research citation rows' `asset`. Not in the site data. |

Each copy:

| Key | Type | Required? | What it contains |
|---|---|---|---|
| `sha256` | string | yes | Hash of the saved bytes; also the saved file's name. |
| `format` | string | yes | `pdf` (1,143), `html` (1,093), `xml` (48). |
| `kind` | string | yes | How it was obtained: `source` (the URL itself, 1,255), `paper_pdf` (a PDF linked from it, 974), `alternative` (an alternate copy such as Europe PMC, 54), `manual` (attached by hand, 1). |
| `resolved_url` | string | yes in existing lines | URL actually fetched. `atlas.add` does not write it. |
| `retrieved_at` | string | yes in existing lines | ISO time of download. `atlas.add` does not write it. |
| `verified` | bool | optional (2,283) | The hash was checked when the source index was built. |
| `extracted_characters` | int | optional (2,238) | Characters of text extracted. |
| `truncated` | bool | optional (2,238) | Extracted text exceeded the 120,000-character limit. |
| `extraction_issues` | list of strings | optional (2,283) | Problems found extracting text. |
| `byte_count`, `empty` | int, bool | optional (1) | Set when the saved file is empty (0 bytes). |
| `version_note` | string | optional (2) | Hand-written note on how an alternate copy's version differs from the cited paper. No code writes it. |

### 3.4 `progress.jsonl` line (4 lines)

One judged progress row per line. `atlas.add` rewrites the whole file: re-adding a URL first removes every earlier row for that URL. Example of a whole-breakthrough step: `{"breakthrough": "QUA-01", "milestone": null, …, "verdict": "advances", …}`.

| Field | Type | Required? | What it contains | Written by | Read by |
|---|---|---|---|---|---|
| `breakthrough` | string | yes | Breakthrough ID. `"QUA-01"` | `atlas.add.add` | `check`; `rebuild` |
| `milestone` | string or null | yes (the key is required) | Milestone ID within it, `"m1"`; or null for a step toward the breakthrough as a whole. | `atlas.add.add` (maps the model's criterion number to the stable ID; criterion 0 → null) | `check`; `rebuild` (converted back to a 1-based `criterion`; null stays null) |
| `url` | string | yes | Source URL; must be in `sources.jsonl`. | `atlas.add.add` | `check`; `rebuild` |
| `copy` | string | yes | SHA-256 of the saved copy the quote was checked against. | `atlas.add.add` | `rebuild` → `progress.asset` and the row ID. Not in the site data. |
| `source_date` | string or null | yes | Publication date the model read from the text: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`. | Model answer in `atlas.add` | Catalog `recent`; b file `progress` |
| `verdict` | string | yes | `advances`, `meets` or `contradicts`. Only `advances` or `contradicts` when `milestone` is null. | Model answer | `check`; milestone status everywhere; catalog `overall` |
| `quote` | string | yes | Exact passage (20 to 600 characters), verified against the saved copy's text by `ingestion.pipeline.passage_matches`. | Model answer | Catalog `recent`; b file `progress` |
| `by` | string | yes | Who judged: the model name (`gpt-6.1-terra`) or a person. Called `model` in the database and site. | `atlas.add` (config `format` model) | `rebuild` → `progress.model` |
| `added_at` | string | yes | ISO time the row was written. | `atlas.add` | `moved_at`, `recent` order |

## 4. The SQLite view

`atlas/data/atlas.sqlite3`, git-ignored. It is rebuilt from `atlas/core/` by `python3 -m atlas.store` (`store.rebuild`) and is never edited by hand. The rebuild runs `atlas.core check` first and stops on any problem; it builds a new file beside the old one and swaps it in only on success. Anything worth keeping goes in `atlas/core/`. Schema: `store.initialize`.

| Table | Columns | Derived from |
|---|---|---|
| `fields` | `id`, `name`, `color`, `boundaries`, `withheld` | Each `field.json`. `withheld` is the field's `withheld` list as JSON, `[]` when the key is absent. |
| `breakthroughs` | `id`, `field`, `payload` | Each active breakthrough file (retired ones left out). `payload` is the record as JSON with each `sources` URL expanded to `{url, title, status, artifacts}`, where `artifacts` is the source's `copies`. |
| `assets` | `id`, `path`, `hash` | Each copy whose file was found on this computer (`store.resolver`) and whose bytes match. `id` and `hash` are the SHA-256; `path` is absolute and local. A missing copy is skipped and counted; a changed one stops the rebuild. |
| `documents` | `id`, `path`, `hash` | Each breakthrough's `provenance` file that exists inside the repository. `id` is `<ID>:<kind>`, such as `QUA-01:review`. |
| `progress` | `id`, `breakthrough`, `criterion`, `url`, `asset`, `source_date`, `verdict`, `quote`, `model`, `added_at` | Two kinds of row. **Judged rows**, one per `progress.jsonl` line: `id` is `added:<copy>:<breakthrough>:<criterion>`, `criterion` is the 1-based milestone position, `model` is `by`. A whole-breakthrough row has `criterion` null and `0` in its ID; its verdict is set, which tells it apart from a research citation row. **Research citation rows**, one per URL cited by each `current_state` paragraph: `id` is `research:<breakthrough>:<paragraph index>:<url>`, `criterion`, `verdict` and `source_date` are null, `quote` is the whole paragraph's text (not a quote from the source), `model` is the config's current review model, `added_at` is the field's `created_at`. |

On November 11: 66 fields, 742 breakthroughs, 2,238 assets, 2,226 documents, 3,554 progress rows of which 4 are judged.

No column was added for whole-breakthrough rows. The database also serves `atlas.add` (milestone ranking, reuse of saved copies). The server's `/api/assets/<sha256>` and `/api/documents/<id>` give verified local downloads from `assets` and `documents`; the site and the export do not use them.

## 5. The site data contract

The site reads only four kinds of file. `atlas.server` builds them on request under `/data/`; `atlas.export` writes the same bytes to `OUT/data/`. All are built in `atlas/store.py` from one `site_view`, and encoded as compact UTF-8 JSON (`store.encode`). The React side loads them in `atlas/web/src/data.jsx`.

Milestone status in every file comes from judged milestone rows only (`meets` → `met`, `advances` → `in_progress`, else `none`). `moved_at` is the latest `added_at` of a breakthrough's judged rows, whole-breakthrough rows included, or null. No file carries `needs` links: there is no `prerequisites`, `needs`, `unlocks` or depth key, and no `claims.json`.

### `data/catalog.json` (`store.catalog`)

Loaded once on every page (`loadAtlas`). Budget: under 300,000 bytes, enforced by `atlas/tests/test_site.py`; 146 KB on November 11.

| Key | Contents | Used by |
|---|---|---|
| `as_of` | The constant `AS_OF` (`"2026-11-01"`). | Header and Method page (`asOf`) |
| `regions` | The eight region names in sky order. | `sky.js`, Home, Method |
| `fields[]` | Sorted by name. `id`, `name`, `region`, `breakthroughs` (count), `milestones` (`{none, in_progress, met}` counts). | Every page via `loadAtlas`; `sky.js` layout |
| `breakthroughs[]` | Sorted by ID. `id`, `field`, `title`, `milestones` (a list of status strings, one per milestone, not objects), `overall` (integer: the number of `advances` rows with no milestone; 0 when none), `moved_at`. | `loadAtlas`; chart, lists, search |
| `recent[]` | Up to 12 latest judged rows, whole-breakthrough rows included: `breakthrough`, `criterion` (null for the whole), `verdict`, `url`, `source_date`, `quote`, `added_at`, plus `milestone` (the stable ID, or null) and the milestone's `label` (null for the whole). | Home "what moved"; chart |
| `withheld[]` | Sorted by field. `{id, title, field}` for each withheld concept (two on November 11). | Method page; Breakthrough page when a withheld ID is opened |

### `data/field/<ID>.json` (`store.field_data`)

Loaded when a field is opened (`useField`).

| Key | Contents | Used by |
|---|---|---|
| `id`, `name`, `region`, `as_of` | As in the catalog. | Field page |
| `boundaries` | The field's scope text, or `""` when the stored text is the research prompt's fixed instruction (65 of 66 fields). | Field page "scope" |
| `withheld[]` | `{id, title, stage, reason}` for each withheld concept of this field; `[]` for most fields. `reason` is the provider's refusal text. | Field page note (CLM, VIR) |
| `breakthroughs[]` | Sorted by ID. `id`; `title`; `summary` (first `concept` paragraph, whole); `milestones` (objects `{id, label, status}`); `source_count`; `progress_count` (all progress rows, research citation rows included); `issue_count` (`unresolved_issues` length); `moved_at`. | Field page rows (`summary`); Atlas page star card (`summary`, milestone `label`). The counts are not displayed today. |

### `data/b/<ID>.json` (`store.breakthrough_data`)

Loaded by the Breakthrough page (`loadBreakthrough`).

| Key | Contents | Used by |
|---|---|---|
| `id`, `field`, `field_name`, `region`, `title`, `status` | Identity. | Breakthrough page; `field_name` and `status` are not displayed today |
| `models` | The record's `models`. | Not displayed today |
| `concept`, `significance`, `missing_breakthrough`, `current_state`, `completion_criteria`, `related_concepts`, `unresolved_issues`, `change_log` | The record's sections, unchanged (paragraphs keep `source_urls`; criteria keep `id`, `label`, `text`). | Breakthrough page (concept, full criterion text and citations); `Record.jsx` (collapsed full record) |
| `milestones` | Objects `{id, label, status}`. | Milestone checklist |
| `moved_at` | As above. | Breakthrough page |
| `sources[]` | `{url, title, status}` only: links to the originals. | Citation titles; `Record.jsx` source list |
| `progress[]` | Every database row for this breakthrough, in this order: milestone rows by milestone, then whole-breakthrough rows, then research citations. Each row: `criterion` (1-based, or null), `milestone` (the stable ID such as `"m1"`, or null), `url`, `source_date`, `verdict`, `quote`, `model`, `added_at`. A row with a `verdict` and `milestone` null is a step toward the breakthrough as a whole. A row with `verdict` null is a research citation whose `quote` is a `current_state` paragraph. | Evidence (judged rows); `Record.jsx` research citations |

### `data/search.json` (`store.search_index`)

Loaded on first use of the search box (`Layout.jsx`). 206 KB on November 11; no budget. Each entry: `id`, `field`, `title`, `summary` (first `concept` paragraph cut at a word boundary to about 160 characters by `store.cut`). Ranking is in `data.jsx` `search`: ID, then title whole-word and prefix matches, then field name, then summary.

### Deliberately left out

- **Saved copies and their hashes** (`copies`, `copy`, `asset`). The copies are private research files, possibly under copyright; the public site links to the originals only (plan, Track B step 4).
- **Provenance and local paths** (`provenance`, `assets.path`, `documents.path`). They point into git-ignored folders on one computer and are not public.
- **Import and pipeline history** (`imported_from`, `original_dispositions`, `reconciliation_change_log`) and field `color`. Not needed by any page, and the catalog must stay small.

## 6. Invariants and rules

**What `python3 -m atlas.core check` enforces** (`atlas.core.check`, plus `atlas.core.load`). It exits 1 and prints each problem.

- Each `field.json` `id` equals its folder name.
- Each breakthrough's `id` equals its file name; its `field` exists, the ID starts with `<field>-`, and the file sits in that field's folder. No breakthrough ID appears in two folders.
- Every breakthrough has milestone IDs, unique within it.
- Every `merged_into` names an existing breakthrough.
- Every URL in a breakthrough's `sources` is a line in `sources.jsonl`; no URL appears twice there.
- Every progress row names an existing breakthrough, has a `milestone` key holding one of its milestone IDs or null, names a URL in `sources.jsonl`, and has a verdict of `advances`, `meets` or `contradicts`. A row with `milestone` null may not be `meets`.
- No string anywhere in the core starts with `/Users/` or `/private/` (no absolute paths).

The rebuild adds one more: a saved copy whose bytes no longer match its hash stops the rebuild.

**Rules not enforced by code.**

- **IDs are permanent.** A breakthrough or milestone ID is never reused or renumbered. A record is retired (`status: "retired"`, optionally `merged_into`), never deleted. Milestone IDs do not change when milestones are inserted, split or reordered.
- **No absolute paths** in `atlas/core/` (checked as above for the two common prefixes).
- **Cost rule.** No new table, record kind or kind of model pass without the owner's explicit decision. Decided so far: one call per paper added, one label call per breakthrough.
- **No editorial changes before v1 is published.** Content ships as the pipeline produced it. Renames, merges, splits, curation and milestone restructuring come after v1, as tracked edits. The label pass is one of the decided passes (plan, Track A step 5); it changes only `label`, never the criterion text.
- **No predicted dates in v1.** `source_date` is the publication date of evidence, not a prediction.
- **Re-running research** on an imported field never overwrites its files ([core design](plans/2026-11-09-atlas-core-design.md)). The importer refuses a field that already exists.

## 7. How to change data

Run everything from the repository root. Commands that call a model are marked; read the module before running one.

**Check and rebuild.**

```bash
python3 -m atlas.core check      # exit 0 when clean
python3 -m atlas.store           # rebuild atlas/data/atlas.sqlite3 from atlas/core/
python3 -m atlas.server --port 8765
```

**Add a field** (model calls). The batch runs the pipeline, then imports each finished field into `atlas/core/`, checks, rebuilds and commits; a failed check rolls the import back. See [ingestion/README.md](../ingestion/README.md).

```bash
python3 -m ingestion.batch run --fields MLC
python3 -m atlas.core import      # no model calls: import every batch-complete field not yet in core; does not rebuild or commit
```

**Add a paper** (one model call). Saves a copy, ranks milestones, judges, writes `sources.jsonl` and `progress.jsonl`, rebuilds, commits `atlas/core/`. The model answers with a milestone number per row, or 0 for a step toward the breakthrough as a whole (never with `meets`); it is told to prefer a specific milestone. Every quote is checked against the saved copy. The command prints "whole breakthrough" for criterion-0 rows.

```bash
python3 -m atlas.add <url> [--breakthrough QUA-01] [--no-commit]
```

**Re-run labels** (one call per breakthrough, `gpt-6.1-sol`). Arguments are breakthrough IDs or field IDs. `--missing` skips breakthroughs that already have a successful label call; given alone, it covers every active breakthrough. Changes only `label` strings, rebuilds once, commits successful ones. Calls are saved in `atlas/data/labels/<ID>-<UTC time>/`.

```bash
python3 -m atlas.labels QUA-01 CSC [--workers 3] [--no-commit]
python3 -m atlas.labels --missing
```

**Correct a record by hand.** Edit the file, run the check, rebuild, commit with the reason. Before v1 only non-editorial fixes are allowed.

**Export the site.** OUT must be empty or an earlier export. `--db` picks another database. Share images are made first from the running site, then copied in.

```bash
python3 -m atlas.store && (cd atlas/web && npm run build)
python3 -m atlas.server --port 8765 &        # the share step photographs the running site
python3 -m atlas.share atlas/data/share-out [--only QUA QUA-01 default] [--force]
python3 -m atlas.export OUT --share atlas/data/share-out [--base-url https://example.org] [--db PATH]
```

`atlas.share` needs Playwright with Chromium (installed for `/opt/homebrew/Caskroom/miniforge/base/bin/python`) and uses Pillow when present. It writes `share/<ID>.png` per breakthrough, `share/field-<ID>.png` per field and `share/default.png`, and skips any image newer than both the database and the built site unless `--force`; all 809 take a few minutes. The export prints how many pages have no share image.

## 8. Where the documents and the code differ

The differences found when this page was written (on `related` links, retired IDs, `progress.jsonl`, source identity, field contents, the label model and the research split) were corrected in the other documents on November 11. If you find a new one, trust the code, fix the document, and note it here until it is fixed.

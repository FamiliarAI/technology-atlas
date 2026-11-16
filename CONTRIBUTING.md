# Contributing to the Technology Atlas

The Technology Atlas is a map of the breakthroughs worth working towards, and of the milestones that show how close each one is. It is a map, not a forecast: it makes no claims about order or dates. Every breakthrough, milestone and judgement on the site is the atlas's own proposal, written with models and published by the owner.

Corrections are the most useful contribution: a milestone set by the wrong body, a quote that does not say what it is cited for, a result the atlas missed, a breakthrough that is missing or is really two.

**You never need an API key or a model account to contribute.** Proposals are plain edits to files in `atlas/core/` or an issue. Every pass that calls a model (writing a page, judging a source, finding papers) runs on the owner's side, after review.

## Without any setup: open an issue

- **Challenge an entry.** Give the breakthrough ID (such as `QUA-01`, shown on its page and in its URL), the milestone if there is one, what is wrong, and a source.
- **Suggest a source.** Give the breakthrough ID, the milestone it bears on (or "the breakthrough as a whole"), the URL of the original (publisher, preprint server, registry or official body; not a news story about it), and the sentence in it that matters.
- **Propose a breakthrough.** Give the field, a title, a sentence or two on what it is, why it belongs on the map, and at least one source.

## Propose a breakthrough in a pull request

You need Git and Python 3.10 or later; the `atlas` package uses only the standard library.

```bash
git clone https://github.com/FamiliarAI/technology-atlas.git && cd technology-atlas
git switch -c propose-mat-riemann
python3 -m atlas.core new MAT "Resolution of the Riemann Hypothesis" \
  --note "A proof or disproof that every nontrivial zero of ζ has real part 1/2." \
  --source https://www.claymath.org/millennium-problems/ \
  --reason "Millennium Prize Problem" --no-commit
python3 -m atlas.core check
git add atlas/core && git commit -m "Propose MAT-NN: Resolution of the Riemann Hypothesis"
```

`atlas.core new` takes an existing field ID (the folders in `atlas/core/`), gives the next free ID in that field and writes a record holding the title, your note as its concept and the sources; the other sections stay empty. It refuses an unknown field and a title the field already has. A new field goes through the research pipeline and is the owner's to start; open an issue for it. `--no-commit` lets you write your own commit message; without it the command commits `atlas/core/` itself.

The owner then writes the breakthrough's page (definition, completion test, milestones set by outside bodies) and judges its sources. That takes model calls, so it happens on the owner's side.

## What happens to a suggested source

Suggest a source in an issue (above), naming the breakthrough, the milestone and the URL. There is no file to edit. The owner runs:

```bash
python3 -m atlas.page add QUA-01 https://example.org/paper     # owner only: saves a copy, one judge call per source
```

which saves a private copy, judges the source against every milestone of the page, checks each quote against the saved copy and records the result. Saved copies are never published; the site links to the original.

Please do not hand-edit `page`, `results` or `progress.jsonl` entries to record a judgement: a result must come from the judge with a quote found in the saved copy.

## How review and publishing work

A breakthrough reaches the public site only when the owner publishes it:

```bash
python3 -m atlas.review list --state published
python3 -m atlas.review publish QUA-01
python3 -m atlas.review hold BME-04 --note "needs the FDA guidance quote"
python3 -m atlas.review merge CLM-11 --into BME-01 --note "same breakthrough"
```

The decision is stored on the record as `review` (`published`, `hold`, `merge`, `revise` or `retire`). Only `published` changes the site: the public export (`python3 -m atlas.export OUT --public`) contains published breakthroughs and their fields, nothing else. Review notes never reach the site. A merged or proposed breakthrough you contributed may therefore stay off the site for a while; the issue thread says why.

## Code changes

- Read `AGENTS.md` for code style: one statement per line, lines up to 100 characters, single quotes; run `ruff format atlas ingestion` before committing. Prompts, SQL and schemas are data: wrapping a long string must not change its value.
- Tests, also listed in `AGENTS.md`:

  ```bash
  python3 -m unittest discover -s atlas/tests
  python3 -m pip install -r ingestion/requirements.txt
  python3 -m unittest discover -s ingestion/tests
  python3 -m atlas.core check
  (cd atlas/web && npm ci && npm run build)
  ```

  They use temporary data and stubbed calls: no model, publisher or network access.
- The site reads only the data contract in `atlas/store.py`; see `docs/data-reference.md` before adding a key, and `docs/plans/2026-11-11-site-design.md` before changing a page.
- To see the site locally: `python3 -m atlas.store && python3 -m atlas.server --port 8765`, after building `atlas/web` once. See `atlas/README.md`.

## Ground rules

- Never commit `.env`, keys, tokens, `atlas/data/` or `ingestion/runs/` (all ignored). Never commit a saved copy of a publisher's page or PDF.
- One proposal per pull request. Say what changed and why, with a source.
- By contributing you agree your contribution is licensed under the repository's terms: code under the MIT License (LICENSE), data in `atlas/core/` under CC BY 4.0 (LICENSE-DATA).

# Technology Atlas plan

Updated November 11, 2026. This is the plan of record. Earlier versions are in git history. Hosting and account creation need the owner's authorization when reached.

## Purpose

Map the breakthroughs that people should work towards, empowered by superintelligence, and the milestones along the way that tell us how close each one is.

- **Breakthrough:** a goal worth working towards.
- **Milestone:** a result we should see on the way to it. Milestones are how we tell how close the goal is.
- **Paper:** a research paper is added as a partial step toward one milestone, or toward the breakthrough as a whole.

The atlas is a map, not a forecast (decided by the owner on November 11). It makes no claim about when a breakthrough will arrive or in what order. There are no dates and no order claims.

## Rules

- **No editorial changes before v1 is published.** Content ships as the research pipeline produced it. Renames, merges, splits, curation and milestone restructuring come after v1, as tracked edits.
- **Cost rule.** Reuse existing data and structures. A new table, record kind or kind of model pass needs an explicit decision. Decided so far: one call per paper added; one label call per breakthrough.
- **Model routing.** Cheapest capable model first: Grok, then Codex GPT-6.1 Sol, then Opus. Fable is for design, architecture and review.
- **Code style.** See `AGENTS.md`.

## Terms

- **Breakthrough:** one proposed future capability, with a permanent ID such as `CSC-02`.
- **Milestone:** one of a breakthrough's completion criteria, with a permanent ID such as `CSC-02.m1`, a short label and the full criterion text.
- **Link:** links were removed on November 11, 2026 and are in git history.
- **Source:** a paper or page, identified by URL, with saved copies identified by SHA-256.
- **Progress:** one source judged against one milestone (`advances`, `meets` or `contradicts`) or against the breakthrough as a whole (`advances` or `contradicts`), with an exact quote.

## Where things stand

- **Core.** `atlas/core/` (files in git) is the source of truth; the SQLite database is rebuilt from it. See the [core design](2026-11-09-atlas-core-design.md).
- **Content.** All 66 fields are in the core (742 breakthroughs), with two withheld concepts (CLM-02 and VIR-01). Grok researched 39 fields; Codex Terra researched 27 after Grok's quota ran out, and its records cite fewer sources (median 1 per breakthrough against 3).
- **Labels.** Every milestone of all 742 breakthroughs has a short label. Grok wrote those for the first 5 fields and Codex Sol the rest, on November 11.
- **Links.** The links were removed on November 11, 2026 and are in git history.
- **Progress.** 4 judged rows.
- **UI.** The v1 site is built in `atlas/web`: home, the sky-map atlas, field, breakthrough and Method pages, with a static export (`python3 -m atlas.export`) and a share image per page. It is not published.
- **Reader's version (pilot).** Eight breakthroughs (QUA-01, QUA-08, SWE-01, SWE-03, NRL-17, ELE-01, CAR-09, MIC-07) have a short reader's version (`brief`) that the page leads with, in six questions; the research record is unchanged beneath it. Written by `python3 -m atlas.brief`, one call per breakthrough. The owner approved the pilot on November 11; running all 742 is not yet decided.
- **Source top-up (pilot).** `python3 -m atlas.find` finds further papers for one breakthrough and adds each through `atlas.add`. Piloted on the four Terra breakthroughs above.
- **Known gap.** 105 of the 193 PubMed sources are marked saved but hold only a cookie notice. `python3 -m atlas.pubmed` re-captures them from PubMed's data service; only the pilot's three are done.
- **Remote.** `github.com/FamiliarAI/technology-atlas`, private.

## Plan to v1

Two tracks run in parallel. They touch different code (`ingestion/` and `atlas/web/`), so they do not block each other.

### Track A: content

1. **Review and clean up the ingestion pipeline.** Read all of `ingestion/` and its documents first and write down what is found. Then remove dead and one-off code, drop the "all 66 complete" gate, let a field finish without a concept the provider refused to review (the refusal guard is never bypassed), and import each finished field into `atlas/core/` automatically.
2. **Make the pipeline use several agents.** Each stage names an ordered list of models instead of one. Grok does research while its quota lasts; when it is exhausted or slow, the stage falls back, in this order, to the latest Codex Terra model with search, then Codex Sol, then Opus, instead of stopping the batch. Every record keeps the name of the model that produced it. The design of the fallback comes out of the review in step 1.
3. **Finish the fields.** Machine Learning first, then the other blocked fields, then the 32 unfinished ones. Fields arrive in the atlas one at a time.
4. Removed: the atlas makes no order claims.
5. **Milestone labels for every field in the core**, using the existing per-breakthrough call.

### Track B: UI

Readable first, good-looking second, on desktop and phone. A full website with the star atlas as its centrepiece; the pages, reading rules, look and mock are in the [site design](2026-11-11-site-design.md).

1. **Design.** A written spec and one static mock of the home and breakthrough screens at desktop and phone sizes, for the owner's approval. Each screen answers one question:

   | Screen | Question | What leads |
   |---|---|---|
   | Home | What is this, and what moved? | Purpose, recent movement, then the map |
   | Map | What is there to work towards? | Breakthroughs grouped by field and region |
   | Field | What is in this area? | A list of its breakthroughs |
   | Breakthrough | How will we know, and how close is it? | Milestone checklist with evidence, papers as steps, sources in context, full record |

   The map is for overview; lists do the reading. Everything is reachable by search, list, keyboard and screen reader. Phone is list-first. Colour means progress state and nothing else.
2. **Visual direction: a science-fiction star atlas** (decided November 11). The bar is a site the owner is proud to publish under his own name.
   - **The idea.** A stellar-cartography instrument. Each breakthrough is a star and each field a constellation on a flat sky map. A star's milestones are a segmented ring around it that fills as they are met; a star ignites as it nears achievement. Today's sky is mostly dark, which is the honest starting picture.
   - **Restraint over cliché.** No neon cyberpunk, no fake terminal text, no decoration that carries no information. The science-fiction feel comes from depth, precision and light: a near-black field with real depth, hairline rings and tick marks, measured glow, and one warm accent reserved for progress.
   - **Type.** A distinctive display face with a technical character, a highly readable text face for long passages, and a mono for IDs and coordinates. Chosen in the mock, bundled locally.
   - **Motion.** The Motion library for React: the sky assembles on load, the view glides to a selected star, and recently moved stars pulse. All of it is off under reduced-motion settings.
   - **Made assets.** Hand-made SVG for the chart, rings, icons and constellation emblems. Generated images (GPT Image 2 through the Codex CLI, confirmed working November 11) only for atmosphere: a deep-field background plate and, after a pilot of ten, an illustration plate per breakthrough.
   - **Who makes what.** Fable writes the art direction and reviews screenshots; it does not draw SVG or generate images. Codex generates images, and Codex Sol or Opus writes the SVG and components.
   - **Quality gate.** Nothing is built past the mock until the owner approves it. Every screen is reviewed from screenshots at desktop and phone sizes before it is called done, and checked for contrast, keyboard use and load time.
3. **Build** in `atlas/web`, React and Vite, reading the existing API. No new tables.
4. **Static export.** The atlas is read-only, so v1 is exported to plain files. Saved source copies stay private; the public site links to originals.

### Publish

When both tracks are done: the owner authorizes hosting, the static site goes up, and editorial changes open.

## After v1

Parked, not forgotten: curating the breakthrough list and merging duplicates across fields; rebuilding milestones as ordered steps; a weekly paper finder; re-importing a field whose pages have been edited; removing saved PDFs from early git history before the repository could be made public.

The deprecated paid-report plan (dated forecasts, PDF product) is history only and is not a goal, input or constraint.

# Site design

November 11, 2026. The spec for Track B of the [project plan](technology-graph-plan.md). This is a website, not a single chart: the star atlas is its centrepiece, and the pages around it explain it, make it readable and make it shareable. The bar is a site the owner is proud to publish under his own name.

## What a visitor should leave with

1. This is an attempt to predict the AI takeoff by naming the wonders in advance.
2. Every wonder has a test for recognising it, and an order it is expected to arrive in.
3. Here is what has moved, with the evidence.

## Pages

| Route | Page | Its one question | Order of content |
|---|---|---|---|
| `/` | Home | What is this, and why trust it? | Hero over the living sky; purpose in two sentences; "Enter the atlas"; what moved recently; how to read a star (three steps); a few constellations to start with; the claims in brief; footer |
| `/atlas` | The atlas | What comes before what? | The full star chart, with search and a field list |
| `/field/QUA` | A constellation | What is in this area? | Field name and scope; its constellation; its breakthroughs as a list in prerequisite order |
| `/b/QUA-01` | A breakthrough | How will we know, and how close is it? | Title and one-paragraph concept; milestone checklist with status; "needs first" and "unlocks"; evidence with quotes; the full record in collapsed sections |
| `/claims` | The claims | What exactly are we predicting? | Every `needs` link as a sentence, grouped by field, marked standing or falsified |
| `/about` | Method | How is this made, and what are its limits? | How breakthroughs are researched; what a milestone and a link mean; how sources are saved and quotes checked; which models did what; that these are proposals and no person reviewed them; how to challenge an entry; the author |

Every page has the same header (wordmark, Atlas, Claims, Method, search) and footer (purpose line, last updated, link to the repository if public). Every breakthrough and field has its own URL, page title and share image, so a link to one star stands on its own.

## Reading rules

- The chart is for overview and wonder. Lists and pages do the reading. Nothing is reachable only through the chart.
- One idea per screen-height on Home. Body text is at least 17px on desktop and 16px on phone, with a measure of 60–72 characters.
- Colour means progress state and nothing else. Fields are told apart by position, name and emblem.
- Status is never colour alone: it always has a word or a shape.
- Keyboard: every star and link is focusable in a sensible order; focus is always visible. Screen readers get the list, not the chart.
- Text contrast is at least 4.5:1. Motion stops under `prefers-reduced-motion`.
- Phone is list-first: the chart is a backdrop and a small locator, never something to pinch at to read.
- First load shows text within one second on a normal connection; the chart and images arrive after.

## The star atlas

Revised November 11 after the full atlas landed (66 fields, 742 breakthroughs, 77 `needs` links). The first mock placed stars on concentric rings by prerequisite depth. With links this sparse almost every star sat on one ring and 66 radial names made a sunburst: a dial, not a sky. The chart is now a flat sky map.

- **The sky** is a wide rectangular chart, about 16:10, that pans and zooms. A faint graticule with coordinate ticks in mono gives it the feel of an instrument. Every star has a stable chart coordinate, shown on its page, so "where is it" has an answer.
- **Regions.** The 66 fields are grouped into eight regions of neighbouring disciplines, each a broad labelled area of the sky: Computing and Information; Mathematics and Physics; Chemistry and Materials; Engineering and Energy; Earth and Space; Life Sciences; Medicine; Mind and Society. Region names are large, wide-tracked and very faint, like the names of oceans on a map.
- **Constellation:** one field. A compact figure with its own recognisable shape, computed once from its IDs so the sky never reshuffles. Its name is set horizontally beneath it. No rotated text anywhere.
- **Star:** one breakthrough. Size by number of milestones. At close zoom a segmented ring, one segment per milestone: empty, in progress, met.
- **Brightness:** a star with nothing met is a dim point; it warms as milestones advance and ignites white-gold when all are met. Today's sky is mostly dim, which is the honest picture, so the rare warm stars must be findable at a glance from the widest view.
- **Two kinds of line, never confused.**
  - *Figure lines* join the stars of one constellation. They mean "same field" and nothing more: hairline, low contrast, no arrowhead.
  - *Claim lines* are `needs` links: curved, in the structure accent, brighter at the end that must come first, with a small arrowhead towards what it unlocks. Across the whole sky they are shown faintly at rest (there are only 77, and they are the predictions), and drawn in full when a star or constellation is focused. The legend says what each kind means.
- **Levels of detail:** widest, regions, constellation figures and names, warm stars; nearer, every star and its ring; nearest, titles. Selecting a star glides the view to it and opens a summary card that links to its page. Selecting a constellation frames it and lists its breakthroughs beside the chart.
- **Desktop:** drag to pan, wheel or buttons to zoom, click a constellation or pick it from the list to fly there. **Phone:** list-first. A small, non-interactive locator shows where the current field sits in the sky.
- **Home** uses the same sky, slowly drifting behind the hero, not a separate drawing.

## Look

Science fiction through depth, precision and light. No neon, no fake terminal text, nothing decorative that carries no information.

- **Palette.** Void `#05070D`; deep `#0B1020`; raised `#111830`; hairline `rgba(160,190,255,0.14)`; starlight text `#E9EEF8`; muted `#8E9BB5`; structure accent (links, rings, focus) `#7FB2FF`; progress amber `#FFB454`; met white-gold `#FFF1C9` with a soft glow; contradiction `#FF6B6B`, rarely.
- **Type.** Display: Jura (titles at 600; small labels in light, wide-tracked capitals). Text: Newsreader, for anything longer than two lines. IDs, coordinates and data: JetBrains Mono. All bundled locally.
- **Space.** Generous. Hairline rules and small tick marks do the structuring; boxes with borders are the exception.
- **Depth.** Three layers that move at different rates: a generated deep-field plate, a drawn starfield, and the chart.
- **Motion** (Motion for React). On load the rings sweep in and constellations assemble, staggered, in under two seconds. Links draw themselves on focus. The view glides, with easing, to a selected star. Stars that moved in the last 30 days pulse slowly. Page changes cross-fade. Nothing loops fast or moves while the reader is reading.

## Assets and who makes them

- Fable: this spec, short briefs, and review of downsized screenshots. No drawing.
- Codex (GPT Image 2): the deep-field plate for Home and the share-image background. Later, after a pilot of ten, one illustration per breakthrough.
- Opus or Codex Sol: all SVG (chart, rings, star glyphs, the wordmark, one emblem per field generated from a rule, not drawn one by one) and all components.

## Technical

- React and Vite in `atlas/web`, with a client-side router. No new tables.
- **One data contract, the same in development and in the export.** The site reads only these files, which the server builds on request and the export writes to disk:
  - `data/catalog.json`: what every page and the chart need, and no more. Fields (`id`, `name`, `region`, counts) and breakthroughs (`id`, `field`, `title`, milestone statuses, `prerequisites`, `moved_at`), plus recent movement and the withheld concepts. Budget: under 300 KB before compression.
  - `data/field/QUA.json`: one field's scope, its breakthroughs with summaries and milestone labels, and any withheld concepts.
  - `data/b/QUA-01.json`: one breakthrough's full record, sources as links to the originals, and its evidence.
  - `data/search.json`: titles and short summaries, loaded when the search box is first used. Search ranks whole-word and title-prefix matches above substrings.
  - `data/claims.json`: every `needs` link with its stated reason and the model that proposed it, for the Claims page.
- v1 is exported as static files by `python3 -m atlas.export OUT`: the built site, the data files above, and one HTML file per route with its own title, description and share image. Saved source copies and working documents are not exported.
- **Share images** are drawn by the site itself and photographed. `/share/default`, `/share/field/QUA` and `/share/b/QUA-01` draw only a 1200×630 card (wordmark, ID, title fitted to at most four lines, field and region, milestone meter in words, the star on a graduated dial and a locator; for a field its constellation; for the default the motto and the whole sky), in their final state, marked `noindex` and never exported as pages. `python3 -m atlas.share DIR` screenshots every card with Playwright (a build-time tool; the rest of atlas stays standard-library only) to `DIR/share/<ID>.png`, `field-<ID>.png` and `default.png`, about 60 KB each; `atlas.export --share DIR` copies them in and reports pages without one.
- First load shows text within one second on a normal connection; the chart arrives after.

## Build status

The three-screen mock was built on November 11. On the same day the owner authorized building the whole site to the best design without a further approval gate. The standing rules still apply: every screen is reviewed from screenshots at desktop (1440) and phone (390) widths, and checked for contrast, keyboard use and load size before it is called done. Publishing still needs the owner's authorization.

# Site design

November 11, 2026. The spec for Track B of the [project plan](technology-graph-plan.md). This is a website, not a single chart: the star atlas is its centrepiece, and the pages around it explain it, make it readable and make it shareable. The bar is a site the owner is proud to publish under his own name.

## What a visitor should leave with

1. This is a map of the breakthroughs worth working towards, empowered by superintelligence.
2. Every breakthrough has milestones along the way that tell us how close it is.
3. Here is what has moved, with the papers that moved it. The atlas is a map, not a forecast: it says nothing about when or in what order.

## Pages

| Route | Page | Its one question | Order of content |
|---|---|---|---|
| `/` | Home | What is this, and why trust it? | Hero over the living sky; purpose in two sentences; "Enter the atlas"; what moved recently; how to read a star (three steps); a few constellations to start with; footer |
| `/atlas` | The atlas | What is there to work towards? | The full star chart, with search and a field list |
| `/field/QUA` | A constellation | What is in this area? | Field name; its constellation; its breakthroughs as a list in ID order |
| `/b/QUA-01` | A breakthrough | How will we know, and how close is it? | Title and concept; milestones along the way with evidence, marked as the atlas's own proposals; papers that are steps toward the whole; why it matters, what has been shown, what is missing, what is uncertain; sources, each with the passages that cite it; the rest of the record in collapsed sections |
| `/about` | Method | How is this made, and what are its limits? | That this is a map and not a forecast; how breakthroughs are researched; what a milestone means and who proposed it; how sources are saved and quotes checked; which models did what; that no person reviewed the proposals; how to challenge an entry; the author |

Every page has the same header (wordmark, Atlas, Method, search) and footer (purpose line, last updated, link to the repository if public). Every breakthrough and field has its own URL, page title and share image, so a link to one star stands on its own.

## Reading rules

- Every status word describes the atlas's own assessment, not the state of the science: a milestone nobody has judged is "Not yet assessed".
- Milestones are shown as the atlas's proposals. A source is shown with the passages that cite it, so a reader can see what it is there for.
- The chart is for overview and wonder. Lists and pages do the reading. Nothing is reachable only through the chart.
- One idea per screen-height on Home. Body text is at least 17px on desktop and 16px on phone, with a measure of 60–72 characters.
- Colour means progress state and nothing else. Fields are told apart by position, name and emblem.
- Status is never colour alone: it always has a word or a shape.
- Keyboard: every star and link is focusable in a sensible order; focus is always visible. Screen readers get the list, not the chart.
- Text contrast is at least 4.5:1. Motion stops under `prefers-reduced-motion`.
- Phone is list-first: the chart is a backdrop and a small locator, never something to pinch at to read.
- First load shows text within one second on a normal connection; the chart and images arrive after.

## The star atlas

Revised November 11 after the full atlas landed (66 fields, 742 breakthroughs). The first mock placed stars on concentric rings by prerequisite depth: a dial, not a sky. The chart is now a flat sky map. Later the same day the owner decided the atlas makes no order claims, so the chart draws no prerequisite lines. Revised November 25: the chart lost its rulers, region colours and the rays on complete stars, and rings no longer overlap. Revised November 26: far points show milestone progress, the panel beside the chart became an index, one vocabulary for progress, and regions pack their constellations in evened rows (every star moved); the bullets below describe it as built.

- **The sky** is a wide rectangular chart, about 16:10, that pans and zooms. A faint grid is texture only: it has no ticks or numbers, because position on the chart carries no scale. Every star still has a stable chart coordinate, shown on its breakthrough page beside the locator, so "where is it" has an answer.
- **Regions.** The 66 fields are grouped into eight regions of neighbouring disciplines, each a broad labelled area of the sky: Computing and Information; Mathematics and Physics; Chemistry and Materials; Engineering and Energy; Earth and Space; Life Sciences; Medicine; Mind and Society. Region names are large, wide-tracked and very faint, like the names of oceans on a map.
- **Constellation:** one field. A compact figure with its own recognisable shape, computed once from its IDs so the sky never reshuffles. Its name is set horizontally beneath it, with its size in words under the name ("17 breakthroughs", and "4 complete" when any are). No rotated text anywhere.
- **Star:** one breakthrough. From afar a point shaded like a small pie by its milestones: the share met in ink, the share in progress in amber, the rest grey, so the widest view shows how far along each field is. At close zoom a segmented ring, one segment per milestone: not yet assessed, in progress, met. Rings are nearly one size and never overlap, so segments can be counted. A complete breakthrough (completion test met) is the ring filled in: one solid disc, with no rays or halo on paper, findable at a glance from the widest view.
- **Colour** means progress and nothing else, on the chart as everywhere: grey, amber, ink. Regions and fields have no hue of their own.
- **Words for progress.** A milestone is not yet assessed, in progress or met. A breakthrough is not yet assessed, in progress (anything judged to move it) or complete (its completion test is met). No other words are used for these, and a count always says what it counts ("2/7 met", never a bare fraction).
- **The legend** is a bar along the chart's foot, on its own ground, and describes the marks drawn at the zoom in view: points from afar, rings close in, the disc, the line.
- **The panel beside the chart** is an index at the widest view: every constellation by region, each with its milestones as one bar (met, in progress, not yet assessed) and its number of breakthroughs, so fields can be compared down the column. With one constellation open it lists that field's breakthroughs in dense rows: star, ID, whole title, milestones met. Summaries are on the star's card, not in the list.
- **One kind of line.** *Figure lines* join the stars of one constellation. They mean "same field" and nothing more: a grey hairline, no arrowhead. The legend says so, and says that a line shows no order or dependency.
- **Levels of detail:** widest, regions, constellation figures and names, stars as points; nearer, every star and its ring; nearer still, every star's ID. Titles are never cut short on the chart: the star pointed at or selected shows its whole title, and the list beside the chart has them all (pointing at a star marks its row). Selecting a star glides the view to it and opens a summary card that links to its page. Selecting a constellation frames its stars to fill the view and lists its breakthroughs beside the chart; its name is then in the panel and the breadcrumb, not on the sky. A label with no clear spot beside its star is set a step away and tied to it by a hairline.
- **Desktop:** drag to pan, wheel or buttons to zoom, click a constellation or pick it from the list to fly there. **Phone:** list-first. A small, non-interactive locator shows where the current field sits in the sky.
- **Home** uses the same sky, slowly drifting behind the hero, not a separate drawing.

## Look

Science fiction through depth, precision and light. No neon, no fake terminal text, nothing decorative that carries no information.

- **Palette.** Void `#05070D`; deep `#0B1020`; raised `#111830`; hairline `rgba(160,190,255,0.14)`; starlight text `#E9EEF8`; muted `#8E9BB5`; structure accent (links, rings, focus) `#7FB2FF`; progress amber `#FFB454`; met white-gold `#FFF1C9` with a soft glow; contradiction `#FF6B6B`, rarely.
- **Type.** Display: Jura (titles at 600; small labels in light, wide-tracked capitals). Text: Newsreader, for anything longer than two lines. IDs, coordinates and data: JetBrains Mono. All bundled locally.
- **Space.** Generous. Hairline rules and small tick marks do the structuring; boxes with borders are the exception.
- **Depth.** Three layers that move at different rates: a generated deep-field plate, a drawn starfield, and the chart.
- **Motion** (Motion for React). On load the rings sweep in and constellations assemble, staggered, in under two seconds. The view glides, with easing, to a selected star. Stars that moved in the last 30 days pulse slowly. Page changes cross-fade. Nothing loops fast or moves while the reader is reading.

## Assets and who makes them

- Fable: this spec, short briefs, and review of downsized screenshots. No drawing.
- Codex (GPT Image 2): the deep-field plate for Home and the share-image background. Later, after a pilot of ten, one illustration per breakthrough.
- Opus or Codex Sol: all SVG (chart, rings, star glyphs, the wordmark, one emblem per field generated from a rule, not drawn one by one) and all components.

## Technical

- React and Vite in `atlas/web`, with a client-side router. No new tables.
- **One data contract, the same in development and in the export.** The site reads only these files, which the server builds on request and the export writes to disk:
  - `data/catalog.json`: what every page and the chart need, and no more. Fields (`id`, `name`, `region`, counts) and breakthroughs (`id`, `field`, `title`, milestone statuses, `overall`, `moved_at`), plus recent movement and the withheld concepts. Budget: under 300 KB before compression.
  - `data/field/QUA.json`: one field's scope, its breakthroughs with summaries and milestone labels, and any withheld concepts.
  - `data/b/QUA-01.json`: one breakthrough's full record, sources as links to the originals, and its evidence.
  - `data/search.json`: titles and short summaries, loaded when the search box is first used. Search ranks whole-word and title-prefix matches above substrings.
- v1 is exported as static files by `python3 -m atlas.export OUT`: the built site, the data files above, and one HTML file per route with its own title, description and share image. Saved source copies and working documents are not exported.
- **Share images** are drawn by the site itself and photographed. `/share/default`, `/share/field/QUA` and `/share/b/QUA-01` draw only a 1200×630 card (wordmark, ID, title fitted to at most four lines, field and region, milestone meter in words, the star on a graduated dial and a locator; for a field its constellation; for the default the motto and the whole sky), in their final state, marked `noindex` and never exported as pages. `python3 -m atlas.share DIR` screenshots every card with Playwright (a build-time tool; the rest of atlas stays standard-library only) to `DIR/share/<ID>.png`, `field-<ID>.png` and `default.png`, about 60 KB each; `atlas.export --share DIR` copies them in and reports pages without one.
- First load shows text within one second on a normal connection; the chart arrives after.

## Build status

The three-screen mock was built on November 11. On the same day the owner authorized building the whole site to the best design without a further approval gate. The standing rules still apply: every screen is reviewed from screenshots at desktop (1440) and phone (390) widths, and checked for contrast, keyboard use and load size before it is called done. Publishing still needs the owner's authorization.

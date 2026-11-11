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

- **Star:** one breakthrough. Size by number of milestones. A segmented ring around it, one segment per milestone: empty, in progress, met.
- **Brightness:** a star with nothing met is a dim point; it warms as milestones advance and ignites white-gold when all are met.
- **Constellation:** one field. Its stars sit in one sector of the sky, in a stable shape (positions are computed once from the IDs, so the sky never reshuffles).
- **Rings:** faint concentric rings are prerequisite depth. The inner ring is what could happen now; each ring out needs something further in.
- **Lines:** `needs` links, drawn from the prerequisite outward. Hidden at rest across fields, drawn when a star or constellation is focused.
- **Levels of detail:** far out, the sky and constellation names; nearer, stars and their rings; nearest, titles. Selecting a star glides the view to it and opens a summary card that links to its page.
- **Desktop:** drag to pan, wheel or buttons to zoom, click a constellation name to fly there. **Phone:** the chart is not interactive; a locator shows where the current field sits.

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

- React and Vite in `atlas/web`, with a client-side router, reading the existing API. No new tables.
- The catalog response gains what the chart needs and already exists in the data: milestone labels and status per breakthrough.
- v1 is exported as static files: one HTML file per route, data as JSON, images optimised. Saved source copies are not exported; the site links to originals.

## The mock (the approval gate)

Three screens, built for real in `atlas/web` on the live data, at desktop (1440) and phone (390) widths:

1. Home.
2. The atlas, with one constellation focused.
3. A breakthrough page (QUA-01).

The mock is judged on: is the purpose clear in five seconds; can a milestone be read in three; does it look like something worth putting a name on. Nothing else is built until the owner approves it.

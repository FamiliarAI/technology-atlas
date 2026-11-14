// The sky's geometry: a flat, wide chart. Everything here is a pure function of the field and
// breakthrough IDs, the field names and regions, so the same data always gives the same sky.
//
// World units are screen pixels at the design scale (k = 1): the widest view of the atlas on a
// 1440-wide screen is close to k = 1.1, so a constellation name set at 9.5 units reads at about
// 10.5px there and never overlaps its neighbours.

const TAU = Math.PI * 2;

// Regions as a two-row map. Neighbouring cells are neighbouring disciplines, across and down:
// Engineering over Earth and Space (rocketry, petroleum), Physics over Chemistry, Computing over
// Life Sciences (bioinformatics, neuroscience), Mind and Society over Medicine (psychiatry).
export const REGION_GRID = [
  ['Engineering and Energy', 'Mathematics and Physics', 'Computing and Information', 'Mind and Society'],
  ['Earth and Space', 'Chemistry and Materials', 'Life Sciences', 'Medicine'],
];

// Order within a region, read left to right and top to bottom, so fields that border another
// region sit near it. Fields not listed (new ones) follow in ID order.
export const FIELD_ORDER = [
  'AER', 'MNE', 'CIV', 'STR', 'MEC', 'IND', 'ROB', 'ELE', 'PET', 'NUC', 'PWR', 'BME',
  'MAT', 'THR', 'PHY', 'OPT',
  'CSC', 'CRY', 'QUA', 'CPE', 'SWE', 'HCI', 'MLC',
  'ECO', 'FIN', 'ACT', 'PSY',
  'AST', 'ROC', 'OCE', 'GEO', 'AGR',
  'CRX', 'CHM', 'MAS', 'MET', 'CRM', 'CHE', 'RHE',
  'BIF', 'GEN', 'BCH', 'NEU', 'MIC', 'VIR', 'IMM', 'BIO', 'BOT', 'ZOO', 'LON',
  'PHA', 'ONC', 'INF', 'NRL', 'CAR', 'END', 'NEP', 'CLM', 'EMR', 'ANS', 'SUR', 'ORT', 'OPH',
  'DER', 'OBG', 'PED',
];

// Sizes in world units.
export const SPACING = 8; // least distance between two stars of one figure
export const LABEL = { size: 10, char: 7.3, line: 12.5, gap: 8, max: 16 };
const CELL = { padX: 14, padY: 10, slack: 1.16 };
const FRAME = 22; // margin between the chart's frame and its first region
export const UNITS_ACROSS = 64; // chart coordinates run 0–64 across and 0–40 or so down

export function hash(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function random(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Radius of a star's milestone ring: more milestones, a larger star.
export const starRadius = (milestones) => 1.75 + 0.34 * milestones;
// Radius of the star's point inside the ring.
export const coreRadius = (milestones) => 0.8 + 0.13 * milestones;

// A field name in at most two balanced lines of capitals.
export function wrapName(name) {
  const text = name.toUpperCase();
  if (text.length <= 12 || !text.includes(' ')) return [text];
  const words = text.split(' ');
  let best = [text];
  let worst = text.length;
  for (let n = 1; n < words.length; n++) {
    const a = words.slice(0, n).join(' ');
    const b = words.slice(n).join(' ');
    const m = Math.max(a.length, b.length);
    if (m < worst) {
      worst = m;
      best = [a, b];
    }
  }
  return best;
}

export const labelWidth = (lines) => Math.max(...lines.map((l) => l.length)) * LABEL.char;

// A region's name, set like an ocean's: wide-tracked capitals in one or two lines, as large as
// the region's width allows, up to a cap.
// A region's name, set like a printed chart's: small wide-tracked capitals in the region's
// top-left corner, in one line or two, always clear of the constellations.
export const REGION_TYPE = { size: 11, char: 10.8, lead: 14.5 };
export function regionLines(name) {
  const text = name.toUpperCase();
  const words = text.split(' ');
  if (words.length < 3 && text.length <= 14) return [text];
  let best = [text];
  let worst = Infinity;
  for (let n = 1; n < words.length; n++) {
    const a = words.slice(0, n).join(' ');
    const b = words.slice(n).join(' ');
    if (Math.max(a.length, b.length) < worst) {
      worst = Math.max(a.length, b.length);
      best = [a, b];
    }
  }
  return best;
}
const regionLabelBox = (lines) => ({
  w: Math.max(...lines.map((l) => l.length)) * REGION_TYPE.char + 16,
  h: REGION_TYPE.size + (lines.length - 1) * REGION_TYPE.lead + 14,
});

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

function crosses(p1, p2, p3, p4) {
  const d = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  const d1 = d(p3, p4, p1);
  const d2 = d(p3, p4, p2);
  const d3 = d(p1, p2, p3);
  const d4 = d(p1, p2, p4);
  return d1 * d2 < 0 && d3 * d4 < 0;
}

// One field's figure: n well-spaced points along a seeded skeleton of two to four strokes,
// sometimes branched, joined by a minimum spanning tree with at most a loop or two added and
// long spurs cut. Returns points in a local frame centred on the figure, each with its
// position along the skeleton so the stars can be laid out in ID order.
export function figure(fieldId, n) {
  const rand = random(hash('figure:' + fieldId));
  // Figures differ in scale as well as shape: some are tight clusters, some loose.
  const s = SPACING * (0.88 + rand() * 0.3);
  if (n <= 0) return { points: [], edges: [], w: 0, h: 0 };
  const length = s * (1.05 * Math.pow(n, 0.82) + 0.8);
  const strokes = Math.min(2 + Math.floor(rand() * 3), Math.max(1, n - 2));
  const weights = Array.from({ length: strokes }, () => 0.55 + rand());
  const total = weights.reduce((a, b) => a + b, 0);
  const branch = strokes >= 3 && rand() < 0.45 ? 1 + Math.floor(rand() * (strokes - 2)) : -1;
  let heading = (rand() - 0.5) * 0.9 + (rand() < 0.5 ? 0 : Math.PI);
  const turnSign = rand() < 0.5 ? -1 : 1;
  const verts = [{ x: 0, y: 0, heading }];
  const segs = [];
  let at = 0;
  for (let i = 0; i < strokes; i++) {
    const len = (length * weights[i]) / total;
    let start = verts[verts.length - 1];
    if (i === strokes - 1 && branch > 0) {
      start = verts[branch];
      heading = start.heading + (rand() < 0.5 ? -1 : 1) * (1.05 + rand() * 0.7);
    }
    const end = {
      x: start.x + Math.cos(heading) * len,
      y: start.y + Math.sin(heading) * len,
      heading,
    };
    segs.push({ a: start, b: end, len, at });
    at += len;
    verts.push(end);
    const bend = (0.3 + rand() * 1.05) * (rand() < 0.72 ? turnSign : -turnSign);
    heading += bend;
  }
  const thick = s * 0.8;
  const sample = () => {
    let u = rand() * at;
    let seg = segs[0];
    for (const g of segs) {
      seg = g;
      if (u <= g.len) break;
      u -= g.len;
    }
    const t = Math.min(1, u / seg.len);
    const dx = (seg.b.x - seg.a.x) / seg.len;
    const dy = (seg.b.y - seg.a.y) / seg.len;
    const off = (rand() - 0.5) * 2 * thick;
    return {
      x: seg.a.x + (seg.b.x - seg.a.x) * t - dy * off,
      y: seg.a.y + (seg.b.y - seg.a.y) * t + dx * off,
      t: seg.at + u,
    };
  };
  const points = [{ x: 0, y: 0, t: 0 }];
  while (points.length < n) {
    let best = null;
    for (let c = 0; c < 26; c++) {
      const p = sample();
      let score = Infinity;
      for (const q of points) score = Math.min(score, dist(p, q));
      if (!best || score > best.score) best = { ...p, score };
    }
    points.push({ x: best.x, y: best.y, t: best.t });
  }
  // A few rounds of gentle repulsion so no two stars crowd each other.
  for (let round = 0; round < 40; round++) {
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = points[i];
        const b = points[j];
        const d = dist(a, b) || 0.01;
        if (d < s) {
          const push = (s - d) / 2 / d;
          const px = (b.x - a.x) * push;
          const py = (b.y - a.y) * push;
          a.x -= px;
          a.y -= py;
          b.x += px;
          b.y += py;
        }
      }
    }
  }
  // Minimum spanning tree (Prim).
  const inTree = new Array(n).fill(false);
  const cost = new Array(n).fill(Infinity);
  const from = new Array(n).fill(-1);
  cost[0] = 0;
  const edges = [];
  const adj = Array.from({ length: n }, () => []);
  for (let k = 0; k < n; k++) {
    let v = -1;
    for (let i = 0; i < n; i++) if (!inTree[i] && (v < 0 || cost[i] < cost[v])) v = i;
    inTree[v] = true;
    if (from[v] >= 0) {
      edges.push([from[v], v]);
      adj[v].push(from[v]);
      adj[from[v]].push(v);
    }
    for (let i = 0; i < n; i++) {
      const d = dist(points[v], points[i]);
      if (!inTree[i] && d < cost[i]) {
        cost[i] = d;
        from[i] = v;
      }
    }
  }
  const lengths = edges.map(([a, b]) => dist(points[a], points[b])).sort((a, b) => a - b);
  const median = lengths[Math.floor(lengths.length / 2)] || s;
  // Close a loop or two, as drawn figures often have a body: the shortest extra edge whose
  // tree path is at least three steps, crossing nothing and meeting no edge at a sharp angle.
  const hops = (a, b) => {
    const seen = new Map([[a, 0]]);
    const queue = [a];
    while (queue.length) {
      const v = queue.shift();
      if (v === b) return seen.get(v);
      for (const w of adj[v]) {
        if (!seen.has(w)) {
          seen.set(w, seen.get(v) + 1);
          queue.push(w);
        }
      }
    }
    return Infinity;
  };
  const sharp = (v, w) => {
    const ax = points[w].x - points[v].x;
    const ay = points[w].y - points[v].y;
    return adj[v].some((u) => {
      const bx = points[u].x - points[v].x;
      const by = points[u].y - points[v].y;
      const cos = (ax * bx + ay * by) / (Math.hypot(ax, ay) * Math.hypot(bx, by));
      return cos > Math.cos(0.5);
    });
  };
  const loops = n >= 14 ? 2 : n >= 7 ? 1 : 0;
  if (loops) {
    const extra = [];
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        if (!adj[i].includes(j)) extra.push([dist(points[i], points[j]), i, j]);
      }
    }
    extra.sort((a, b) => a[0] - b[0]);
    let added = 0;
    for (const [d, i, j] of extra) {
      if (added >= loops || d > median * 1.75) break;
      if (hops(i, j) < 3) continue;
      if (sharp(i, j) || sharp(j, i)) continue;
      const clash = edges.some(
        ([a, b]) => a !== i && a !== j && b !== i && b !== j && crosses(points[i], points[j], points[a], points[b]),
      );
      if (clash) continue;
      edges.push([i, j]);
      adj[i].push(j);
      adj[j].push(i);
      added++;
    }
  }
  // Cut a long spur to a lone star: drawn figures leave an outlier unjoined.
  const figureEdges = edges.filter(([a, b]) => {
    const leaf = adj[a].length === 1 || adj[b].length === 1;
    return !(leaf && dist(points[a], points[b]) > median * 2.1);
  });
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  for (const p of points) {
    p.x -= cx;
    p.y -= cy;
  }
  return {
    points,
    edges: figureEdges,
    w: Math.max(...xs) - Math.min(...xs),
    h: Math.max(...ys) - Math.min(...ys),
  };
}

// Turns a figure to the angle that keeps it lowest without growing much wider than its name,
// so constellations and their names pack together. Turning keeps the shape and its spacing.
function settle(fig, labelW) {
  if (fig.points.length < 3) return fig;
  let best = null;
  for (let step = 0; step < 24; step++) {
    const a = (step / 24) * Math.PI;
    const c = Math.cos(a);
    const s = Math.sin(a);
    const pts = fig.points.map((p) => ({ x: p.x * c - p.y * s, y: p.x * s + p.y * c, t: p.t }));
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    const w = Math.max(...xs) - Math.min(...xs);
    const h = Math.max(...ys) - Math.min(...ys);
    const score = h + Math.max(0, w - Math.max(labelW, fig.w) * 1.1) * 2;
    if (!best || score < best.score) best = { score, pts, w, h };
  }
  const xs = best.pts.map((p) => p.x);
  const ys = best.pts.map((p) => p.y);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  for (const p of best.pts) {
    p.x -= cx;
    p.y -= cy;
  }
  return { points: best.pts, edges: fig.edges, w: best.w, h: best.h };
}

// Places every constellation and star. Regions take a share of the map in proportion to what
// they hold; inside a region, constellations start on a loose grid and are relaxed apart, so
// nothing overlaps and the result reads as a hand-set chart rather than a table.
export function layout(fields, items) {
  const known = new Map(fields.map((f) => [f.id, f]));
  const regionNames = [...new Set(fields.map((f) => f.region || 'Other'))];
  const grid = REGION_GRID.map((row) => row.filter((r) => regionNames.includes(r)));
  for (const r of regionNames) {
    if (!grid.some((row) => row.includes(r))) {
      const lighter = grid[0].length <= grid[1].length ? grid[0] : grid[1];
      lighter.push(r);
    }
  }
  const rank = (id) => {
    const i = FIELD_ORDER.indexOf(id);
    return i < 0 ? FIELD_ORDER.length : i;
  };
  const byRegion = {};
  for (const r of regionNames) {
    byRegion[r] = fields
      .filter((f) => (f.region || 'Other') === r)
      .map((f) => f.id)
      .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  }
  const order = grid.flat().flatMap((r) => byRegion[r]);
  const members = {};
  for (const item of Object.values(items)) (members[item.field] ||= []).push(item);

  // Each constellation's figure and the cell it needs, label included.
  const cells = {};
  for (const id of order) {
    const mine = (members[id] || []).sort((a, b) => a.id.localeCompare(b.id));
    const lines = wrapName(known.get(id).name);
    const fig = settle(figure(id, mine.length), labelWidth(lines));
    const reach = starRadius(6);
    const fw = fig.w + reach * 2;
    const fh = fig.h + reach * 2;
    const w = Math.max(fw, labelWidth(lines)) + CELL.padX;
    const h = fh + LABEL.gap + lines.length * LABEL.line + CELL.padY;
    cells[id] = { id, fig, lines, mine, fw, fh, w, h };
  }

  // Each region's name is a fixed cell in its top-left corner; constellations keep clear of it.
  for (const r of regionNames) {
    const lines = regionLines(r);
    const b = regionLabelBox(lines);
    cells['@' + r] = { id: '@' + r, w: b.w, h: b.h, lines, fixed: true };
  }

  // Shelf-packs a region's cells into a given width: its name first, then the constellations,
  // tallest first so each shelf holds cells of similar height. Returns the height it needs.
  const shelves = (region, w) => {
    const ids = [
      '@' + region,
      ...[...byRegion[region]].sort((a, b) => cells[b].h - cells[a].h || rank(a) - rank(b)),
    ];
    const rows = [];
    let row = [];
    let used = 0;
    for (const id of ids) {
      const cw = cells[id].w;
      if (row.length && used + cw > w) {
        rows.push(row);
        row = [];
        used = 0;
      }
      row.push(id);
      used += cw;
    }
    if (row.length) rows.push(row);
    const height = rows.reduce((n, r) => n + Math.max(...r.map((id) => cells[id].h)), 0);
    return { rows, height };
  };

  // Region rectangles: rows of equal width. In each row, the least height at which every
  // region's cells fit, found by bisection; then the frame width whose chart is largest on the
  // desktop stage while staying near 16:10.
  const widest = (r) => Math.max(...[...byRegion[r], '@' + r].map((id) => cells[id].w));
  const widthFor = (r, h) => {
    let lo = widest(r);
    let hi = [...byRegion[r], '@' + r].reduce((n, id) => n + cells[id].w, 0) + 1;
    if (shelves(r, lo).height <= h) return lo;
    if (shelves(r, hi).height > h) return Infinity;
    for (let i = 0; i < 14; i++) {
      const mid = (lo + hi) / 2;
      if (shelves(r, mid).height <= h) hi = mid;
      else lo = mid;
    }
    return hi;
  };
  const fitRow = (row, w) => {
    let lo = Math.max(...row.flatMap((r) => [...byRegion[r], '@' + r].map((id) => cells[id].h)));
    let hi = row.reduce((n, r) => n + shelves(r, 0).height, 0);
    for (let i = 0; i < 16; i++) {
      const mid = (lo + hi) / 2;
      const need = row.reduce((n, r) => n + widthFor(r, mid) * CELL.slack, 0);
      if (need <= w) hi = mid;
      else lo = mid;
    }
    const raw = row.map((r) => widthFor(r, hi) * CELL.slack);
    const spare = w - raw.reduce((a, b) => a + b, 0);
    const sum = raw.reduce((a, b) => a + b, 0);
    return { h: hi * CELL.slack, widths: raw.map((x) => x + (spare * x) / sum) };
  };
  // The stage is the desktop atlas's chart area at 1440 by 900, less its panels.
  const STAGE = { w: 1076, h: 726 };
  const cellArea = Object.values(cells).reduce((n, c) => n + c.w * c.h, 0);
  const guess = Math.sqrt(1.5 * cellArea * 1.5);
  let best = null;
  for (let w = Math.round(guess * 0.75); w <= guess * 1.4; w += 8) {
    const rows = grid.map((row) => fitRow(row, w));
    const h = rows.reduce((n, r) => n + r.h, 0);
    const aspect = (w + FRAME * 2) / (h + FRAME * 2);
    if (aspect < 1.4 || aspect > 1.66) continue;
    const k = Math.min(STAGE.w / (w + FRAME * 2), STAGE.h / (h + FRAME * 2));
    if (!best || k > best.k) best = { k, w, rows };
  }
  if (!best) {
    const w = Math.round(guess);
    best = { w, rows: grid.map((row) => fitRow(row, w)) };
  }
  const width = best.w;
  const widths = {};
  const heights = best.rows.map((r) => r.h);
  grid.forEach((row, ri) => row.forEach((r, n) => (widths[r] = best.rows[ri].widths[n])));
  const regions = [];
  let top = FRAME;
  grid.forEach((row, ri) => {
    let left = FRAME;
    for (const r of row) {
      regions.push({ name: r, x: left, y: top, w: widths[r], h: heights[ri], row: ri });
      left += widths[r];
    }
    top += heights[ri];
  });
  const world = { w: width + FRAME * 2, h: top + FRAME, frame: FRAME };
  world.unit = width / UNITS_ACROSS;

  // Constellations inside each region: shelf positions spread over the spare room, then each
  // pulled towards a seeded offset of its own and relaxed apart, so rows break up into a loose
  // scatter. If relaxing ever leaves an overlap, the region keeps its plain shelf positions.
  const overlaps = (a, b) =>
    Math.abs(a.x - b.x) < (a.w + b.w) / 2 - 0.5 && Math.abs(a.y - b.y) < (a.h + b.h) / 2 - 0.5;
  const figures = {};
  for (const region of regions) {
    const rand = random(hash('region:' + region.name));
    const x0 = region.x + 6;
    const x1 = region.x + region.w - 6;
    const y0 = region.y + 4;
    const y1 = region.y + region.h - 4;
    const { rows, height } = shelves(region.name, x1 - x0);
    const spareY = Math.max(0, y1 - y0 - height);
    const boxes = [];
    let y = y0 + spareY / (rows.length + 1) / 2;
    rows.forEach((row, ri) => {
      const rowH = Math.max(...row.map((id) => cells[id].h));
      const spareX = Math.max(0, x1 - x0 - row.reduce((n, id) => n + cells[id].w, 0));
      const gap = spareX / (row.length + (ri % 2 ? 0.5 : 1.5));
      // Alternate rows start at different offsets, as on a hand-set chart.
      let x = x0 + (row[0][0] === '@' ? 0 : gap * (ri % 2 ? 0.25 : 0.75));
      for (const id of row) {
        const c = cells[id];
        const fixed = id[0] === '@';
        const bx = fixed ? x0 + c.w / 2 : x + c.w / 2;
        const by = fixed ? y0 + c.h / 2 : y + (rowH - c.h) * rand() + c.h / 2;
        boxes.push({ id, x: bx, y: by, w: c.w, h: c.h, fixed, home: { x: bx, y: by } });
        x += c.w + gap;
      }
      y += rowH + spareY / (rows.length + 1);
    });
    const clamp = (b) => {
      b.x = Math.min(Math.max(b.x, x0 + b.w / 2), x1 - b.w / 2);
      b.y = Math.min(Math.max(b.y, y0 + b.h / 2), y1 - b.h / 2);
    };
    for (const b of boxes) {
      if (b.fixed) continue;
      b.target = {
        x: b.x + (rand() - 0.5) * Math.min(b.w * 0.8, 70),
        y: b.y + (rand() - 0.5) * Math.min(b.h * 0.9, 60),
      };
    }
    for (let round = 0; round < 260; round++) {
      const pull = round < 180 ? 0.08 : 0;
      for (const b of boxes) {
        if (b.fixed) continue;
        b.x += (b.target.x - b.x) * pull;
        b.y += (b.target.y - b.y) * pull;
      }
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i];
          const b = boxes[j];
          const ox = (a.w + b.w) / 2 - Math.abs(a.x - b.x);
          const oy = (a.h + b.h) / 2 - Math.abs(a.y - b.y);
          if (ox <= 0 || oy <= 0) continue;
          const share = a.fixed ? [0, 1] : b.fixed ? [1, 0] : [0.5, 0.5];
          if (ox < oy) {
            const sgn = a.x < b.x ? -1 : 1;
            a.x += sgn * ox * share[0];
            b.x -= sgn * ox * share[1];
          } else {
            const sgn = a.y < b.y ? -1 : 1;
            a.y += sgn * oy * share[0];
            b.y -= sgn * oy * share[1];
          }
        }
      }
      boxes.forEach((b) => !b.fixed && clamp(b));
    }
    // Any pair still overlapping steps back towards its shelf positions, which never overlap.
    for (let pass = 0; pass < 60; pass++) {
      let clash = false;
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          if (!overlaps(boxes[i], boxes[j])) continue;
          clash = true;
          for (const b of [boxes[i], boxes[j]]) {
            if (b.fixed) continue;
            const near = pass > 8 || Math.hypot(b.x - b.home.x, b.y - b.home.y) < 1;
            b.x = near ? b.home.x : (b.x + b.home.x) / 2;
            b.y = near ? b.home.y : (b.y + b.home.y) / 2;
          }
        }
      }
      if (!clash) break;
    }
    for (const b of boxes) {
      const cell = cells[b.id];
      if (b.fixed) {
        region.label = { lines: cell.lines, x: b.x - b.w / 2 + 8, y: b.y - b.h / 2 + 7, size: REGION_TYPE.size };
        continue;
      }
      const fx = b.x;
      const fy = b.y - cell.h / 2 + CELL.padY / 2 + cell.fh / 2;
      const lw = labelWidth(cell.lines);
      figures[b.id] = {
        id: b.id,
        x: fx,
        y: fy,
        cell: { x: b.x - cell.w / 2, y: b.y - cell.h / 2, w: cell.w, h: cell.h },
        box: {
          x: fx - Math.max(cell.fw, lw) / 2,
          y: fy - cell.fh / 2,
          w: Math.max(cell.fw, lw),
          h: cell.fh + LABEL.gap + cell.lines.length * LABEL.line,
        },
        label: { x: fx, y: fy + cell.fh / 2 + LABEL.gap, lines: cell.lines },
        region: region.name,
        edges: [],
      };
    }
  }

  // Stars: the field's breakthroughs in ID order, along its figure from the start.
  const cx = world.w / 2;
  const cy = world.h / 2;
  const placed = {};
  const sectors = {};
  order.forEach((id, index) => {
    const cell = cells[id];
    if (!cell.fig) return;
    const f = figures[id];
    const pts = [...cell.fig.points.keys()].sort((a, b) => cell.fig.points[a].t - cell.fig.points[b].t);
    const slot = {};
    cell.mine.forEach((item, n) => {
      const p = cell.fig.points[pts[n]];
      slot[pts[n]] = item.id;
      const x = f.x + p.x;
      const y = f.y + p.y;
      placed[item.id] = {
        x,
        y,
        angle: Math.atan2(y - cy, x - cx),
        radius: Math.hypot(x - cx, y - cy),
      };
    });
    f.edges = cell.fig.edges.map(([a, b]) => [slot[a], slot[b]]);
    const bearing = Math.atan2(f.y - cy, f.x - cx);
    // Kept for older callers: a field's "sector" is now its bearing from the chart's centre.
    sectors[id] = { index, mid: bearing, start: bearing, end: bearing };
  });
  return { order, sectors, placed, world, regions, figures, outer: Math.max(world.w, world.h) / 2 };
}

// A star's chart coordinate: two short numbers, across then down, in chart units (0 to 64
// across the frame). Stable for the same data, and printable on any page.
export function chartCoord(point, sky) {
  if (!point || !sky?.world) return null;
  const { frame, unit } = sky.world;
  const x = (point.x - frame) / unit;
  const y = (point.y - frame) / unit;
  const fmt = (v) => (v < 10 ? '0' : '') + v.toFixed(1);
  return { x, y, text: `${fmt(x)} · ${fmt(y)}` };
}

// A field's emblem is its own constellation in miniature, with a tick on the rim at its
// bearing from the centre of the sky.
export function emblem(field, sky, items) {
  const sector = sky.sectors[field.id];
  const f = sky.figures?.[field.id];
  const pts = items.map((i) => {
    const p = sky.placed[i.id];
    return { x: p.x, y: p.y, lit: i.met + i.moving + (i.overall || 0) > 0 };
  });
  if (!pts.length || !f) return { dots: [], lines: [], bearing: sector?.mid || 0 };
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 1);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const at = (p) => ({ x: ((p.x - cx) / span) * 30, y: ((p.y - cy) / span) * 30 });
  return {
    dots: pts.map((p) => ({ ...at(p), lit: p.lit })),
    lines: f.edges.map(([a, b]) => [at(sky.placed[a]), at(sky.placed[b])]),
    bearing: sector.mid,
  };
}

export function arc(cx, cy, r, a0, a1) {
  const x0 = cx + Math.cos(a0) * r;
  const y0 = cy + Math.sin(a0) * r;
  const x1 = cx + Math.cos(a1) * r;
  const y1 = cy + Math.sin(a1) * r;
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

export { TAU };

// The sky's geometry. Everything here is a pure function of field and breakthrough IDs plus
// the prerequisite links, so the same data always gives the same sky.

const TAU = Math.PI * 2;

// Sector order: neighbouring constellations are neighbouring disciplines. Fields not listed
// (new ones) follow in ID order, so adding a field never reorders the named ones.
export const FIELD_ORDER = [
  'CSC', 'SWE', 'CPE', 'QUA', 'CRY', 'ROB',
  'OPT', 'PHY', 'CRX', 'CHEMREV', 'THR', 'RHE',
  'CHE', 'CRM', 'PET', 'PWR', 'CIV', 'STR', 'ROC', 'OCE',
  'ZOO', 'PHA', 'ONC', 'SUR', 'ORT', 'OPH', 'DER', 'OBG', 'PED', 'PSY',
  'ECO',
];

// World units. Ring 0 (could happen now) is a broad band so its many stars have room;
// each later ring is a narrower band further out.
export const GEOMETRY = { core: 220, band0: 210, gap: 46, band: 74, step: 120 };

export const band = (depth) => {
  const { core, band0, gap, band: width, step } = GEOMETRY;
  if (depth === 0) return [core, core + band0];
  const start = core + band0 + gap + (depth - 1) * step;
  return [start, start + width];
};

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

export function depths(items) {
  const memo = {};
  const visit = (id, trail) => {
    if (memo[id] !== undefined) return memo[id];
    if (trail.has(id)) return 0; // a loop is rejected upstream; never recurse forever
    trail.add(id);
    const prereqs = (items[id]?.prerequisites || []).filter((p) => items[p]);
    memo[id] = prereqs.length ? 1 + Math.max(...prereqs.map((p) => visit(p, trail))) : 0;
    return memo[id];
  };
  for (const id of Object.keys(items)) visit(id, new Set());
  return memo;
}

// Radius of a star's milestone ring: more milestones, a larger star.
export const starRadius = (milestones) => 4.2 + 0.6 * milestones;

// Places every star. Fields get equal sectors clockwise from the top; within its sector and
// ring, each star (in ID order) takes the best of a few seeded candidate spots, the one
// furthest from stars already placed. Later IDs never move earlier ones.
export function layout(fields, items) {
  const known = new Set(fields.map((f) => f.id));
  const order = [
    ...FIELD_ORDER.filter((id) => known.has(id)),
    ...fields.map((f) => f.id).filter((id) => !FIELD_ORDER.includes(id)).sort(),
  ];
  const width = TAU / order.length;
  const depth = depths(items);
  const sectors = {};
  order.forEach((id, n) => {
    const start = -Math.PI / 2 + n * width;
    sectors[id] = { index: n, start, end: start + width, mid: start + width / 2 };
  });
  const placed = {};
  for (const fieldId of order) {
    const sector = sectors[fieldId];
    const pad = width * 0.1;
    const mine = Object.values(items)
      .filter((i) => i.field === fieldId)
      .sort((a, b) => a.id.localeCompare(b.id));
    const here = [];
    for (const item of mine) {
      const d = depth[item.id];
      const [r0, r1] = band(d);
      const rand = random(hash(item.id));
      let best = null;
      for (let c = 0; c < 18; c++) {
        const a = sector.start + pad + rand() * (width - 2 * pad);
        const r = Math.sqrt(r0 * r0 + rand() * (r1 * r1 - r0 * r0));
        const x = Math.cos(a) * r;
        const y = Math.sin(a) * r;
        let score = Math.min(
          r * (a - sector.start - pad) * 2.2 + 8,
          r * (sector.end - pad - a) * 2.2 + 8,
          (r - r0) * 2.2 + 8,
          (r1 - r) * 2.2 + 8,
        );
        for (const p of here) score = Math.min(score, Math.hypot(p.x - x, p.y - y));
        if (!best || score > best.score) best = { x, y, a, r, score };
      }
      const point = { x: best.x, y: best.y, angle: best.a, radius: best.r, depth: d };
      here.push(point);
      placed[item.id] = point;
    }
  }
  const maxDepth = Math.max(0, ...Object.values(depth));
  return { order, sectors, placed, maxDepth, outer: band(maxDepth)[1] };
}

// A field's emblem is its own constellation in miniature, turned so its sector points up,
// with a tick on the rim at its bearing in the sky.
export function emblem(field, sky, items) {
  const sector = sky.sectors[field.id];
  const turn = -Math.PI / 2 - sector.mid;
  const pts = items
    .filter((i) => i.field === field.id)
    .map((i) => {
      const p = sky.placed[i.id];
      return {
        x: p.x * Math.cos(turn) - p.y * Math.sin(turn),
        y: p.x * Math.sin(turn) + p.y * Math.cos(turn),
        lit: i.met + i.moving > 0,
      };
    });
  if (!pts.length) return { dots: [], bearing: sector.mid };
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  // Each axis is stretched to fill the emblem, so the pattern, not the sector's narrowness, shows.
  const sx = Math.max(Math.max(...xs) - Math.min(...xs), 1);
  const sy = Math.max(Math.max(...ys) - Math.min(...ys), 1);
  return {
    dots: pts.map((p) => ({ x: ((p.x - cx) / sx) * 15, y: ((p.y - cy) / sy) * 15, lit: p.lit })),
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

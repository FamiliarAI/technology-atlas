import { createContext, useContext, useEffect, useState } from 'react';
import { layout } from './sky.js';

const get = async (path) => {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
};

const DAY = 864e5;
export const TODAY = new Date();

export const STATUS = {
  none: 'No evidence yet',
  in_progress: 'In progress',
  met: 'Met',
};

// One request: the catalog carries milestone labels and status per breakthrough.
export async function loadAtlas() {
  const catalog = await get('/api/catalog');
  const items = {};
  for (const raw of catalog.breakthroughs) {
    const status = raw.milestones.map((m) => m.status);
    const met = status.filter((s) => s === 'met').length;
    const moving = status.filter((s) => s === 'in_progress').length;
    items[raw.id] = {
      ...raw,
      status,
      met,
      moving,
      // 0 = nothing judged; 1 = every milestone met. In progress counts half.
      glow: status.length ? (met + moving * 0.5) / status.length : 0,
      recent: raw.moved_at ? TODAY - new Date(raw.moved_at) < 30 * DAY : false,
      unlocks: [],
    };
  }
  for (const item of Object.values(items)) {
    for (const p of item.prerequisites) items[p]?.unlocks.push(item.id);
  }
  const sky = layout(catalog.fields, items);
  for (const [id, point] of Object.entries(sky.placed)) Object.assign(items[id], point);
  const fields = sky.order.map((id) => {
    const field = catalog.fields.find((f) => f.id === id);
    const list = Object.values(items)
      .filter((i) => i.field === id)
      .sort((a, b) => a.depth - b.depth || a.id.localeCompare(b.id));
    return {
      ...field,
      sector: sky.sectors[id],
      items: list,
      moving: list.filter((i) => i.moving || i.met).length,
      links: list.reduce((n, i) => n + i.prerequisites.length, 0),
    };
  });
  const links = Object.values(items).flatMap((i) =>
    i.prerequisites.filter((p) => items[p]).map((p) => ({ from: p, to: i.id })),
  );
  const all = Object.values(items);
  return {
    fields,
    field: Object.fromEntries(fields.map((f) => [f.id, f])),
    items,
    links,
    sky,
    recent: catalog.recent,
    asOf: catalog.as_of,
    totals: {
      breakthroughs: all.length,
      milestones: all.reduce((n, i) => n + i.status.length, 0),
      met: all.reduce((n, i) => n + i.met, 0),
      moving: all.reduce((n, i) => n + i.moving, 0),
      links: links.length,
    },
  };
}

export const loadBreakthrough = (id) => get('/api/breakthroughs/' + encodeURIComponent(id));

const Atlas = createContext({ atlas: null, error: null });

export function AtlasProvider({ children }) {
  const [state, setState] = useState({ atlas: null, error: null });
  useEffect(() => {
    loadAtlas().then(
      (atlas) => setState({ atlas, error: null }),
      (e) => setState({ atlas: null, error: e.message }),
    );
  }, []);
  return <Atlas.Provider value={state}>{children}</Atlas.Provider>;
}

export const useAtlas = () => useContext(Atlas);

export const formatDate = (iso) => {
  if (!iso) return '';
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};

export function search(atlas, query, limit = 8) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const scored = [];
  for (const i of Object.values(atlas.items)) {
    const id = i.id.toLowerCase();
    const title = i.title.toLowerCase();
    let score = 0;
    if (id === q) score = 100;
    else if (id.startsWith(q)) score = 60;
    else if (title.includes(q)) score = 40 - title.indexOf(q) / 100;
    else if (atlas.field[i.field].name.toLowerCase().includes(q)) score = 20;
    else if (i.search_text.toLowerCase().includes(q)) score = 10;
    if (score) scored.push([score, i]);
  }
  return scored
    .sort((a, b) => b[0] - a[0] || a[1].id.localeCompare(b[1].id))
    .slice(0, limit)
    .map(([, i]) => i);
}

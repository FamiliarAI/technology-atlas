import { createContext, useContext, useEffect, useState } from 'react';
import { layout } from './sky.js';

// The site reads only the data contract (docs/plans/2026-11-11-site-design.md, Technical):
// data/catalog.json up front, and one field, one breakthrough or the search index on demand.
// Paths are under Vite's base, so the same build works from the server and from the export.
const DATA = import.meta.env.BASE_URL + 'data/';

const get = async (path) => {
  const res = await fetch(DATA + path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
};

// Each file is fetched once per visit; a failed fetch is forgotten so it can be retried.
const cache = new Map();
const once = (path) => {
  if (!cache.has(path)) {
    cache.set(
      path,
      get(path).catch((e) => {
        cache.delete(path);
        throw e;
      }),
    );
  }
  return cache.get(path);
};

const DAY = 864e5;
export const TODAY = new Date();

// The words describe the atlas's own assessment, not the science: almost no milestone has been
// judged yet, so "none" means nobody has assessed it, not that nothing has happened.
export const STATUS = {
  none: 'Not yet assessed',
  in_progress: 'In progress',
  met: 'Met',
};

// One request: the catalog carries every breakthrough's milestone statuses. Summaries and
// milestone labels are in the field and breakthrough files.
export async function loadAtlas() {
  const catalog = await once('catalog.json');
  const items = {};
  for (const raw of catalog.breakthroughs) {
    const status = raw.milestones || [];
    const met = status.filter((s) => s === 'met').length;
    const moving = status.filter((s) => s === 'in_progress').length;
    // Papers judged to advance the breakthrough as a whole, not one milestone.
    const overall = Number.isInteger(raw.overall) ? raw.overall : 0;
    const n = status.length;
    // 0 = nothing judged; 1 = every milestone met. In progress counts half. A star whose only
    // progress is a step toward the whole is warm, as warm as one milestone in progress.
    const glow = n ? (met + moving * 0.5) / n : 0;
    items[raw.id] = {
      id: raw.id,
      field: raw.field,
      title: raw.title,
      moved_at: raw.moved_at || null,
      status,
      met,
      moving,
      overall,
      glow: glow || (overall ? 0.5 / Math.max(n, 4) : 0),
      recent: raw.moved_at ? TODAY - new Date(raw.moved_at) < 30 * DAY : false,
    };
  }
  const sky = layout(catalog.fields, items);
  for (const [id, point] of Object.entries(sky.placed)) Object.assign(items[id], point);
  const fields = sky.order.map((id) => {
    const field = catalog.fields.find((f) => f.id === id);
    const list = Object.values(items)
      .filter((i) => i.field === id)
      .sort((a, b) => a.id.localeCompare(b.id));
    return {
      ...field,
      sector: sky.sectors[id],
      items: list,
      moving: list.filter(warm).length,
    };
  });
  const all = Object.values(items);
  return {
    fields,
    field: Object.fromEntries(fields.map((f) => [f.id, f])),
    items,
    sky,
    regions: catalog.regions,
    recent: catalog.recent || [],
    // Concepts left out because a provider refused to review them: {id, title, field}.
    withheld: catalog.withheld || [],
    asOf: catalog.as_of,
    totals: {
      breakthroughs: all.length,
      milestones: all.reduce((n, i) => n + i.status.length, 0),
      met: all.reduce((n, i) => n + i.met, 0),
      moving: all.reduce((n, i) => n + i.moving, 0),
      overall: all.reduce((n, i) => n + i.overall, 0),
      warm: all.filter(warm).length,
    },
  };
}

// Has anything been judged to move this breakthrough: a milestone, or the whole?
export const warm = (item) => item.met + item.moving + item.overall > 0;

// Which milestone a judged row is about: a 1-based number, or null for the whole breakthrough.
// Rows carry `criterion` (a number) or `milestone` (an ID such as "m2", or null).
export function milestoneOf(row) {
  if (Number.isInteger(row.criterion)) return row.criterion;
  if (Number.isInteger(row.milestone)) return row.milestone;
  const m = /^m(\d+)$/.exec(row.milestone || '');
  return m ? Number(m[1]) : null;
}

export const loadField = (id) => once('field/' + encodeURIComponent(id) + '.json');
export const loadBreakthrough = (id) => once('b/' + encodeURIComponent(id) + '.json');
export const loadSearch = () => once('search.json');

// A field file, or null until it arrives (or if it fails).
export function useField(id) {
  const [state, setState] = useState({ id: null, data: null });
  useEffect(() => {
    if (!id) return undefined;
    let live = true;
    loadField(id).then(
      (data) => live && setState({ id, data }),
      () => live && setState({ id, data: null }),
    );
    return () => {
      live = false;
    };
  }, [id]);
  return state.id === id ? state.data : null;
}

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

const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Ranks one text against the query: whole word, then the text's start, then the start of a
// word, then any substring. 0 when absent.
function match(text, q, words) {
  const at = text.indexOf(q);
  if (at < 0) return 0;
  if (words.test(text)) return 4;
  if (at === 0) return 3;
  if (new RegExp('(^|[^\\p{L}\\p{N}])' + escape(q), 'u').test(text)) return 2;
  return 1;
}

// Search over the catalog's titles, plus the search index's summaries once it has loaded.
// Title whole-word and title-prefix matches rank above other substrings, so "shor" puts
// "Shor's algorithm" above "short-wave".
export function search(atlas, index, query, limit = 8) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const words = new RegExp('(^|[^\\p{L}\\p{N}])' + escape(q) + '($|[^\\p{L}\\p{N}])', 'u');
  const terms = q.split(/\s+/);
  const summaries = {};
  for (const entry of index || []) summaries[entry.id] = entry.summary;
  const scored = [];
  for (const i of Object.values(atlas.items)) {
    const id = i.id.toLowerCase();
    let score = 0;
    if (id === q) score = 100;
    else if (id.startsWith(q)) score = 90;
    else {
      const title = match(i.title.toLowerCase(), q, words);
      if (title) score = 40 + title * 10 - i.title.toLowerCase().indexOf(q) / 1000;
      else if (atlas.field[i.field].name.toLowerCase().includes(q)) score = 30;
      else {
        const summary = match((summaries[i.id] || '').toLowerCase(), q, words);
        if (summary) score = 10 + summary;
        // Several words in any order, anywhere in the title or summary.
        else if (terms.length > 1) {
          const text = `${i.title} ${summaries[i.id] || ''}`.toLowerCase();
          if (terms.every((t) => text.includes(t))) score = 5;
        }
      }
    }
    if (score) scored.push([score, i]);
  }
  return scored
    .sort((a, b) => b[0] - a[0] || a[1].id.localeCompare(b[1].id))
    .slice(0, limit)
    .map(([, i]) => i);
}

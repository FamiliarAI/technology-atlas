import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { StatusMark } from '../glyphs.jsx';
import { SITE } from '../site.js';

// Every page names itself in the tab: "Page · Technology Atlas".
export function useTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · ${SITE}` : SITE;
  }, [title]);
}

export const number = (n) => n.toLocaleString('en-GB');

export const plural = (n, one, many = one + 's') => `${number(n)} ${n === 1 ? one : many}`;

// One word for a breakthrough's state, never colour alone.
export function progressOf(item) {
  const n = item.status.length;
  if (n && item.met === n) return { status: 'met', word: 'Met' };
  if (item.met && item.moving)
    return { status: 'in_progress', word: `${item.met} met, ${item.moving} in progress, of ${n}` };
  if (item.met) return { status: 'in_progress', word: `${item.met} of ${n} met` };
  if (item.moving) return { status: 'in_progress', word: `${item.moving} of ${n} in progress` };
  return { status: 'none', word: 'No evidence yet' };
}

// A compact row of milestone marks (hollow, half, full) and a word for the whole.
export function MilestoneMeter({ item }) {
  const { status, word } = progressOf(item);
  const n = item.status.length;
  return (
    <span className={'meter ' + status}>
      <span className="meter-marks" aria-hidden="true">
        {item.status.map((s, i) => (
          <StatusMark key={i} status={s} size={11} />
        ))}
      </span>
      <span className="meter-word">
        {word}
        <span className="visually-hidden"> ({plural(n, 'milestone')})</span>
      </span>
    </span>
  );
}

// Steps of `needs` links behind a breakthrough, across all fields. 0 when nothing is needed.
export function stepsBehind(atlas, id, seen = new Set()) {
  if (seen.has(id)) return 0;
  seen.add(id);
  const prereqs = (atlas.items[id]?.prerequisites || []).filter((p) => atlas.items[p]);
  if (!prereqs.length) return 0;
  return 1 + Math.max(...prereqs.map((p) => stepsBehind(atlas, p, new Set(seen))));
}

// A field's breakthroughs in prerequisite order: nothing appears before something it needs
// within the field; among those free to go next, ones needed by any breakthrough come first,
// then by ID, so the order is stable.
export function prerequisiteOrder(items) {
  const here = new Set(items.map((i) => i.id));
  const waiting = new Map(
    items.map((i) => [i.id, new Set(i.prerequisites.filter((p) => here.has(p)))]),
  );
  const key = (i) => [i.unlocks.length ? 0 : 1, i.id];
  const before = (a, b) => {
    const [ka, kb] = [key(a), key(b)];
    return ka[0] - kb[0] || ka[1].localeCompare(kb[1]);
  };
  const out = [];
  const left = [...items];
  while (left.length) {
    const ready = left.filter((i) => waiting.get(i.id).size === 0).sort(before);
    // A loop would be rejected upstream; if one slips through, fall back to ID order.
    const next = ready[0] || [...left].sort(before)[0];
    out.push(next);
    left.splice(left.indexOf(next), 1);
    for (const set of waiting.values()) set.delete(next.id);
  }
  return out;
}

export function BreakthroughChip({ atlas, id }) {
  const item = atlas.items[id];
  if (!item) return null;
  return (
    <Link to={'/b/' + id} className="chip" title={item.title}>
      <span className="mono">{id}</span>
      <span className="chip-title">{item.title}</span>
    </Link>
  );
}

export const Arrow = ({ size = 13 }) => (
  <svg viewBox="-8 -8 16 16" width={size} height={size} aria-hidden="true" className="arrow">
    <path d="M-5 0H5M1 -4L5 0L1 4" />
  </svg>
);

import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import Chart, { Locator } from '../Chart.jsx';
import Starfield from '../Starfield.jsx';
import { useAtlas } from '../data.jsx';
import { FieldEmblem, StarGlyph, StatusMark, ringSegments } from '../glyphs.jsx';
import { EASE } from '../motion.js';

export function useNarrow(query = '(max-width: 900px)') {
  const [narrow, setNarrow] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const m = matchMedia(query);
    const on = () => setNarrow(m.matches);
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, [query]);
  return narrow;
}

const RING = ['Ring 0 · could happen now', 'Ring 1 · needs one step first', 'Ring 2 · needs two steps first'];
const ringName = (d) => RING[d] || `Ring ${d} · needs ${d} steps first`;

function BreakthroughList({ atlas, field, onHighlight, selected }) {
  const rings = [];
  for (const item of field.items) (rings[item.depth] ||= []).push(item);
  return (
    <div className="b-list">
      {rings.map(
        (items, d) =>
          items && (
            <section key={d} aria-label={ringName(d)}>
              <h3 className="ring-head">{ringName(d)}</h3>
              <ul>
                {items.map((item) => (
                  <li key={item.id}>
                    <Link
                      to={'/b/' + item.id}
                      className={'b-row' + (selected === item.id ? ' selected' : '')}
                      onMouseEnter={() => onHighlight?.(item.id)}
                      onMouseLeave={() => onHighlight?.(null)}
                      onFocus={() => onHighlight?.(item.id)}
                      onBlur={() => onHighlight?.(null)}
                    >
                      <StarGlyph item={item} size={34} />
                      <span className="b-row-text">
                        <span className="mono">{item.id}</span>
                        <span className="b-row-title">{item.title}</span>
                        {item.prerequisites.length > 0 && (
                          <span className="b-row-needs">needs {item.prerequisites.join(', ')}</span>
                        )}
                      </span>
                      <span className="b-row-count mono" aria-label={`${item.met + item.moving} of ${item.status.length} milestones moving`}>
                        {item.met + item.moving} of {item.status.length}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ),
      )}
    </div>
  );
}

function FieldList({ atlas, onPick, filter }) {
  const q = filter.trim().toLowerCase();
  const fields = atlas.fields.filter((f) => !q || f.name.toLowerCase().includes(q) || f.id.toLowerCase().includes(q));
  return (
    <ul className="field-list">
      {fields.map((f) => (
        <li key={f.id}>
          <button type="button" className="field-row" onClick={() => onPick(f.id)}>
            <FieldEmblem field={f} atlas={atlas} size={30} />
            <span className="field-row-name">{f.name}</span>
            <span className="field-row-meta mono">
              {f.moving > 0 && <i className="moving-dot" aria-label={`${f.moving} moving`} />}
              {f.items.length}
            </span>
          </button>
        </li>
      ))}
      {!fields.length && <li className="muted empty">No constellation matches “{filter}”.</li>}
    </ul>
  );
}

function StarCard({ atlas, id, onClose }) {
  const item = atlas.items[id];
  const field = atlas.field[item.field];
  return (
    <motion.aside
      className="star-card"
      aria-labelledby="star-card-title"
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 24 }}
      transition={{ duration: 0.45, ease: EASE }}
    >
      <div className="star-card-top">
        <p className="crumb">
          <span className="mono">{item.id}</span> {field.name}
        </p>
        <button type="button" className="close" onClick={onClose} aria-label="Close summary">
          <svg viewBox="-8 -8 16 16" width="14" height="14" aria-hidden="true">
            <path d="M-4.5 -4.5L4.5 4.5M4.5 -4.5L-4.5 4.5" />
          </svg>
        </button>
      </div>
      <h2 id="star-card-title">{item.title}</h2>
      <p className="star-card-sum">{item.summary}</p>
      <ol className="mini-milestones">
        {item.milestones.map((m, n) => (
          <li key={m.id} className={m.status}>
            <StatusMark status={m.status} />
            <span className="mono">M{n + 1}</span>
            <span>{m.label || 'Milestone ' + (n + 1)}</span>
          </li>
        ))}
      </ol>
      <p className="star-card-order mono">
        {item.prerequisites.length ? `Needs ${item.prerequisites.join(', ')}` : 'Ring 0 · could happen now'}
        {item.unlocks.length > 0 && ` · unlocks ${item.unlocks.length}`}
      </p>
      <Link to={'/b/' + item.id} className="button primary small">
        Open the breakthrough
        <svg viewBox="-8 -8 16 16" width="13" height="13" aria-hidden="true">
          <path d="M-5 0H5M1 -4L5 0L1 4" />
        </svg>
      </Link>
    </motion.aside>
  );
}

function Legend() {
  const segs = ringSegments(['met', 'in_progress', 'none', 'none'], 7);
  return (
    <div className="legend" aria-hidden="true">
      <div className="legend-row">
        <svg width="22" height="22" viewBox="-11 -11 22 22">
          <circle r="2.6" fill="#FFB454" />
          {segs.map((s, n) => (
            <path key={n} d={s.d} className={'seg ' + s.status} />
          ))}
        </svg>
        <span>
          Ring segments are milestones: <b className="t-none">empty</b>, <b className="t-amber">in progress</b>,{' '}
          <b className="t-met">met</b>
        </span>
      </div>
      <div className="legend-row">
        <svg width="22" height="22" viewBox="-11 -11 22 22">
          <circle r="4" className="legend-ring" />
          <circle r="9" className="legend-ring" />
        </svg>
        <span>Rings outward: each needs something further in</span>
      </div>
      <div className="legend-row">
        <svg width="22" height="22" viewBox="-11 -11 22 22">
          <path d="M-8 6Q-2 -2 8 -6" className="legend-link" />
        </svg>
        <span>Lines: “needs” links, drawn on focus</span>
      </div>
    </div>
  );
}

function DesktopAtlas({ atlas, field, star, setParams }) {
  const [filter, setFilter] = useState('');
  const [highlight, setHighlight] = useState(null);
  const f = field && atlas.field[field];
  const pick = (id) => setParams(id ? { field: id } : {});
  const select = (id) => {
    if (!id) return setParams(field ? { field } : {});
    setParams({ field: atlas.items[id].field, star: id });
  };
  return (
    <div className="atlas-desk">
      <aside className="rail" aria-label="Constellations">
        <AnimatePresence mode="wait" initial={false}>
          {f ? (
            <motion.div
              key={f.id}
              className="rail-inner"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <button type="button" className="back" onClick={() => pick(null)}>
                <svg viewBox="-8 -8 16 16" width="12" height="12" aria-hidden="true">
                  <path d="M5 0H-5M-1 -4L-5 0L-1 4" />
                </svg>
                All constellations
              </button>
              <div className="rail-field">
                <FieldEmblem field={f} atlas={atlas} size={48} />
                <div>
                  <p className="eyebrow">
                    Constellation <span className="mono">{f.id}</span>
                  </p>
                  <h1>{f.name}</h1>
                </div>
              </div>
              <p className="rail-meta">
                {f.items.length} breakthroughs, listed in prerequisite order. {f.moving} moving
                {f.links ? `, ${f.links} order links.` : '.'}
              </p>
              <BreakthroughList atlas={atlas} field={f} onHighlight={setHighlight} selected={star} />
            </motion.div>
          ) : (
            <motion.div
              key="all"
              className="rail-inner"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <p className="eyebrow">The atlas</p>
              <h1>What comes before what?</h1>
              <p className="rail-meta">
                {atlas.totals.breakthroughs} breakthroughs in {atlas.fields.length} constellations,
                listed clockwise from the top. The centre is now; each ring outward needs something
                further in.
              </p>
              <label className="filter">
                <span className="visually-hidden">Filter constellations</span>
                <input
                  type="search"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter constellations"
                />
              </label>
              <FieldList atlas={atlas} onPick={pick} filter={filter} />
            </motion.div>
          )}
        </AnimatePresence>
      </aside>
      <div className="atlas-stage">
        <Starfield density={0.7} seed={11} />
        <Chart
          atlas={atlas}
          interactive
          intro
          focusField={field}
          selected={star}
          highlight={highlight}
          onSelect={select}
          onFocusField={pick}
          inset={{ right: star ? 400 : 0 }}
        />
        <p className="stage-crumb" aria-live="polite">
          <button type="button" onClick={() => pick(null)}>
            Sky
          </button>
          {f && (
            <>
              <span aria-hidden="true">/</span>
              <button type="button" onClick={() => setParams({ field: f.id })}>
                {f.name}
              </button>
            </>
          )}
          {star && (
            <>
              <span aria-hidden="true">/</span>
              <span className="mono">{star}</span>
            </>
          )}
        </p>
        <Legend />
        <AnimatePresence>
          {star && atlas.items[star] && <StarCard key={star} atlas={atlas} id={star} onClose={() => select(null)} />}
        </AnimatePresence>
      </div>
    </div>
  );
}

function PhoneAtlas({ atlas, field, setParams }) {
  const f = field && atlas.field[field];
  return (
    <div className="atlas-phone">
      <div className="phone-sky" aria-hidden="true">
        <Starfield density={0.8} seed={11} />
        <Chart atlas={atlas} labels={false} pad={0} />
      </div>
      <header className="phone-head">
        <p className="eyebrow">The atlas</p>
        <h1>{f ? f.name : 'What comes before what?'}</h1>
        <p className="phone-intro">
          {f
            ? `${f.items.length} breakthroughs, in prerequisite order. ${f.moving} moving.`
            : `${atlas.totals.breakthroughs} breakthroughs in ${atlas.fields.length} constellations. The centre of the sky is now; each ring outward needs something further in.`}
        </p>
      </header>
      <div className="locator-row">
        <Locator atlas={atlas} field={field} size={92} />
        <label className="field-select">
          <span className="eyebrow">Constellation</span>
          <select value={field || ''} onChange={(e) => setParams(e.target.value ? { field: e.target.value } : {})}>
            <option value="">All {atlas.fields.length}</option>
            {atlas.fields.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {f ? (
        <BreakthroughList atlas={atlas} field={f} />
      ) : (
        <FieldList atlas={atlas} onPick={(id) => setParams({ field: id })} filter="" />
      )}
    </div>
  );
}

export default function Atlas() {
  const { atlas, error } = useAtlas();
  const [params, setParams] = useSearchParams();
  const narrow = useNarrow();
  const field = params.get('field');
  const star = params.get('star');
  useEffect(() => {
    const f = field && atlas?.field[field];
    document.title = f ? `${f.name} · Technology Atlas` : 'The atlas · Technology Atlas';
  }, [atlas, field]);
  if (error) return <p className="page-state">The atlas data could not be loaded: {error}.</p>;
  if (!atlas) return <p className="page-state">Charting the sky…</p>;
  const set = (p) => setParams(p, { replace: false });
  return narrow ? (
    <PhoneAtlas atlas={atlas} field={atlas.field[field] ? field : null} setParams={set} />
  ) : (
    <DesktopAtlas
      atlas={atlas}
      field={atlas.field[field] ? field : null}
      star={atlas.items[star] ? star : null}
      setParams={set}
    />
  );
}

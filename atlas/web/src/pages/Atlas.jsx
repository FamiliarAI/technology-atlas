import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import Chart, { Locator } from '../Chart.jsx';
import Starfield from '../Starfield.jsx';
import { useAtlas, useField, warm as isWarm } from '../data.jsx';
import { FieldEmblem, StarGlyph, StatusMark, ringSegments } from '../glyphs.jsx';
import { chartCoord, REGION_GRID } from '../sky.js';
import { whenText } from './Page.jsx';
import { EASE } from '../motion.js';
import '../sky.css';

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

// Regions in the order they sit on the chart, left to right and top to bottom.
function useRegions(atlas) {
  return useMemo(() => {
    const names = [...REGION_GRID.flat(), ...atlas.regions.filter((r) => !REGION_GRID.flat().includes(r))];
    return names
      .map((name) => ({ name, fields: atlas.fields.filter((f) => f.region === name) }))
      .filter((r) => r.fields.length);
  }, [atlas]);
}

function Arrow({ back = false }) {
  return (
    <svg viewBox="-8 -8 16 16" width="12" height="12" aria-hidden="true" className="sa-arrow">
      <path d={back ? 'M5 0H-5M-1 -4L-5 0L-1 4' : 'M-5 0H5M1 -4L5 0L1 4'} />
    </svg>
  );
}

// ---------- Lists ----------

function FieldList({ atlas, regions, filter, onPick, onHover, onRegion }) {
  const q = filter.trim().toLowerCase();
  const match = (f) => !q || f.name.toLowerCase().includes(q) || f.id.toLowerCase().includes(q);
  const shown = regions.map((r) => ({ ...r, fields: r.fields.filter(match) })).filter((r) => r.fields.length);
  return (
    <div className="sa-regions">
      {shown.map((r) => (
        <section key={r.name} aria-label={r.name}>
          <h2 className="sa-region-head">
            {onRegion ? (
              <button type="button" onClick={() => onRegion(r.name)} title={`Zoom to ${r.name}`}>
                {r.name}
              </button>
            ) : (
              r.name
            )}
            <span className="mono">{r.fields.length}</span>
          </h2>
          <ul className="sa-fields">
            {r.fields.map((f) => (
              <li key={f.id}>
                <button
                  type="button"
                  className="sa-field"
                  onClick={() => onPick(f.id)}
                  onMouseEnter={() => onHover?.(f.id)}
                  onMouseLeave={() => onHover?.(null)}
                  onFocus={() => onHover?.(f.id)}
                  onBlur={() => onHover?.(null)}
                >
                  <FieldEmblem field={f} atlas={atlas} size={28} />
                  <span className="sa-field-name">{f.name}</span>
                  <span className="sa-field-meta mono">
                    {f.moving > 0 && (
                      <span className="sa-moving" title={`${f.moving} moving`}>
                        <i aria-hidden="true" />
                        <span className="visually-hidden">{f.moving} moving, </span>
                      </span>
                    )}
                    {f.items.length}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {!shown.length && <p className="sa-empty">No constellation matches “{filter}”.</p>}
    </div>
  );
}

function BreakthroughList({ atlas, field, selected, onSelect, onHighlight, links = false }) {
  const detail = useField(field.id);
  const summary = useMemo(
    () => Object.fromEntries((detail?.breakthroughs || []).map((b) => [b.id, b.summary])),
    [detail],
  );
  return (
    <div className="sa-blist">
      <ul>
        {field.items.map((item) => {
          const lit = isWarm(item);
          const inner = (
            <>
              <StarGlyph item={item} size={30} />
              <span className="sa-b-text">
                <span className="sa-b-id mono">
                  {item.id}
                  <span>{chartCoord(item, atlas.sky)?.text}</span>
                </span>
                <span className="sa-b-title">{item.title}</span>
                {summary[item.id] && <span className="sa-b-sum">{summary[item.id]}</span>}
              </span>
              <span
                className={'sa-b-count mono' + (lit ? ' warm' : '')}
                aria-label={
                  `${item.met} met and ${item.moving} in progress of ${item.status.length} milestones` +
                  (item.overall ? `; ${item.overall} toward the whole` : '')
                }
              >
                {item.complete ? 'Done' : `${item.met + item.moving}/${item.status.length}`}
                {item.overall > 0 && <span className="sa-b-whole">+{item.overall}</span>}
              </span>
            </>
          );
          const hover = {
            onMouseEnter: () => onHighlight?.(item.id),
            onMouseLeave: () => onHighlight?.(null),
            onFocus: () => onHighlight?.(item.id),
            onBlur: () => onHighlight?.(null),
          };
          return (
            <li key={item.id}>
              {links ? (
                <Link to={'/b/' + item.id} className="sa-b" {...hover}>
                  {inner}
                </Link>
              ) : (
                <button
                  type="button"
                  className={'sa-b' + (selected === item.id ? ' selected' : '')}
                  aria-pressed={selected === item.id}
                  onClick={() => onSelect(item.id)}
                  {...hover}
                >
                  {inner}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ---------- The star card ----------

function StarCard({ atlas, id, onClose }) {
  const item = atlas.items[id];
  const field = atlas.field[item.field];
  const detail = useField(item.field)?.breakthroughs.find((b) => b.id === id);
  const coord = chartCoord(item, atlas.sky);
  return (
    <motion.aside
      className="sa-card"
      aria-labelledby="sa-card-title"
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 24 }}
      transition={{ duration: 0.45, ease: EASE }}
    >
      <div className="sa-card-top">
        <p className="sa-card-crumb">
          <span className="mono">{item.id}</span>
          {field.name}
        </p>
        <button type="button" className="sa-close" onClick={onClose} aria-label="Close summary">
          <svg viewBox="-8 -8 16 16" width="14" height="14" aria-hidden="true">
            <path d="M-4.5 -4.5L4.5 4.5M4.5 -4.5L-4.5 4.5" />
          </svg>
        </button>
      </div>
      <h2 id="sa-card-title">{item.title}</h2>
      {item.complete && (
        <p className="sa-card-complete">Complete{item.completed ? ` · ${whenText(item.completed)}` : ''}</p>
      )}
      <p className="sa-card-coord mono">
        Chart {coord.text}
        {item.recent && <span className="sa-card-recent">moved in the last 30 days</span>}
      </p>
      {detail?.summary && <p className="sa-card-sum">{detail.summary}</p>}
      {item.overall > 0 && (
        <p className="sa-card-whole mono">
          {item.overall === 1 ? '1 paper' : `${item.overall} papers`} toward the whole
        </p>
      )}
      <ol className="sa-card-milestones">
        {item.status.map((status, n) => (
          <li key={n} className={status}>
            <StatusMark status={status} />
            <span className="mono">M{n + 1}</span>
            <span>{detail?.milestones[n]?.label || 'Milestone ' + (n + 1)}</span>
          </li>
        ))}
      </ol>
      <Link to={'/b/' + item.id} className="button primary small">
        Open the breakthrough
        <Arrow />
      </Link>
    </motion.aside>
  );
}

// ---------- The legend ----------

function Legend() {
  const segs = ringSegments(['met', 'in_progress', 'none', 'none'], 7);
  return (
    <div className="sa-legend" aria-label="How to read the sky" role="note">
      <p className="sa-legend-row">
        <svg width="34" height="16" viewBox="0 0 34 16" aria-hidden="true">
          <path d="M3 11L15 5L31 9" className="lg-fig" />
          <circle cx="3" cy="11" r="1.6" className="lg-dot" />
          <circle cx="15" cy="5" r="1.6" className="lg-dot" />
          <circle cx="31" cy="9" r="1.6" className="lg-dot" />
        </svg>
        <span>
          <b>Figure line</b> one field
        </span>
      </p>
      <p className="sa-legend-row">
        <svg width="34" height="16" viewBox="0 0 34 16" aria-hidden="true">
          <circle cx="4" cy="8" r="1.6" fill="#C3CDE2" opacity="0.85" />
          <circle cx="17" cy="8" r="2.4" fill="#FFB454" />
          <circle cx="30" cy="8" r="2.6" fill="#FFF1C9" />
        </svg>
        <span>
          <b>Brightness</b> <em className="t-none">not yet assessed</em> · <em className="t-amber">under way</em> ·{' '}
          <em className="t-met">all met</em>
        </span>
      </p>
      <p className="sa-legend-row">
        <svg width="34" height="18" viewBox="-17 -9 34 18" aria-hidden="true">
          <circle r="2" fill="#FFB454" />
          {segs.map((s, n) => (
            <path key={n} d={s.d} className={'sky-seg legend ' + s.status} />
          ))}
        </svg>
        <span>
          <b>Ring</b> one segment per milestone
        </span>
      </p>
      <p className="sa-legend-row">
        <svg width="34" height="18" viewBox="-17 -9 34 18" aria-hidden="true">
          <circle r="11" fill="url(#sky-halo-met)" />
          <path d="M0 -9L0 9M-9 0L9 0" className="sky-sparkle-spikes legend" />
          <circle r="4.5" className="sky-sparkle-disc" />
        </svg>
        <span>
          <b>Bright star</b> complete: its completion test met
        </span>
      </p>
    </div>
  );
}

// ---------- Desktop ----------

function DesktopAtlas({ atlas, field, region, star, setParams }) {
  const [filter, setFilter] = useState('');
  const [highlight, setHighlight] = useState(null);
  const [highlightField, setHighlightField] = useState(null);
  const regions = useRegions(atlas);
  const f = field && atlas.field[field];
  // The region in view: a field's own region when a field is open.
  const inRegion = f ? f.region : region;
  const r = inRegion && regions.find((x) => x.name === inRegion);
  const pick = (id) => {
    setHighlightField(null);
    // Stepping back from a field goes to its region, not the whole sky.
    setParams(id ? { field: id } : f ? { region: f.region } : {});
  };
  const zoomRegion = (name) => {
    setHighlightField(null);
    setParams(name ? { region: name } : {});
  };
  const select = (id) => {
    if (!id) return setParams(field ? { field } : {});
    setParams({ field: atlas.items[id].field, star: id });
  };
  useEffect(() => setHighlight(null), [field]);
  const warm = Object.values(atlas.items).filter(isWarm);
  return (
    <div className="atlas-desk sa-desk">
      <aside className="sa-rail" aria-label="Constellations">
        <AnimatePresence mode="wait" initial={false}>
          {f ? (
            <motion.div
              key={f.id}
              className="sa-rail-inner"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <button type="button" className="sa-back" onClick={() => pick(null)}>
                <Arrow back />
                {f.region}
              </button>
              <div className="sa-rail-field">
                <FieldEmblem field={f} atlas={atlas} size={46} />
                <div>
                  <p className="eyebrow">
                    {f.region} <span className="mono">{f.id}</span>
                  </p>
                  <h1>{f.name}</h1>
                </div>
              </div>
              <p className="sa-rail-meta">
                {f.items.length} breakthroughs.{' '}
                {f.moving ? `${f.moving} moving.` : 'None has moved yet.'}
              </p>
              <Link to={'/field/' + f.id} className="sa-text-link">
                The constellation’s page
                <Arrow />
              </Link>
              <BreakthroughList atlas={atlas} field={f} selected={star} onSelect={select} onHighlight={setHighlight} />
            </motion.div>
          ) : r ? (
            <motion.div
              key={'region:' + r.name}
              className="sa-rail-inner"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <button type="button" className="sa-back" onClick={() => zoomRegion(null)}>
                <Arrow back />
                All regions
              </button>
              <p className="eyebrow">Region</p>
              <h1>{r.name}</h1>
              <p className="sa-rail-meta">
                {r.fields.reduce((n, x) => n + x.items.length, 0)} breakthroughs in {r.fields.length}{' '}
                constellations. Pick one to see its breakthroughs.
              </p>
              <FieldList atlas={atlas} regions={[r]} filter="" onPick={pick} onHover={setHighlightField} />
            </motion.div>
          ) : (
            <motion.div
              key="all"
              className="sa-rail-inner"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <p className="eyebrow">The atlas</p>
              <h1>The breakthroughs, field by field</h1>
              <p className="sa-rail-meta">
                {atlas.totals.breakthroughs} breakthroughs in {atlas.fields.length} constellations, across
                eight regions of neighbouring disciplines.
              </p>
              {warm.length > 0 && (
                <div className="sa-warm">
                  <p className="sa-warm-head">Moving now</p>
                  <ul>
                    {warm.map((i) => (
                      <li key={i.id}>
                        <button type="button" onClick={() => select(i.id)}>
                          <StarGlyph item={i} size={24} />
                          <span className="mono">{i.id}</span>
                          <span className="sa-warm-title">{i.title}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <label className="sa-filter">
                <span className="visually-hidden">Filter constellations</span>
                <input
                  type="search"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter constellations"
                />
              </label>
              <FieldList
                atlas={atlas}
                regions={regions}
                filter={filter}
                onPick={pick}
                onHover={setHighlightField}
                onRegion={zoomRegion}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </aside>
      <div className="sa-stage">
        <Starfield density={0.6} seed={11} />
        <Chart
          atlas={atlas}
          interactive
          intro
          focusField={field}
          focusRegion={field ? null : region}
          onFocusRegion={zoomRegion}
          selected={star}
          highlight={highlight}
          highlightField={highlightField}
          onSelect={select}
          onFocusField={pick}
          inset={{ right: star ? 420 : 0, top: 30, bottom: 50 }}
          pad={10}
        />
        <nav className="sa-crumb" aria-label="Chart position">
          <button type="button" onClick={() => zoomRegion(null)}>
            Sky
          </button>
          {r && (
            <>
              <span aria-hidden="true">/</span>
              <button type="button" onClick={() => zoomRegion(r.name)}>
                {r.name}
              </button>
            </>
          )}
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
        </nav>
        <Legend />
        <AnimatePresence>
          {star && atlas.items[star] && <StarCard key={star} atlas={atlas} id={star} onClose={() => select(null)} />}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ---------- Phone: list first, a small locator on top ----------

function PhoneAtlas({ atlas, field, setParams }) {
  const regions = useRegions(atlas);
  const f = field && atlas.field[field];
  return (
    <div className="sa-phone">
      <header className="sa-phone-head">
        <p className="eyebrow">{f ? f.region : 'The atlas'}</p>
        <h1>{f ? f.name : 'The breakthroughs, field by field'}</h1>
        <p className="sa-phone-intro">
          {f
            ? `${f.items.length} breakthroughs. ${f.moving ? `${f.moving} moving.` : 'None has moved yet.'}`
            : `${atlas.totals.breakthroughs} breakthroughs in ${atlas.fields.length} constellations, across eight regions of neighbouring disciplines.`}
        </p>
      </header>
      <figure className="sa-phone-sky">
        <Locator atlas={atlas} field={field} width={358} />
        <figcaption className="mono">
          {f ? `${f.name} in the sky` : `The whole sky · ${atlas.fields.length} constellations`}
        </figcaption>
      </figure>
      {f ? (
        <>
          <button type="button" className="sa-back" onClick={() => setParams({})}>
            <Arrow back />
            All constellations
          </button>
          <BreakthroughList atlas={atlas} field={f} links />
        </>
      ) : (
        <FieldList atlas={atlas} regions={regions} filter="" onPick={(id) => setParams({ field: id })} />
      )}
    </div>
  );
}

export default function Atlas() {
  const { atlas, error } = useAtlas();
  const [params, setParams] = useSearchParams();
  const narrow = useNarrow();
  const field = params.get('field');
  const region = params.get('region');
  const star = params.get('star');
  useEffect(() => {
    const f = field && atlas?.field[field];
    document.title = f
      ? `${f.name} · Technology Atlas`
      : region
        ? `${region} · Technology Atlas`
        : 'The atlas · Technology Atlas';
  }, [atlas, field, region]);
  useEffect(() => {
    if (narrow) window.scrollTo(0, 0);
  }, [narrow, field]);
  if (error) return <p className="page-state">The atlas data could not be loaded: {error}.</p>;
  if (!atlas) return <p className="page-state">Charting the sky…</p>;
  const set = (p) => setParams(p, { replace: false });
  return narrow ? (
    <PhoneAtlas atlas={atlas} field={atlas.field[field] ? field : null} setParams={set} />
  ) : (
    <DesktopAtlas
      atlas={atlas}
      field={atlas.field[field] ? field : null}
      region={atlas.fields.some((x) => x.region === region) ? region : null}
      star={atlas.items[star] ? star : null}
      setParams={set}
    />
  );
}

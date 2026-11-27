import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import Starfield from '../Starfield.jsx';
import Chart, { FarPoint, Locator } from '../Chart.jsx';
import { STATUS, useAtlas, useField } from '../data.jsx';
import { StarGlyph, StatusMark, ringSegments } from '../glyphs.jsx';
import { REGION_GRID } from '../sky.js';
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

const regionAnchor = (name) => 'region-' + name.toLowerCase().replace(/[^a-z]+/g, '-');

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

// One sentence, one vocabulary: a breakthrough is complete, in progress or not yet assessed.
function tally(fields) {
  const total = fields.reduce((n, f) => n + f.items.length, 0);
  const complete = fields.reduce((n, f) => n + f.complete, 0);
  const inProgress = fields.reduce((n, f) => n + f.inProgress, 0);
  const rest = total - complete - inProgress;
  const parts = [];
  if (complete) parts.push(`${complete} complete`);
  if (inProgress) parts.push(`${inProgress} in progress`);
  if (rest) parts.push(`${rest} not yet assessed`);
  return { total, text: parts.join(', ') };
}

// A field's milestones as one bar: met, then in progress, then not yet assessed. Set in a
// column, the bars of neighbouring fields can be compared at a glance.
function MilestoneBar({ milestones }) {
  const { total, met, inProgress } = milestones;
  const w = 56;
  const a = total ? (met / total) * w : 0;
  const b = total ? (inProgress / total) * w : 0;
  const label = `${met} of ${total} milestones met, ${inProgress} in progress`;
  return (
    <svg className="sa-bar" width={w} height="6" viewBox={`0 0 ${w} 6`} role="img" aria-label={label}>
      <title>{label}</title>
      <rect width={w} height="6" className="none" />
      <rect width={a} height="6" className="met" />
      <rect x={a} width={b} height="6" className="in_progress" />
    </svg>
  );
}

function BarKey() {
  return (
    <p className="sa-key">
      <span>
        <i className="met" />
        milestones met
      </span>
      <span>
        <i className="in_progress" />
        in progress
      </span>
      <span>
        <i className="none" />
        not yet assessed
      </span>
      <span className="sa-key-n">no. of breakthroughs</span>
    </p>
  );
}

function FieldList({ regions, filter, onPick, onHover, onRegion }) {
  const q = filter.trim().toLowerCase();
  const match = (f) => !q || f.name.toLowerCase().includes(q) || f.id.toLowerCase().includes(q);
  const shown = regions.map((r) => ({ ...r, fields: r.fields.filter(match) })).filter((r) => r.fields.length);
  return (
    <div className="sa-regions">
      <BarKey />
      {shown.map((r) => (
        <section key={r.name} aria-label={r.name} id={regionAnchor(r.name)}>
          <h2 className="sa-region-head">
            {onRegion ? (
              <button type="button" onClick={() => onRegion(r.name)} title={`Zoom to ${r.name}`}>
                {r.name}
              </button>
            ) : (
              r.name
            )}
            <span className="mono" title={plural(r.fields.reduce((n, f) => n + f.items.length, 0), 'breakthrough')}>
              {r.fields.reduce((n, f) => n + f.items.length, 0)}
            </span>
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
                  <span className="sa-field-name">{f.name}</span>
                  <MilestoneBar milestones={f.milestones} />
                  <span className="sa-field-meta mono" title={plural(f.items.length, 'breakthrough')}>
                    {f.items.length}
                    <span className="visually-hidden"> breakthroughs</span>
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

// A breakthrough's count, in words that say what is counted.
function Count({ item }) {
  const n = item.status.length;
  return (
    <span
      className={'sa-b-count mono' + (item.complete ? ' complete' : '')}
      aria-label={
        (item.complete ? 'Complete; ' : '') +
        `${item.met} of ${n} milestones met, ${item.moving} in progress` +
        (item.overall ? `; ${plural(item.overall, 'paper')} toward the whole` : '')
      }
    >
      {item.complete ? 'Complete' : `${item.met}/${n} met`}
    </span>
  );
}

// `dense` is the list beside the chart: one compact row per breakthrough, whole title, no
// summary (the star's card has it). Without it (the phone) each row links to its page and
// carries the summary.
function BreakthroughList({ field, selected, highlight, onSelect, onHighlight, dense = false }) {
  const detail = useField(dense ? null : field.id);
  // A star pointed at on the chart marks its row here and brings it into view.
  const rows = useRef(null);
  useEffect(() => {
    if (!highlight) return;
    rows.current?.querySelector(`[data-id="${highlight}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [highlight]);
  const summary = useMemo(
    () => Object.fromEntries((detail?.breakthroughs || []).map((b) => [b.id, b.summary])),
    [detail],
  );
  return (
    <div className={'sa-blist' + (dense ? ' dense' : '')} ref={rows}>
      <ul>
        {field.items.map((item) => {
          const inner = (
            <>
              <StarGlyph item={item} size={dense ? 24 : 30} />
              <span className="sa-b-text">
                <span className="sa-b-id mono">{item.id}</span>
                <span className="sa-b-title">{item.title}</span>
                {summary[item.id] && <span className="sa-b-sum">{summary[item.id]}</span>}
              </span>
              <Count item={item} />
            </>
          );
          const hover = {
            onMouseEnter: () => onHighlight?.(item.id),
            onMouseLeave: () => onHighlight?.(null),
            onFocus: () => onHighlight?.(item.id),
            onBlur: () => onHighlight?.(null),
          };
          return (
            <li key={item.id} data-id={item.id}>
              {dense ? (
                <button
                  type="button"
                  className={'sa-b' + (selected === item.id ? ' selected' : '') + (highlight === item.id ? ' lit' : '')}
                  aria-pressed={selected === item.id}
                  onClick={() => onSelect(item.id)}
                  {...hover}
                >
                  {inner}
                </button>
              ) : (
                <Link to={'/b/' + item.id} className="sa-b" {...hover}>
                  {inner}
                </Link>
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
      {item.recent && (
        <p className="sa-card-coord mono">
          <span className="sa-card-recent">a milestone changed status in the last 30 days</span>
        </p>
      )}
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

// Everything the chart draws at the zoom in view, in the chart's own marks: from afar a point
// shaded by its milestones, close in a ring with one segment per milestone; the filled disc of
// a complete breakthrough; and what a line does and does not mean.
function Legend({ far }) {
  const ring = (status) => ringSegments([status, status, status, status], 6);
  const sample = (status) => (
    <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden="true">
      {far ? (
        <circle r="4.5" className={'sky-far ' + status} />
      ) : (
        ring(status).map((s, n) => <path key={n} d={s.d} className={'sky-seg legend ' + s.status} />)
      )}
    </svg>
  );
  const states = ['none', 'in_progress', 'met'];
  return (
    <div className="sa-legend" aria-label="How to read the chart" role="note">
      <p className="sa-legend-row">
        {far ? (
          <>
            <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden="true">
              <FarPoint item={{ status: [1, 2, 3, 4], met: 2, moving: 1 }} r={5.5} />
            </svg>
            <span>
              <b>Point</b> a breakthrough, shaded by its milestones
            </span>
          </>
        ) : (
          <span>
            <b>Ring</b> one segment per milestone
          </span>
        )}
        {states.map((status) => (
          <span key={status} className="sa-legend-state">
            {sample(status)}
            {STATUS[status].toLowerCase()}
          </span>
        ))}
      </p>
      <p className="sa-legend-row">
        <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden="true">
          <circle r="6" className="sky-complete" />
        </svg>
        <span>
          <b>Disc</b> complete: completion test met
        </span>
      </p>
      <p className="sa-legend-row">
        <svg width="28" height="16" viewBox="0 0 28 16" aria-hidden="true">
          <path d="M3 11L13 5L25 9" className="lg-fig" />
        </svg>
        <span>
          <b>Line</b> same field; no order or dependency
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
  const [far, setFar] = useState(true);
  const onLevel = useCallback((level) => setFar(level === 0), []);
  const fade = { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: 0.25 } };
  return (
    <div className="atlas-desk sa-desk">
      <aside className="sa-rail" aria-label="Constellations">
        <AnimatePresence mode="wait" initial={false}>
          {f ? (
            <motion.div key={f.id} className="sa-rail-inner" {...fade}>
              <p className="eyebrow">
                {f.region} <span className="mono">{f.id}</span>
              </p>
              <h1>{f.name}</h1>
              <p className="sa-rail-meta">
                {plural(f.items.length, 'breakthrough')}: {tally([f]).text}.
              </p>
              <Link to={'/field/' + f.id} className="sa-text-link">
                The constellation’s page
                <Arrow />
              </Link>
              <BreakthroughList
                field={f}
                dense
                selected={star}
                highlight={highlight}
                onSelect={select}
                onHighlight={setHighlight}
              />
            </motion.div>
          ) : r ? (
            <motion.div key={'region:' + r.name} className="sa-rail-inner" {...fade}>
              <p className="eyebrow">Region</p>
              <h1>{r.name}</h1>
              <p className="sa-rail-meta">
                {plural(tally(r.fields).total, 'breakthrough')} in {r.fields.length} constellations:{' '}
                {tally(r.fields).text}.
              </p>
              <FieldList regions={[r]} filter="" onPick={pick} onHover={setHighlightField} />
            </motion.div>
          ) : (
            <motion.div key="all" className="sa-rail-inner" {...fade}>
              <p className="eyebrow">The atlas</p>
              <h1>The breakthroughs, field by field</h1>
              <p className="sa-rail-meta">
                {atlas.totals.breakthroughs} breakthroughs in {atlas.fields.length} constellations, across
                eight regions of neighbouring disciplines: {tally(atlas.fields).text}.
              </p>
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
          onHover={setHighlight}
          onLevel={onLevel}
          onFocusField={pick}
          inset={{ right: star ? 420 : 0, top: 30, bottom: 40 }}
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
        <Legend far={far} />
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
            ? `${plural(f.items.length, 'breakthrough')}: ${tally([f]).text}.`
            : `${atlas.totals.breakthroughs} breakthroughs in ${atlas.fields.length} constellations, across eight regions of neighbouring disciplines: ${tally(atlas.fields).text}.`}
        </p>
      </header>
      <figure className="sa-phone-sky">
        <Locator
          atlas={atlas}
          field={field}
          width={358}
          names
          onPick={(hit) => {
            if (hit.field) setParams({ field: hit.field });
            else if (!f) document.getElementById(regionAnchor(hit.region))?.scrollIntoView({ behavior: 'smooth' });
            else setParams({});
          }}
        />
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
          <BreakthroughList field={f} />
        </>
      ) : (
        <FieldList regions={regions} filter="" onPick={(id) => setParams({ field: id })} />
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

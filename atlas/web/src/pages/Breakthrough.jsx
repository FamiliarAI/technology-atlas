import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { Locator } from '../Chart.jsx';
import { formatDate, loadBreakthrough, milestoneOf, useAtlas, warm } from '../data.jsx';
import { StarGlyph, StarMark, StatusLabel, ringSegments } from '../glyphs.jsx';
import Record, { Cite, Citations, Paragraphs, SourceList, safe, sourceIndex, sourceName, host } from '../Record.jsx';
import { EASE } from '../motion.js';
import * as sky from '../sky.js';
import { plural, useTitle } from './common.jsx';
import NotFound from './NotFound.jsx';

const VERDICT = { meets: 'Meets', advances: 'Advances', contradicts: 'Contradicts' };

const list = (value) => (Array.isArray(value) ? value : []);

const papers = (n) => (n === 1 ? '1 paper' : `${n} papers`);

function summaryLine(item) {
  const n = item.status.length;
  const whole = item.overall ? ` ${papers(item.overall)} toward the whole.` : '';
  if (n && item.met === n) return `All ${n} milestones met.${whole}`;
  const parts = [];
  if (item.met) parts.push(`${item.met} met`);
  if (item.moving) parts.push(`${item.moving} in progress`);
  if (!parts.length) {
    return item.overall
      ? `No milestone assessed yet.${whole}`
      : `Not yet assessed against any of its ${n} milestones.`;
  }
  return `${parts.join(', ')} of ${n} milestones.${item.met ? '' : ' None met.'}${whole}`;
}

const stateOf = (item) =>
  item.status.length && item.met === item.status.length ? 'met' : warm(item) ? 'in_progress' : 'none';

// The star at plate size: its ring numbered so each segment can be matched to a milestone.
function Plate({ item }) {
  const r = 16;
  const ring = 34;
  const segs = ringSegments(item.status, ring);
  const n = item.status.length;
  return (
    <svg viewBox="-80 -80 160 160" className="plate-star" role="img" aria-label={summaryLine(item)}>
      <circle r="62" className="plate-guide" />
      {Array.from({ length: 60 }, (_, i) => {
        const a = (i / 60) * Math.PI * 2;
        const l = i % 5 === 0 ? 5 : 2.5;
        return (
          <line
            key={i}
            x1={Math.cos(a) * 62}
            y1={Math.sin(a) * 62}
            x2={Math.cos(a) * (62 - l)}
            y2={Math.sin(a) * (62 - l)}
            className="plate-tick"
          />
        );
      })}
      <StarMark item={item} r={ring} ring={false} core={5.5} />
      {segs.map((s, i) => (
        <path key={i} d={s.d} className={'seg plate ' + s.status} />
      ))}
      {item.status.map((_, i) => {
        const a = -Math.PI / 2 + ((i + 0.5) / n) * Math.PI * 2;
        return (
          <text key={i} x={Math.cos(a) * 46} y={Math.sin(a) * 46} dy="0.35em" textAnchor="middle" className="plate-num">
            {i + 1}
          </text>
        );
      })}
    </svg>
  );
}

// One judged row: its verdict, the exact quote, and the paper it comes from. When the paper is
// also one of the record's sources, a numbered link leads to its entry.
const shortUrl = (url) => {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, '') + u.pathname.replace(/\/$/, '');
  } catch {
    return host(url);
  }
};

function Evidence({ row, label, sources }) {
  const entry = sources.byUrl.get(row.url);
  return (
    <figure className={'quote ' + row.verdict}>
      <figcaption>
        <span className={'verdict ' + row.verdict}>{VERDICT[row.verdict] || row.verdict}</span>
        {label && <span className="mono">{label}</span>}
      </figcaption>
      <blockquote>
        <p>“{row.quote}”</p>
      </blockquote>
      <p className="quote-source">
        <span>
          <a href={safe(row.url)} target="_blank" rel="noopener noreferrer">
            {entry ? sourceName(entry) : shortUrl(row.url)}
          </a>{' '}
          <Cite entry={entry} />
        </span>
        <span className="mono muted">
          {row.source_date ? `published ${formatDate(row.source_date)}` : 'date not stated'} · judged by{' '}
          {row.model || row.by} · {formatDate(row.added_at)}
        </span>
      </p>
    </figure>
  );
}

// The sections read in full, in this order, under these headings.
const READING = [
  ['significance', 'Why it matters'],
  ['current_state', 'What has been shown'],
  ['missing_breakthrough', 'What is still missing'],
];

export default function Breakthrough() {
  const { id } = useParams();
  const { atlas, error: atlasError } = useAtlas();
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);
  const still = useReducedMotion();
  const sources = useMemo(() => sourceIndex(record), [record]);
  useEffect(() => {
    let live = true;
    setRecord(null);
    setError(null);
    loadBreakthrough(id).then(
      (r) => live && setRecord(r),
      (e) => live && setError(e.message),
    );
    return () => {
      live = false;
    };
  }, [id]);
  const item = atlas?.items[id];
  useTitle(item ? `${item.title} (${item.id})` : atlas ? 'Not found' : id);

  if (atlasError) return <p className="page-state">The atlas data could not be loaded: {atlasError}.</p>;
  if (atlas && !item) {
    const held = atlas.withheld.find((w) => w.id === id.toUpperCase());
    return held ? (
      <NotFound
        eyebrow="Withheld"
        title={`${held.id} is withheld from the atlas.`}
        text={`“${held.title}” was researched, but the provider of the reviewing model declined to review it, so it is left out. The Method page explains why.`}
      />
    ) : (
      <NotFound
        eyebrow="Not in the atlas"
        title={`No breakthrough has the ID ${id}.`}
        text="Breakthrough IDs are a field’s short ID and a number, such as QUA-01. The atlas lists every one."
      />
    );
  }
  if (!item) return <p className="page-state">Finding {id}…</p>;

  const field = atlas.field[item.field];
  // The star's chart coordinate, printed when the sky provides one (sky.js chartCoord).
  const coord = typeof sky.chartCoord === 'function' ? sky.chartCoord(item, atlas.sky) : null;
  const where = coord && Number.isFinite(coord.x) && Number.isFinite(coord.y) ? coord.text : null;
  const milestones = list(record?.milestones);
  const criteria = list(record?.completion_criteria);
  // Which milestone a judged row is about, as a 1-based position; null for the whole.
  const position = (row) => {
    if (typeof row.milestone === 'string') {
      const at = milestones.findIndex((m) => m.id === row.milestone);
      if (at >= 0) return at + 1;
    }
    return milestoneOf(row);
  };
  const judged = list(record?.progress).filter((r) => r.verdict && r.quote);
  const whole = judged.filter((r) => position(r) === null);
  const concept = list(record?.concept);
  const issues = list(record?.unresolved_issues).filter((t) => typeof t === 'string' && t.trim());
  const fade = (n) =>
    still
      ? {}
      : {
          initial: { opacity: 0, y: 12 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.7, delay: 0.05 + n * 0.08, ease: EASE },
        };

  return (
    <article className="bpage">
      <div className="bpage-wash" aria-hidden="true" />
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/atlas">Atlas</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/field/${field.id}`}>{field.name}</Link>
        <span aria-hidden="true">/</span>
        <span className="mono" aria-current="page">
          {item.id}
        </span>
      </nav>
      <div className="bpage-grid">
        <div className="bpage-main">
          <motion.header className="bpage-head" {...fade(0)}>
            <p className="eyebrow bpage-id">
              <span className="mono">{item.id}</span>
            </p>
            <h1>{item.title}</h1>
            <p className="status-line">
              <span className="bpage-head-glyph">
                <StarGlyph item={item} size={40} />
              </span>
              <StatusLabel status={stateOf(item)} />
              <span>{summaryLine(item)}</span>
            </p>
          </motion.header>

          <motion.section className="concept" aria-label="Concept" {...fade(1)}>
            <p className={'lead' + (open ? ' open' : '')}>{concept[0]?.text}</p>
            <Citations urls={concept[0]?.source_urls} sources={sources} />
            {!open && concept[0] && (
              <button type="button" className="read-on" onClick={() => setOpen(true)}>
                Read the whole paragraph
              </button>
            )}
            {concept.length > 1 && (
              <details className="criterion more-concept">
                <summary>More on the concept</summary>
                <Paragraphs items={concept.slice(1)} sources={sources} />
              </details>
            )}
          </motion.section>

          <motion.section className="milestones" aria-labelledby="ms-title" {...fade(2)}>
            <h2 id="ms-title">Milestones along the way</h2>
            <p className="section-note">
              Proposed by the atlas as tests of progress. No outside body has adopted them.
            </p>
            <p className="section-lead">
              The breakthrough is reached when all {item.status.length} are met.
              {record && !judged.length && ' No paper has been judged against them yet.'}
            </p>
            <ol>
              {item.status.map((status, n) => {
                const m = milestones[n] || { id: n, label: null, status };
                const criterion = criteria[n];
                const rows = judged.filter((r) => position(r) === n + 1);
                return (
                  <li key={m.id} className={'milestone ' + m.status} id={`m${n + 1}`}>
                    <span className="milestone-num mono" aria-hidden="true">
                      {n + 1}
                    </span>
                    <div className="milestone-body">
                      <StatusLabel status={m.status} />
                      <h3>
                        <span className="visually-hidden">Milestone {n + 1}: </span>
                        {m.label || criterion?.text || `Milestone ${n + 1}`}
                      </h3>
                      {criterion && m.label && (
                        <details className="criterion">
                          <summary>The full criterion</summary>
                          <p>{criterion.text}</p>
                          <Citations urls={criterion.source_urls} sources={sources} />
                        </details>
                      )}
                      {rows.map((r, k) => (
                        <Evidence key={k} row={r} sources={sources} />
                      ))}
                    </div>
                  </li>
                );
              })}
            </ol>
          </motion.section>

          {!record && !error && <p className="muted bpage-loading">Loading the record…</p>}
          {error && <p className="muted bpage-loading">The full record could not be loaded: {error}.</p>}

          {whole.length > 0 && (
            <section className="bpage-section whole" aria-labelledby="whole-title">
              <h2 id="whole-title">Steps toward the whole</h2>
              <p className="section-note">
                Papers that move the breakthrough forward as a whole, without meeting or advancing
                one milestone.
              </p>
              {whole.map((r, k) => (
                <Evidence key={k} row={r} label="the whole" sources={sources} />
              ))}
            </section>
          )}

          {record &&
            READING.map(([key, title]) =>
              list(record[key]).length ? (
                <section key={key} className="bpage-section reading" aria-labelledby={key + '-title'}>
                  <h2 id={key + '-title'}>{title}</h2>
                  <Paragraphs items={record[key]} sources={sources} />
                </section>
              ) : null,
            )}

          {issues.length > 0 && (
            <section className="bpage-section reading" aria-labelledby="issues-title">
              <h2 id="issues-title">What is uncertain</h2>
              <ul className="issues">
                {issues.map((issue, n) => (
                  <li key={n}>{issue}</li>
                ))}
              </ul>
            </section>
          )}

          {record && (
            <section className="bpage-section sources" id="sources" aria-labelledby="sources-title">
              <h2 id="sources-title">Sources</h2>
              <p className="section-note">
                Each source supports part of this record. Citing it does not mean its authors endorse
                how the atlas defines the breakthrough or its milestones.
              </p>
              <SourceList sources={sources} />
            </section>
          )}

          {record && (
            <section className="full-record" aria-label="More of the record">
              <Record record={record} sources={sources} />
            </section>
          )}
        </div>

        <aside className="bpage-side" aria-label="In the sky">
          <div className="side-inner">
            <Plate item={item} />
            <dl className="facts">
              <div>
                <dt>ID</dt>
                <dd className="mono">{item.id}</dd>
              </div>
              <div>
                <dt>Constellation</dt>
                <dd>
                  <Link to={`/field/${field.id}`}>{field.name}</Link>
                </dd>
              </div>
              <div>
                <dt>Region</dt>
                <dd>{field.region}</dd>
              </div>
              {where && (
                <div>
                  <dt>Chart position</dt>
                  <dd className="mono">{where}</dd>
                </div>
              )}
              <div>
                <dt>Sources</dt>
                <dd>
                  {record ? (
                    <a href="#sources" onClick={(e) => {
                      e.preventDefault();
                      document.getElementById('sources')?.scrollIntoView({ block: 'start' });
                    }}>
                      {plural(sources.entries.length, 'source')}
                    </a>
                  ) : (
                    '…'
                  )}
                </dd>
              </div>
              <div>
                <dt>Last moved</dt>
                <dd>{item.moved_at ? formatDate(item.moved_at) : 'Not yet'}</dd>
              </div>
            </dl>
            <div className="side-locator">
              <Locator atlas={atlas} field={item.field} star={item.id} size={112} />
              <Link to={`/atlas?field=${field.id}&star=${item.id}`} className="text-link">
                Find it in the sky
                <svg viewBox="-8 -8 16 16" width="13" height="13" aria-hidden="true">
                  <path d="M-5 0H5M1 -4L5 0L1 4" />
                </svg>
              </Link>
            </div>
          </div>
        </aside>
      </div>
    </article>
  );
}

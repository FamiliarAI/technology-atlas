import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { Locator } from '../Chart.jsx';
import { formatDate, loadBreakthrough, useAtlas } from '../data.jsx';
import { StarGlyph, StarMark, StatusLabel, ringSegments } from '../glyphs.jsx';
import Record, { Citations, host, safe } from '../Record.jsx';
import { EASE } from '../motion.js';

const VERDICT = { meets: 'Meets', advances: 'Advances', contradicts: 'Contradicts' };

function summaryLine(item) {
  const n = item.status.length;
  if (item.met === n) return `All ${n} milestones met.`;
  const parts = [];
  if (item.met) parts.push(`${item.met} met`);
  if (item.moving) parts.push(`${item.moving} in progress`);
  if (!parts.length) return `None of ${n} milestones has evidence yet.`;
  return `${parts.join(', ')} of ${n} milestones. ${item.met ? '' : 'None met.'}`.trim();
}

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

function Related({ atlas, ids, empty }) {
  if (!ids.length) return <p className="order-empty">{empty}</p>;
  return (
    <ul className="order-list">
      {ids.map((id) => {
        const item = atlas.items[id];
        return (
          <li key={id}>
            <Link to={'/b/' + id} className="order-row">
              <StarGlyph item={item} size={34} />
              <span>
                <span className="mono">
                  {id} · {atlas.field[item.field].name}
                </span>
                <span className="order-title">{item.title}</span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export default function Breakthrough() {
  const { id } = useParams();
  const { atlas, error: atlasError } = useAtlas();
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);
  const still = useReducedMotion();
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
  useEffect(() => {
    document.title = item ? `${item.title} · ${item.id} · Technology Atlas` : `${id} · Technology Atlas`;
  }, [item, id]);

  if (atlasError) return <p className="page-state">The atlas data could not be loaded: {atlasError}.</p>;
  if (atlas && !item)
    return (
      <div className="page-state">
        <p className="eyebrow">Not in the atlas</p>
        <h1>No breakthrough has the ID {id}.</h1>
        <p>
          <Link to="/atlas">Go to the atlas</Link>
        </p>
      </div>
    );
  if (!item) return <p className="page-state">Finding {id}…</p>;

  const field = atlas.field[item.field];
  const sourceTitle = (url) => record?.sources.find((s) => s.url === url)?.title || host(url);
  const judged = record ? record.progress.filter((r) => r.criterion) : [];
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
        <Link to={`/atlas?field=${field.id}`}>{field.name}</Link>
        <span aria-hidden="true">/</span>
        <span className="mono" aria-current="page">
          {item.id}
        </span>
      </nav>
      <div className="bpage-grid">
        <div className="bpage-main">
          <motion.header className="bpage-head" {...fade(0)}>
            <h1>{item.title}</h1>
            <p className="status-line">
              <span className="bpage-head-glyph">
                <StarGlyph item={item} size={40} />
              </span>
              <StatusLabel status={item.met === item.status.length ? 'met' : item.moving || item.met ? 'in_progress' : 'none'} />
              <span>{summaryLine(item)}</span>
            </p>
          </motion.header>

          <motion.section className="concept" aria-label="Concept" {...fade(1)}>
            <p className={'lead' + (open ? ' open' : '')}>{record?.concept[0]?.text}</p>
            {!open && (
              <button type="button" className="read-on" onClick={() => setOpen(true)}>
                Read the whole paragraph
              </button>
            )}
            {record?.concept.length > 1 && (
              <details className="criterion more-concept">
                <summary>More on the concept</summary>
                {record.concept.slice(1).map((p, n) => (
                  <p key={n}>{p.text}</p>
                ))}
              </details>
            )}
          </motion.section>

          <motion.section className="milestones" aria-labelledby="ms-title" {...fade(2)}>
            <h2 id="ms-title">How we will know</h2>
            <p className="section-note">
              This counts as achieved when all {item.status.length} milestones are met.
            </p>
            <ol>
              {item.status.map((status, n) => {
                const m = record?.milestones[n] || { id: n, label: null, status };
                const criterion = record?.completion_criteria[n];
                const rows = judged.filter((r) => r.criterion === n + 1);
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
                      {rows.length > 0 && (
                        <p className="milestone-evidence">
                          <a href={`#evidence-m${n + 1}`}>
                            {rows.length === 1 ? '1 source' : `${rows.length} sources`}{' '}
                            {rows.map((r) => r.verdict).includes('meets') ? 'meet' : 'advance'}
                            {rows.length === 1 ? 's' : ''} it
                          </a>
                        </p>
                      )}
                      {criterion && m.label && (
                        <details className="criterion">
                          <summary>The full criterion</summary>
                          <p>{criterion.text}</p>
                          <Citations urls={criterion.source_urls} titleOf={sourceTitle} />
                        </details>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </motion.section>

          <section className="order" aria-labelledby="order-title">
            <h2 id="order-title">Order</h2>
            <div className="order-cols">
              <div>
                <h3 className="eyebrow">Needs first</h3>
                <Related
                  atlas={atlas}
                  ids={item.prerequisites.filter((p) => atlas.items[p])}
                  empty="Nothing. It sits on the inner ring: it could happen now."
                />
              </div>
              <div>
                <h3 className="eyebrow">Unlocks</h3>
                <Related atlas={atlas} ids={item.unlocks} empty="No breakthrough is linked as needing this one yet." />
              </div>
            </div>
          </section>

          <section className="evidence" aria-labelledby="evidence-title">
            <h2 id="evidence-title">Evidence</h2>
            {!record && !error && <p className="muted">Loading the record…</p>}
            {error && <p className="muted">The full record could not be loaded: {error}.</p>}
            {record && !judged.length && (
              <p className="section-note">
                No source has been judged against these milestones yet. Research behind the record is
                listed in the full record below.
              </p>
            )}
            {judged.map((r, n) => (
              <figure key={n} className={'quote ' + r.verdict} id={`evidence-m${r.criterion}`}>
                <figcaption>
                  <span className={'verdict ' + r.verdict}>{VERDICT[r.verdict]}</span>
                  <span className="mono">milestone {r.criterion}</span>
                </figcaption>
                <blockquote>
                  <p>“{r.quote}”</p>
                </blockquote>
                <p className="quote-source">
                  <a href={safe(r.url)} target="_blank" rel="noopener noreferrer">
                    {sourceTitle(r.url)}
                  </a>
                  <span className="mono muted">
                    {r.source_date ? `published ${formatDate(r.source_date)}` : 'date not stated'} · judged by{' '}
                    {r.model} · {formatDate(r.added_at)}
                  </span>
                </p>
              </figure>
            ))}
          </section>

          {record && (
            <section className="full-record" aria-labelledby="record-title">
              <h2 id="record-title">Full record</h2>
              <Record record={record} />
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
                  <Link to={`/atlas?field=${field.id}`}>{field.name}</Link>
                </dd>
              </div>
              <div>
                <dt>Ring</dt>
                <dd>
                  {item.depth} · {item.depth ? `needs ${item.depth} step${item.depth > 1 ? 's' : ''} first` : 'could happen now'}
                </dd>
              </div>
              <div>
                <dt>Sources</dt>
                <dd className="mono">{record ? record.sources.length : '…'}</dd>
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

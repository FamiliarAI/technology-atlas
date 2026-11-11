import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { loadBreakthrough } from './api.js';
import MilestoneBar from './MilestoneBar.jsx';
import { EASE } from './motion.js';

const STATUS = { met: 'Met', in_progress: 'In progress', none: 'No progress linked' };
const VERDICT = { meets: 'Meets', advances: 'Advances', contradicts: 'Contradicts' };
const safe = (url) => {
  try {
    const u = new URL(url);
    return ['http:', 'https:'].includes(u.protocol) ? u.href : '#';
  } catch {
    return '#';
  }
};
const PARAGRAPH_SECTIONS = [
  ['significance', 'Significance'],
  ['missing_breakthrough', 'Missing breakthrough'],
  ['current_state', 'Current state'],
  ['related_concepts', 'Related concepts'],
];

function Citations({ urls = [] }) {
  return (
    <div className="evidence-meta">
      {urls.map((url, n) => (
        <a key={n} href={safe(url)} target="_blank" rel="noopener noreferrer">
          Source {n + 1} ↗
        </a>
      ))}
    </div>
  );
}

export default function Detail({ atlas, id, narrow, onOpen, onClose }) {
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);
  const still = useReducedMotion();
  const close = useRef(null);
  const summary = atlas.items[id];
  const field = atlas.fields.find((f) => f.id === summary.field);
  useEffect(() => {
    let live = true;
    setRecord(null);
    setError(null);
    loadBreakthrough(id).then((r) => live && setRecord(r), (e) => live && setError(e.message));
    return () => { live = false; };
  }, [id]);
  useEffect(() => {
    close.current?.focus();
    const key = (e) => e.key === 'Escape' && onClose();
    addEventListener('keydown', key);
    return () => removeEventListener('keydown', key);
  }, [onClose]);
  const from = narrow ? { y: '100%' } : { x: '100%' };
  const titleOf = (url) =>
    record?.sources.find((s) => s.url === url)?.title ||
    new URL(safe(url) === '#' ? 'https://invalid' : url).hostname;
  return (
    <>
      <motion.div
        className="shade"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      />
      <motion.aside
        className={'detail' + (narrow ? ' sheet' : '')}
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
        style={{ '--c': summary.color }}
        initial={still ? { opacity: 0 } : from}
        animate={still ? { opacity: 1 } : { x: 0, y: 0 }}
        exit={still ? { opacity: 0 } : from}
        transition={{ duration: 0.45, ease: EASE }}
        drag={narrow ? 'y' : false}
        dragConstraints={{ top: 0, bottom: 0 }}
        dragElastic={{ top: 0, bottom: 0.6 }}
        onDragEnd={(_, info) => { if (info.offset.y > 120) onClose(); }}
      >
        {narrow && <div className="grip" aria-hidden="true" />}
        <div className="detail-top">
          <span className="lane-code">Breakthrough · {field.name} / {id}</span>
          <button ref={close} className="close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <h2 id="detail-title">{summary.title}</h2>
        <MilestoneBar
          status={summary.status}
          labels={record?.completion_criteria.map((c) => c.label)}
          large
        />
        {error && <p className="note">Could not load this record: {error}</p>}
        {!record && !error && <p className="note">Loading record…</p>}
        {record && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4, ease: EASE }}
          >
            {record.concept.map((paragraph, n) => (
              <div key={n}>
                <p className={n === 0 ? 'lead' : undefined}>{paragraph.text}</p>
                <Citations urls={paragraph.source_urls} />
              </div>
            ))}

            <h3>Milestones</h3>
            <ol className="milestones">
              {record.completion_criteria.map((c, n) => {
                const rows = record.progress.filter((r) => r.criterion === n + 1);
                const status = record.milestone_status[n];
                return (
                  <li key={n} className={status}>
                    <div className="milestone-head">
                      <span className="lane-code">MILESTONE {n + 1}</span>
                      <span className={'pill ' + status}>{STATUS[status]}</span>
                    </div>
                    {c.label ? (
                      <>
                        <h4 className="milestone-title">{c.label}</h4>
                        <details className="milestone-details">
                          <summary>Details</summary>
                          <p>{c.text}</p>
                        </details>
                      </>
                    ) : <p>{c.text}</p>}
                    <Citations urls={c.source_urls} />
                    {rows.map((r) => (
                      <div key={r.id} className={'evidence ' + r.verdict}>
                        <span className="pill">{VERDICT[r.verdict]}</span>
                        <blockquote>“{r.quote}”</blockquote>
                        <div className="evidence-meta">
                          <a href={safe(r.url)} target="_blank" rel="noopener noreferrer">
                    {titleOf(r.url)} ↗
                  </a>
                          {r.asset && <a href={`/api/assets/${r.asset}`}>Saved copy ↓</a>}
                          <span>{r.source_date || 'date not stated'} · judged by {r.model}</span>
                        </div>
                      </div>
                    ))}
                  </li>
                );
              })}
            </ol>

            <details className="research">
              <summary>
                Research sources not yet tied to a milestone · {
                  record.progress.filter((r) => !r.criterion).length
                }
              </summary>
              {record.progress.filter((r) => !r.criterion).map((r) => (
                <div key={r.id} className="evidence">
                  <a href={safe(r.url)} target="_blank" rel="noopener noreferrer">
                    {titleOf(r.url)} ↗
                  </a>
                  {r.asset && <a href={`/api/assets/${r.asset}`}>Saved copy ↓</a>}
                  <p>{r.quote}</p>
                </div>
              ))}
            </details>

            {atlas.related[id] && (
              <>
                <h3>Discussed together</h3>
                <div className="related">
                  {[...atlas.related[id]].filter((r) => atlas.items[r]).map((r) => (
                    <button
                      key={r}
                      style={{ '--c': atlas.items[r].color }}
                      onClick={() => onOpen(r)}
                    >
                      <span className="lane-code">{r}</span>{atlas.items[r].title}
                    </button>
                  ))}
                </div>
              </>
            )}
            <section className="full-record">
              <h3>Full record</h3>
              {PARAGRAPH_SECTIONS.map(([key, title]) => (
                <details key={key} className="research">
                  <summary>{title}</summary>
                  {record[key].map((paragraph, n) => (
                    <div key={n} className="evidence">
                      <p>{paragraph.text}</p>
                      <Citations urls={paragraph.source_urls} />
                    </div>
                  ))}
                </details>
              ))}
              <details className="research">
                <summary>Unresolved issues</summary>
                <ul>
                  {record.unresolved_issues.map((issue, n) => <li key={n}>{issue}</li>)}
                </ul>
              </details>
              <details className="research">
                <summary>Review changes</summary>
                {record.change_log.map((entry, n) => (
                  <div key={n} className="evidence">
                    <strong>{entry.change}</strong>
                    <p>{entry.reason}</p>
                  </div>
                ))}
              </details>
              <details className="research">
                <summary>Sources</summary>
                {record.sources.map((source) => (
                  <div key={source.url} className="evidence">
                    <strong>{source.title || source.url}</strong>
                    <p>{source.status.replaceAll('_', ' ')}</p>
                    <a href={safe(source.url)} target="_blank" rel="noopener noreferrer">
                      Original ↗
                    </a>
                    {source.artifacts.map((artifact) => (
                      <a key={artifact.sha256} href={`/api/assets/${artifact.sha256}`}>
                        Saved copy{artifact.format ? ` (${artifact.format})` : ''} ↓
                      </a>
                    ))}
                  </div>
                ))}
              </details>
              <details className="research">
                <summary>Provenance</summary>
                {record.documents.map((kind) => (
                  <p key={kind} className="evidence-meta">
                    <a href={`/api/documents/${encodeURIComponent(`${id}:${kind}`)}`}>
                      Download {kind.replaceAll('_', ' ')} ↓
                    </a>
                  </p>
                ))}
              </details>
            </section>
          </motion.div>
        )}
      </motion.aside>
    </>
  );
}

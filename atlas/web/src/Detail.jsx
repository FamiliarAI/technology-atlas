import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { loadBreakthrough } from './api.js';
import MilestoneBar from './MilestoneBar.jsx';
import { EASE } from './motion.js';

const STATUS = { met: 'Met', in_progress: 'In progress', none: 'No progress linked' };
const VERDICT = { meets: 'Meets', advances: 'Advances', contradicts: 'Contradicts' };
const safe = (url) => { try { const u = new URL(url); return ['http:', 'https:'].includes(u.protocol) ? u.href : '#'; } catch { return '#'; } };

export default function Detail({ atlas, id, narrow, onOpen, onClose }) {
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);
  const still = useReducedMotion();
  const close = useRef(null);
  const summary = atlas.items[id];
  const field = atlas.fields.find((f) => f.id === summary.field);

  useEffect(() => {
    let live = true;
    setRecord(null); setError(null);
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
  const titleOf = (url) => record?.sources.find((s) => s.url === url)?.title || new URL(safe(url) === '#' ? 'https://invalid' : url).hostname;

  return (
    <>
      <motion.div className="shade" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.aside className={'detail' + (narrow ? ' sheet' : '')} role="dialog" aria-modal="true" aria-labelledby="detail-title"
        style={{ '--c': summary.color }}
        initial={still ? { opacity: 0 } : from} animate={still ? { opacity: 1 } : { x: 0, y: 0 }} exit={still ? { opacity: 0 } : from}
        transition={{ duration: 0.45, ease: EASE }}
        drag={narrow ? 'y' : false} dragConstraints={{ top: 0, bottom: 0 }} dragElastic={{ top: 0, bottom: 0.6 }}
        onDragEnd={(_, info) => { if (info.offset.y > 120) onClose(); }}>
        {narrow && <div className="grip" aria-hidden="true" />}
        <div className="detail-top">
          <span className="lane-code">Breakthrough · {field.name} / {id}</span>
          <button ref={close} className="close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <h2 id="detail-title">{summary.title}</h2>
        <MilestoneBar status={summary.status} labels={record?.completion_criteria.map((c) => c.label)} large />
        {error && <p className="note">Could not load this record: {error}</p>}
        {!record && !error && <p className="note">Loading record…</p>}
        {record && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4, ease: EASE }}>
            <p className="lead">{record.concept[0].text}</p>

            <h3>Milestones</h3>
            <ol className="milestones">
              {record.completion_criteria.map((c, n) => {
                const rows = record.progress.filter((r) => r.criterion === n + 1);
                const status = record.milestone_status[n];
                return (
                  <li key={n} className={status}>
                    <div className="milestone-head"><span className="lane-code">MILESTONE {n + 1}</span><span className={'pill ' + status}>{STATUS[status]}</span></div>
                    {c.label ? (
                      <>
                        <h4 className="milestone-title">{c.label}</h4>
                        <details className="milestone-details">
                          <summary>Details</summary>
                          <p>{c.text}</p>
                        </details>
                      </>
                    ) : <p>{c.text}</p>}
                    {rows.map((r) => (
                      <div key={r.id} className={'evidence ' + r.verdict}>
                        <span className="pill">{VERDICT[r.verdict]}</span>
                        <blockquote>“{r.quote}”</blockquote>
                        <div className="evidence-meta">
                          <a href={safe(r.url)} target="_blank" rel="noopener noreferrer">{titleOf(r.url)} ↗</a>
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
              <summary>Research sources not yet tied to a milestone · {record.progress.filter((r) => !r.criterion).length}</summary>
              {record.progress.filter((r) => !r.criterion).map((r) => (
                <div key={r.id} className="evidence">
                  <a href={safe(r.url)} target="_blank" rel="noopener noreferrer">{titleOf(r.url)} ↗</a>
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
                    <button key={r} style={{ '--c': atlas.items[r].color }} onClick={() => onOpen(r)}>
                      <span className="lane-code">{r}</span>{atlas.items[r].title}
                    </button>
                  ))}
                </div>
              </>
            )}
            <a className="full" href={`/#${id}`}>Full record, sources and review history ↗</a>
          </motion.div>
        )}
      </motion.aside>
    </>
  );
}

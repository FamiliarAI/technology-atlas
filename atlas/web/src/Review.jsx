import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTitle } from './pages/common.jsx';

// The owner's review (atlas.review), shown only by the local server: /api/review answers there
// and nowhere else, so on the exported site these components draw nothing.

const STATE = {
  published: 'Published',
  hold: 'Held: needs investigation',
  merge: 'Merge',
  revise: 'Revise',
  retire: 'Retire',
};
const NOTE = { hold: 'What needs investigating?', revise: 'What should change?', retire: 'Why retire it?' };

async function api(path, body) {
  const res = await fetch('/api/review' + path, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const value = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(value.error || res.statusText);
  return value;
}

function Matches({ rows, likely, empty }) {
  if (!rows.length) return <p className="review-empty">{empty}</p>;
  return (
    <ol className="review-matches">
      {rows.map((row) => (
        <li key={row.id} className={row.score >= likely ? 'likely' : ''}>
          <span className="mono review-score">{row.score.toFixed(2)}</span>
          <Link to={`/draft/${row.id}`} className="mono">
            {row.id}
          </Link>
          <span>{row.title}</span>
          {row.state && <span className="review-chip">{STATE[row.state] || row.state}</span>}
        </li>
      ))}
    </ol>
  );
}

export function ReviewPanel({ id, local }) {
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(null); // the decision being made: {state, note, into}
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    setState(null);
    setPending(null);
    if (!local) return undefined;
    api('/' + id).then(
      (value) => live && setState(value),
      () => live && setState(false),
    );
    return () => {
      live = false;
    };
  }, [id, local]);
  if (!state) return null;
  const review = state.review || {};
  const similar = state.similar;
  const send = async (decision) => {
    setBusy(true);
    setError(null);
    try {
      const value = await api('/' + id, decision);
      if (value.warning) {
        setError(value.warning);
        setState(await api('/' + id));
      } else setState(value);
      setPending(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const close = similar.published.filter((row) => row.score >= similar.likely);
  return (
    <section className="review-panel" aria-label="Review">
      <header>
        <p className="eyebrow">Review · local only</p>
        <p className="review-current">
          {review.state ? STATE[review.state] : 'Draft'}
          {review.into && (
            <>
              {' into '}
              <Link to={`/draft/${review.into}`} className="mono">
                {review.into}
              </Link>
            </>
          )}
          {review.note && <span className="review-note"> · {review.note}</span>}
          {review.at && <span className="review-at"> · {review.at}</span>}
        </p>
        <Link to="/review" className="text-link">
          Review queue
        </Link>
      </header>
      {!state.page && <p className="review-empty">No page yet: it cannot be published.</p>}

      {pending ? (
        <div className="review-form">
          {pending.state === 'published' && (
            <>
              <p>
                Closest published pages{' '}
                {close.length ? `(${close.length} look like duplicates)` : '(none look like duplicates)'}:
              </p>
              <Matches rows={similar.published} likely={similar.likely} empty="Nothing is published yet." />
            </>
          )}
          {pending.state === 'merge' && (
            <label>
              Merge into
              <input
                className="mono"
                value={pending.into || ''}
                placeholder="ID, such as BME-01"
                onChange={(e) => setPending({ ...pending, into: e.target.value.trim().toUpperCase() })}
              />
            </label>
          )}
          {pending.state !== 'published' && pending.state !== null && (
            <label>
              {NOTE[pending.state] || 'Note (optional)'}
              <textarea value={pending.note || ''} onChange={(e) => setPending({ ...pending, note: e.target.value })} />
            </label>
          )}
          <div className="review-actions">
            <button type="button" className="primary" disabled={busy} onClick={() => send(pending)}>
              {pending.state === null ? 'Clear the decision' : `Confirm: ${STATE[pending.state]}`}
            </button>
            <button type="button" disabled={busy} onClick={() => setPending(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="review-actions">
          {state.page && review.state !== 'published' && (
            <button type="button" className="primary" onClick={() => setPending({ state: 'published' })}>
              Publish…
            </button>
          )}
          <button type="button" onClick={() => setPending({ state: 'hold' })}>
            Hold
          </button>
          <button type="button" onClick={() => setPending({ state: 'merge' })}>
            Merge…
          </button>
          <button type="button" onClick={() => setPending({ state: 'revise' })}>
            Revise
          </button>
          <button type="button" onClick={() => setPending({ state: 'retire' })}>
            Retire
          </button>
          {review.state && (
            <button type="button" onClick={() => setPending({ state: null })}>
              {review.state === 'published' ? 'Unpublish' : 'Clear'}
            </button>
          )}
        </div>
      )}
      {error && <p className="review-error">{error}</p>}
      <details className="review-similar">
        <summary>Closest across the whole atlas</summary>
        <Matches rows={similar.all} likely={similar.likely} empty="No other breakthrough shares its wording." />
      </details>
    </section>
  );
}

const FILTERS = [
  ['todo', 'To review'],
  ['judged', 'Judged, to review'],
  ['published', 'Published'],
  ['hold', 'Held'],
  ['merge', 'Merge'],
  ['revise', 'Revise'],
  ['retire', 'Retire'],
  ['all', 'All'],
];

export function ReviewQueue() {
  useTitle('Review');
  const [rows, setRows] = useState(null);
  const [filter, setFilter] = useState('judged');
  const [field, setField] = useState('');
  useEffect(() => {
    api('').then(setRows, () => setRows(false));
  }, []);
  const fields = useMemo(() => [...new Set((rows || []).map((r) => r.field))].sort(), [rows]);
  if (rows === false) {
    return <p className="page-state">The review queue is available only on the local server.</p>;
  }
  if (!rows) return <p className="page-state">Loading the queue…</p>;
  const shown = rows.filter((r) => {
    if (field && r.field !== field) return false;
    if (filter === 'todo') return !r.state && r.page;
    if (filter === 'judged') return !r.state && r.judged;
    if (filter === 'all') return true;
    return r.state === filter;
  });
  const count = (key) =>
    rows.filter((r) =>
      key === 'todo' ? !r.state && r.page : key === 'judged' ? !r.state && r.judged : key === 'all' || r.state === key,
    ).length;
  return (
    <article className="review-queue">
      <header>
        <p className="eyebrow">Local only</p>
        <h1>Review queue</h1>
        <p>
          Pages written so far, and what has been decided. “Judged” pages have had their results pass;
          the others show no results yet. Publishing shows the closest published pages first.
        </p>
      </header>
      <div className="review-filters" role="group" aria-label="Filter">
        {FILTERS.map(([key, label]) => (
          <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)}>
            {label} <span className="mono">{count(key)}</span>
          </button>
        ))}
        <select value={field} onChange={(e) => setField(e.target.value)} aria-label="Field">
          <option value="">Every field</option>
          {fields.map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
      </div>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Page</th>
            <th>Results</th>
            <th>Decision</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.id}>
              <td className="mono">
                <Link to={`/draft/${r.id}`}>{r.id}</Link>
              </td>
              <td>{r.title}</td>
              <td className="mono">{r.judged ? r.results : '–'}</td>
              <td>
                {r.state ? STATE[r.state] : 'Draft'}
                {r.into && <span className="mono"> → {r.into}</span>}
                {r.note && <span className="review-note"> · {r.note}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!shown.length && <p className="review-empty">Nothing here.</p>}
    </article>
  );
}

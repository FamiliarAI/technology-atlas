import { Link } from 'react-router-dom';
import { formatDate } from './data.jsx';

// A breakthrough's sources in context, its citations as numbered in-page links, and the parts
// of the record kept collapsed at the foot of its page.

export const safe = (url) => {
  try {
    const u = new URL(url);
    return ['http:', 'https:'].includes(u.protocol) ? u.href : '#';
  } catch {
    return '#';
  }
};

export const host = (url) => {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

// The sections whose paragraphs cite sources, with the heading each has on the page.
const PASSAGES = [
  ['concept', 'The concept'],
  ['completion_criteria', 'Milestone'],
  ['significance', 'Why it matters'],
  ['current_state', 'What has been shown'],
  ['missing_breakthrough', 'What is still missing'],
  ['related_concepts', 'Related concepts'],
];

// A passage cut at a word's end to about `max` characters.
export function trim(text, max = 240) {
  const clean = (text || '').replace(/\s+/g, ' ').trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max).replace(/\s+\S*$/, '');
  return cut.replace(/[\s,;:.–—-]+$/, '') + '…';
}

const list = (value) => (Array.isArray(value) ? value : []);

// Every source of the record, numbered in the record's own order, with each passage that cites
// it. A URL cited by a paragraph but missing from `sources` is still listed, after the rest.
export function sourceIndex(record) {
  const entries = [];
  const byUrl = new Map();
  const add = (url, title = '', status = '') => {
    if (!url || byUrl.has(url)) return byUrl.get(url);
    const n = entries.length + 1;
    const entry = { url, title: (title || '').trim(), status, n, id: `source-${n}`, cited: [] };
    entries.push(entry);
    byUrl.set(url, entry);
    return entry;
  };
  for (const s of list(record?.sources)) add(s.url, s.title, s.status);
  for (const [key, label] of PASSAGES) {
    list(record?.[key]).forEach((p, n) => {
      for (const url of new Set(list(p?.source_urls))) {
        const entry = add(url);
        entry.cited.push({
          label: key === 'completion_criteria' ? `${label} ${n + 1}` : label,
          text: trim(p.text),
        });
      }
    });
  }
  return { entries, byUrl };
}

export const sourceName = (entry) => entry.title || host(entry.url);

// Opens every collapsed section that holds an element, so a link into it lands on something seen.
export function reveal(el) {
  for (let d = el?.closest('details'); d; d = d.parentElement?.closest('details')) d.open = true;
}

// Moves the view and keyboard focus to an in-page entry, and marks it for a moment.
export function jumpTo(id) {
  const el = document.getElementById(id);
  if (!el) return;
  reveal(el);
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  el.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'center' });
  el.focus({ preventScroll: true });
  el.classList.remove('flash');
  void el.offsetWidth;
  el.classList.add('flash');
  clearTimeout(el.flashTimer);
  el.flashTimer = setTimeout(() => el.classList.remove('flash'), 2000);
}

// One numbered link to a source entry on this page.
export function Cite({ entry }) {
  if (!entry) return null;
  return (
    <a
      href={'#' + entry.id}
      className="cite"
      aria-label={`Source ${entry.n}: ${sourceName(entry)}`}
      onClick={(e) => {
        e.preventDefault();
        jumpTo(entry.id);
      }}
    >
      [{entry.n}]
    </a>
  );
}

// The citations under a paragraph: small numbered links to the Sources section.
export function Citations({ urls, sources }) {
  const entries = [...new Set(list(urls))].map((u) => sources?.byUrl.get(u))
    .filter(Boolean)
    .sort((a, b) => a.n - b.n);
  if (!entries.length) return null;
  return (
    <p className="citations">
      <span className="visually-hidden">Sources: </span>
      {entries.map((entry) => (
        <Cite key={entry.id} entry={entry} />
      ))}
    </p>
  );
}

// Paragraphs of one section, each with its citations.
export function Paragraphs({ items, sources }) {
  return list(items).map((paragraph, n) => (
    <div key={n} className="record-para">
      <p>{paragraph.text}</p>
      <Citations urls={paragraph.source_urls} sources={sources} />
    </div>
  ));
}

const VERDICT = { meets: 'Meets', advances: 'Advances', contradicts: 'Contradicts' };

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

export function Evidence({ row, label, sources }) {
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

// Passages shown at once under a source; the rest are one click away.
const SHOWN = 3;

function Passages({ items }) {
  return (
    <ul>
      {items.map((c, n) => (
        <li key={n}>
          <span className="source-section">{c.label}</span>
          <span className="source-passage">{c.text}</span>
        </li>
      ))}
    </ul>
  );
}

const STATUS = { saved: 'copy saved', not_captured: 'no copy saved' };

// The Sources section: one entry per source, what it is and what this record cites it for.
export function SourceList({ sources, heading: Heading = 'h3' }) {
  if (!sources.entries.length) return <p className="section-note">This record cites no source.</p>;
  return (
    <ol className="source-list">
      {sources.entries.map((entry) => (
        <li key={entry.id} id={entry.id} className="source-entry" tabIndex={-1}>
          <span className="source-num mono" aria-hidden="true">
            {entry.n}
          </span>
          <div className="source-body">
            <Heading>
              <span className="visually-hidden">Source {entry.n}: </span>
              {sourceName(entry)}
            </Heading>
            <p className="source-meta mono muted">
              {host(entry.url)}
              {STATUS[entry.status] && ` · ${STATUS[entry.status]}`}
            </p>
            <p className="source-open">
              <a href={safe(entry.url)} target="_blank" rel="noopener noreferrer" className="text-link">
                Open the original
                <svg viewBox="-8 -8 16 16" width="11" height="11" aria-hidden="true">
                  <path d="M-4 4L4 -4M-2 -4H4V2" />
                </svg>
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
            </p>
            {entry.cited.length > 0 && (
              <div className="source-cited">
                <p className="eyebrow">Cited for:</p>
                <Passages items={entry.cited.length > SHOWN + 1 ? entry.cited.slice(0, SHOWN) : entry.cited} />
                {entry.cited.length > SHOWN + 1 && (
                  <details className="criterion source-more">
                    <summary>
                      {entry.cited.length - SHOWN} more{' '}
                      {entry.cited.length - SHOWN === 1 ? 'passage' : 'passages'}
                    </summary>
                    <Passages items={entry.cited.slice(SHOWN)} />
                  </details>
                )}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Section({ title, count, children }) {
  return (
    <details className="record-section">
      <summary>
        <span>{title}</span>
        {count !== undefined && <span className="mono muted">{count}</span>}
        <svg viewBox="-8 -8 16 16" width="12" height="12" aria-hidden="true">
          <path d="M-4 -2L0 2L4 -2" />
        </svg>
      </summary>
      <div className="record-body">{children}</div>
    </details>
  );
}

const STAGES = [
  ['research', 'Research'],
  ['reconcile', 'Reconcile'],
  ['format', 'Format'],
  ['review', 'Review'],
  ['rewrite', 'Rewrite'],
];

// The parts of the record a reader rarely needs: collapsed, at the foot of the page.
export default function Record({ record, sources }) {
  const related = list(record.related_concepts);
  const changes = list(record.change_log);
  const models = record.models && typeof record.models === 'object' ? record.models : {};
  const stages = STAGES.filter(([key]) => models[key]);
  return (
    <div className="record">
      {related.length > 0 && (
        <Section title="Related concepts" count={related.length}>
          <Paragraphs items={related} sources={sources} />
        </Section>
      )}
      {changes.length > 0 && (
        <Section title="Changes made in review" count={changes.length}>
          {changes.map((entry, n) => (
            <div key={n} className="record-para">
              <p>
                <strong>{entry.change}</strong>
              </p>
              <p className="muted">{entry.reason}</p>
            </div>
          ))}
        </Section>
      )}
      {stages.length > 0 && (
        <Section title="How this record was made">
          <p className="record-para">
            Each stage of the research pipeline, and the model that did it. The{' '}
            <Link to="/about#research">Method page</Link> describes the stages.
          </p>
          <dl className="record-models">
            {stages.map(([key, name]) => (
              <div key={key}>
                <dt>{name}</dt>
                <dd className="mono">{models[key]}</dd>
              </div>
            ))}
          </dl>
        </Section>
      )}
    </div>
  );
}

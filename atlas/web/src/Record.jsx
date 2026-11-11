// The full record, in collapsed sections (carried over from the first tree's detail panel).

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

const PARAGRAPH_SECTIONS = [
  ['significance', 'Significance'],
  ['missing_breakthrough', 'What is missing'],
  ['current_state', 'Current state'],
  ['related_concepts', 'Related concepts'],
];

export function Citations({ urls = [], titleOf }) {
  if (!urls.length) return null;
  return (
    <p className="citations">
      {urls.map((url, n) => (
        <a key={n} href={safe(url)} target="_blank" rel="noopener noreferrer">
          {titleOf ? titleOf(url) : `Source ${n + 1}`}
        </a>
      ))}
    </p>
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

export default function Record({ id, record }) {
  const research = record.progress.filter((r) => !r.criterion);
  return (
    <div className="record">
      {PARAGRAPH_SECTIONS.map(([key, title]) => (
        <Section key={key} title={title} count={record[key].length}>
          {record[key].map((paragraph, n) => (
            <div key={n} className="record-para">
              <p>{paragraph.text}</p>
              <Citations urls={paragraph.source_urls} />
            </div>
          ))}
        </Section>
      ))}
      <Section title="Research sources not yet tied to a milestone" count={research.length}>
        {research.map((r) => (
          <div key={r.id} className="record-para">
            <p>
              <a href={safe(r.url)} target="_blank" rel="noopener noreferrer">
                {record.sources.find((s) => s.url === r.url)?.title || host(r.url)}
              </a>
              {r.asset && (
                <>
                  {' · '}
                  <a href={`/api/assets/${r.asset}`}>saved copy</a>
                </>
              )}
            </p>
            <p className="muted">{r.quote}</p>
          </div>
        ))}
      </Section>
      <Section title="Unresolved issues" count={record.unresolved_issues.length}>
        <ul>
          {record.unresolved_issues.map((issue, n) => (
            <li key={n}>{issue}</li>
          ))}
        </ul>
      </Section>
      <Section title="Review changes" count={record.change_log.length}>
        {record.change_log.map((entry, n) => (
          <div key={n} className="record-para">
            <p>
              <strong>{entry.change}</strong>
            </p>
            <p className="muted">{entry.reason}</p>
          </div>
        ))}
      </Section>
      <Section title="Sources" count={record.sources.length}>
        {record.sources.map((source) => (
          <div key={source.url} className="record-para source">
            <p>
              <a href={safe(source.url)} target="_blank" rel="noopener noreferrer">
                {source.title || source.url}
              </a>
            </p>
            <p className="mono muted">
              {host(source.url)} · {source.status.replaceAll('_', ' ')}
              {source.artifacts.map((artifact) => (
                <span key={artifact.sha256}>
                  {' · '}
                  <a href={`/api/assets/${artifact.sha256}`}>
                    saved copy{artifact.format ? ` (${artifact.format})` : ''}
                  </a>
                </span>
              ))}
            </p>
          </div>
        ))}
      </Section>
      <Section title="Provenance" count={record.documents.length}>
        {record.documents.map((kind) => (
          <p key={kind}>
            <a href={`/api/documents/${encodeURIComponent(`${id}:${kind}`)}`}>
              Download {kind.replaceAll('_', ' ')}
            </a>
          </p>
        ))}
      </Section>
    </div>
  );
}

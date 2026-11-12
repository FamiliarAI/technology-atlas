import { motion } from 'framer-motion';
import { StatusLabel } from '../glyphs.jsx';
import Record, { Citations, Evidence, Paragraphs, SourceList, host, safe, sourceName } from '../Record.jsx';
import { plural } from './common.jsx';

// A page shows this many sources in full; the rest fold under one line.
const LEAD_SOURCES = 4;

// The reader's version of a breakthrough (the record's `brief`): a few plain questions, the
// sources that answer them, and the milestones in plain words. The research record it was
// written from follows, collapsed. Any part may be missing; a missing part shows nothing.

const list = (value) => (Array.isArray(value) ? value : []);

// Paragraphs and items are strings; a {text} object is read the same way.
const texts = (value) =>
  list(value)
    .map((t) => (typeof t === 'string' ? t : t?.text))
    .filter((t) => typeof t === 'string' && t.trim());

const said = (value) => (typeof value === 'string' && value.trim() ? value.trim() : null);

function Question({ id, title, note, fade, children }) {
  return (
    <motion.section className="bpage-section reading brief-q" aria-labelledby={id} {...fade}>
      <h2 id={id}>{title}</h2>
      {note && <p className="section-note">{note}</p>}
      {children}
    </motion.section>
  );
}

function Prose({ items }) {
  return items.map((text, n) => (
    <div key={n} className="record-para">
      <p>{text}</p>
    </div>
  ));
}

function Items({ items }) {
  return (
    <ul className="issues">
      {items.map((text, n) => (
        <li key={n}>{text}</li>
      ))}
    </ul>
  );
}

// One source of the brief: who, then what they showed; what the atlas takes from it and what
// it does not.
function BriefSource({ source, entry }) {
  const who = said(source.who);
  const title = entry ? said(entry.title) : null;
  const showed = said(source.showed);
  const quote = said(source.quote);
  const citedFor = said(source.cited_for);
  const notEstablished = said(source.not_established);
  const url = said(source.url);
  const checked = source.checked === true;
  const note = checked
    ? quote
      ? 'quote checked against the saved copy'
      : 'saved copy kept'
    : 'no saved copy to check';
  return (
    <li className="brief-source">
      <h3 className="brief-who">{who || title || (url ? host(url) : 'A source')}</h3>
      {title && who && <p className="brief-paper">{title}</p>}
      {showed && <p className="brief-showed">{showed}</p>}
      {quote && (
        <blockquote className="brief-quote">
          <p>“{quote}”</p>
        </blockquote>
      )}
      {(citedFor || notEstablished) && (
        <dl className="brief-why">
          {citedFor && (
            <div>
              <dt className="source-section">Why the atlas cites it</dt>
              <dd className="source-passage">{citedFor}</dd>
            </div>
          )}
          {notEstablished && (
            <div>
              <dt className="source-section">What it does not establish</dt>
              <dd className="source-passage">{notEstablished}</dd>
            </div>
          )}
        </dl>
      )}
      <p className="brief-source-foot">
        {url && (
          <a href={safe(url)} target="_blank" rel="noopener noreferrer" className="text-link">
            Open the original
            <svg viewBox="-8 -8 16 16" width="11" height="11" aria-hidden="true">
              <path d="M-4 4L4 -4M-2 -4H4V2" />
            </svg>
            <span className="visually-hidden">
              {' '}
              ({entry ? sourceName(entry) : host(url)}, opens in a new tab)
            </span>
          </a>
        )}
        <span className="mono muted">{note}</span>
      </p>
    </li>
  );
}

// The record's own reading sections, as they were on the page before the brief.
const READING = [
  ['concept', 'The concept'],
  ['significance', 'Why it matters'],
  ['current_state', 'What has been shown'],
  ['missing_breakthrough', 'What is still missing'],
];

function ResearchRecord({ record, sources }) {
  const issues = list(record.unresolved_issues).filter((t) => typeof t === 'string' && t.trim());
  return (
    <details className="bpage-record">
      <summary>
        <span>The research record</span>
        <span className="muted">
          What this page was written from: the full text, {plural(sources.entries.length, 'source')}{' '}
          and how it was reviewed.
        </span>
      </summary>
      <div className="bpage-record-body">
        {READING.map(([key, title]) =>
          list(record[key]).length ? (
            <section key={key} className="bpage-section reading" aria-labelledby={'rr-' + key}>
              <h3 id={'rr-' + key}>{title}</h3>
              <Paragraphs items={record[key]} sources={sources} />
            </section>
          ) : null,
        )}
        {issues.length > 0 && (
          <section className="bpage-section reading" aria-labelledby="rr-issues">
            <h3 id="rr-issues">What is uncertain</h3>
            <Items items={issues} />
          </section>
        )}
        <section className="bpage-section sources" id="sources" aria-labelledby="sources-title">
          <h3 id="sources-title">Sources</h3>
          <p className="section-note">
            Each source supports part of this record. Citing it does not mean its authors endorse how
            the atlas defines the breakthrough or its milestones.
          </p>
          <SourceList sources={sources} heading="h4" />
        </section>
        <Record record={record} sources={sources} />
      </div>
    </details>
  );
}

export default function BriefBody({ brief, record, item, sources, position, judged, fade }) {
  const possible = texts(brief.possible);
  const why = texts(brief.why);
  const shown = texts(brief.shown);
  const missing = texts(brief.missing);
  const uncertain = texts(brief.uncertain);
  const briefSources = list(brief.sources).filter((s) => s && typeof s === 'object');
  const milestones = list(record.milestones);
  const criteria = list(record.completion_criteria);
  const plain = new Map(list(brief.milestones).filter((m) => m?.id).map((m) => [m.id, m]));
  const whole = judged.filter((r) => position(r) === null);
  return (
    <>
      {possible.length > 0 && (
        <Question id="possible-title" title="What becomes possible?" fade={fade(1)}>
          <div className="brief-lead">
            <Prose items={possible} />
          </div>
        </Question>
      )}

      {why.length > 0 && (
        <Question id="why-title" title="Why would it matter?" fade={fade(2)}>
          <Prose items={why} />
        </Question>
      )}

      {briefSources.length > 0 && (
        <Question
          id="who-title"
          title="Who has shown what?"
          note="A source supports part of the case. Its authors have not endorsed how the atlas defines this breakthrough."
          fade={fade(3)}
        >
          <ol className="brief-sources">
            {briefSources.slice(0, LEAD_SOURCES).map((source, n) => (
              <BriefSource key={n} source={source} entry={sources.byUrl.get(source.url)} />
            ))}
          </ol>
          {briefSources.length > LEAD_SOURCES && (
            <details className="criterion brief-more">
              <summary>
                {briefSources.length - LEAD_SOURCES} more{' '}
                {briefSources.length - LEAD_SOURCES === 1 ? 'source' : 'sources'}
              </summary>
              <ol className="brief-sources">
                {briefSources.slice(LEAD_SOURCES).map((source, n) => (
                  <BriefSource key={n} source={source} entry={sources.byUrl.get(source.url)} />
                ))}
              </ol>
            </details>
          )}
        </Question>
      )}

      {shown.length > 0 && (
        <Question id="shown-title" title="What has been demonstrated?" fade={{}}>
          <Prose items={shown} />
        </Question>
      )}

      {missing.length > 0 && (
        <Question id="missing-title" title="What is still missing?" fade={{}}>
          <Items items={missing} />
        </Question>
      )}

      {item.status.length > 0 && (
        <section className="bpage-section milestones brief-q" aria-labelledby="ms-title">
          <h2 id="ms-title">What result would convince us?</h2>
          <p className="section-note">
            The atlas proposed these tests. No outside body has adopted them.
          </p>
          <ol>
            {item.status.map((status, n) => {
              const m = milestones[n] || { id: `m${n + 1}`, label: null, status };
              const words = plain.get(m.id) || {};
              const label = said(words.label) || m.label;
              const explanation = said(words.explanation);
              const criterion = criteria[n];
              const rows = judged.filter((r) => position(r) === n + 1);
              return (
                <li key={m.id} className={'milestone ' + (m.status || status)} id={`m${n + 1}`}>
                  <span className="milestone-num mono" aria-hidden="true">
                    {n + 1}
                  </span>
                  <div className="milestone-body">
                    <StatusLabel status={m.status || status} />
                    <h3>
                      <span className="visually-hidden">Milestone {n + 1}: </span>
                      {label || criterion?.text || `Milestone ${n + 1}`}
                    </h3>
                    {explanation && <p className="milestone-explain">{explanation}</p>}
                    {criterion && (label || explanation) && (
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
          {whole.length > 0 && (
            <div className="brief-whole">
              <h3>Steps toward the whole</h3>
              <p className="section-note">
                Papers that move the breakthrough forward as a whole, without meeting or advancing
                one milestone.
              </p>
              {whole.map((r, k) => (
                <Evidence key={k} row={r} label="the whole" sources={sources} />
              ))}
            </div>
          )}
        </section>
      )}

      {uncertain.length > 0 && (
        <Question id="uncertain-title" title="What is still uncertain?" fade={{}}>
          <Items items={uncertain} />
        </Question>
      )}

      <ResearchRecord record={record} sources={sources} />
    </>
  );
}

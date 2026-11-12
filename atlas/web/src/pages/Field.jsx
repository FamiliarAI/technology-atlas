import { Link, useParams } from 'react-router-dom';
import { Locator } from '../Chart.jsx';
import { useAtlas, useField } from '../data.jsx';
import { FieldEmblem } from '../glyphs.jsx';
import NotFound from './NotFound.jsx';
import { Arrow, MilestoneMeter, number, plural, useTitle } from './common.jsx';

// The first sentence of a summary, as the row's one line; the page has the rest.
function firstSentence(text) {
  if (!text) return '';
  const m = text.match(/^.+?[.!?](?=\s+[A-Z“"(]|$)/s);
  return (m ? m[0] : text).trim();
}

// Is there any scope text at all? An empty string, list or object has none.
function hasScope(value) {
  if (!value) return false;
  if (typeof value === 'string') return value.trim().length > 0;
  if (Array.isArray(value)) return value.some(hasScope);
  if (typeof value === 'object') return Object.values(value).some(hasScope);
  return true;
}

// The scope as stored is the brief the researcher was given. It is usually one string, but
// render a list or an object of lists without guessing at its meaning.
function Scope({ value }) {
  if (!hasScope(value)) return null;
  if (typeof value === 'string') return <p className="field-scope-text">{value.trim()}</p>;
  if (Array.isArray(value))
    return (
      <ul className="field-scope-list">
        {value.map((v, n) => (
          <li key={n}>{typeof v === 'string' ? v : JSON.stringify(v)}</li>
        ))}
      </ul>
    );
  return (
    <dl className="field-scope-dl">
      {Object.entries(value).map(([k, v]) => (
        <div key={k}>
          <dt>{k.replaceAll('_', ' ')}</dt>
          <dd>
            <Scope value={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Row({ item, summary }) {
  return (
    <li className="frow" id={item.id}>
      <div className="frow-id mono">{item.id}</div>
      <div className="frow-body">
        <h3>
          <Link to={'/b/' + item.id}>{item.title}</Link>
        </h3>
        {summary && <p className="frow-summary">{firstSentence(summary)}</p>}
        <div className="frow-meta">
          <MilestoneMeter item={item} />
          <span className="frow-count mono muted" aria-hidden="true">
            {plural(item.status.length, 'milestone')}
          </span>
        </div>
      </div>
    </li>
  );
}

export default function Field() {
  const { field: raw } = useParams();
  const id = (raw || '').toUpperCase();
  const { atlas, error } = useAtlas();
  const field = atlas?.field[id];
  const data = useField(field ? id : null);
  useTitle(field ? `${field.name} (${field.id})` : atlas ? 'Not found' : id);

  if (error) return <p className="page-state">The atlas data could not be loaded: {error}.</p>;
  if (!atlas) return <p className="page-state">Finding {id}…</p>;
  if (!field)
    return (
      <NotFound
        eyebrow="No such constellation"
        title={`No field has the ID ${raw}.`}
        text="Every field of research in the atlas has a short ID, such as QUA for Quantum Computing. The atlas lists them all."
      />
    );

  const items = [...field.items].sort((a, b) => a.id.localeCompare(b.id));
  const summaries = Object.fromEntries((data?.breakthroughs || []).map((b) => [b.id, b.summary]));
  const milestones = items.reduce((n, i) => n + i.status.length, 0);
  const met = items.reduce((n, i) => n + i.met, 0);
  const moving = items.reduce((n, i) => n + i.moving, 0);
  const neighbours = atlas.fields.filter((f) => f.region === field.region && f.id !== field.id);

  return (
    <article className="page fpage">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/atlas">Atlas</Link>
        <span aria-hidden="true">/</span>
        <span>{field.region}</span>
        <span aria-hidden="true">/</span>
        <span className="mono" aria-current="page">
          {field.id}
        </span>
      </nav>

      <div className="fpage-head">
        <header className="fpage-title">
          <p className="eyebrow">Constellation</p>
          <h1>{field.name}</h1>
          <dl className="fpage-figures" aria-label={`${field.name} in numbers`}>
            <div>
              <dt>Breakthroughs</dt>
              <dd>{items.length}</dd>
            </div>
            <div>
              <dt>Milestones</dt>
              <dd>{number(milestones)}</dd>
            </div>
            <div>
              <dt>In progress</dt>
              <dd className={moving ? 'amber' : ''}>{moving}</dd>
            </div>
            <div>
              <dt>Met</dt>
              <dd>{met}</dd>
            </div>
          </dl>
        </header>
        <aside className="fpage-sky" aria-label="In the sky">
          <div className="fpage-marks">
            <FieldEmblem field={field} atlas={atlas} size={72} />
            <Locator atlas={atlas} field={field.id} size={132} />
          </div>
          <Link to={`/atlas?field=${field.id}`} className="button quiet small">
            Open in the atlas
            <Arrow />
          </Link>
        </aside>
      </div>

      <section className="fpage-list" aria-labelledby="list-title">
        <h2 id="list-title">Its breakthroughs</h2>
        <p className="section-note">
          Each is a breakthrough worth working towards, listed by ID. The marks show how many of
          its milestones the atlas has assessed as in progress or met.
        </p>
        {data?.withheld?.length > 0 && (
          <p className="fpage-withheld">
            {data.withheld.length === 1 ? 'One concept' : `${data.withheld.length} concepts`} in
            this field {data.withheld.length === 1 ? 'is' : 'are'} withheld:{' '}
            {data.withheld.map((w, n) => (
              <span key={w.id}>
                {n > 0 && '; '}
                <span className="mono">{w.id}</span> {w.title}
              </span>
            ))}
            . The provider of the reviewing model declined to review{' '}
            {data.withheld.length === 1 ? 'it' : 'them'}, so{' '}
            {data.withheld.length === 1 ? 'it is' : 'they are'} not listed here.{' '}
            <Link to="/about#limits">Why</Link>
          </p>
        )}
        <ol className="frows">
          {items.map((item) => (
            <Row key={item.id} item={item} summary={summaries[item.id]} />
          ))}
        </ol>
      </section>

      {hasScope(data?.boundaries) && (
        <details className="fpage-brief">
          <summary>
            <span>Research brief</span>
            <span className="muted">the scope the research model was given for this field</span>
          </summary>
          <Scope value={data.boundaries} />
        </details>
      )}

      {neighbours.length > 0 && (
        <nav className="fpage-neighbours" aria-labelledby="near-title">
          <h2 id="near-title" className="eyebrow">
            Also in {field.region}
          </h2>
          <ul>
            {neighbours.map((f) => (
              <li key={f.id}>
                <Link to={'/field/' + f.id}>
                  <FieldEmblem field={f} atlas={atlas} size={26} />
                  <span>{f.name}</span>
                  <span className="mono muted">{f.items.length}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </article>
  );
}

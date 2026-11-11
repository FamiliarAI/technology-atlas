import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { loadClaims, useAtlas } from '../data.jsx';
import { StatusMark } from '../glyphs.jsx';
import { Arrow, number, plural, useTitle } from './common.jsx';

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
const words = (n) => WORDS[n] || String(n);

const done = (item) => item.status.length > 0 && item.met === item.status.length;

// "B needs A first" is falsified once B is achieved while A is not.
export const claimState = (a, b) => (done(b) && !done(a) ? 'falsified' : 'standing');

export function ClaimStatus({ state }) {
  return (
    <span className={'claim-status ' + state}>
      {state === 'falsified' ? (
        <svg width="14" height="14" viewBox="-8 -8 16 16" aria-hidden="true">
          <path d="M-5 -5L5 5M5 -5L-5 5" />
        </svg>
      ) : (
        <StatusMark status="none" />
      )}
      {state === 'falsified' ? 'Falsified' : 'Standing'}
    </span>
  );
}

// One file, data/claims.json, carries every link's reason; the sentences come from the
// catalog, so they show at once and the reasons fill in when the file arrives.
function useReasons() {
  const [reasons, setReasons] = useState(null);
  useEffect(() => {
    let live = true;
    loadClaims().then(
      (rows) => {
        const map = {};
        for (const row of rows) (map[row.id] ||= {})[row.needs] = row.reason;
        if (live) setReasons(map);
      },
      () => live && setReasons({}),
    );
    return () => {
      live = false;
    };
  }, []);
  return reasons;
}

function Claim({ atlas, link, reason }) {
  const a = atlas.items[link.from];
  const b = atlas.items[link.to];
  const across = a.field !== b.field;
  return (
    <li className="claim">
      <div className="claim-text">
        <p className="claim-sentence">
          <Link to={'/b/' + b.id}>{b.title}</Link> <span className="mono muted">{b.id}</span>{' '}
          <em>needs</em> <Link to={'/b/' + a.id}>{a.title}</Link>{' '}
          <span className="mono muted">{a.id}</span> <em>first.</em>
        </p>
        {across && (
          <p className="claim-across">
            Across fields: the prerequisite is in{' '}
            <Link to={'/field/' + a.field}>{atlas.field[a.field].name}</Link>.
          </p>
        )}
        {reason === undefined ? (
          <p className="claim-reason pending">Loading the stated reason…</p>
        ) : reason ? (
          <p className="claim-reason">
            <span className="visually-hidden">Stated reason: </span>
            {reason}
          </p>
        ) : null}
      </div>
      <ClaimStatus state={claimState(a, b)} />
    </li>
  );
}

export default function Claims() {
  const { atlas, error } = useAtlas();
  const [region, setRegion] = useState('');
  useTitle('The claims');
  const reasons = useReasons();
  if (error) return <p className="page-state">The atlas data could not be loaded: {error}.</p>;
  if (!atlas) return <p className="page-state">Gathering the claims…</p>;

  const regionOf = (link) => atlas.field[atlas.items[link.to].field].region;
  const counts = {};
  for (const l of atlas.links) counts[regionOf(l)] = (counts[regionOf(l)] || 0) + 1;
  const shown = atlas.links.filter((l) => !region || regionOf(l) === region);
  const groups = [];
  for (const field of [...atlas.fields].sort(
    (x, y) =>
      atlas.regions.indexOf(x.region) - atlas.regions.indexOf(y.region) ||
      x.name.localeCompare(y.name),
  )) {
    const links = shown
      .filter((l) => atlas.items[l.to].field === field.id)
      .sort((x, y) => x.to.localeCompare(y.to) || x.from.localeCompare(y.from));
    if (links.length) groups.push({ field, links });
  }
  const falsified = atlas.links.filter(
    (l) => claimState(atlas.items[l.from], atlas.items[l.to]) === 'falsified',
  ).length;
  const t = atlas.totals;
  const sizes = Object.values(atlas.items).map((i) => i.status.length);

  return (
    <article className="page claims-page">
      <header className="page-head">
        <p className="eyebrow">The claims</p>
        <h1>What exactly are we predicting?</h1>
        <p className="lead">
          The atlas makes two kinds of claim, and both can be proven wrong. A recognition claim says
          a breakthrough counts as achieved when its milestones are met; an order claim says that B
          needs A first, and is falsified if B arrives before A.
        </p>
        <p className="page-note">There are no dates in this version of the atlas.</p>
      </header>

      <section className="claims-order" aria-labelledby="order-title">
        <div className="claims-order-head">
          <h2 id="order-title">
            <span className="claims-total">{t.links}</span> order claims
          </h2>
          <p className="section-note">
            Each is a <code>needs</code> link proposed by one model call per field, with the reason
            it gave.{' '}
            {falsified === 0 ? 'All of them are standing today.' : `${falsified} are falsified.`}{' '}
            Grouped by the field of the breakthrough that needs the other.
          </p>
          <ul className="claims-legend">
            <li>
              <ClaimStatus state="standing" />
              <span>nothing has yet arrived out of order.</span>
            </li>
            <li>
              <ClaimStatus state="falsified" />
              <span>the later one was achieved first.{falsified === 0 && ' None so far.'}</span>
            </li>
          </ul>
        </div>

        <div className="region-filter" role="group" aria-label="Show claims from one region">
          <button type="button" aria-pressed={!region} onClick={() => setRegion('')}>
            All regions <span className="mono">{t.links}</span>
          </button>
          {atlas.regions
            .filter((r) => counts[r])
            .map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={region === r}
                onClick={() => setRegion(r)}
              >
                {r} <span className="mono">{counts[r]}</span>
              </button>
            ))}
        </div>
        <label className="region-select">
          <span className="eyebrow">Region</span>
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">All regions ({t.links})</option>
            {atlas.regions
              .filter((r) => counts[r])
              .map((r) => (
                <option key={r} value={r}>
                  {r} ({counts[r]})
                </option>
              ))}
          </select>
        </label>
        <p className="claims-shown muted" aria-live="polite">
          Showing {plural(shown.length, 'claim')}
          {region ? ` from ${region}` : ''} in {plural(groups.length, 'field')}.
          {!reasons && ' Loading the stated reasons…'}
        </p>

        {groups.map(({ field, links }) => (
          <section key={field.id} className="claim-group" aria-labelledby={'g-' + field.id}>
            <h3 id={'g-' + field.id}>
              <Link to={'/field/' + field.id}>{field.name}</Link>
              <span className="mono muted">
                {field.id} · {links.length}
              </span>
            </h3>
            <ul className="claims">
              {links.map((l) => (
                <Claim
                  key={l.from + l.to}
                  atlas={atlas}
                  link={l}
                  reason={reasons ? reasons[l.to]?.[l.from] || null : undefined}
                />
              ))}
            </ul>
          </section>
        ))}
      </section>

      <section className="claims-recognition" aria-labelledby="rec-title">
        <h2 id="rec-title">
          <span className="claims-total">{number(t.breakthroughs)}</span> recognition claims
        </h2>
        <div className="prose">
          <p>
            Every breakthrough in the atlas is a claim of the first kind. Each has between{' '}
            {words(Math.min(...sizes))} and {words(Math.max(...sizes))} milestones,{' '}
            {number(t.milestones)} in all, and counts as achieved only when all of its milestones
            are met. A milestone is in progress when a saved source advances it, and met when a
            source shows it has been reached; each judgement quotes the source exactly.
          </p>
          <p>
            So far {plural(t.moving, 'milestone')} {t.moving === 1 ? 'is' : 'are'} in progress and{' '}
            {t.met} {t.met === 1 ? 'is' : 'are'} met. The rest have no evidence yet, which is the
            honest starting picture.
          </p>
        </div>
        <p className="claims-ways">
          <Link to="/atlas" className="text-link">
            Read them in the atlas <Arrow />
          </Link>
          <Link to="/about" className="text-link">
            How milestones and links are made <Arrow />
          </Link>
        </p>
      </section>
    </article>
  );
}

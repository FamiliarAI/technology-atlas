import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { search, useAtlas } from '../data.jsx';
import { StarGlyph } from '../glyphs.jsx';
import { Arrow, useTitle } from './common.jsx';

// A breakthrough ID or field ID typed in the wrong case or the wrong place still finds its page.
function guess(atlas, path) {
  const last = decodeURIComponent(path.split('/').filter(Boolean).pop() || '').toUpperCase();
  if (atlas.items[last]) return { to: '/b/' + last, label: `${last} · ${atlas.items[last].title}` };
  if (atlas.field[last]) return { to: '/field/' + last, label: `${atlas.field[last].name}` };
  return null;
}

export default function NotFound({
  eyebrow = 'Off the chart',
  title = 'There is nothing at this address.',
  text = 'The link may be mistyped, or the page may have moved. Every breakthrough has a page at /b/ followed by its ID, and every field at /field/ followed by its short ID.',
}) {
  const { atlas } = useAtlas();
  const location = useLocation();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  useTitle('Not found');
  const hint = atlas && guess(atlas, location.pathname);
  const results = atlas ? search(atlas, null, query, 5) : [];
  return (
    <section className="page notfound" aria-labelledby="nf-title">
      <svg className="nf-mark" viewBox="-40 -40 80 80" width="80" height="80" aria-hidden="true">
        <circle r="30" className="nf-ring" />
        <path d="M-36 0H-24M24 0H36M0 -36V-24M0 24V36" className="nf-tick" />
      </svg>
      <p className="eyebrow">{eyebrow}</p>
      <h1 id="nf-title">{title}</h1>
      <p className="nf-text">{text}</p>
      {hint && (
        <p className="nf-hint">
          Perhaps you meant <Link to={hint.to}>{hint.label}</Link>.
        </p>
      )}
      <form
        className="nf-search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          if (results[0]) navigate('/b/' + results[0].id);
        }}
      >
        <label htmlFor="nf-q" className="eyebrow">
          Search the breakthroughs
        </label>
        <input
          id="nf-q"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="A title, an ID or a field"
          autoComplete="off"
        />
      </form>
      {results.length > 0 && (
        <ul className="nf-results">
          {results.map((item) => (
            <li key={item.id}>
              <Link to={'/b/' + item.id}>
                <StarGlyph item={item} size={26} title={false} />
                <span className="mono">{item.id}</span>
                <span>{item.title}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p className="nf-ways">
        <Link to="/" className="text-link">
          Home <Arrow />
        </Link>
        <Link to="/atlas" className="text-link">
          The atlas <Arrow />
        </Link>
        <Link to="/claims" className="text-link">
          The claims <Arrow />
        </Link>
        <Link to="/about" className="text-link">
          Method <Arrow />
        </Link>
      </p>
    </section>
  );
}

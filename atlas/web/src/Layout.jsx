import { useEffect, useId, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { formatDate, loadSearch, search, useAtlas } from './data.jsx';
import { SharedDefs, StarGlyph, Wordmark } from './glyphs.jsx';
import Starfield from './Starfield.jsx';
import { EASE } from './motion.js';
import { AUTHOR, REPOSITORY_PUBLIC, REPOSITORY_URL } from './site.js';

function Search({ open, onClose }) {
  const { atlas } = useAtlas();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [index, setIndex] = useState(null);
  const navigate = useNavigate();
  const input = useRef(null);
  const listId = useId();
  const results = atlas ? search(atlas, index, query) : [];
  // The summaries index loads on first use; until then titles and IDs are searched.
  const prime = () => {
    if (!index) loadSearch().then(setIndex, () => {});
  };
  useEffect(() => {
    const key = (e) => {
      if (e.key === '/' && !/input|textarea/i.test(document.activeElement?.tagName)) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    addEventListener('keydown', key);
    return () => removeEventListener('keydown', key);
  }, []);
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  const go = (item) => {
    setQuery('');
    input.current?.blur();
    onClose?.();
    navigate('/b/' + item.id);
  };
  return (
    <div className={'search' + (open ? ' open' : '')}>
      <svg className="search-icon" viewBox="-8 -8 16 16" width="15" height="15" aria-hidden="true">
        <circle cx="-1.5" cy="-1.5" r="4.6" />
        <path d="M2 2L6 6" />
      </svg>
      <input
        ref={input}
        type="search"
        value={query}
        placeholder="Search breakthroughs"
        aria-label="Search breakthroughs"
        role="combobox"
        aria-expanded={results.length > 0}
        aria-controls={listId}
        aria-activedescendant={results.length ? `${listId}-${active}` : undefined}
        onFocus={prime}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, results.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === 'Enter' && results[active]) {
            go(results[active]);
          } else if (e.key === 'Escape') {
            setQuery('');
            onClose?.();
          }
        }}
      />
      <kbd aria-hidden="true">/</kbd>
      {results.length > 0 && (
        <ul className="results" id={listId} role="listbox">
          {results.map((item, n) => (
            <li
              key={item.id}
              id={`${listId}-${n}`}
              role="option"
              aria-selected={n === active}
              className={n === active ? 'active' : ''}
              onMouseDown={(e) => {
                e.preventDefault();
                go(item);
              }}
              onMouseEnter={() => setActive(n)}
            >
              <StarGlyph item={item} size={26} title={false} />
              <span>
                <span className="mono">{item.id}</span>
                <span className="result-title">{item.title}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const NAV = [
  ['/atlas', 'Atlas'],
  ['/claims', 'Claims'],
  ['/about', 'Method'],
];

function Header() {
  const [searching, setSearching] = useState(false);
  const [menu, setMenu] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();
  const menuId = useId();
  const menuButton = useRef(null);
  useEffect(() => {
    setSearching(false);
    setMenu(false);
  }, [location.pathname, location.search]);
  useEffect(() => {
    const on = () => setScrolled(scrollY > 8);
    on();
    addEventListener('scroll', on, { passive: true });
    return () => removeEventListener('scroll', on);
  }, []);
  useEffect(() => {
    if (!menu) return undefined;
    const key = (e) => {
      if (e.key === 'Escape') {
        setMenu(false);
        menuButton.current?.focus();
      }
    };
    addEventListener('keydown', key);
    return () => removeEventListener('keydown', key);
  }, [menu]);
  return (
    <header className={'site-header' + (scrolled || menu || searching ? ' scrolled' : '')}>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <Link to="/" className="home-link" aria-label="Technology Atlas, home">
        <Wordmark />
      </Link>
      <nav aria-label="Main" className="main-nav">
        {NAV.map(([to, label]) => (
          <NavLink key={to} to={to}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Search open={searching} onClose={() => setSearching(false)} />
      <div className="header-buttons">
        <button
          type="button"
          className="icon-button search-toggle"
          aria-label={searching ? 'Close search' : 'Search breakthroughs'}
          aria-expanded={searching}
          onClick={() => {
            setMenu(false);
            setSearching((s) => !s);
          }}
        >
          <svg viewBox="-8 -8 16 16" width="18" height="18" aria-hidden="true">
            {searching ? (
              <path d="M-4.5 -4.5L4.5 4.5M4.5 -4.5L-4.5 4.5" />
            ) : (
              <>
                <circle cx="-1.5" cy="-1.5" r="4.6" />
                <path d="M2 2L6 6" />
              </>
            )}
          </svg>
        </button>
        <button
          ref={menuButton}
          type="button"
          className="icon-button menu-toggle"
          aria-label="Menu"
          aria-expanded={menu}
          aria-controls={menuId}
          onClick={() => {
            setSearching(false);
            setMenu((m) => !m);
          }}
        >
          <svg viewBox="-8 -8 16 16" width="18" height="18" aria-hidden="true">
            {menu ? (
              <path d="M-4.5 -4.5L4.5 4.5M4.5 -4.5L-4.5 4.5" />
            ) : (
              <path d="M-6 -3.5H6M-6 0.5H6M-6 4.5H2" />
            )}
          </svg>
        </button>
      </div>
      <nav id={menuId} className={'phone-menu' + (menu ? ' open' : '')} aria-label="Menu" hidden={!menu}>
        <ul>
          {[['/', 'Home'], ...NAV].map(([to, label]) => (
            <li key={to}>
              <NavLink to={to} end={to === '/'}>
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}

function Footer() {
  const { atlas } = useAtlas();
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div>
          <Wordmark />
          <p className="footer-purpose">
            An attempt to predict the AI takeoff by naming its wonders in advance, each with a test
            for recognising it, so that every prediction can be proven wrong.
          </p>
        </div>
        <dl className="footer-meta">
          <div>
            <dt>Research as of</dt>
            <dd>{atlas ? formatDate(atlas.asOf) : '…'}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>Proposals. No person has reviewed them yet.</dd>
          </div>
          <div>
            <dt>Read</dt>
            <dd>
              <Link to="/atlas">Atlas</Link> · <Link to="/claims">Claims</Link> ·{' '}
              <Link to="/about">Method</Link>
              {REPOSITORY_PUBLIC && (
                <>
                  {' '}
                  · <a href={REPOSITORY_URL}>Repository</a>
                </>
              )}
            </dd>
          </div>
          <div>
            <dt>Made by</dt>
            <dd>{AUTHOR}</dd>
          </div>
        </dl>
      </div>
    </footer>
  );
}

export default function Layout({ children }) {
  const location = useLocation();
  useEffect(() => {
    // A link to a section (/about#limits) lands on it once the page has faded in.
    if (location.hash) {
      const id = decodeURIComponent(location.hash.slice(1));
      const timer = setTimeout(() => document.getElementById(id)?.scrollIntoView(), 350);
      return () => clearTimeout(timer);
    }
    window.scrollTo(0, 0);
    return undefined;
  }, [location.pathname, location.hash]);
  return (
    <div className="site">
      <SharedDefs />
      <div className="site-sky" aria-hidden="true">
        <Starfield density={0.45} seed={3} />
      </div>
      <Header />
      <AnimatePresence mode="wait" initial={false}>
        <motion.main
          id="main"
          key={location.pathname}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28, ease: EASE }}
        >
          {children}
        </motion.main>
      </AnimatePresence>
      <Footer />
    </div>
  );
}

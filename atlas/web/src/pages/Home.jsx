import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';
import Chart from '../Chart.jsx';
import Starfield from '../Starfield.jsx';
import { formatDate, useAtlas } from '../data.jsx';
import { FieldEmblem, StarGlyph, StarMark, StatusLabel, ringSegments } from '../glyphs.jsx';
import { useNarrow } from './Atlas.jsx';
import { EASE } from '../motion.js';
import { claimState, ClaimStatus } from './claims.jsx';
import { Arrow } from './common.jsx';

const rise = (n, still) =>
  still
    ? {}
    : {
        initial: { opacity: 0, y: 14 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0.8, delay: 0.15 + n * 0.12, ease: EASE },
      };

const reveal = (still) =>
  still
    ? {}
    : {
        initial: { opacity: 0, y: 24 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true, margin: '-12% 0px' },
        transition: { duration: 0.8, ease: EASE },
      };

const number = (n) => n.toLocaleString('en-GB');

function SectionHead({ index, label, title, children }) {
  return (
    <header className="section-head">
      <p className="eyebrow">
        <span className="mono">{String(index).padStart(2, '0')}</span>
        {label}
      </p>
      <h2>{title}</h2>
      {children && <p className="section-lede">{children}</p>}
    </header>
  );
}

function Hero() {
  const { atlas } = useAtlas();
  const still = useReducedMotion();
  const { scrollY } = useScroll();
  const plateY = useTransform(scrollY, [0, 900], [0, still ? 0 : 260]);
  const starsY = useTransform(scrollY, [0, 900], [0, still ? 0 : 140]);
  const t = atlas?.totals;
  const narrow = useNarrow('(max-width: 760px)');
  return (
    <section className="hero" aria-labelledby="hero-title">
      <motion.div className="plate" style={{ y: plateY }} aria-hidden="true" />
      <motion.div className="hero-stars" style={{ y: starsY }}>
        <Starfield density={0.9} />
      </motion.div>
      <div className="hero-sky">{atlas && <Chart atlas={atlas} intro pad={8} labels={!narrow} />}</div>
      <div className="hero-copy">
        <motion.p className="eyebrow" {...rise(0, still)}>
          A star atlas of the AI takeoff
        </motion.p>
        <motion.h1 id="hero-title" {...rise(1, still)}>
          Naming the wonders before they arrive.
        </motion.h1>
        <motion.p className="lead" {...rise(2, still)}>
          This atlas predicts the AI takeoff by naming, in advance, the breakthroughs expected on the
          way. Each one has a test for recognising it and an order it should arrive in, so every
          prediction here can be proven wrong.
        </motion.p>
        <motion.div className="hero-actions" {...rise(3, still)}>
          <Link to="/atlas" className="button primary">
            Enter the atlas
            <svg viewBox="-8 -8 16 16" width="14" height="14" aria-hidden="true">
              <path d="M-5 0H5M1 -4L5 0L1 4" />
            </svg>
          </Link>
          <a href="#read" className="button quiet">
            How to read a star
          </a>
        </motion.div>
      </div>
      <motion.dl className="hero-figures" {...rise(4, still)} aria-label="The atlas today">
        <div>
          <dt>Breakthroughs</dt>
          <dd>{t ? number(t.breakthroughs) : '—'}</dd>
        </div>
        <div>
          <dt>Constellations</dt>
          <dd>{atlas ? atlas.fields.length : '—'}</dd>
        </div>
        <div>
          <dt>Milestones</dt>
          <dd>{t ? number(t.milestones) : '—'}</dd>
        </div>
        <div>
          <dt>In progress</dt>
          <dd className="amber">{t ? t.moving : '—'}</dd>
        </div>
        <div>
          <dt>Met</dt>
          <dd>{t ? t.met : '—'}</dd>
        </div>
      </motion.dl>
    </section>
  );
}

const host = (url) => {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, '') + u.pathname.replace(/\/$/, '');
  } catch {
    return url;
  }
};

const VERDICT = { advances: 'in_progress', meets: 'met', contradicts: 'none' };

function Moved() {
  const { atlas } = useAtlas();
  const still = useReducedMotion();
  if (!atlas) return null;
  const groups = [];
  for (const row of atlas.recent) {
    let g = groups.find((x) => x.id === row.breakthrough);
    if (!g) groups.push((g = { id: row.breakthrough, rows: [] }));
    g.rows.push(row);
  }
  return (
    <section className="section moved" aria-labelledby="moved-title">
      <SectionHead index={1} label="Recent movement" title={<span id="moved-title">What moved</span>}>
        A source is saved, read against one milestone, and quoted exactly. Newest first.
      </SectionHead>
      <motion.ol className="moved-list" {...reveal(still)}>
        {groups.map((g) => {
          const item = atlas.items[g.id];
          return (
            <li key={g.id} className="moved-item">
              <div className="moved-star">
                <StarGlyph item={item} size={64} />
                <time className="mono">{formatDate(g.rows[0].added_at)}</time>
              </div>
              <div className="moved-body">
                <p className="crumb">
                  <span className="mono">{item.id}</span> {atlas.field[item.field].name}
                </p>
                <h3>
                  <Link to={'/b/' + item.id}>{item.title}</Link>
                </h3>
                <ul className="moved-rows">
                  {g.rows.map((row, n) => {
                    return (
                      <li key={n}>
                        <div className="moved-row-head">
                          <StatusLabel status={VERDICT[row.verdict]} />
                          <span className="mono muted">M{row.criterion}</span>
                          <span className="milestone-label">{row.label}</span>
                        </div>
                        <blockquote>
                          <p>“{row.quote}”</p>
                          <footer>
                            <a href={row.url} target="_blank" rel="noopener noreferrer">
                              {host(row.url)}
                            </a>
                            {row.source_date && <span> · published {formatDate(row.source_date)}</span>}
                          </footer>
                        </blockquote>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </li>
          );
        })}
        {atlas && (
          <li className="moved-note">
            That is every judgement so far: {atlas.recent.length} milestone readings across{' '}
            {groups.length} breakthroughs. The rest of the sky is dark, which is the honest
            starting picture.
          </li>
        )}
      </motion.ol>
    </section>
  );
}

function DemoStar() {
  const item = { status: ['none', 'none', 'none', 'none'], glow: 0 };
  return (
    <svg viewBox="-60 -60 120 120" className="demo" aria-hidden="true">
      <circle r="44" className="demo-guide" />
      <StarMark item={item} r={13} core={3.2} />
      <line x1="14" y1="-14" x2="32" y2="-32" className="demo-leader" />
      <text x="36" y="-38" className="demo-text">QUA-01</text>
    </svg>
  );
}

function DemoRing() {
  const states = ['met', 'in_progress', 'none', 'none'];
  const segs = ringSegments(states, 30);
  const item = { status: states, glow: 0.375 };
  const labels = [
    ['Met', 28, -30, 'start'],
    ['In progress', 28, 34, 'start'],
    ['No evidence yet', -28, 34, 'end'],
  ];
  return (
    <svg viewBox="-80 -60 160 120" className="demo" aria-hidden="true">
      <StarMark item={item} r={30} ring={false} core={5} />
      {segs.map((s, n) => (
        <path key={n} d={s.d} className={'seg big ' + s.status} />
      ))}
      {labels.map(([t, x, y, a]) => (
        <text key={t} x={x} y={y} textAnchor={a} className="demo-text small">
          {t}
        </text>
      ))}
    </svg>
  );
}

// Two stars and the claim line between them: brighter at the end that must come first, with
// an arrowhead towards what it unlocks, as in the chart.
function DemoOrder() {
  const first = { status: ['in_progress', 'none', 'none', 'none'], glow: 0.125 };
  const later = { status: ['none', 'none', 'none'], glow: 0 };
  return (
    <svg viewBox="-80 -60 160 120" className="demo" aria-hidden="true">
      <defs>
        <linearGradient id="demo-claim" x1="-40" y1="28" x2="38" y2="-22" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#7FB2FF" stopOpacity="0.95" />
          <stop offset="1" stopColor="#7FB2FF" stopOpacity="0.35" />
        </linearGradient>
      </defs>
      <path d="M-34 24Q-6 -18 26 -18" className="demo-link" stroke="url(#demo-claim)" />
      <path d="M20 -22.5L27 -18L20 -13.5" className="demo-link" stroke="#7FB2FF" strokeOpacity="0.5" />
      <g transform="translate(-42 30)">
        <StarMark item={first} r={9} core={2.5} />
      </g>
      <g transform="translate(40 -18)">
        <StarMark item={later} r={8} core={2.1} />
      </g>
      <text x="-42" y="54" textAnchor="middle" className="demo-text small">
        Needed first
      </text>
      <text x="40" y="-38" textAnchor="middle" className="demo-text small">
        Unlocked
      </text>
    </svg>
  );
}

function HowToRead() {
  const still = useReducedMotion();
  const steps = [
    [
      <DemoStar key="d" />,
      'A star is one breakthrough',
      'Each star is a capability we expect on the way to the takeoff, with a permanent ID. The more milestones it has, the larger it is drawn.',
    ],
    [
      <DemoRing key="d" />,
      'Its ring is the test',
      'One segment per milestone: the conditions under which we will say it has happened. A segment turns amber when a source advances it and white-gold when it is met. The star warms with them.',
    ],
    [
      <DemoOrder key="d" />,
      'Its lines are the order',
      'A curved line is a claim that one breakthrough needs another first. It is brightest at the end that must come first, and points to what it unlocks. If the later one arrives first, the claim is proven wrong.',
    ],
  ];
  return (
    <section className="section read" id="read" aria-labelledby="read-title">
      <SectionHead index={2} label="Reading the chart" title={<span id="read-title">How to read a star</span>} />
      <motion.ol className="steps" {...reveal(still)}>
        {steps.map(([demo, title, text], n) => (
          <li key={n}>
            <div className="step-figure">{demo}</div>
            <p className="step-index mono">{n + 1}</p>
            <h3>{title}</h3>
            <p>{text}</p>
          </li>
        ))}
      </motion.ol>
    </section>
  );
}

function StartWith() {
  const { atlas } = useAtlas();
  const still = useReducedMotion();
  if (!atlas) return null;
  // Fields with movement and order claims first: they have the most to show today.
  const picks = [...atlas.fields]
    .sort((a, b) => b.moving * 3 + b.links - (a.moving * 3 + a.links) || a.id.localeCompare(b.id))
    .slice(0, 4);
  return (
    <section className="section start" aria-labelledby="start-title">
      <SectionHead
        index={3}
        label="Constellations"
        title={<span id="start-title">A few constellations to start with</span>}
      >
        Each field of research is a constellation, and neighbouring fields share one of{' '}
        {atlas.regions.length} regions of the sky. These four have the most to show today.
      </SectionHead>
      <motion.ul className="field-tiles" {...reveal(still)}>
        {picks.map((f) => (
          <li key={f.id}>
            <Link to={`/field/${f.id}`} className="field-tile">
              <FieldEmblem field={f} atlas={atlas} size={44} />
              <p className="tile-region">{f.region}</p>
              <h3>{f.name}</h3>
              <p className="mono muted">
                {f.items.length} breakthroughs · {f.moving} moving · {f.links} order links
              </p>
              <div className="tile-stars" aria-hidden="true">
                {f.items.map((i) => (
                  <StarGlyph key={i.id} item={i} size={22} title={false} />
                ))}
              </div>
            </Link>
          </li>
        ))}
      </motion.ul>
      <p className="more">
        <Link to="/atlas">All {atlas.fields.length} constellations in the atlas</Link>
      </p>
    </section>
  );
}

function Claims() {
  const { atlas } = useAtlas();
  const still = useReducedMotion();
  if (!atlas) return null;
  return (
    <section className="section claims-brief" aria-labelledby="claims-title">
      <SectionHead index={4} label="The claims" title={<span id="claims-title">What exactly is predicted</span>}>
        Two kinds of claim, both falsifiable. There are no dates.
      </SectionHead>
      <motion.div className="claim-kinds" {...reveal(still)}>
        <div>
          <p className="claim-count mono">{number(atlas.totals.breakthroughs)}</p>
          <h3>Recognition</h3>
          <p>“This breakthrough counts as achieved when these milestones are met.” One per star.</p>
        </div>
        <div>
          <p className="claim-count mono">{atlas.totals.links}</p>
          <h3>Order</h3>
          <p>“B needs A first.” Proven wrong if B arrives before A. One per line in the chart.</p>
        </div>
      </motion.div>
      <ul className="claim-list">
        {atlas.links.slice(0, 4).map((l) => {
          const a = atlas.items[l.from];
          const b = atlas.items[l.to];
          return (
            <li key={l.from + l.to}>
              <p>
                <Link to={'/b/' + b.id}>{b.title}</Link> <span className="mono muted">{b.id}</span>{' '}
                <em>needs</em> <Link to={'/b/' + a.id}>{a.title}</Link>{' '}
                <span className="mono muted">{a.id}</span> <em>first.</em>
              </p>
              <ClaimStatus state={claimState(a, b)} />
            </li>
          );
        })}
      </ul>
      <p className="more">
        <Link to="/claims" className="text-link">
          All {atlas.totals.links} order claims, with their reasons <Arrow />
        </Link>
      </p>
    </section>
  );
}

function Method() {
  const still = useReducedMotion();
  return (
    <section className="section method-brief" aria-labelledby="method-title">
      <SectionHead index={5} label="Method" title={<span id="method-title">How it is made</span>} />
      <motion.div className="method-cols" {...reveal(still)}>
        <p>
          Language models researched every field and cited their sources; a second model then
          reviewed each record against saved copies of those sources. Every quote shown as evidence was found,
          word for word, in the saved text.
        </p>
        <p>
          No person has reviewed the entries yet. They are proposals, published so they can be
          checked and challenged. Editing opens after this first version.
        </p>
      </motion.div>
      <p className="more">
        <Link to="/about" className="text-link">
          The method and its limits <Arrow />
        </Link>
      </p>
    </section>
  );
}

export default function Home() {
  const { error } = useAtlas();
  useEffect(() => {
    document.title = 'Technology Atlas · The wonders of the AI takeoff, named in advance';
  }, []);
  return (
    <div className="home">
      <Hero />
      {error ? (
        <p className="section load-error">The atlas data could not be loaded: {error}.</p>
      ) : (
        <>
          <Moved />
          <HowToRead />
          <StartWith />
          <Claims />
          <Method />
        </>
      )}
    </div>
  );
}

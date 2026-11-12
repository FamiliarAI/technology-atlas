import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';
import Chart from '../Chart.jsx';
import Starfield from '../Starfield.jsx';
import { formatDate, milestoneOf, useAtlas } from '../data.jsx';
import { FieldEmblem, StarGlyph, StarMark, StatusLabel, ringSegments } from '../glyphs.jsx';
import { useNarrow } from './Atlas.jsx';
import { EASE } from '../motion.js';
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
          A star atlas of what to work towards
        </motion.p>
        <motion.h1 id="hero-title" {...rise(1, still)}>
          The breakthroughs worth working towards.
        </motion.h1>
        <motion.p className="lead" {...rise(2, still)}>
          A map of the breakthroughs people can work towards, with superintelligence to help. Each
          has milestones along the way that tell us how close we are, and research papers are
          added as they bring one nearer.
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

const VERDICT = { advances: 'in_progress', meets: 'met' };

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
        A paper is saved, read against one milestone or against the breakthrough as a whole, and
        quoted exactly. Newest first.
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
                    const m = milestoneOf(row);
                    return (
                      <li key={n}>
                        <div className="moved-row-head">
                          {VERDICT[row.verdict] ? (
                            <StatusLabel status={VERDICT[row.verdict]} />
                          ) : (
                            <span className={'verdict ' + row.verdict}>Contradicts</span>
                          )}
                          <span className="mono muted">{m ? `M${m}` : 'Whole'}</span>
                          <span className="milestone-label">
                            {m ? row.label : 'A step toward the breakthrough as a whole'}
                          </span>
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
            That is every judgement so far: {atlas.recent.length} readings across {groups.length}{' '}
            breakthroughs. The rest of the sky is dark because the atlas has not yet assessed it,
            not because nothing has happened.
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
    ['Not yet assessed', -30, 46, 'middle'],
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

// A star and two papers: one added as a step toward a milestone (its ring segment), one as a
// step toward the breakthrough as a whole (its point of light).
function Paper({ x, y }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <path d="M-5 -6.5H2.5L5 -4V6.5H-5Z" className="demo-paper" />
      <path d="M-2.6 -2H2.6M-2.6 0.8H2.6M-2.6 3.6H0.8" className="demo-leader" />
    </g>
  );
}

function DemoPapers() {
  const item = { status: ['in_progress', 'none', 'none', 'none'], glow: 0.125 };
  return (
    <svg viewBox="-80 -60 160 120" className="demo" aria-hidden="true">
      <StarMark item={item} r={24} core={4.5} />
      <line x1="44" y1="-32" x2="19" y2="-17" className="demo-leader" />
      <Paper x={50} y={-36} />
      <text x="50" y="-48" textAnchor="middle" className="demo-text small">
        To a milestone
      </text>
      <line x1="-44" y1="26" x2="-7" y2="4" className="demo-leader" />
      <Paper x={-50} y={30} />
      <text x="-50" y="48" textAnchor="middle" className="demo-text small">
        To the whole
      </text>
    </svg>
  );
}

function HowToRead() {
  const still = useReducedMotion();
  const steps = [
    [
      <DemoStar key="d" />,
      'A star is a breakthrough to work towards',
      'Each star is one capability worth working towards, with a permanent ID. The more milestones it has, the larger it is drawn.',
    ],
    [
      <DemoRing key="d" />,
      'Its ring is its milestones',
      'One segment per milestone along the way. A segment turns amber when a paper advances it and white-gold when it is met. Until a paper is judged against it, it reads as not yet assessed.',
    ],
    [
      <DemoPapers key="d" />,
      'Papers are steps along the way',
      'A paper that moves a breakthrough forward is added with an exact quote, as a step toward one milestone or toward the breakthrough as a whole. Either kind warms the star.',
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
  // Fields with movement first: they have the most to show today.
  const picks = [...atlas.fields]
    .sort((a, b) => b.moving - a.moving || b.items.length - a.items.length || a.id.localeCompare(b.id))
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
                {f.items.length} breakthroughs · {f.moving} moving
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

function Method() {
  const still = useReducedMotion();
  return (
    <section className="section method-brief" aria-labelledby="method-title">
      <SectionHead index={4} label="Method" title={<span id="method-title">How it is made</span>} />
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
    document.title = 'Technology Atlas · The breakthroughs worth working towards';
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
          <Method />
        </>
      )}
    </div>
  );
}

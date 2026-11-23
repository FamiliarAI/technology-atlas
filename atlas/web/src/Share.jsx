import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Route, Routes, useParams } from 'react-router-dom';
import { Locator } from './Chart.jsx';
import { STATUS, loadBreakthrough, useAtlas, warm as isWarm } from './data.jsx';
import { ringSegments, starColor } from './glyphs.jsx';
import { onPaper } from './style.js';
import { whenText } from './pages/Page.jsx';
import { chartCoord, regionInk, starRadius } from './sky.js';
import './share.css';

// Share cards: the 1200×630 images that link previews show, drawn by the site itself and
// screenshotted by `python3 -m atlas.share`. Only the card is drawn, in its final state: no
// header, footer, scrolling or motion. When everything has loaded and the title has been
// fitted, <html> gets data-share-ready (or data-share-error with a reason).
//
//   /share/default        the atlas as a whole
//   /share/field/QUA      one field and its constellation
//   /share/b/QUA-01       one breakthrough

const W = 1200;
const H = 630;
const PLATE = import.meta.env.BASE_URL + 'deep-field.webp';
const FONTS = [
  '300 20px Jura',
  '400 20px Jura',
  '600 20px Jura',
  '400 20px Newsreader',
  'italic 400 20px Newsreader',
  '400 20px "JetBrains Mono"',
  '400 20px "DM Sans"',
  '500 20px "DM Sans"',
  '500 20px Newsreader',
];

const signal = (key, value) => {
  document.documentElement.dataset[key] = value;
};

// Fonts and the plate, loaded before anything is measured.
function useAssets() {
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let live = true;
    const plate = new Image();
    plate.src = PLATE;
    Promise.all([
      ...FONTS.map((f) => document.fonts.load(f)),
      plate.decode().catch(() => null),
    ])
      .then(() => document.fonts.ready)
      .then(() => live && setLoaded(true));
    return () => {
      live = false;
    };
  }, []);
  return loaded;
}

// The page is the card: no scroll, no robots, a fixed size.
function useCardPage() {
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.classList.add('share-page');
    const robots = document.createElement('meta');
    robots.name = 'robots';
    robots.content = 'noindex, nofollow';
    document.head.appendChild(robots);
    return () => {
      root.classList.remove('share-page');
      robots.remove();
      delete root.dataset.shareReady;
      delete root.dataset.shareError;
    };
  }, []);
}

// Sets the largest font size at which the text fits its box without overflowing sideways,
// trying each [lines, smallest size] step in turn: a short title stays large on two lines
// rather than filling four. Past the last step it is clamped to that step's lines.
function FitText({ as: Tag = 'h1', className, max, steps, lead = 1.06, children }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    el.style.lineHeight = String(lead);
    el.classList.remove('clamped');
    el.style.webkitLineClamp = '';
    // Measure with words kept whole, so a long word makes the type smaller instead of breaking.
    el.style.overflowWrap = 'normal';
    const fits = (size, lines) => {
      el.style.fontSize = size + 'px';
      const count = Math.round(el.scrollHeight / (size * lead));
      return count <= lines && el.scrollWidth <= el.clientWidth + 1;
    };
    let size = max;
    for (const [lines, floor] of steps) {
      for (size = max; size >= floor; size -= 1) if (fits(size, lines)) return;
    }
    const [lines, floor] = steps[steps.length - 1];
    el.style.fontSize = floor + 'px';
    el.style.overflowWrap = '';
    el.style.webkitLineClamp = String(lines);
    el.classList.add('clamped');
  }, [children, max, steps, lead]);
  return (
    <Tag ref={ref} className={className}>
      {children}
    </Tag>
  );
}

// Title sizes: two lines down to 64 px, three down to 44, four down to 38, then clamped.
const TITLE_STEPS = [
  [2, 64],
  [3, 44],
  [4, 38],
];
const NAME_STEPS = [
  [2, 60],
  [3, 44],
];

// Tick marks along an edge, every 10 px, longer every 50 and 100: the chart's ruler.
function Ruler({ y, flip = false }) {
  let d = '';
  for (let x = 40; x <= W - 40; x += 10) {
    const len = x % 100 === 0 ? 9 : x % 50 === 0 ? 6 : 3;
    d += `M${x} ${y}v${flip ? -len : len}`;
  }
  return <path d={d} className="card-ticks" />;
}

function Frame() {
  const corner = (x, y, dx, dy) => `M${x + dx} ${y}H${x}V${y + dy}`;
  return (
    <svg className="card-frame" width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <rect x="28.5" y="28.5" width={W - 57} height={H - 57} className="card-hair" />
      <Ruler y={28.5} />
      <Ruler y={H - 28.5} flip />
      <path
        d={[
          corner(14.5, 14.5, 22, 22),
          corner(W - 14.5, 14.5, -22, 22),
          corner(14.5, H - 14.5, 22, -22),
          corner(W - 14.5, H - 14.5, -22, -22),
        ].join('')}
        className="card-corner"
      />
    </svg>
  );
}

function Wordmark() {
  return (
    <div className="card-wordmark">
      <svg width="34" height="34" viewBox="-13 -13 26 26" aria-hidden="true">
        <circle r="2.8" fill="#FFF1C9" className="card-wm-core" />
        {ringSegments(['in_progress', 'none', 'none', 'none'], 9).map((s, n) => (
          <path key={n} d={s.d} className={'cseg ' + s.status} strokeWidth={s.status === 'none' ? 1.1 : 1.9} />
        ))}
      </svg>
      <span>Technology Atlas</span>
    </div>
  );
}

function Card({ kind, ready, children }) {
  useCardPage();
  useEffect(() => {
    if (ready) requestAnimationFrame(() => signal('shareReady', kind));
  }, [ready, kind]);
  return (
    <div className={'card card-' + kind}>
      <div className="card-plate" aria-hidden="true" />
      <div className="card-shade" aria-hidden="true" />
      <Frame />
      {children}
    </div>
  );
}

function Failed({ reason }) {
  useCardPage();
  useEffect(() => signal('shareError', reason), [reason]);
  return <p className="card-failed">{reason}</p>;
}

// Hyphenated words are kept whole ("gamma-ray", not "gamma- / ray"); if one is too wide for
// the line, FitText makes the type smaller instead.
function Words({ text }) {
  return text.split(/(\s+)/).map((part, n) =>
    part.includes('-') ? (
      <span key={n} className="nobr">
        {part}
      </span>
    ) : (
      part
    ),
  );
}

const plural = (n, one, many = one + 's') => `${n.toLocaleString('en-GB')} ${n === 1 ? one : many}`;

// The milestone meter in words, for someone who has never seen the atlas.
export function meterWords(item) {
  const n = item.status.length;
  const noun = n === 1 ? 'milestone' : 'milestones';
  // A met completion test outranks the milestone count, as on the page.
  if (item.complete) return item.completed ? `Complete, ${whenText(item.completed)}` : 'Complete';
  if (!item.met && !item.moving) {
    if (!item.overall) return STATUS.none;
    return `${item.overall === 1 ? '1 paper' : `${item.overall} papers`} toward the whole`;
  }
  if (item.met === n) return n === 1 ? 'Its milestone is met' : `All ${n} milestones met`;
  if (item.met && item.moving) return `${item.met} met, ${item.moving} in progress, of ${n} ${noun}`;
  if (item.met) return `${item.met} of ${n} ${noun} met`;
  return `${item.moving} of ${n} ${noun} in progress`;
}

function MeterMark({ status }) {
  return (
    <svg className={'card-mark ' + status} width="30" height="30" viewBox="-8 -8 16 16" aria-hidden="true">
      <circle r="6.2" className="rim" />
      {status === 'in_progress' && <path d="M0 -6.2A6.2 6.2 0 0 1 0 6.2Z" className="fill" />}
      {status === 'met' && <circle r="6.2" className="fill" />}
    </svg>
  );
}

const stateOf = (item) =>
  item.complete || (item.status.length && item.met === item.status.length) ? 'met' : isWarm(item) ? 'in_progress' : 'none';

// One star, large: its point, its halo when warm, its ring of milestones, a graduated dial.
function BigStar({ item, size = 300 }) {
  const n = item.status.length;
  const R = 100;
  // On paper a complete star is the chart's mark for it: an ink disc with a gold heart.
  const gilt = item.complete && onPaper();
  const color = gilt ? '#1D2027' : starColor(item.glow);
  let ticks = '';
  for (let i = 0; i < 120; i++) {
    const a = (i / 120) * Math.PI * 2 - Math.PI / 2;
    const len = i % 30 === 0 ? 12 : i % 10 === 0 ? 7 : 3.5;
    const r0 = 136;
    ticks += `M${(Math.cos(a) * r0).toFixed(2)} ${(Math.sin(a) * r0).toFixed(2)}L${(Math.cos(a) * (r0 - len)).toFixed(2)} ${(Math.sin(a) * (r0 - len)).toFixed(2)}`;
  }
  return (
    <svg className="card-star" width={size} height={size} viewBox="-150 -150 300 300" aria-hidden="true">
      <defs>
        <radialGradient id="card-halo">
          <stop offset="0%" stopColor="#FFD08A" stopOpacity="0.55" />
          <stop offset="30%" stopColor="#FFB454" stopOpacity="0.18" />
          <stop offset="65%" stopColor="#FFB454" stopOpacity="0.04" />
          <stop offset="100%" stopColor="#FFB454" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle r="136" className="dial" />
      <path d={ticks} className="dial-ticks" />
      {item.glow > 0 && (
        <circle r={R * 1.25} fill="url(#card-halo)" opacity={0.5 + item.glow * 0.5} className="card-halo" />
      )}
      {ringSegments(item.complete ? item.status.map(() => 'met') : item.status, R).map((s, k) => (
        <path key={k} d={s.d} className={'cseg ' + s.status} strokeWidth={s.status === 'none' ? 2.4 : 7} />
      ))}
      <circle r={9 + n * 1.2} fill={color} opacity={item.glow > 0 ? 1 : 0.8} />
      {item.glow > 0 && <circle r={4 + n * 0.5} fill="#FFF8E6" className="card-star-heart" />}
      {gilt && <circle r={4 + n * 0.5} fill="#F2C14E" />}
    </svg>
  );
}

export function BreakthroughCard() {
  const { id } = useParams();
  const { atlas, error } = useAtlas();
  const loaded = useAssets();
  // The card leads with the reader's title, as the page does; the record says whether one exists.
  const [record, setRecord] = useState(null);
  useEffect(() => {
    let live = true;
    loadBreakthrough(id).then(
      (data) => live && setRecord({ id, data }),
      () => live && setRecord({ id, data: null }),
    );
    return () => {
      live = false;
    };
  }, [id]);
  if (error) return <Failed reason={'Data: ' + error} />;
  if (!atlas || !loaded || record?.id !== id) return null;
  const item = atlas.items[id];
  if (!item) return <Failed reason={'No breakthrough ' + id} />;
  const plain = record.data?.brief?.title;
  const title = typeof plain === 'string' && plain.trim() ? plain.trim() : item.title;
  const field = atlas.field[item.field];
  const coord = chartCoord(item, atlas.sky);
  const state = stateOf(item);
  return (
    <Card kind="b" ready>
      <div className="card-main">
        <header className="card-top">
          <Wordmark />
        </header>
        <div className="card-body">
          <p className="card-eyebrow">
            <span className="card-id">{item.id}</span>
            <span className="card-rule" />
            <span>{field.name}</span>
          </p>
          <FitText className="card-title" max={84} steps={TITLE_STEPS}>
            <Words text={title} />
          </FitText>
        </div>
        <footer className={'card-meter ' + state}>
          <span className="card-marks">
            {item.status.map((s, k) => (
              <MeterMark key={k} status={s} />
            ))}
          </span>
          <span className="card-meter-word">{meterWords(item)}</span>
        </footer>
      </div>
      <aside className="card-side">
        <BigStar item={item} />
        <div className="card-locator">
          <Locator atlas={atlas} field={item.field} star={item.id} width={250} />
        </div>
        <p className="card-coord">
          <span>{field.region}</span>
          {coord && <span className="mono">{coord.text}</span>}
        </p>
      </aside>
    </Card>
  );
}

// A field's constellation, drawn large: its figure's lines and every star with its ring.
function Constellation({ atlas, field, w = 500, h = 520 }) {
  const fig = atlas.sky.figures[field.id];
  const items = field.items;
  const xs = items.map((i) => i.x);
  const ys = items.map((i) => i.y);
  const pad = 50;
  const spanX = Math.max(...xs) - Math.min(...xs) || 1;
  const spanY = Math.max(...ys) - Math.min(...ys) || 1;
  const k = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY, 10);
  const cx = (Math.max(...xs) + Math.min(...xs)) / 2;
  const cy = (Math.max(...ys) + Math.min(...ys)) / 2;
  const at = (i) => ({ x: w / 2 + (i.x - cx) * k, y: h / 2 + (i.y - cy) * k });
  const scale = Math.min(1.5, Math.max(0.9, k / 6));
  return (
    <svg
      className="card-constellation"
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={regionInk(field.region)}
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="card-halo-s">
          <stop offset="0%" stopColor="#FFD08A" stopOpacity="0.5" />
          <stop offset="35%" stopColor="#FFB454" stopOpacity="0.14" />
          <stop offset="100%" stopColor="#FFB454" stopOpacity="0" />
        </radialGradient>
      </defs>
      {fig.edges.map(([a, b], n) => {
        const p = at(atlas.items[a]);
        const q = at(atlas.items[b]);
        return <line key={n} x1={p.x} y1={p.y} x2={q.x} y2={q.y} className="con-line" />;
      })}
      {items.map((i) => {
        const p = at(i);
        const r = starRadius(i.status.length) * 3.4 * scale;
        return (
          <g key={i.id} transform={`translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})`}>
            <circle r={r + 5} className="con-gap" />
            {i.glow > 0 && <circle r={r * 2.4} fill="url(#card-halo-s)" className="card-halo" />}
            {ringSegments(i.status, r).map((s, n) => (
              <path key={n} d={s.d} className={'cseg ' + s.status} strokeWidth={s.status === 'none' ? 1.6 : 4} />
            ))}
            {i.complete && onPaper() ? (
              <>
                <circle r={r * 0.5} fill="#1D2027" />
                <circle r={r * 0.24} fill="#F2C14E" />
              </>
            ) : (
              <circle r={r * 0.34} fill={starColor(i.glow)} />
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function FieldCard() {
  const { id } = useParams();
  const { atlas, error } = useAtlas();
  const loaded = useAssets();
  if (error) return <Failed reason={'Data: ' + error} />;
  if (!atlas || !loaded) return null;
  const field = atlas.field[id];
  if (!field) return <Failed reason={'No field ' + id} />;
  const milestones = field.items.reduce((n, i) => n + i.status.length, 0);
  const warm = field.items.filter(isWarm).length;
  return (
    <Card kind="field" ready>
      <div className="card-main">
        <header className="card-top">
          <Wordmark />
        </header>
        <div className="card-body">
          <p className="card-eyebrow">
            <span className="card-id">{field.id}</span>
            <span className="card-rule" />
            <span>{field.region}</span>
          </p>
          <FitText className="card-title card-field-name" max={84} steps={NAME_STEPS}>
            <Words text={field.name} />
          </FitText>
        </div>
        <footer className="card-counts">
          <div>
            <b>{field.items.length}</b>
            <span>{field.items.length === 1 ? 'breakthrough' : 'breakthroughs'}</span>
          </div>
          <div>
            <b>{milestones}</b>
            <span>milestones</span>
          </div>
          <div className={warm ? 'warm' : ''}>
            <b>{warm}</b>
            <span>in progress</span>
          </div>
        </footer>
      </div>
      <aside className="card-side card-side-wide">
        <Constellation atlas={atlas} field={field} />
      </aside>
    </Card>
  );
}

export function DefaultCard() {
  const { atlas, error } = useAtlas();
  const loaded = useAssets();
  if (error) return <Failed reason={'Data: ' + error} />;
  if (!atlas || !loaded) return null;
  const { totals } = atlas;
  // Breakthroughs with any judged progress, as on the field cards.
  const warm = Object.values(atlas.items).filter(isWarm).length;
  return (
    <Card kind="default" ready>
      <div className="card-intro">
        <header className="card-top">
          <Wordmark />
        </header>
        <div className="card-body">
          <h1 className="card-motto">The breakthroughs worth working towards.</h1>
          <p className="card-sub">
            A map of breakthroughs in {atlas.fields.length} fields, and the milestones that tell us
            how close we are.
          </p>
        </div>
        <footer className="card-counts">
          <div>
            <b>{totals.breakthroughs}</b>
            <span>breakthroughs</span>
          </div>
          <div>
            <b>{totals.milestones.toLocaleString('en-GB')}</b>
            <span>milestones</span>
          </div>
          <div className={warm ? 'warm' : ''}>
            <b>{warm}</b>
            <span>in progress</span>
          </div>
        </footer>
      </div>
      <aside className="card-sky">
        <Locator atlas={atlas} width={600} />
        <p className="card-coord card-sky-legend">
          <span>The sky of the atlas</span>
          <span className="mono">{atlas.regions.length} regions</span>
        </p>
      </aside>
    </Card>
  );
}

export default function Share() {
  return (
    <Routes>
      <Route path="/share/default" element={<DefaultCard />} />
      <Route path="/share/field/:id" element={<FieldCard />} />
      <Route path="/share/b/:id" element={<BreakthroughCard />} />
      <Route path="*" element={<Failed reason="No such card" />} />
    </Routes>
  );
}

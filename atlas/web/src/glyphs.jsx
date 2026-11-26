import { STATUS } from './data.jsx';
import { arc, emblem } from './sky.js';
import { onPaper } from './style.js';

const mix = (a, b, t) => {
  const pa = a.match(/\w\w/g).map((h) => parseInt(h, 16));
  const pb = b.match(/\w\w/g).map((h) => parseInt(h, 16));
  return '#' + pa.map((v, n) => Math.round(v + (pb[n] - v) * t).toString(16).padStart(2, '0')).join('');
};

// Colour means progress and nothing else: a dim blue-grey point warms to amber as milestones
// advance and ignites white-gold when all are met.
// On paper a star's point has two states, the same two as a ring segment: grey when nothing is
// assessed, amber once anything is under way. Ink is kept for met segments and complete stars.
export function starColor(glow) {
  if (onPaper()) return glow <= 0 ? '#A4A8B0' : '#A8650A';
  if (glow <= 0) return '#7D89A3';
  if (glow >= 1) return '#FFF1C9';
  return glow < 0.5 ? mix('9AA3B8', 'FFB454', glow * 2) : mix('FFB454', 'FFF1C9', (glow - 0.5) * 2);
}

export const starOpacity = (glow) => (glow > 0 ? 0.9 + glow * 0.1 : 0.62);

// Segments of a milestone ring around (0,0), one per milestone, clockwise from the top.
export function ringSegments(status, radius) {
  const n = status.length;
  const gap = Math.min(0.5, (Math.PI * 2) / n) * 0.42;
  const each = (Math.PI * 2) / n;
  return status.map((s, i) => {
    const a0 = -Math.PI / 2 + i * each + gap / 2;
    return { d: arc(0, 0, radius, a0, a0 + each - gap), status: s };
  });
}

// r is the radius of the milestone ring; the star itself is a small point inside it.
export function StarMark({ item, r, ring = true, core }) {
  const color = starColor(item.glow);
  const c = core ?? Math.max(1.2, r * 0.36);
  // Complete: the ring filled in, one disc and nothing else (as on the chart).
  if (ring && item.complete) return <circle r={r} className="star-complete" />;
  return (
    <>
      {item.glow > 0 && <circle r={r * 1.9} fill="url(#halo)" opacity={0.45 + item.glow * 0.55} />}
      <circle r={c} fill={color} opacity={starOpacity(item.glow)} />
      {item.glow > 0 && <circle r={c * 0.45} fill="#FFF8E6" className="star-heart" />}
      {ring && ringSegments(item.status, r).map((seg, n) => <path key={n} d={seg.d} className={'seg ' + seg.status} />)}
    </>
  );
}

// One shared definition, mounted once by the layout.
export function SharedDefs() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
      <defs>
        <Halo />
      </defs>
    </svg>
  );
}

export function Halo() {
  return (
    <radialGradient id="halo">
      <stop offset="0%" stopColor="#FFD08A" stopOpacity="0.5" />
      <stop offset="25%" stopColor="#FFB454" stopOpacity="0.2" />
      <stop offset="60%" stopColor="#FFB454" stopOpacity="0.05" />
      <stop offset="100%" stopColor="#FFB454" stopOpacity="0" />
    </radialGradient>
  );
}

export function StarGlyph({ item, size = 40, title = true }) {
  const r = 6 + item.status.length * 0.5;
  const box = r + 3;
  const met = item.met;
  const moving = item.moving;
  return (
    <svg
      className="star-glyph"
      width={size}
      height={size}
      viewBox={`${-box} ${-box} ${box * 2} ${box * 2}`}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={
        title
          ? `${item.status.length} milestones: ${met} met, ${moving} in progress`
          : undefined
      }
    >
      <StarMark item={item} r={r} core={r * 0.34} />
    </svg>
  );
}

// Status is never colour alone: hollow, half and full marks carry it too.
export function StatusMark({ status, size = 14 }) {
  return (
    <svg className={'status-mark ' + status} width={size} height={size} viewBox="-8 -8 16 16" aria-hidden="true">
      <circle r="6" className="rim" />
      {status === 'in_progress' && <path d="M0 -6A6 6 0 0 1 0 6Z" className="fill" />}
      {status === 'met' && <circle r="6" className="fill" />}
    </svg>
  );
}

export function StatusLabel({ status }) {
  return (
    <span className={'status-label ' + status}>
      <StatusMark status={status} />
      {STATUS[status]}
    </span>
  );
}

export function FieldEmblem({ field, atlas, size = 28 }) {
  const { dots, bearing } = emblem(field, atlas.sky, field.items);
  const tx = Math.cos(bearing);
  const ty = Math.sin(bearing);
  return (
    <svg className="emblem" width={size} height={size} viewBox="-15 -15 30 30" aria-hidden="true">
      <circle r="12.5" className="emblem-rim" />
      <line x1={tx * 12.5} y1={ty * 12.5} x2={tx * 15} y2={ty * 15} className="emblem-tick" />
      {dots.map((d, n) => (
        <circle key={n} cx={d.x * 0.6} cy={d.y * 0.6} r={d.lit ? 1.5 : 1.05} className={d.lit ? 'lit' : 'dot'} />
      ))}
    </svg>
  );
}

// The wordmark's glyph is a star read the way the atlas reads every star: a point inside a
// ring of four milestones, one of them in progress.
export function Wordmark() {
  return (
    <span className="wordmark">
      <svg width="26" height="26" viewBox="-13 -13 26 26" aria-hidden="true">
        <circle r="2.6" fill="#FFF1C9" className="wordmark-core" />
        {ringSegments(['in_progress', 'none', 'none', 'none'], 9).map((s, n) => (
          <path key={n} d={s.d} className={'seg ' + s.status} strokeWidth="1.6" />
        ))}
      </svg>
      <span className="wordmark-text">
        <span>Technology</span> <span>Atlas</span>
      </span>
    </span>
  );
}

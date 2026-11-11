import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'framer-motion';
import { ringSegments, starColor } from './glyphs.jsx';
import { chartCoord, claimPath, coreRadius, hash, LABEL, REGION_TYPE, starRadius, UNITS_ACROSS } from './sky.js';
import { EASE } from './motion.js';
import './sky.css';

// Levels of detail by zoom (k is screen pixels per world unit; the widest desktop view is
// about 1): far = regions, figures, names and warm stars; nearer = every star with its
// milestone ring; nearer still = IDs (and short titles in a focused constellation);
// nearest = titles.
const LOD = [0, 2.1, 3.6, 6.5];
const lodOf = (k) => LOD.filter((t) => k >= t).length - 1;
const K_MAX = 14;
// Claims across fields are drawn as arcs, so many together read as a sweep, not a scribble.
const ARC = 0.22;

function wrap(text, max) {
  const words = text.split(' ');
  const lines = [''];
  for (const w of words) {
    const line = lines[lines.length - 1];
    if (line && (line + ' ' + w).length > max) lines.push(w);
    else lines[lines.length - 1] = line ? line + ' ' + w : w;
  }
  return lines.length > 3 ? [...lines.slice(0, 2), lines[2] + '…'] : lines;
}

function truncate(text, max) {
  if (text.length <= max) return text;
  let cut = text.slice(0, max - 1);
  // Cut at a word's end: drop a word the limit split, and any trailing punctuation.
  if (/\S/.test(text[max - 1])) cut = cut.replace(/\s+\S*$/, '');
  return cut.replace(/[\s,;:-]+$/, '') + '…';
}

const fitBox = (box, w, h, pad, kMin, kMax) => {
  const k = Math.min((w - pad * 2) / Math.max(box.w, 1), (h - pad * 2) / Math.max(box.h, 1));
  return { cx: box.x + box.w / 2, cy: box.y + box.h / 2, k: Math.max(kMin, Math.min(kMax, k)) };
};

// A star with nothing met is a cool point of light; more milestones, a little larger and
// brighter. Amber and white-gold stay reserved for progress.
const DIM = '#C3CDE2';
const starFill = (item) => (item.glow > 0 ? starColor(item.glow) : DIM);
const starAlpha = (item) => (item.glow > 0 ? 1 : Math.min(1, 0.5 + 0.09 * item.status.length));

// Does the segment p–q cross the box?
function hits(p, q, b) {
  let t0 = 0;
  let t1 = 1;
  const dx = q.x - p.x;
  const dy = q.y - p.y;
  const edges = [
    [-dx, p.x - b.x],
    [dx, b.x + b.w - p.x],
    [-dy, p.y - b.y],
    [dy, b.y + b.h - p.y],
  ];
  for (const [pp, qq] of edges) {
    if (pp === 0) {
      if (qq < 0) return false;
    } else {
      const r = qq / pp;
      if (pp < 0) t0 = Math.max(t0, r);
      else t1 = Math.min(t1, r);
      if (t0 > t1) return false;
    }
  }
  return true;
}

const meets = (a, b) => !(a.x >= b.x + b.w || b.x >= a.x + a.w || a.y >= b.y + b.h || b.y >= a.y + a.h);

// ---------- The sky's structure: frame, graticule, region boundaries and names ----------

const Graticule = memo(function Graticule({ world, regions, fine, bare, names }) {
  const { frame, unit } = world;
  const x1 = world.w - frame;
  const y1 = world.h - frame;
  const across = UNITS_ACROSS;
  const down = Math.floor((y1 - frame) / unit);
  if (bare) return null;
  const lines = [];
  for (let u = 0; u <= across; u++) {
    const major = u % 4 === 0;
    if (!major && !fine) continue;
    const x = frame + u * unit;
    lines.push(<line key={'x' + u} x1={x} x2={x} y1={frame} y2={y1} className={major ? 'major' : 'minor'} />);
  }
  for (let u = 0; u <= down; u++) {
    const major = u % 4 === 0;
    if (!major && !fine) continue;
    const y = frame + u * unit;
    lines.push(<line key={'y' + u} x1={frame} x2={x1} y1={y} y2={y} className={major ? 'major' : 'minor'} />);
  }
  const ticks = [];
  for (let u = 0; u <= across; u++) {
    const x = frame + u * unit;
    const len = u % 4 === 0 ? 6 : 3;
    ticks.push(<line key={'t' + u} x1={x} x2={x} y1={frame} y2={frame - len} />);
    ticks.push(<line key={'b' + u} x1={x} x2={x} y1={y1} y2={y1 + len} />);
  }
  for (let u = 0; u <= down; u++) {
    const y = frame + u * unit;
    const len = u % 4 === 0 ? 6 : 3;
    ticks.push(<line key={'l' + u} x1={frame} x2={frame - len} y1={y} y2={y} />);
    ticks.push(<line key={'r' + u} x1={x1} x2={x1 + len} y1={y} y2={y} />);
  }
  // Boundaries between regions, dashed like the constellation boundaries of a printed chart.
  let bounds = '';
  const rows = [...new Set(regions.map((r) => r.row))];
  for (const row of rows) {
    const mine = regions.filter((r) => r.row === row);
    for (const r of mine.slice(1)) bounds += `M${r.x.toFixed(1)} ${r.y.toFixed(1)}V${(r.y + r.h).toFixed(1)}`;
    if (row > 0) bounds += `M${frame} ${mine[0].y.toFixed(1)}H${x1}`;
  }
  return (
    <g className="sky-structure" aria-hidden="true">
      <g className="sky-grid">{lines}</g>
      <path d={bounds} className="sky-bounds" />
      <rect x={frame} y={frame} width={x1 - frame} height={y1 - frame} className="sky-frame" />
      {!fine && <g className="sky-ticks">{ticks}</g>}
      {names && (
        <g className="sky-regions">
          {regions.map((r) => (
            <g key={r.name} transform={`translate(${r.label.x.toFixed(1)} ${r.label.y.toFixed(1)})`}>
              <g className="sky-label-scale">
                <text style={{ fontSize: REGION_TYPE.size }}>
                  {r.label.lines.map((w, n) => (
                    <tspan key={n} x="0" y={n * REGION_TYPE.lead} dy="0.8em">
                      {w}
                    </tspan>
                  ))}
                </text>
              </g>
            </g>
          ))}
        </g>
      )}
    </g>
  );
});

// ---------- Stars ----------

// Label text for a star, drawn in screen pixels from the top-left of its planned box.
function StarLabel({ item, plan }) {
  const { kind, end } = plan;
  const anchor = end ? 'end' : 'start';
  const x = 0;
  return (
    <g>
      <text className="sky-star-id" x={x} y="0" dy="0.8em" textAnchor={anchor}>
        {item.id}
      </text>
      {kind === 'short' && (
        <text className="sky-star-title short" x={x} y="13" dy="0.85em" textAnchor={anchor}>
          {truncate(item.title, 28)}
        </text>
      )}
      {kind === 'title' && (
        <text className="sky-star-title" x={x} y="13" textAnchor={anchor}>
          {wrap(item.title, 26).map((line, n) => (
            <tspan key={n} x={x} dy={n === 0 ? '0.95em' : '1.2em'}>
              {line}
            </tspan>
          ))}
        </text>
      )}
    </g>
  );
}

const Star = memo(function Star({ item, lod, state, plan, crossing, interactive, tabbable, onSelect, onHover }) {
  const r = starRadius(item.status.length);
  const core = coreRadius(item.status.length);
  const warm = item.glow > 0;
  const active = state === 'selected' || state === 'hovered';
  const live = interactive && lod >= 1;
  const props = live
    ? {
        tabIndex: tabbable ? 0 : -1,
        role: 'button',
        'aria-label': `${item.id}: ${item.title}. ${item.met} of ${item.status.length} milestones met, ${item.moving} in progress.`,
        onClick: (e) => {
          e.stopPropagation();
          onSelect(item.id);
        },
        onKeyDown: (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            e.stopPropagation();
            onSelect(item.id);
          }
        },
        onPointerEnter: () => onHover(item.id),
        onPointerLeave: () => onHover(null),
        onFocus: () => onHover(item.id),
        onBlur: () => onHover(null),
      }
    : {};
  return (
    <g
      className={'sky-star ' + state + (warm ? ' warm' : '') + (live ? ' live' : '')}
      transform={`translate(${item.x.toFixed(2)} ${item.y.toFixed(2)})`}
      {...props}
    >
      {live && <circle r={r + 2.5} className="sky-star-hit" />}
      {item.recent && <circle r={r + 0.6} className="sky-pulse" />}
      {lod >= 1 ? (
        // Close up, a star stays a point of light: its core is sized on screen, not in the sky.
        <g className="sky-screen">
          <circle r={1.3 + 0.32 * item.status.length} fill={starFill(item)} opacity={starAlpha(item)} className="sky-star-core" />
          {warm && <circle r={1.1} className="sky-star-heart" />}
        </g>
      ) : (
        <circle r={core} fill={starFill(item)} opacity={starAlpha(item)} className="sky-star-core" />
      )}
      {crossing && (
        // A quiet mark: this star has a claim with another field, drawn on hover or focus.
        <g className="sky-screen">
          <path d={lod >= 1 ? 'M7 -9.5L10.5 -13' : 'M3.2 -4.2L5.6 -6.6'} className="sky-cross" />
        </g>
      )}
      {lod >= 1 &&
        ringSegments(item.status, r).map((seg, n) => <path key={n} d={seg.d} className={'sky-seg ' + seg.status} />)}
      {active && (
        <g className="sky-reticle">
          <circle r={r + 2.2} />
          <line y1={-(r + 2.2)} y2={-(r + 4.6)} />
          <line y1={r + 2.2} y2={r + 4.6} />
          <line x1={-(r + 2.2)} x2={-(r + 4.6)} />
          <line x1={r + 2.2} x2={r + 4.6} />
        </g>
      )}
      {plan && (
        // Placed in the sky, sized on screen: as the view closes in the label shrinks within
        // the room it was given, so it never drifts onto a line it was placed clear of.
        <g transform={`translate(${plan.wx.toFixed(2)} ${plan.wy.toFixed(2)})`}>
          <g className="sky-screen">
            <StarLabel item={item} plan={plan} />
          </g>
        </g>
      )}
    </g>
  );
});

// ---------- Constellations ----------

const Constellation = memo(function Constellation({
  field,
  fig,
  lod,
  state,
  selected,
  hovered,
  linked,
  plan,
  crossing,
  labels,
  interactive,
  delay,
  onFocusField,
  onHoverField,
  onSelect,
  onHoverStar,
}) {
  const d = fig.edges
    .map(([a, b]) => {
      const p = field.byId[a];
      const q = field.byId[b];
      return `M${p.x.toFixed(2)} ${p.y.toFixed(2)}L${q.x.toFixed(2)} ${q.y.toFixed(2)}`;
    })
    .join('');
  const linkedSet = linked ? new Set(linked.split(' ')) : null;
  const starState = (item) => {
    if (item.id === selected) return 'selected';
    if (item.id === hovered) return 'hovered';
    if (state === 'dim') return linkedSet?.has(item.id) ? 'linked' : 'dim';
    return 'rest';
  };
  const box = fig.box;
  return (
    <g
      className={'sky-con ' + state}
      style={{ '--d': delay.toFixed(2) + 's' }}
      onPointerEnter={interactive ? () => onHoverField(field.id) : undefined}
      onPointerLeave={interactive ? () => onHoverField(null) : undefined}
    >
      <g className="sky-con-body">
        {interactive && (
          <rect
            x={box.x - 5}
            y={box.y - 5}
            width={box.w + 10}
            height={box.h + 8}
            rx="4"
            className="sky-con-hit"
            onClick={(e) => {
              e.stopPropagation();
              onFocusField(field.id);
            }}
          />
        )}
        <ellipse
          cx={fig.x}
          cy={fig.y}
          rx={box.w * 0.62}
          ry={(box.h - fig.label.lines.length * LABEL.line) * 0.75 + 6}
          className="sky-con-glow"
        />
        <path d={d} pathLength="1" className="sky-fig" />
        {field.items.map((item) => (
          <Star
            key={item.id}
            item={item}
            lod={lod}
            state={starState(item)}
            plan={plan?.get(item.id) || null}
            crossing={crossing.has(item.id)}
            interactive={interactive}
            tabbable={interactive && state === 'focus'}
            onSelect={onSelect}
            onHover={onHoverStar}
          />
        ))}
        {labels && (
          <g transform={`translate(${fig.label.x.toFixed(2)} ${fig.label.y.toFixed(2)})`} className="sky-name">
            <g className="sky-label-scale">
              <text textAnchor="middle" style={{ fontSize: LABEL.size }}>
                {fig.label.lines.map((line, n) => (
                  // Tracking adds space after the last letter too; shift by half to centre.
                  <tspan key={n} x={LABEL.size * 0.04} y={n * LABEL.line} dy="0.8em">
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          </g>
        )}
      </g>
    </g>
  );
});

// ---------- Claim lines ----------

function useClaims(atlas) {
  return useMemo(
    () =>
      atlas.links.map((l, n) => {
        const a = atlas.items[l.from];
        const b = atlas.items[l.to];
        const cross = a.field !== b.field;
        const path = claimPath(a, b, starRadius(b.status.length) + 1.6, cross ? ARC : 0);
        return { ...l, n, path, a, b, cross };
      }),
    [atlas],
  );
}

function Arrow({ path }) {
  return (
    <g transform={`translate(${path.tip.x.toFixed(2)} ${path.tip.y.toFixed(2)})`}>
      <g className="sky-screen">
        <path d="M-5.5 -3.2L0 0L-5.5 3.2" transform={`rotate(${path.angle.toFixed(1)})`} className="sky-arrow" />
      </g>
    </g>
  );
}

// At rest only the claims inside a constellation are drawn, faintly; claims between fields
// would cross the whole sky, so they wait for a hover, a focus or the "all claims" switch.
const RestingClaims = memo(function RestingClaims({ claims }) {
  return (
    <g className="sky-claims-in" aria-hidden="true">
      <g className="sky-claims rest">
        {claims
          .filter((c) => !c.cross)
          .map((c) => (
            <g key={c.n}>
              <path d={c.path.d} stroke={`url(#claim-${c.n})`} className="sky-claim" />
              <Arrow path={c.path} />
            </g>
          ))}
      </g>
    </g>
  );
});

// ---------- Screen-edge rulers ----------

const STEPS = [16, 8, 4, 2, 1, 0.5, 0.25];

function Rulers({ subscribe, inset }) {
  const [v, setV] = useState(null);
  useEffect(() => subscribe(setV), [subscribe]);
  if (!v) return null;
  const { cx, cy, k, w, h, oy, unit, frame } = v;
  const ox = (w - inset) / 2;
  const px = unit * k;
  const step = [...STEPS].reverse().find((s) => s * px >= 72) || STEPS[0];
  const toX = (u) => ox + (frame + u * unit - cx) * k;
  const toY = (u) => oy + (frame + u * unit - cy) * k;
  const fromX = (sx) => ((sx - ox) / k + cx - frame) / unit;
  const fromY = (sy) => ((sy - oy) / k + cy - frame) / unit;
  const fmt = (u) => (step < 1 ? u.toFixed(step < 0.5 ? 2 : 1) : String(u));
  const ticks = (from, to, axis) => {
    const out = [];
    const minor = step / 4;
    for (let u = Math.ceil(from / minor) * minor; u <= to; u += minor) {
      const major = Math.abs(u / step - Math.round(u / step)) < 1e-6;
      const at = axis === 'x' ? toX(u) : toY(u);
      out.push({ u: Math.round(u * 1000) / 1000, at, major });
    }
    return out;
  };
  const xs = ticks(fromX(0), fromX(w - inset), 'x');
  const ys = ticks(fromY(0), fromY(h), 'y');
  return (
    <svg className="sky-rulers" width={w} height={h} aria-hidden="true">
      <g className="sky-ruler">
        {xs.map((t) => (
          <g key={'x' + t.u} transform={`translate(${t.at.toFixed(1)} 0)`}>
            <line y1="0" y2={t.major ? 7 : 3.5} />
            {t.major && (
              <text x="3" y="16">
                {fmt(t.u)}
              </text>
            )}
          </g>
        ))}
        {ys.map((t) => (
          <g key={'y' + t.u} transform={`translate(0 ${t.at.toFixed(1)})`}>
            <line x1="0" x2={t.major ? 7 : 3.5} />
            {t.major && t.at > 26 && (
              <text x="10" y="3.5">
                {fmt(t.u)}
              </text>
            )}
          </g>
        ))}
      </g>
    </svg>
  );
}

// ---------- The chart ----------

export default function Chart({
  atlas,
  interactive = false,
  focusField = null,
  selected = null,
  highlight = null,
  highlightField = null,
  allClaims = false,
  onSelect = () => {},
  onFocusField = () => {},
  onHover = () => {},
  intro = false,
  inset = { right: 0 },
  pad = 24,
  labels = true,
  className = '',
}) {
  const still = useReducedMotion();
  const sky = atlas.sky;
  const world = sky.world;
  const wrapRef = useRef(null);
  const svg = useRef(null);
  const worldRef = useRef(null);
  const view = useRef({ cx: world.w / 2, cy: world.h / 2, k: 1 });
  const glide = useRef(null);
  const listeners = useRef(new Set());
  const [size, setSize] = useState(null);
  const [lod, setLod] = useState(0);
  const [kq, setKq] = useState(1);
  const [visible, setVisible] = useState('');
  const [hover, setHover] = useState(null);
  const [hoverField, setHoverField] = useState(null);
  // The intro is an enhancement: the sky is drawn in its final state, and only animates in
  // when the page is visible at mount. The class comes off after the intro either way, so
  // nothing waits on an animation finishing (a hidden tab never runs one).
  const [introOn, setIntroOn] = useState(() => intro && typeof document !== 'undefined' && !document.hidden);
  useEffect(() => {
    if (!introOn) return undefined;
    const t = setTimeout(() => setIntroOn(false), 2600);
    return () => clearTimeout(t);
  }, [introOn]);
  const drag = useRef(null);
  const insetRight = inset?.right || 0;
  const insetTop = inset?.top || 0;
  const insetBottom = inset?.bottom || 0;
  // The centre of the part of the chart left free by panels over it.
  const oyOf = (h) => insetTop + (h - insetTop - insetBottom) / 2;
  // A backdrop without names (the phone hero) is figures only: no frame, grid or claims.
  const bare = !interactive && !labels;
  const names = interactive;

  // Fields with their stars looked up by ID, for figure lines.
  const fields = useMemo(
    () =>
      atlas.fields.map((f) => ({
        ...f,
        byId: Object.fromEntries(f.items.map((i) => [i.id, i])),
      })),
    [atlas],
  );
  const claims = useClaims(atlas);
  const warm = useMemo(() => Object.values(atlas.items).filter((i) => i.glow > 0), [atlas]);
  // Stars with a claim to or from another field, by field.
  const crossing = useMemo(() => {
    const out = Object.fromEntries(atlas.fields.map((f) => [f.id, new Set()]));
    for (const c of claims) {
      if (!c.cross) continue;
      out[c.a.field].add(c.a.id);
      out[c.b.field].add(c.b.id);
    }
    return out;
  }, [atlas, claims]);
  const none = useMemo(() => new Set(), []);

  const apply = useCallback(() => {
    if (!size || !worldRef.current) return;
    const { cx, cy, k } = view.current;
    const ox = (size.w - insetRight) / 2;
    const oy = oyOf(size.h);
    worldRef.current.setAttribute(
      'transform',
      `translate(${(ox - cx * k).toFixed(2)} ${(oy - cy * k).toFixed(2)}) scale(${k})`,
    );
    const style = svg.current.style;
    if (style.getPropertyValue('--k') !== String(k)) {
      style.setProperty('--k', k);
      style.setProperty('--ik', 1 / k);
      // Names are set at 10 units. From the widest desktop view in, they read at 10 to 11
      // pixels and then hold still on screen; on smaller boxes they shrink with the sky.
      const shown = k >= 0.88 ? Math.min(Math.max(k, 1), 1.1) : k / 0.88;
      style.setProperty('--ls', shown / k);
    }
    const level = lodOf(k);
    setLod(level);
    setKq(Math.pow(2, Math.floor(Math.log2(k) * 3) / 3));
    if (level >= 1) {
      const x0 = cx - ox / k;
      const x1 = cx + (size.w - ox) / k;
      const y0 = cy - oy / k;
      const y1 = cy + (size.h - oy) / k;
      const ids = atlas.fields
        .filter((f) => {
          const b = sky.figures[f.id].box;
          return b.x < x1 && b.x + b.w > x0 && b.y < y1 && b.y + b.h > y0;
        })
        .map((f) => f.id)
        .join(' ');
      setVisible(ids);
    }
    for (const fn of listeners.current) fn({ cx, cy, k, w: size.w, h: size.h, oy, unit: world.unit, frame: world.frame });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size, insetRight, insetTop, insetBottom, atlas, sky, world]);

  const subscribe = useCallback(
    (fn) => {
      listeners.current.add(fn);
      apply();
      return () => listeners.current.delete(fn);
    },
    [apply],
  );

  useLayoutEffect(() => {
    const el = wrapRef.current;
    const measure = () => {
      const box = el.getBoundingClientRect();
      if (box.width && box.height) setSize({ w: box.width, h: box.height });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // The whole sky: contained in the chart (interactive) or covering it (a backdrop).
  const whole = useMemo(() => {
    if (!size) return null;
    const w = size.w - insetRight;
    const contain = Math.min((w - pad * 2) / world.w, (size.h - insetTop - insetBottom - pad * 2) / world.h);
    const cover = Math.max(size.w / world.w, size.h / world.h);
    return { cx: world.w / 2, cy: world.h / 2, k: interactive ? contain : cover };
  }, [size, insetRight, insetTop, insetBottom, pad, world, interactive]);

  const target = useMemo(() => {
    if (!whole) return null;
    const w = size.w - insetRight;
    if (selected && atlas.items[selected]) {
      const s = atlas.items[selected];
      return { cx: s.x, cy: s.y, k: Math.max(6.8, Math.min(view.current.k, K_MAX)) };
    }
    if (focusField && sky.figures[focusField]) {
      return fitBox(sky.figures[focusField].box, w, size.h - insetTop - insetBottom, Math.max(pad, 120), whole.k, 6.4);
    }
    return whole;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atlas, sky, size, whole, focusField, selected, insetRight, pad]);

  const lastSize = useRef(null);
  useLayoutEffect(() => {
    if (!target) return;
    glide.current?.stop();
    // A new box (first measure, a resize) snaps; a new subject glides. A hidden page snaps
    // too, since nothing would draw the glide.
    const resized = lastSize.current !== size;
    lastSize.current = size;
    if (resized || still || document.hidden) {
      view.current = { cx: target.cx, cy: target.cy, k: target.k };
      apply();
      return;
    }
    const from = { ...view.current };
    glide.current = animate(0, 1, {
      duration: 1.15,
      ease: EASE,
      onUpdate: (t) => {
        const k = Math.exp(Math.log(from.k) + (Math.log(target.k) - Math.log(from.k)) * t);
        // Move in proportion to the change of scale, so the target slides in steadily on
        // screen instead of racing at the end of a deep zoom.
        const span = 1 / from.k - 1 / target.k;
        const p = Math.abs(span) > 1e-6 ? (1 / from.k - 1 / k) / span : t;
        view.current = {
          cx: from.cx + (target.cx - from.cx) * p,
          cy: from.cy + (target.cy - from.cy) * p,
          k,
        };
        apply();
      },
      onComplete: () => {
        view.current = { cx: target.cx, cy: target.cy, k: target.k };
        apply();
      },
    });
  }, [target, apply, still]);

  const kMin = () => (whole?.k || 0.3) * 0.8;

  const zoomAt = (px, py, factor) => {
    const { cx, cy, k } = view.current;
    const k2 = Math.max(kMin(), Math.min(K_MAX, k * factor));
    const ox = (size.w - insetRight) / 2;
    const oy = oyOf(size.h);
    const wx = cx + (px - ox) / k;
    const wy = cy + (py - oy) / k;
    view.current = { cx: wx - (px - ox) / k2, cy: wy - (py - oy) / k2, k: k2 };
    apply();
  };

  // Wheel zoom about the cursor.
  useEffect(() => {
    if (!interactive || !svg.current || !size) return undefined;
    const el = svg.current;
    const wheel = (e) => {
      e.preventDefault();
      glide.current?.stop();
      const box = el.getBoundingClientRect();
      const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      zoomAt(e.clientX - box.left, e.clientY - box.top, Math.exp(-delta * 0.0018));
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  });

  const zoomBy = (factor) => {
    glide.current?.stop();
    const from = { ...view.current };
    const to = Math.max(kMin(), Math.min(K_MAX, from.k * factor));
    if (still) {
      view.current = { ...from, k: to };
      apply();
      return;
    }
    glide.current = animate(from.k, to, {
      duration: 0.5,
      ease: EASE,
      onUpdate: (k) => {
        view.current = { ...view.current, k };
        apply();
      },
    });
  };

  const reset = () => {
    onSelect(null);
    onFocusField(null);
    if (!selected && !focusField && whole) {
      glide.current?.stop();
      const from = { ...view.current };
      glide.current = animate(0, 1, {
        duration: still ? 0 : 0.9,
        ease: EASE,
        onUpdate: (t) => {
          view.current = {
            cx: from.cx + (whole.cx - from.cx) * t,
            cy: from.cy + (whole.cy - from.cy) * t,
            k: Math.exp(Math.log(from.k) + (Math.log(whole.k) - Math.log(from.k)) * t),
          };
          apply();
        },
      });
    }
  };

  const pointerDown = (e) => {
    if (!interactive || e.button !== 0) return;
    glide.current?.stop();
    drag.current = { x: e.clientX, y: e.clientY, moved: 0, id: e.pointerId };
  };
  const pointerMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    d.moved += Math.abs(dx) + Math.abs(dy);
    if (d.moved > 4 && !d.captured) {
      svg.current.setPointerCapture(d.id);
      d.captured = true;
      setHover(null);
      setHoverField(null);
      wrapRef.current.classList.add('dragging');
    }
    d.x = e.clientX;
    d.y = e.clientY;
    if (!d.captured) return;
    const { k } = view.current;
    view.current = { ...view.current, cx: view.current.cx - dx / k, cy: view.current.cy - dy / k };
    apply();
  };
  const pointerUp = () => {
    const d = drag.current;
    drag.current = null;
    wrapRef.current?.classList.remove('dragging');
    if (d && d.moved > 4) {
      // Swallow the click that ends a drag.
      const stop = (ev) => {
        ev.stopPropagation();
        window.removeEventListener('click', stop, true);
      };
      window.addEventListener('click', stop, true);
      setTimeout(() => window.removeEventListener('click', stop, true), 0);
    }
  };

  const keyDown = (e) => {
    if (!interactive) return;
    const step = 60 / view.current.k;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[e.key] && e.target === wrapRef.current) {
      e.preventDefault();
      glide.current?.stop();
      view.current = { ...view.current, cx: view.current.cx + moves[e.key][0], cy: view.current.cy + moves[e.key][1] };
      apply();
    } else if (e.key === '+' || e.key === '=') zoomBy(1.4);
    else if (e.key === '-') zoomBy(1 / 1.4);
    else if (e.key === 'Escape') {
      if (selected) onSelect(null);
      else if (focusField) onFocusField(null);
    }
  };

  const hoverStar = useCallback(
    (id) => {
      if (drag.current?.captured) return;
      setHover(id);
      onHover(id);
    },
    [onHover],
  );
  const hoverFieldAt = useCallback((id) => {
    if (drag.current?.captured) return;
    setHoverField(id);
  }, []);
  const selectStar = useCallback((id) => onSelect(id), [onSelect]);
  const focusAt = useCallback((id) => onFocusField(id), [onFocusField]);

  const hovered = hover || highlight;
  const active = selected || hovered;
  const liftField = hoverField || highlightField;
  const activeField = active ? atlas.items[active]?.field : null;

  // Claims in full: every one with the switch on; otherwise those of the focused or lifted
  // constellation, and of the active star's constellation.
  const fieldOf = (id) => atlas.items[id].field;
  const touching = (l) => {
    if (allClaims) return true;
    const fs = [fieldOf(l.from), fieldOf(l.to)];
    return (
      (focusField && fs.includes(focusField)) ||
      (activeField && fs.includes(activeField)) ||
      (!focusField && liftField && fs.includes(liftField))
    );
  };
  const shown = interactive ? claims.filter(touching) : [];
  const shownKey = shown.map((c) => c.n).join(',');
  const linkedByField = useMemo(() => {
    const out = {};
    for (const c of shown) {
      for (const it of [c.a, c.b]) (out[it.field] ||= new Set()).add(it.id);
    }
    return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, [...v].sort().join(' ')]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shownKey]);

  const visibleSet = useMemo(() => new Set(visible.split(' ')), [visible]);

  // Which stars get a label, how much, and on which side: greedily, most important first.
  // Each label tries the right, left, below and above of its star, and takes the first spot
  // that covers no other label, star, constellation name, figure line or drawn claim.
  const plans = useMemo(() => {
    if (lod < 2 || !interactive) return {};
    const k = kq;
    const out = {};
    const considered = atlas.fields.filter((f) => visibleSet.has(f.id) && (!focusField || f.id === focusField));
    const items = considered.flatMap((f) => f.items);
    const taken = [];
    const segs = [];
    for (const f of considered) {
      const fig = sky.figures[f.id];
      for (const [a, b] of fig.edges) segs.push([atlas.items[a], atlas.items[b]]);
      // The constellation's name, at the size it is drawn at this zoom (see --ls).
      const sc = (k >= 0.88 ? Math.min(Math.max(k, 1), 1.1) : k / 0.88) / k;
      const lw = Math.max(...fig.label.lines.map((l) => l.length)) * LABEL.char * sc;
      taken.push({ x: fig.label.x - lw / 2, y: fig.label.y, w: lw, h: fig.label.lines.length * LABEL.line * sc });
      for (const i of f.items) {
        const r = starRadius(i.status.length);
        taken.push({ x: i.x - r, y: i.y - r, w: r * 2, h: r * 2, star: i.id });
      }
    }
    for (const c of claims) {
      if (c.cross && !shown.includes(c)) continue;
      const pts = c.path.points;
      for (let n = 1; n < pts.length; n++) segs.push([pts[n - 1], pts[n]]);
    }
    const priority = (i) =>
      i.id === selected ? 0 : i.id === hovered ? 1 : i.glow > 0 ? 2 : i.field === focusField ? 3 : 4;
    items.sort((a, b) => priority(a) - priority(b) || a.depth - b.depth || a.id.localeCompare(b.id));
    const kinds = lod >= 3 ? ['title', 'short', 'id'] : focusField ? ['short', 'id'] : ['id'];
    for (const i of items) {
      const gap = starRadius(i.status.length) * k + 6;
      let chosen = null;
      for (const kind of i.id === selected || i.id === hovered ? ['title', 'short', 'id'] : kinds) {
        const lines = kind === 'title' ? wrap(i.title, 26).length : 0;
        const w = kind === 'id' ? 8 + i.id.length * 6.6 : kind === 'short' ? 178 : 182;
        const h = kind === 'id' ? 13 : kind === 'short' ? 30 : 17 + lines * 15.4;
        const sides = [
          { ox: gap, oy: -h / 2 + (kind === 'id' ? 0 : 6), end: false },
          { ox: -gap - w, oy: -h / 2 + (kind === 'id' ? 0 : 6), end: true },
          { ox: -w / 2 + 20, oy: gap - 2, end: false },
          { ox: -w / 2 + 20, oy: -gap - h + 2, end: false },
        ];
        for (const side of sides) {
          const box = { x: i.x + side.ox / k, y: i.y + side.oy / k, w: w / k, h: h / k };
          // Glyphs reach a little above the box's top line; keep a margin round the text.
          const room = { x: box.x - 2 / k, y: box.y - 4 / k, w: box.w + 4 / k, h: box.h + 6 / k };
          const clear =
            taken.every((b) => b.star === i.id || !meets(room, b)) && segs.every(([p, q]) => !hits(p, q, room));
          if (clear) {
            chosen = { kind, end: side.end, box, wx: box.x - i.x + (side.end ? box.w : 0), wy: box.y - i.y };
            break;
          }
        }
        if (chosen) break;
      }
      if (!chosen && (i.id === selected || i.id === hovered)) {
        const w = 182;
        chosen = { kind: 'title', end: false, box: { x: i.x + gap / k, y: i.y - 10 / k, w: w / k, h: 60 / k }, wx: gap / k, wy: -10 / k };
      }
      if (!chosen) continue;
      taken.push(chosen.box);
      (out[i.field] ||= new Map()).set(i.id, chosen);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atlas, sky, claims, shownKey, lod, kq, visibleSet, focusField, selected, hovered, interactive]);
  const intoView = (fx) => 0.15 + (fx / world.w) * 0.95 + (hash(String(Math.round(fx))) % 100) / 1000;

  // A backdrop drifts slowly across whatever part of the sky does not fit its box.
  const drift = !interactive && size && whole ? Math.max(0, (world.w * whole.k - size.w) / 2) : 0;

  return (
    <div
      ref={wrapRef}
      className={'sky-chart ' + (interactive ? 'interactive ' : 'backdrop ') + (bare ? 'bare ' : '') + className}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={keyDown}
      aria-label={
        interactive ? 'Star chart. Drag or use arrow keys to pan, plus and minus to zoom, Escape to step back.' : undefined
      }
      role={interactive ? 'application' : undefined}
      aria-hidden={interactive ? undefined : true}
    >
      {interactive && (
        <div className="sky-zoom" role="group" aria-label="Zoom">
          <button type="button" onClick={() => zoomBy(1.6)} aria-label="Zoom in">
            <svg viewBox="-8 -8 16 16" width="14" height="14" aria-hidden="true">
              <path d="M-5 0H5M0 -5V5" />
            </svg>
          </button>
          <button type="button" onClick={() => zoomBy(1 / 1.6)} aria-label="Zoom out">
            <svg viewBox="-8 -8 16 16" width="14" height="14" aria-hidden="true">
              <path d="M-5 0H5" />
            </svg>
          </button>
          <button type="button" onClick={reset} aria-label="Show the whole sky">
            <svg viewBox="-8 -8 16 16" width="14" height="14" aria-hidden="true">
              <rect x="-6" y="-4.2" width="12" height="8.4" />
              <path d="M-2 0H2M0 -2V2" />
            </svg>
          </button>
        </div>
      )}
      <svg
        ref={svg}
        width="100%"
        height="100%"
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={pointerUp}
        onClick={() => interactive && selected && onSelect(null)}
        style={{ '--k': 1, '--ik': 1, '--ls': 1, '--drift': drift + 'px' }}
      >
        <defs>
          <radialGradient id="sky-halo">
            <stop offset="0%" stopColor="#FFD08A" stopOpacity="0.6" />
            <stop offset="22%" stopColor="#FFB454" stopOpacity="0.25" />
            <stop offset="55%" stopColor="#FFB454" stopOpacity="0.07" />
            <stop offset="100%" stopColor="#FFB454" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="sky-halo-met">
            <stop offset="0%" stopColor="#FFF8E6" stopOpacity="0.7" />
            <stop offset="25%" stopColor="#FFF1C9" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#FFF1C9" stopOpacity="0" />
          </radialGradient>
          {claims.map((c) => (
            <linearGradient
              key={c.n}
              id={`claim-${c.n}`}
              gradientUnits="userSpaceOnUse"
              x1={c.a.x}
              y1={c.a.y}
              x2={c.path.tip.x}
              y2={c.path.tip.y}
            >
              <stop offset="0" stopColor="#7FB2FF" stopOpacity="1" />
              <stop offset="1" stopColor="#7FB2FF" stopOpacity="0.3" />
            </linearGradient>
          ))}
        </defs>
        <g className={drift > 1 && !still ? 'sky-drift' : undefined}>
          <g
            ref={worldRef}
            className={
              'sky-world lod-' +
              lod +
              (focusField ? ' focused' : '') +
              (active ? ' has-active' : '') +
              (allClaims ? ' all-claims' : '') +
              (introOn && !still ? ' intro' : '')
            }
          >
            <Graticule world={world} regions={sky.regions} fine={lod >= 1} bare={bare} names={names} />
            {!bare && <RestingClaims claims={claims} />}
            {fields.map((f) => {
              const fig = sky.figures[f.id];
              const state =
                focusField === f.id ? 'focus' : focusField ? 'dim' : liftField === f.id ? 'hover' : 'rest';
              return (
                <Constellation
                  key={f.id}
                  field={f}
                  fig={fig}
                  lod={lod >= 1 && visibleSet.has(f.id) ? lod : 0}
                  state={state}
                  selected={selected && atlas.items[selected]?.field === f.id ? selected : null}
                  hovered={hovered && atlas.items[hovered]?.field === f.id ? hovered : null}
                  linked={linkedByField[f.id] || ''}
                  labels={labels && interactive}
                  plan={plans[f.id]}
                  crossing={interactive && !allClaims ? crossing[f.id] : none}
                  interactive={interactive}
                  delay={intoView(fig.x)}
                  onFocusField={focusAt}
                  onHoverField={hoverFieldAt}
                  onSelect={selectStar}
                  onHoverStar={hoverStar}
                />
              );
            })}
            <g className="sky-claims full" aria-hidden="true">
              {shown.map((c) => (
                <g key={`${c.n}-${focusField}-${activeField}-${liftField}-${allClaims}`} className={still ? '' : 'drawn'}>
                  <path d={c.path.d} pathLength="1" stroke={`url(#claim-${c.n})`} className="sky-claim" />
                  <g className="sky-arrow-in">
                    <Arrow path={c.path} />
                  </g>
                </g>
              ))}
            </g>
            <g className="sky-beacons" aria-hidden="true">
              {warm.map((i) => (
                <g key={i.id} transform={`translate(${i.x.toFixed(2)} ${i.y.toFixed(2)})`}>
                  <g className="sky-screen">
                    <circle r={lod >= 1 ? 20 : 16} fill={i.glow >= 1 ? 'url(#sky-halo-met)' : 'url(#sky-halo)'} />
                    {lod === 0 && (
                      <>
                        <circle r="6.5" className={'sky-beacon-ring' + (i.glow >= 1 ? ' met' : '')} />
                        <circle r="2.2" fill={starColor(i.glow)} />
                      </>
                    )}
                  </g>
                </g>
              ))}
            </g>
          </g>
        </g>
      </svg>
      {interactive && <Rulers subscribe={subscribe} inset={insetRight} />}
    </div>
  );
}

// ---------- The locator: the whole sky in miniature, not interactive ----------

// Shows where a constellation (and optionally one star) sits in the sky: every star as a
// point, the field's figure drawn and bracketed, the star fixed by crosshairs to the frame.
// `size` is the locator's height-equivalent from the old square locator; the flat sky is
// drawn about one and a half times as wide.
export function Locator({ atlas, field, star, size = 132, width }) {
  const sky = atlas.sky;
  const { w, h, frame } = sky.world;
  const f = field && atlas.field[field];
  const fig = f && sky.figures[field];
  const s = star && atlas.items[star];
  // The locator shows the frame and what is inside it, without the chart's outer margin.
  const vx = frame - 6;
  const vw = w - (frame - 6) * 2;
  const vh = h - (frame - 6) * 2;
  const px = width || Math.round(size * 1.5);
  const scale = px / vw;
  const stroke = (n) => n / scale; // n screen pixels in world units
  const all = useMemo(() => {
    let figures = '';
    for (const x of atlas.fields) {
      for (const [a, b] of sky.figures[x.id].edges) {
        const p = atlas.items[a];
        const q = atlas.items[b];
        figures += `M${p.x.toFixed(1)} ${p.y.toFixed(1)}L${q.x.toFixed(1)} ${q.y.toFixed(1)}`;
      }
    }
    return figures;
  }, [atlas, sky]);
  const mine = useMemo(() => {
    if (!fig) return '';
    return fig.edges
      .map(([a, b]) => `M${atlas.items[a].x.toFixed(1)} ${atlas.items[a].y.toFixed(1)}L${atlas.items[b].x.toFixed(1)} ${atlas.items[b].y.toFixed(1)}`)
      .join('');
  }, [atlas, fig]);
  const coord = s ? chartCoord(s, sky) : null;
  const corner = (x, y, dx, dy) => `M${x + dx} ${y}H${x}V${y + dy}`;
  const box = fig?.box;
  const m = stroke(5);
  return (
    <svg
      className="sky-locator"
      width={px}
      height={Math.round((px * vh) / vw)}
      viewBox={`${vx} ${vx} ${vw} ${vh}`}
      role="img"
      aria-label={
        s
          ? `${s.id} sits at chart coordinate ${coord.text}, in ${f?.name || 'the sky'}`
          : f
            ? `Where ${f.name} sits in the sky`
            : 'The whole sky'
      }
    >
      <rect x={frame} y={frame} width={w - frame * 2} height={h - frame * 2} className="loc-frame" style={{ strokeWidth: stroke(1) }} />
      <path
        d={sky.regions
          .filter((r) => r.x > frame + 1 || r.y > frame + 1)
          .map((r) => (r.x > frame + 1 ? `M${r.x} ${r.y}V${r.y + r.h}` : '') + (r.y > frame + 1 && r.x <= frame + 1 ? `M${frame} ${r.y}H${w - frame}` : ''))
          .join('')}
        className="loc-bounds"
        style={{ strokeWidth: stroke(0.7), strokeDasharray: `${stroke(2.5)} ${stroke(2.5)}` }}
      />
      <path d={all} className="loc-figures" style={{ strokeWidth: stroke(0.6) }} />
      {Object.values(atlas.items).map((i) => (
        <circle
          key={i.id}
          cx={i.x}
          cy={i.y}
          r={stroke(i.glow > 0 ? 1.6 : f && i.field === field ? 1.1 : 0.75)}
          className={'loc-dot' + (f && i.field === field ? ' in' : '') + (i.glow > 0 ? ' lit' : '')}
        />
      ))}
      {fig && (
        <>
          <path d={mine} className="loc-mine" style={{ strokeWidth: stroke(1.1) }} />
          <path
            d={[
              corner(box.x - m, box.y - m, 3 * m, 3 * m),
              corner(box.x + box.w + m, box.y - m, -3 * m, 3 * m),
              corner(box.x - m, box.y + box.h + m, 3 * m, -3 * m),
              corner(box.x + box.w + m, box.y + box.h + m, -3 * m, -3 * m),
            ].join('')}
            className="loc-bracket"
            style={{ strokeWidth: stroke(1.2) }}
          />
        </>
      )}
      {s && (
        <g className="loc-fix" style={{ strokeWidth: stroke(0.8) }}>
          <line x1={frame} x2={s.x - stroke(6)} y1={s.y} y2={s.y} />
          <line x1={s.x + stroke(6)} x2={w - frame} y1={s.y} y2={s.y} />
          <line x1={s.x} x2={s.x} y1={frame} y2={s.y - stroke(6)} />
          <line x1={s.x} x2={s.x} y1={s.y + stroke(6)} y2={h - frame} />
          <circle cx={s.x} cy={s.y} r={stroke(4)} style={{ strokeWidth: stroke(1.2) }} />
        </g>
      )}
    </svg>
  );
}

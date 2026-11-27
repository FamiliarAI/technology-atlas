import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'framer-motion';
import { ringSegments } from './glyphs.jsx';
import { onPaper } from './style.js';
import { chartCoord, hash, LABEL, REGION_TYPE, starRadius, UNITS_ACROSS } from './sky.js';
import { EASE } from './motion.js';
import './sky.css';

// Levels of detail by zoom (k is screen pixels per world unit; the widest desktop view is
// about 1): far = regions, figures, names and each star as a point shaded by its milestones;
// nearer = every star with its milestone ring; nearer still = IDs.
const LOD = [0, 2.1, 3.6];
const lodOf = (k) => LOD.filter((t) => k >= t).length - 1;
const K_MAX = 14;

function wrap(text, max) {
  const words = text.split(' ');
  const lines = [''];
  for (const w of words) {
    const line = lines[lines.length - 1];
    if (line && (line + ' ' + w).length > max) lines.push(w);
    else lines[lines.length - 1] = line ? line + ' ' + w : w;
  }
  return lines.length > 4 ? [...lines.slice(0, 3), lines[3] + '…'] : lines;
}

const fitBox = (box, w, h, pad, kMin, kMax) => {
  const k = Math.min((w - pad * 2) / Math.max(box.w, 1), (h - pad * 2) / Math.max(box.h, 1));
  return { cx: box.x + box.w / 2, cy: box.y + box.h / 2, k: Math.max(kMin, Math.min(kMax, k)) };
};

// A star's point has two states, set in CSS: nothing assessed, or under way. A complete star
// is drawn as a filled disc instead.
const tone = (item) => (item.glow > 0 ? 'moving' : 'none');

// From afar a star is its ring closed into a point: a small disc shaded by the share of its
// milestones met, then the share in progress, clockwise from the top; the rest is not yet
// assessed. A complete star is a larger, solid disc.
const FAR = { r: 2.4, complete: 3.1 };
function wedge(from, to, r) {
  const a0 = -Math.PI / 2 + from * Math.PI * 2;
  const a1 = -Math.PI / 2 + to * Math.PI * 2;
  const p = (a) => `${(Math.cos(a) * r).toFixed(2)} ${(Math.sin(a) * r).toFixed(2)}`;
  return `M0 0L${p(a0)}A${r} ${r} 0 ${to - from > 0.5 ? 1 : 0} 1 ${p(a1)}Z`;
}
export function FarPoint({ item, r = FAR.r }) {
  if (item.complete) return <circle r={(r * FAR.complete) / FAR.r} className="sky-complete far" />;
  const n = item.status.length || 1;
  const met = item.met / n;
  const moving = item.moving / n;
  return (
    <>
      <circle r={r} className="sky-far none" />
      {moving > 0 &&
        (met + moving > 0.999 && met === 0 ? (
          <circle r={r} className="sky-far in_progress" />
        ) : (
          <path d={wedge(met, Math.min(met + moving, 0.9999), r)} className="sky-far in_progress" />
        ))}
      {met > 0 &&
        (met > 0.999 ? <circle r={r} className="sky-far met" /> : <path d={wedge(0, met, r)} className="sky-far met" />)}
    </>
  );
}

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

// Each region is a click target behind its constellations: a click on its open sky (or its
// name) zooms to the region; a click on a constellation still goes to that field.
const RegionTargets = memo(function RegionTargets({ regions, focusRegion, onFocusRegion }) {
  return (
    <g className="sky-region-hits">
      {regions.map((r) => (
        <rect
          key={r.name}
          x={r.x}
          y={r.y}
          width={r.w}
          height={r.h}
          className={'sky-region-hit' + (focusRegion === r.name ? ' focus' : '')}
          onClick={(e) => {
            e.stopPropagation();
            onFocusRegion(r.name);
          }}
        >
          <title>{`${r.name}: zoom in`}</title>
        </rect>
      ))}
    </g>
  );
});

const Graticule = memo(function Graticule({ world, regions, bare, names, focusRegion, onFocusRegion }) {
  const { frame, unit } = world;
  const x1 = world.w - frame;
  const y1 = world.h - frame;
  const down = Math.floor((y1 - frame) / unit);
  if (bare) return null;
  // A faint grid, as texture only: it carries no scale, so it has no ticks or numbers.
  const lines = [];
  for (let u = 4; u < UNITS_ACROSS; u += 4) {
    const x = frame + u * unit;
    lines.push(<line key={'x' + u} x1={x} x2={x} y1={frame} y2={y1} />);
  }
  for (let u = 4; u <= down; u += 4) {
    const y = frame + u * unit;
    lines.push(<line key={'y' + u} x1={frame} x2={x1} y1={y} y2={y} />);
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
    <g className="sky-structure">
      <g aria-hidden="true">
        <g className="sky-grid">{lines}</g>
        <path d={bounds} className="sky-bounds" />
        <rect x={frame} y={frame} width={x1 - frame} height={y1 - frame} className="sky-frame" />
      </g>
      {names && (
        <g className="sky-regions" aria-hidden={onFocusRegion ? undefined : 'true'}>
          {regions.map((r) => (
            <g
              key={r.name}
              transform={`translate(${r.label.x.toFixed(1)} ${r.label.y.toFixed(1)})`}
              className={'sky-region-name' + (focusRegion === r.name ? ' focus' : '')}
              role={onFocusRegion ? 'button' : undefined}
              tabIndex={onFocusRegion ? 0 : undefined}
              aria-label={onFocusRegion ? `${r.name}: zoom in` : undefined}
              onClick={
                onFocusRegion
                  ? (e) => {
                      e.stopPropagation();
                      onFocusRegion(r.name);
                    }
                  : undefined
              }
              onKeyDown={
                onFocusRegion
                  ? (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onFocusRegion(r.name);
                      }
                    }
                  : undefined
              }
            >
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
function StarLabel({ item, plan, plate = false }) {
  const { title, end } = plan;
  const anchor = end ? 'end' : 'start';
  const x = 0;
  return (
    <g>
      {plate && (
        // The label of the star pointed at sits on a plate, so whatever lies under it is hidden
        // rather than mixed with its text.
        <rect
          className="sky-label-plate"
          x={(end ? -plan.sw : 0) - 7}
          y={-6}
          width={plan.sw + 14}
          height={plan.sh + 10}
          rx="2"
        />
      )}
      <text className="sky-star-id" x={x} y="0" dy="0.8em" textAnchor={anchor}>
        {item.id}
      </text>
      {title && (
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

const Star = memo(function Star({ item, lod, state, plan, interactive, tabbable, onSelect, onHover }) {
  const r = starRadius(item.status.length);
  const active = state === 'selected' || state === 'hovered';
  const live = interactive && lod >= 1;
  const props = live
    ? {
        tabIndex: tabbable ? 0 : -1,
        role: 'button',
        'aria-label': `${item.id}: ${item.title}. ${item.complete ? 'Complete; ' : ''}${item.met} of ${item.status.length} milestones met, ${item.moving} in progress.`,
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
      className={'sky-star ' + state + (live ? ' live' : '')}
      transform={`translate(${item.x.toFixed(2)} ${item.y.toFixed(2)})`}
      {...props}
    >
      {live && <circle r={r + 2.5} className="sky-star-hit" />}
      {item.pulse && <circle r={r + 0.6} className="sky-pulse" />}
      {lod === 0 ? (
        <FarPoint item={item} />
      ) : item.complete ? (
        // Complete: the ring filled in. One mark, the same ink as a met segment.
        <circle r={r} className="sky-complete" />
      ) : (
        <>
          <g className="sky-screen">
            <circle r="2.2" className={'sky-star-core ' + tone(item)} />
          </g>
          {ringSegments(item.status, r).map((seg, n) => (
            <path key={n} d={seg.d} className={'sky-seg ' + seg.status} />
          ))}
        </>
      )}
      {active && (
        <g className="sky-reticle">
          <circle r={r + 2.2} />
          <line y1={-(r + 2.2)} y2={-(r + 4.6)} />
          <line y1={r + 2.2} y2={r + 4.6} />
          <line x1={-(r + 2.2)} x2={-(r + 4.6)} />
          <line x1={r + 2.2} x2={r + 4.6} />
        </g>
      )}
      {plan?.lead && (
        // A label set a step away from a hemmed-in star is tied to it by a short hairline.
        <line className="sky-leader" x1={plan.lead[0]} y1={plan.lead[1]} x2={plan.lead[2]} y2={plan.lead[3]} />
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

// A field's size in words under its name, and how many of its breakthroughs are complete when
// any are. The milestone counts are in the tooltip.
function FieldCount({ field, y }) {
  let met = 0;
  let moving = 0;
  let total = 0;
  let complete = 0;
  for (const i of field.items) {
    met += i.met;
    moving += i.moving;
    total += i.status.length;
    if (i.complete) complete += 1;
  }
  const n = field.items.length;
  if (!n) return null;
  return (
    <text className="sky-field-count" textAnchor="middle" y={y} dy="0.8em">
      {n === 1 ? '1 breakthrough' : `${n} breakthroughs`}
      {complete > 0 && <tspan className="done">{` · ${complete} complete`}</tspan>}
      <title>{`${n} breakthroughs, ${complete} complete; ${met} of ${total} milestones met, ${moving} in progress`}</title>
    </text>
  );
}

const Constellation = memo(function Constellation({
  field,
  fig,
  lod,
  state,
  selected,
  hovered,
  plan,
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
  const starState = (item) => {
    if (item.id === selected) return 'selected';
    if (item.id === hovered) return 'hovered';
    if (state === 'dim') return 'dim';
    return 'rest';
  };
  const box = fig.box;
  // The label of the star pointed at or selected is drawn last, above every star and name.
  const lifted = [...new Set([selected, hovered])].filter((id) => id && plan?.get(id));
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
            plan={lifted.includes(item.id) ? null : plan?.get(item.id) || null}
            interactive={interactive}
            tabbable={interactive && state === 'focus'}
            onSelect={onSelect}
            onHover={onHoverStar}
          />
        ))}
        {labels && !(state === 'focus' && lod >= 2) && (
          // Close in on one field, its name is in the panel and the breadcrumb, not on the sky.
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
              <FieldCount field={field} y={fig.label.lines.length * LABEL.line - 1.5} />
            </g>
          </g>
        )}
        {lifted.map((id) => {
          const item = field.byId[id];
          const at = plan.get(id);
          return (
            <g
              key={id}
              className="sky-label-lift"
              transform={`translate(${(item.x + at.wx).toFixed(2)} ${(item.y + at.wy).toFixed(2)})`}
            >
              <g className="sky-screen">
                <StarLabel item={item} plan={at} plate />
              </g>
            </g>
          );
        })}
      </g>
    </g>
  );
});

// ---------- The chart ----------

export default function Chart({
  atlas,
  interactive = false,
  focusField = null,
  focusRegion = null,
  selected = null,
  highlight = null,
  highlightField = null,
  onSelect = () => {},
  onFocusField = () => {},
  onFocusRegion = null,
  onHover = () => {},
  onLevel = null,
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
  // The page's legend describes the marks drawn at this level of detail.
  useEffect(() => {
    onLevel?.(lod);
  }, [lod, onLevel]);
  const drag = useRef(null);
  const insetRight = inset?.right || 0;
  const insetTop = inset?.top || 0;
  const insetBottom = inset?.bottom || 0;
  // The centre of the part of the chart left free by panels over it.
  const oyOf = (h) => insetTop + (h - insetTop - insetBottom) / 2;
  // A backdrop without names (the phone hero) is figures only: no frame or grid.
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

  // Only breakthroughs with every milestone met get a beacon. With most stars showing some
  // progress, a beacon for each turned the wide view into blobs; the rest show their progress
  // in their rings up close, and in their field's bar from afar.
  const warm = useMemo(() => Object.values(atlas.items).filter((i) => i.complete), [atlas]);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size, insetRight, insetTop, insetBottom, atlas, sky, world]);

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
      // One field fills the view: its stars and their rings, with room at the sides for labels.
      const stars = atlas.field[focusField].items;
      const xs = stars.map((i) => i.x);
      const ys = stars.map((i) => i.y);
      const reach = 3.4;
      const box = stars.length
        ? {
            x: Math.min(...xs) - reach,
            y: Math.min(...ys) - reach,
            w: Math.max(...xs) - Math.min(...xs) + reach * 2,
            h: Math.max(...ys) - Math.min(...ys) + reach * 2,
          }
        : sky.figures[focusField].box;
      return fitBox(box, w, size.h - insetTop - insetBottom, Math.max(pad, 96), whole.k, 9);
    }
    const region = focusRegion && sky.regions.find((r) => r.name === focusRegion);
    if (region) {
      // A region fills the view, its constellations large enough to read and pick.
      return fitBox(region, w, size.h - insetTop - insetBottom, Math.max(pad, 40), whole.k, 4.2);
    }
    return whole;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atlas, sky, size, whole, focusField, focusRegion, selected, insetRight, pad]);

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
    onFocusRegion?.(null);
    if (!selected && !focusField && !focusRegion && whole) {
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
      else if (focusRegion) onFocusRegion?.(null);
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

  const visibleSet = useMemo(() => new Set(visible.split(' ')), [visible]);

  // Every star in view gets the same label, its ID; the star pointed at or selected gets its
  // whole title as well (the list beside the chart has every title). Labels are placed
  // greedily, most important first: each tries the sides and corners of its star and takes the
  // first spot that covers no other label, star or constellation name, and no figure line; if
  // there is none, it may cross a line (labels sit on a paper-coloured halo) but nothing else.
  const plans = useMemo(() => {
    if (lod < 2 || !interactive) return {};
    const k = kq;
    const out = {};
    const considered = atlas.fields.filter((f) => visibleSet.has(f.id) && (!focusField || f.id === focusField));
    const items = considered.flatMap((f) => f.items);
    const isActive = (i) => i.id === selected || i.id === hovered;
    const taken = [];
    const segs = [];
    for (const f of considered) {
      const fig = sky.figures[f.id];
      for (const [a, b] of fig.edges) segs.push([atlas.items[a], atlas.items[b]]);
      // The constellation's name, at the size it is drawn at this zoom (see --ls). The field in
      // focus has no name on the sky.
      if (f.id !== focusField) {
        const sc = (k >= 0.88 ? Math.min(Math.max(k, 1), 1.1) : k / 0.88) / k;
        const lw = Math.max(...fig.label.lines.map((l) => l.length)) * LABEL.char * sc;
        taken.push({ x: fig.label.x - lw / 2, y: fig.label.y, w: lw, h: (fig.label.lines.length + 1) * LABEL.line * sc });
      }
      for (const i of f.items) {
        // The active star's box takes in its reticle.
        const r = starRadius(i.status.length) + (isActive(i) ? 4.6 : 0);
        taken.push({ x: i.x - r, y: i.y - r, w: r * 2, h: r * 2, star: i.id });
      }
    }
    const priority = (i) => (i.id === selected ? 0 : i.id === hovered ? 1 : i.field === focusField ? 2 : 3);
    items.sort((a, b) => priority(a) - priority(b) || a.id.localeCompare(b.id));
    for (const i of items) {
      const title = isActive(i);
      const ring = starRadius(i.status.length);
      const gap = (ring + (title ? 4.6 : 0)) * k + 6;
      const lines = title ? wrap(i.title, 26) : [];
      const w = title ? Math.max(8 + i.id.length * 6.6, ...lines.map((l) => 6 + l.length * 6.5)) : 8 + i.id.length * 6.6;
      const h = title ? 17 + lines.length * 15.4 : 13;
      const mid = -h / 2 + (title ? 6 : 0);
      const d = gap * 0.72;
      const sides = [
        { ox: gap, oy: mid, end: false },
        { ox: -gap - w, oy: mid, end: true },
        { ox: -w / 2 + 20, oy: gap - 2, end: false },
        { ox: -w / 2 + 20, oy: -gap - h + 2, end: false },
        { ox: d, oy: -d - h + 3, end: false },
        { ox: d, oy: d - 3, end: false },
        { ox: -d - w, oy: -d - h + 3, end: true },
        { ox: -d - w, oy: d - 3, end: true },
        // Centred above and below, and a step further out, for a star hemmed in by its figure.
        { ox: -w / 2, oy: gap - 2, end: false },
        { ox: -w / 2, oy: -gap - h + 2, end: false },
        { ox: gap + 9, oy: mid, end: false },
        { ox: -gap - 9 - w, oy: mid, end: true },
      ];
      // The same spots a step or two further out, for a star hemmed in on every side: such a
      // label is tied back to its star by a hairline.
      const further = [14, 28, 44].flatMap((m) =>
        sides.slice(0, 8).map((side) => {
          const cx = side.ox + w / 2;
          const cy = side.oy + h / 2;
          const d0 = Math.hypot(cx, cy) || 1;
          return { ox: side.ox + (m * cx) / d0, oy: side.oy + (m * cy) / d0, end: side.end, lead: true };
        }),
      );
      const place = (side) => {
        const box = { x: i.x + side.ox / k, y: i.y + side.oy / k, w: w / k, h: h / k };
        // Glyphs reach a little above the box's top line; keep a margin round the text.
        const room = { x: box.x - 2 / k, y: box.y - 4 / k, w: box.w + 4 / k, h: box.h + 6 / k };
        const plan = { title, end: side.end, box, sw: w, sh: h, wx: box.x - i.x + (side.end ? box.w : 0), wy: box.y - i.y };
        if (side.lead) {
          // From the ring's edge to the nearest point of the label.
          const qx = Math.min(Math.max(0, box.x - i.x), box.x - i.x + box.w);
          const qy = Math.min(Math.max(0, box.y - i.y), box.y - i.y + box.h);
          const len = Math.hypot(qx, qy) || 1;
          const from = ring + 1.5 / k;
          const to = len - 2 / k;
          if (to > from) plan.lead = [(qx / len) * from, (qy / len) * from, (qx / len) * to, (qy / len) * to].map((v) => +v.toFixed(2));
        }
        return { plan, room };
      };
      const covered = (room) => taken.filter((b) => b.star !== i.id && meets(room, b));
      let chosen = null;
      const passes = [
        [sides, true],
        [sides, false],
        [further, false],
      ];
      for (const [spots, strict] of passes) {
        for (const side of spots) {
          const { plan, room } = place(side);
          if (covered(room).length === 0 && (!strict || segs.every(([p, q]) => !hits(p, q, room)))) {
            chosen = plan;
            break;
          }
        }
        if (chosen) break;
      }
      // The active star always shows its title: where it covers least, stars counting most.
      if (!chosen && title) {
        let least = Infinity;
        for (const side of [...sides, ...further]) {
          const { plan, room } = place(side);
          const cost = covered(room).reduce((n, b) => n + (b.star ? 3 : 1), 0);
          if (cost < least) {
            least = cost;
            chosen = plan;
          }
        }
      }
      if (!chosen) continue;
      taken.push(chosen.box);
      (out[i.field] ||= new Map()).set(i.id, chosen);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atlas, sky, lod, kq, visibleSet, focusField, selected, hovered, interactive]);
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
        </defs>
        <g className={drift > 1 && !still ? 'sky-drift' : undefined}>
          <g
            ref={worldRef}
            className={
              'sky-world lod-' +
              lod +
              (focusField ? ' focused' : focusRegion ? ' region-focused' : '') +
              (active ? ' has-active' : '') +
              (introOn && !still ? ' intro' : '')
            }
          >
            <Graticule
              world={world}
              regions={sky.regions}
              bare={bare}
              names={names}
              focusRegion={focusField ? null : focusRegion}
              onFocusRegion={interactive ? onFocusRegion : null}
            />
            {interactive && onFocusRegion && !focusField && (
              <RegionTargets regions={sky.regions} focusRegion={focusRegion} onFocusRegion={onFocusRegion} />
            )}
            {fields.map((f) => {
              const fig = sky.figures[f.id];
              const state =
                focusField === f.id
                  ? 'focus'
                  : focusField || (focusRegion && f.region !== focusRegion)
                    ? 'dim'
                    : liftField === f.id
                      ? 'hover'
                      : 'rest';
              return (
                <Constellation
                  key={f.id}
                  field={f}
                  fig={fig}
                  lod={lod >= 1 && visibleSet.has(f.id) ? lod : 0}
                  state={state}
                  selected={selected && atlas.items[selected]?.field === f.id ? selected : null}
                  hovered={hovered && atlas.items[hovered]?.field === f.id ? hovered : null}
                  labels={labels && interactive}
                  plan={plans[f.id]}
                  interactive={interactive}
                  delay={intoView(fig.x)}
                  onFocusField={focusAt}
                  onHoverField={hoverFieldAt}
                  onSelect={selectStar}
                  onHoverStar={hoverStar}
                />
              );
            })}
            <g className="sky-beacons" aria-hidden="true">
              {warm.map((i) => (
                <g key={i.id} transform={`translate(${i.x.toFixed(2)} ${i.y.toFixed(2)})`}>
                  <g className="sky-screen">
                    <circle r={lod >= 1 ? 18 : 9} fill="url(#sky-halo-met)" />
                  </g>
                </g>
              ))}
            </g>
          </g>
        </g>
      </svg>
    </div>
  );
}

// ---------- The locator: the whole sky in miniature, not interactive ----------

// Shows where a constellation (and optionally one star) sits in the sky: every star as a
// point, the field's figure drawn and bracketed, the star fixed by crosshairs to the frame.
// `size` is the locator's height-equivalent from the old square locator; the flat sky is
// drawn about one and a half times as wide.
// With `onPick`, a tap on the locator picks the constellation under or nearest it (within a
// finger's width), else the region it falls in: onPick({ field }) or onPick({ region }).
export function Locator({ atlas, field, star, size = 132, width, names = false, onPick }) {
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
  const pick = (e) => {
    const svgEl = e.currentTarget;
    const ctm = svgEl.getScreenCTM();
    if (!ctm) return;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    const reach = stroke(14);
    let best = null;
    for (const x of atlas.fields) {
      const b = sky.figures[x.id].box;
      const dx = Math.max(b.x - pt.x, 0, pt.x - (b.x + b.w));
      const dy = Math.max(b.y - pt.y, 0, pt.y - (b.y + b.h));
      const d = Math.hypot(dx, dy);
      if (d <= reach && (!best || d < best.d)) best = { d, id: x.id };
    }
    if (best) return onPick({ field: best.id });
    const r = sky.regions.find((q) => pt.x >= q.x && pt.x <= q.x + q.w && pt.y >= q.y && pt.y <= q.y + q.h);
    if (r) onPick({ region: r.name });
  };
  return (
    <svg
      onClick={onPick ? pick : undefined}
      className={'sky-locator' + (onPick ? ' pickable' : '')}
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
      {names &&
        sky.regions.map((r) => (
          <text
            key={r.name}
            className="loc-region"
            style={{ fontSize: stroke(5.6), letterSpacing: stroke(0.6) }}
          >
            {r.label.lines.map((line, n) => (
              <tspan key={n} x={r.label.x} y={r.label.y + stroke(6 + n * 8)}>
                {onPaper() ? line : line.toUpperCase()}
              </tspan>
            ))}
          </text>
        ))}
      {/* As on the chart, only a breakthrough with every milestone met is lit: with most stars
          showing some progress, lighting each turned the small sky into blobs. */}
      {Object.values(atlas.items).map((i) => (
        <circle
          key={i.id}
          cx={i.x}
          cy={i.y}
          r={stroke(i.complete ? 1.6 : f && i.field === field ? 1.1 : 0.75)}
          className={'loc-dot' + (f && i.field === field ? ' in' : '') + (i.complete ? ' lit' : '')}
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

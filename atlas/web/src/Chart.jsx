import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { animate, motion, useReducedMotion } from 'framer-motion';
import { StarMark } from './glyphs.jsx';
import { band, starRadius } from './sky.js';
import { EASE } from './motion.js';

// Levels of detail by zoom: far = the sky and constellation names; nearer = stars with
// their milestone rings; nearer still = IDs; nearest = titles.
const LOD = [0, 0.9, 1.8, 3.4];
const lodOf = (k) => LOD.filter((t) => k >= t).length - 1;
const K_MAX = 5;
const LABEL_GAP = 16; // screen px between the outer ring and a constellation name
const labelWidth = (name) => name.length * 8.7 + 2; // Jura 10.5px, tracked capitals

const deg = (a) => (a * 180) / Math.PI;

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

// The largest zoom at which the whole sky, names included, fits the box.
function fitSky(atlas, w, h, pad, labels = true) {
  const outer = atlas.sky.outer;
  if (!labels) return { cx: 0, cy: 0, k: (Math.min(w, h) / 2 - pad) / (outer + 24) };
  let best = 0.1;
  for (let k = 2; k > 0.08; k *= 0.97) {
    const fits = atlas.fields.every((f) => {
      const reach = outer * k + LABEL_GAP + labelWidth(f.name);
      const x = Math.cos(f.sector.mid) * reach;
      const y = Math.sin(f.sector.mid) * reach;
      return Math.abs(x) <= w / 2 - pad && Math.abs(y) <= h / 2 - pad;
    });
    if (fits) {
      best = k;
      break;
    }
  }
  return { cx: 0, cy: 0, k: best };
}

function fitPoints(points, w, h, pad, kMin, kMax) {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);
  const k = Math.min((w - pad * 2) / Math.max(x1 - x0, 1), (h - pad * 2) / Math.max(y1 - y0, 1));
  return { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, k: Math.max(kMin, Math.min(kMax, k)) };
}

const Sky = memo(function Sky({ atlas, intro, still }) {
  const rings = [];
  for (let d = 0; d <= atlas.sky.maxDepth; d++) rings.push(band(d));
  const outer = atlas.sky.outer;
  const sweep = (n) =>
    intro && !still
      ? {
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1 },
          transition: { duration: 1.3, delay: 0.1 + n * 0.18, ease: EASE },
        }
      : {};
  return (
    <g className="sky-structure" aria-hidden="true">
      {rings.map(([r0, r1], d) => (
        <g key={d}>
          <motion.circle r={r0} className="ring" transform="rotate(-90)" {...sweep(d)} />
          {d === 0 && <motion.circle r={r1} className="ring faint" transform="rotate(-90)" {...sweep(0.5)} />}
        </g>
      ))}
      <motion.circle r={outer + 18} className="ring outer" transform="rotate(-90)" {...sweep(rings.length)} />
      {atlas.fields.map((f) => {
        const a = f.sector.start;
        const c = Math.cos(a);
        const s = Math.sin(a);
        return (
          <g key={f.id}>
            <line x1={c * (band(0)[0] - 10)} y1={s * (band(0)[0] - 10)} x2={c * band(0)[0]} y2={s * band(0)[0]} className="tick" />
            <line x1={c * (outer + 12)} y1={s * (outer + 12)} x2={c * (outer + 24)} y2={s * (outer + 24)} className="tick" />
          </g>
        );
      })}
      {Array.from({ length: 72 }, (_, n) => {
        const a = (n / 72) * Math.PI * 2;
        const r = band(0)[0] - (n % 6 === 0 ? 6 : 3);
        return (
          <line
            key={n}
            x1={Math.cos(a) * r}
            y1={Math.sin(a) * r}
            x2={Math.cos(a) * (band(0)[0] - 1)}
            y2={Math.sin(a) * (band(0)[0] - 1)}
            className="tick fine"
          />
        );
      })}
      <g className="now">
        <line x1="-14" x2="-5" className="tick" />
        <line x1="5" x2="14" className="tick" />
        <line y1="-14" y2="-5" className="tick" />
        <line y1="5" y2="14" className="tick" />
        <g className="screen" style={{ transform: 'scale(calc(1 / var(--k)))' }}>
          <text y="30" textAnchor="middle" className="now-label">NOW</text>
        </g>
      </g>
    </g>
  );
});

function FieldLabel({ field, atlas, dim, active, interactive, onFocusField }) {
  const a = field.sector.mid;
  const left = Math.cos(a) < -0.01;
  const r = atlas.sky.outer;
  const x = Math.cos(a) * r;
  const y = Math.sin(a) * r;
  const rot = deg(a) + (left ? 180 : 0);
  const props = interactive
    ? {
        tabIndex: 0,
        role: 'button',
        'aria-label': `Focus ${field.name}`,
        onClick: (e) => {
          e.stopPropagation();
          onFocusField(field.id);
        },
        onKeyDown: (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onFocusField(field.id);
          }
        },
      }
    : {};
  return (
    <g
      className={'field-label' + (dim ? ' dim' : '') + (active ? ' active' : '')}
      style={{ transform: `translate(${x}px, ${y}px) scale(calc(1 / var(--k))) rotate(${rot}deg)` }}
      {...props}
    >
      <rect
        x={left ? -LABEL_GAP - labelWidth(field.name) - 6 : LABEL_GAP - 6}
        y="-11"
        width={labelWidth(field.name) + 12}
        height="22"
        className="hit"
      />
      <text x={left ? -LABEL_GAP : LABEL_GAP} y="0" dy="0.35em" textAnchor={left ? 'end' : 'start'}>
        {field.name.toUpperCase()}
      </text>
    </g>
  );
}

const Star = memo(function Star({ item, lod, state, tabbable, onSelect, onHover }) {
  const r = starRadius(item.status.length);
  const activate = () => onSelect(item.id);
  return (
    <g
      className={'star ' + state}
      transform={`translate(${item.x.toFixed(2)} ${item.y.toFixed(2)})`}
      tabIndex={tabbable ? 0 : -1}
      role="button"
      aria-label={`${item.id}: ${item.title}. ${item.met} of ${item.status.length} milestones met, ${item.moving} in progress.`}
      onClick={(e) => {
        e.stopPropagation();
        activate();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          activate();
        }
      }}
      onPointerEnter={() => onHover(item.id)}
      onPointerLeave={() => onHover(null)}
      onFocus={() => onHover(item.id)}
      onBlur={() => onHover(null)}
    >
      <circle r={r + 9} className="hit" />
      {item.recent && <circle r={r + 1.5} className="pulse" />}
      <StarMark item={item} r={r} ring={lod >= 1 && state !== 'dim'} core={lod >= 1 ? 1.3 + item.status.length * 0.22 : r * 0.62} />
      {(state === 'selected' || state === 'hovered') && (
        <g className="reticle">
          <circle r={r + 4.5} />
          <line y1={-(r + 4.5)} y2={-(r + 9)} />
          <line y1={r + 4.5} y2={r + 9} />
          <line x1={-(r + 4.5)} x2={-(r + 9)} />
          <line x1={r + 4.5} x2={r + 9} />
        </g>
      )}
      {lod >= 2 && state !== 'dim' && (
        <g transform={`translate(${r + 1} 0)`}>
          <g className="screen" style={{ transform: 'scale(calc(1 / var(--k)))' }}>
            <text className="star-id" x="7" y="0" dy={lod >= 3 ? '-0.5em' : '0.35em'}>
              {item.id}
            </text>
            {lod >= 3 && (
              <text className="star-title" x="7" y="0">
                {wrap(item.title, 24).map((line, n) => (
                  <tspan key={n} x="7" dy={n === 0 ? '1.15em' : '1.2em'}>
                    {line}
                  </tspan>
                ))}
              </text>
            )}
          </g>
        </g>
      )}
    </g>
  );
});

function linkPath(a, b) {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  // Bow each link slightly clockwise so crossing links stay distinguishable.
  return `M${a.x} ${a.y}Q${mx - dy * 0.12} ${my + dx * 0.12} ${b.x} ${b.y}`;
}

export default function Chart({
  atlas,
  interactive = false,
  focusField = null,
  selected = null,
  highlight = null,
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
  const wrapRef = useRef(null);
  const svg = useRef(null);
  const world = useRef(null);
  const view = useRef({ cx: 0, cy: 0, k: 0.4 });
  const glide = useRef(null);
  const [size, setSize] = useState(null);
  const [lod, setLod] = useState(0);
  const [hover, setHover] = useState(null);
  const drag = useRef(null);

  const apply = useCallback(() => {
    if (!size || !world.current) return;
    const { cx, cy, k } = view.current;
    const ox = (size.w - inset.right) / 2;
    const oy = size.h / 2;
    world.current.setAttribute('transform', `translate(${ox - cx * k} ${oy - cy * k}) scale(${k})`);
    svg.current.style.setProperty('--k', k);
    setLod(lodOf(k));
  }, [size, inset.right]);

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

  const target = useMemo(() => {
    if (!size) return null;
    const w = size.w - inset.right;
    const sky = fitSky(atlas, w, size.h, pad, labels);
    if (selected && atlas.items[selected]) {
      const s = atlas.items[selected];
      return { cx: s.x, cy: s.y, k: Math.max(2.4, Math.min(view.current.k, K_MAX)), fit: sky.k };
    }
    if (focusField && atlas.field[focusField]) {
      const pts = atlas.field[focusField].items;
      return { ...fitPoints(pts, w, size.h, Math.max(pad, 90), sky.k, 2.6), fit: sky.k };
    }
    return { ...sky, fit: sky.k };
  }, [atlas, size, focusField, selected, inset.right, pad, labels]);

  const first = useRef(true);
  useLayoutEffect(() => {
    if (!target) return;
    glide.current?.stop();
    if (first.current || still) {
      first.current = false;
      view.current = { cx: target.cx, cy: target.cy, k: target.k };
      apply();
      return;
    }
    const from = { ...view.current };
    glide.current = animate(0, 1, {
      duration: 1.1,
      ease: EASE,
      onUpdate: (t) => {
        const k = Math.exp(Math.log(from.k) + (Math.log(target.k) - Math.log(from.k)) * t);
        view.current = {
          cx: from.cx + (target.cx - from.cx) * t,
          cy: from.cy + (target.cy - from.cy) * t,
          k,
        };
        apply();
      },
    });
  }, [target, apply, still]);

  // Wheel zoom about the cursor (desktop only).
  useEffect(() => {
    if (!interactive || !svg.current || !size) return;
    const el = svg.current;
    const wheel = (e) => {
      e.preventDefault();
      glide.current?.stop();
      const box = el.getBoundingClientRect();
      zoomAt(e.clientX - box.left, e.clientY - box.top, Math.exp(-e.deltaY * 0.0016));
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  });

  const zoomAt = (px, py, factor) => {
    const { cx, cy, k } = view.current;
    const kMin = (target?.fit || 0.3) * 0.85;
    const k2 = Math.max(kMin, Math.min(K_MAX, k * factor));
    const ox = (size.w - inset.right) / 2;
    const oy = size.h / 2;
    const wx = cx + (px - ox) / k;
    const wy = cy + (py - oy) / k;
    view.current = { cx: wx - (px - ox) / k2, cy: wy - (py - oy) / k2, k: k2 };
    apply();
  };

  const zoomBy = (factor) => {
    glide.current?.stop();
    const from = { ...view.current };
    const to = Math.max((target?.fit || 0.3) * 0.85, Math.min(K_MAX, from.k * factor));
    if (still) {
      view.current = { ...from, k: to };
      apply();
      return;
    }
    glide.current = animate(from.k, to, {
      duration: 0.45,
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
    }
    d.x = e.clientX;
    d.y = e.clientY;
    const { k } = view.current;
    view.current = { ...view.current, cx: view.current.cx - dx / k, cy: view.current.cy - dy / k };
    apply();
  };
  const pointerUp = () => {
    const d = drag.current;
    drag.current = null;
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
      view.current = { ...view.current, cx: view.current.cx + moves[e.key][0], cy: view.current.cy + moves[e.key][1] };
      apply();
    } else if (e.key === '+' || e.key === '=') zoomBy(1.4);
    else if (e.key === '-') zoomBy(1 / 1.4);
    else if (e.key === 'Escape') {
      if (selected) onSelect(null);
      else if (focusField) onFocusField(null);
    }
  };

  const hovered = hover || highlight;
  const hoverAt = (id) => {
    if (drag.current?.captured) return;
    setHover(id);
    onHover(id);
  };

  const active = selected || hovered;
  const linked = useMemo(() => {
    const set = new Set();
    for (const l of atlas.links) {
      const touches =
        (focusField && (atlas.items[l.from].field === focusField || atlas.items[l.to].field === focusField)) ||
        (active && (l.from === active || l.to === active));
      if (touches) {
        set.add(l.from);
        set.add(l.to);
      }
    }
    return set;
  }, [atlas, focusField, active]);
  const shownLinks = atlas.links.filter(
    (l) =>
      (focusField && (atlas.items[l.from].field === focusField || atlas.items[l.to].field === focusField)) ||
      (active && (l.from === active || l.to === active)),
  );

  const stateOf = (item) => {
    if (item.id === selected) return 'selected';
    if (item.id === hovered) return 'hovered';
    if (focusField && item.field !== focusField && !linked.has(item.id)) return 'dim';
    return 'rest';
  };

  const tip = hover && interactive && size && atlas.items[hover] && hover !== selected ? atlas.items[hover] : null;
  const tipPos = tip
    ? (() => {
        const { cx, cy, k } = view.current;
        return {
          left: (size.w - inset.right) / 2 + (tip.x - cx) * k,
          top: size.h / 2 + (tip.y - cy) * k,
        };
      })()
    : null;

  return (
    <div
      ref={wrapRef}
      className={'chart ' + (interactive ? 'interactive ' : '') + className}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={keyDown}
      aria-label={interactive ? 'Star chart. Drag or use arrow keys to pan, plus and minus to zoom.' : undefined}
      role={interactive ? 'application' : undefined}
      aria-hidden={interactive ? undefined : true}
    >
      <svg
        ref={svg}
        width="100%"
        height="100%"
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={pointerUp}
        onClick={() => interactive && selected && onSelect(null)}
        style={{ '--k': view.current.k }}
      >
        <g ref={world} className={'world lod-' + lod}>
          <Sky atlas={atlas} intro={intro} still={still} />
          <g className="links">
            {shownLinks.map((l) => (
              <motion.path
                key={`${l.from}-${l.to}-${focusField}-${active}`}
                d={linkPath(atlas.items[l.from], atlas.items[l.to])}
                className="link"
                initial={still ? false : { pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ duration: 0.9, ease: EASE }}
              />
            ))}
          </g>
          {atlas.fields.map((f, n) => (
            <motion.g
              key={f.id}
              className="constellation"
              initial={
                intro && !still
                  ? { opacity: 0, x: -Math.cos(f.sector.mid) * 60, y: -Math.sin(f.sector.mid) * 60 }
                  : false
              }
              animate={{ opacity: 1, x: 0, y: 0 }}
              transition={{ duration: 0.9, delay: 0.25 + n * 0.03, ease: EASE }}
            >
              {labels && <FieldLabel
                field={f}
                atlas={atlas}
                dim={focusField && focusField !== f.id}
                active={focusField === f.id}
                interactive={interactive}
                onFocusField={onFocusField}
              />}
              {f.items.map((item) => (
                <Star
                  key={item.id}
                  item={item}
                  lod={lod}
                  state={stateOf(item)}
                  tabbable={interactive && focusField === f.id}
                  onSelect={interactive ? onSelect : () => {}}
                  onHover={interactive ? hoverAt : () => {}}
                />
              ))}
            </motion.g>
          ))}
        </g>
      </svg>
      {tip && lod < 3 && (
        <div className="chart-tip" style={tipPos} aria-hidden="true">
          <span className="mono">{tip.id}</span>
          {tip.title}
        </div>
      )}
      {interactive && (
        <div className="zoom" role="group" aria-label="Zoom">
          <button type="button" onClick={() => zoomBy(1.5)} aria-label="Zoom in">
            <svg viewBox="-8 -8 16 16" width="14" height="14"><path d="M-5 0H5M0 -5V5" /></svg>
          </button>
          <button type="button" onClick={() => zoomBy(1 / 1.5)} aria-label="Zoom out">
            <svg viewBox="-8 -8 16 16" width="14" height="14"><path d="M-5 0H5" /></svg>
          </button>
          <button type="button" onClick={reset} aria-label="Show the whole sky">
            <svg viewBox="-8 -8 16 16" width="14" height="14">
              <circle r="5.5" />
              <circle r="1.2" className="solid" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

// The phone's locator: the whole sky as points, the current constellation's sector marked.
export function Locator({ atlas, field, star, size = 132 }) {
  const outer = atlas.sky.outer + 30;
  const f = field && atlas.field[field];
  const s = star && atlas.items[star];
  return (
    <svg
      className="locator"
      width={size}
      height={size}
      viewBox={`${-outer} ${-outer} ${outer * 2} ${outer * 2}`}
      role="img"
      aria-label={f ? `Where ${f.name} sits in the sky` : 'The whole sky'}
    >
      <circle r={band(0)[0]} className="ring" />
      <circle r={atlas.sky.outer + 18} className="ring" />
      {f && (
        <path
          d={`M0 0L${Math.cos(f.sector.start) * (outer - 4)} ${Math.sin(f.sector.start) * (outer - 4)}A${outer - 4} ${outer - 4} 0 0 1 ${Math.cos(f.sector.end) * (outer - 4)} ${Math.sin(f.sector.end) * (outer - 4)}Z`}
          className="sector"
        />
      )}
      {Object.values(atlas.items).map((i) => (
        <circle
          key={i.id}
          cx={i.x}
          cy={i.y}
          r={i.glow > 0 ? 11 : 6.5}
          className={'dot' + (f && i.field === field ? ' in' : '') + (i.glow > 0 ? ' lit' : '')}
        />
      ))}
      {s && <circle cx={s.x} cy={s.y} r="30" className="here" />}
    </svg>
  );
}

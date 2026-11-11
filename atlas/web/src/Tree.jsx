import { useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import MilestoneBar from './MilestoneBar.jsx';
import { EASE } from './motion.js';

const LABEL_W = 210, COL_W = 248, NODE_W = 220, NODE_H = 100, ROW_H = 132, PAD = 16;

export default function Tree({ atlas, matches, selected, onOpen }) {
  const [hover, setHover] = useState(null);
  const scroller = useRef(null);
  const still = useReducedMotion();
  const active = hover || selected;
  const layout = useMemo(() => {
    const pos = {};
    atlas.fields.forEach((f, lane) => f.items.forEach((i, col) => {
      pos[i.id] = { x: LABEL_W + col * COL_W + PAD, y: lane * ROW_H + PAD, lane, col };
    }));
    const cols = Math.max(...atlas.fields.map((f) => f.items.length));
    return {
      pos,
      width: LABEL_W + cols * COL_W + PAD * 2,
      height: atlas.fields.length * ROW_H + PAD,
    };
  }, [atlas]);
  const edges = useMemo(() => {
    if (!active || !atlas.related[active]) return [];
    const a = layout.pos[active];
    return [...atlas.related[active]].filter((id) => layout.pos[id]).map((id) => {
      const b = layout.pos[id];
      const ax = a.x + NODE_W / 2,
        ay = a.y + NODE_H / 2,
        bx = b.x + NODE_W / 2,
        by = b.y + NODE_H / 2;
      const bend = a.lane === b.lane ? -70 : 0;
      return {
        id,
        d: `M${ax},${ay} C${ax},${(ay + by) / 2 + bend} ${bx},${(ay + by) / 2 + bend} ${bx},${by}`,
      };
    });
  }, [active, atlas, layout]);
  const jump = (lane) =>
    scroller.current?.scrollTo({ top: lane * ROW_H, behavior: still ? 'auto' : 'smooth' });
  const linked = active ? atlas.related[active] || new Set() : null;
  return (
    <section className="tree-wrap">
      <nav className="chips" aria-label="Jump to field">
        {atlas.fields.map((f, n) => (
          <button key={f.id} style={{ '--c': f.color }} onClick={() => jump(n)}>{f.name}</button>
        ))}
      </nav>
      <div className="tree" ref={scroller} tabIndex={-1}>
        <div className="tree-inner" style={{ width: layout.width, height: layout.height }}>
          {atlas.fields.map((f, lane) => (
            <motion.div
              key={f.id}
              className="lane"
              style={{ top: lane * ROW_H, height: ROW_H, width: layout.width, '--c': f.color }}
              initial={still ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: Math.min(lane * 0.03, 0.6), ease: EASE }}
            >
              <div className="lane-label">
                <span className="lane-code">{f.id}</span>
                <strong>{f.name}</strong>
                <small>{f.items.length} breakthroughs</small>
              </div>
            </motion.div>
          ))}
          <svg className="edges" width={layout.width} height={layout.height} aria-hidden="true">
            <AnimatePresence>
              {edges.map((e) => (
                <motion.path
                  key={active + e.id}
                  d={e.d}
                  className="edge"
                  initial={{ pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: still ? 0 : 0.7, ease: EASE }}
                />
              ))}
            </AnimatePresence>
          </svg>
          {atlas.fields.flatMap((f) => f.items.map((i) => {
            const p = layout.pos[i.id];
            const dim =
              (matches && !matches.has(i.id)) || (linked && i.id !== active && !linked.has(i.id));
            return (
              <motion.button
                key={i.id}
                className={
                  'node' + (i.id === selected ? ' selected' : '') + (i.score ? ' moving' : '')
                }
                style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H, '--c': i.color }}
                initial={still ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: dim ? 0.18 : 1, y: 0 }}
                transition={{
                  duration: 0.5,
                  delay: still ? 0 : Math.min(p.lane * 0.03 + p.col * 0.02, 0.9),
                  ease: EASE,
                }}
                whileHover={still ? undefined : { y: -3 }}
                onMouseEnter={() => setHover(i.id)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i.id)}
                onBlur={() => setHover(null)}
                onClick={() => onOpen(i.id)}
                aria-label={`${i.id} ${i.title}`}
              >
                <span className="node-id">{i.id}<em>{i.progressCount} progress</em></span>
                <span className="node-title">{i.title}</span>
                <MilestoneBar status={i.status} />
              </motion.button>
            );
          }))}
        </div>
      </div>
    </section>
  );
}

import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import MilestoneBar from './MilestoneBar.jsx';
import { EASE } from './motion.js';

// One field at a time as a vertical path; swipe sideways to change field.
export default function MobilePath({ atlas, matches, onOpen }) {
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const still = useReducedMotion();
  const chips = useRef(null);
  const field = atlas.fields[index];
  const items = field.items.filter((i) => !matches || matches.has(i.id));
  const go = (n) => {
    if (n < 0 || n >= atlas.fields.length) return;
    setDirection(n > index ? 1 : -1);
    setIndex(n);
  };
  useEffect(() => {
    chips.current?.children[index]?.scrollIntoView({
      inline: 'center',
      block: 'nearest',
      behavior: still ? 'auto' : 'smooth',
    });
  }, [index, still]);
  return (
    <section className="mobile">
      <nav className="chips swipe" ref={chips} aria-label="Fields">
        {atlas.fields.map((f, n) => {
          const hits = matches ? f.items.filter((i) => matches.has(i.id)).length : f.items.length;
          return (
            <button
              key={f.id}
              style={{ '--c': f.color }}
              aria-pressed={n === index}
              className={n === index ? 'on' : ''}
              onClick={() => go(n)}
            >
              {f.name}<small>{hits}</small>
            </button>
          );
        })}
      </nav>
      <motion.div
        key={field.id}
        className="path"
        style={{ '--c': field.color }}
        // New field slides in at once; no exit wait, so switching never blocks on the old one.
        initial={still ? false : { opacity: 0, x: 40 * direction }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.35, ease: EASE }}
        drag="x"
        dragConstraints={{ left: 0, right: 0 }}
        dragElastic={0.2}
        onDragEnd={(_, info) => {
          if (info.offset.x < -70) go(index + 1);
          else if (info.offset.x > 70) go(index - 1);
        }}
      >
        <div className="path-head">
          <span className="lane-code">
            {String(index + 1).padStart(2, '0')} / {atlas.fields.length} · {field.id}
          </span>
          <h2>{field.name}</h2>
          <small>Swipe for the next field</small>
        </div>
        <svg className="spine" aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 2 100">
          <motion.line
            x1="1"
            y1="0"
            x2="1"
            y2="100"
            initial={{ pathLength: still ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.9, ease: EASE }}
          />
        </svg>
        {items.length ? items.map((i, n) => (
          <motion.button key={i.id} className="step" onClick={() => onOpen(i.id)}
            initial={still ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: still ? 0 : Math.min(n * 0.05, 0.5), ease: EASE }}>
            <span className={'dot' + (i.score ? ' moving' : '')} />
            <span className="node-id">{i.id}<em>{i.progressCount} progress</em></span>
            <span className="node-title">{i.title}</span>
            <MilestoneBar status={i.status} />
          </motion.button>
        )) : <p className="empty">No matches in this field.</p>}
      </motion.div>
    </section>
  );
}

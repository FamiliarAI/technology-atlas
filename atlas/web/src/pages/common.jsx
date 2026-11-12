import { useEffect } from 'react';
import { STATUS } from '../data.jsx';
import { StatusMark } from '../glyphs.jsx';
import { SITE } from '../site.js';

// Every page names itself in the tab: "Page · Technology Atlas".
export function useTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · ${SITE}` : SITE;
  }, [title]);
}

export const number = (n) => n.toLocaleString('en-GB');

export const plural = (n, one, many = one + 's') => `${number(n)} ${n === 1 ? one : many}`;

// One word for a breakthrough's state, never colour alone. It describes the atlas's
// assessment: a breakthrough nobody has judged a source against is "not yet assessed".
export function progressOf(item) {
  const n = item.status.length;
  const whole = item.overall
    ? `${item.overall === 1 ? '1 paper' : `${item.overall} papers`} toward the whole`
    : '';
  if (n && item.met === n) return { status: 'met', word: 'Met' };
  let word = '';
  if (item.met && item.moving) word = `${item.met} met, ${item.moving} in progress, of ${n}`;
  else if (item.met) word = `${item.met} of ${n} met`;
  else if (item.moving) word = `${item.moving} of ${n} in progress`;
  if (word) return { status: 'in_progress', word: whole ? `${word}; ${whole}` : word };
  if (whole) return { status: 'in_progress', word: whole };
  return { status: 'none', word: STATUS.none };
}

// A compact row of milestone marks (hollow, half, full) and a word for the whole.
export function MilestoneMeter({ item }) {
  const { status, word } = progressOf(item);
  const n = item.status.length;
  return (
    <span className={'meter ' + status}>
      <span className="meter-marks" aria-hidden="true">
        {item.status.map((s, i) => (
          <StatusMark key={i} status={s} size={11} />
        ))}
      </span>
      <span className="meter-word">
        {word}
        <span className="visually-hidden"> ({plural(n, 'milestone')})</span>
      </span>
    </span>
  );
}

export const Arrow = ({ size = 13 }) => (
  <svg viewBox="-8 -8 16 16" width={size} height={size} aria-hidden="true" className="arrow">
    <path d="M-5 0H5M1 -4L5 0L1 4" />
  </svg>
);

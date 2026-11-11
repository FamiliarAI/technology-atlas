import { useEffect, useRef } from 'react';
import { random } from './sky.js';

// The middle depth layer: a drawn field of faint background stars, seeded so it never changes.
export default function Starfield({ density = 1, seed = 7, className = '' }) {
  const canvas = useRef(null);
  useEffect(() => {
    const el = canvas.current;
    const draw = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (!w || !h) return;
      el.width = w * ratio;
      el.height = h * ratio;
      const ctx = el.getContext('2d');
      ctx.scale(ratio, ratio);
      const rand = random(seed);
      const count = Math.round(((w * h) / 2600) * density);
      for (let n = 0; n < count; n++) {
        const x = rand() * w;
        const y = rand() * h;
        const m = Math.pow(rand(), 3.2);
        const r = 0.35 + m * 1.1;
        const warm = rand() < 0.12;
        ctx.globalAlpha = 0.18 + m * 0.6;
        ctx.fillStyle = warm ? '#FFE2B8' : '#D7E2FF';
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [density, seed]);
  return <canvas ref={canvas} className={'starfield ' + className} aria-hidden="true" />;
}

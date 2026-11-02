import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { loadAtlas } from './api.js';
import Tree from './Tree.jsx';
import MobilePath from './MobilePath.jsx';
import Detail from './Detail.jsx';
import { EASE } from './motion.js';

const useNarrow = () => {
  const query = '(max-width: 760px)';
  const [narrow, setNarrow] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const m = matchMedia(query);
    const on = () => setNarrow(m.matches);
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, []);
  return narrow;
};

const fromHash = () => decodeURIComponent(location.hash.slice(1)) || null;

export default function App() {
  const [atlas, setAtlas] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(fromHash);
  const narrow = useNarrow();

  useEffect(() => { loadAtlas().then(setAtlas, (e) => setError(e.message)); }, []);
  useEffect(() => {
    const on = () => setSelected(fromHash());
    addEventListener('hashchange', on);
    return () => removeEventListener('hashchange', on);
  }, []);

  const open = (id) => { history.replaceState(null, '', id ? '#' + id : location.pathname); setSelected(id); };

  const matches = useMemo(() => {
    if (!atlas || !query.trim()) return null;
    const q = query.trim().toLowerCase();
    return new Set(Object.values(atlas.items).filter((i) => `${i.id} ${i.title} ${i.search_text}`.toLowerCase().includes(q)).map((i) => i.id));
  }, [atlas, query]);

  if (error) return <div className="state">Collection unavailable: {error}. Check that <code>python3 -m atlas.server</code> is running.</div>;
  if (!atlas) return <div className="state"><span className="pulse" /> Loading the tree…</div>;

  const totals = Object.values(atlas.items).reduce((t, i) => {
    for (const s of i.status) t[s] = (t[s] || 0) + 1;
    return t;
  }, {});

  return (
    <div className="app">
      <header className="top">
        <motion.div className="brand" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: EASE }}>
          <span className="mark">✳</span>
          <div>
            <div className="eyebrow">TECHNOLOGY ATLAS · TECH TREE</div>
            <h1>What becomes <em>possible next?</em></h1>
          </div>
        </motion.div>
        <div className="stats">
          <Stat value={Object.keys(atlas.items).length} label="breakthroughs" />
          <Stat value={atlas.fields.length} label="fields" />
          <Stat value={totals.met || 0} label="milestones met" tone="met" />
          <Stat value={totals.in_progress || 0} label="in progress" tone="moving" />
        </div>
        <label className="search">
          <span aria-hidden="true">⌕</span>
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search capabilities, ideas, IDs…" aria-label="Search breakthroughs" />
          {matches && <span className="hits">{matches.size}</span>}
        </label>
      </header>
      <Legend />
      {narrow
        ? <MobilePath atlas={atlas} matches={matches} onOpen={open} />
        : <Tree atlas={atlas} matches={matches} selected={selected} onOpen={open} />}
      <AnimatePresence>
        {selected && atlas.items[selected] && <Detail key={selected} atlas={atlas} id={selected} narrow={narrow} onOpen={open} onClose={() => open(null)} />}
      </AnimatePresence>
      <footer className="foot">Proposals, not forecasts. Nothing here is presented as achieved unless a milestone is marked met. Research as of {atlas.asOf}.</footer>
    </div>
  );
}

function Stat({ value, label, tone }) {
  return <div className={'stat ' + (tone || '')}><strong>{value}</strong><span>{label}</span></div>;
}

function Legend() {
  return (
    <div className="legend" aria-label="Milestone legend">
      <span><i className="seg met" /> Milestone met</span>
      <span><i className="seg in_progress" /> In progress</span>
      <span><i className="seg none" /> No progress linked</span>
      <span className="legend-note">Each bar segment is one milestone. Lines show breakthroughs discussed together, not prerequisites.</span>
    </div>
  );
}

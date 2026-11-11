import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAtlas } from '../data.jsx';
import { FieldEmblem } from '../glyphs.jsx';

const PAGES = {
  claims: {
    eyebrow: 'The claims',
    title: 'What exactly are we predicting?',
    text: 'Every “needs” link written out as a sentence, grouped by field and marked standing or falsified. The claims in brief are on the home page.',
    link: ['/#claims-title', 'The claims in brief'],
  },
  about: {
    eyebrow: 'Method',
    title: 'How is this made, and what are its limits?',
    text: 'How breakthroughs are researched, what a milestone and a link mean, how sources are saved and quotes checked, which models did what, and how to challenge an entry.',
    link: ['/atlas', 'Go to the atlas'],
  },
  missing: {
    eyebrow: 'Off the chart',
    title: 'There is nothing at this address.',
    text: 'The page may have moved, or the link may be mistyped.',
    link: ['/', 'Back to the home page'],
  },
};

export default function Coming({ page }) {
  const { field: fieldId } = useParams();
  const { atlas } = useAtlas();
  const field = fieldId && atlas?.field[fieldId];
  const p = fieldId
    ? {
        eyebrow: `Constellation ${fieldId}`,
        title: field ? field.name : 'What is in this area?',
        text: 'A page for each constellation: its scope, its shape in the sky, and its breakthroughs in prerequisite order. Until then the atlas lists them.',
        link: [`/atlas?field=${fieldId}`, 'Show it in the atlas'],
      }
    : PAGES[page];
  useEffect(() => {
    document.title = `${p.eyebrow} · Technology Atlas`;
  }, [p.eyebrow]);
  return (
    <section className="coming">
      {field && <FieldEmblem field={field} atlas={atlas} size={56} />}
      <p className="eyebrow">{p.eyebrow}</p>
      <h1>{p.title}</h1>
      <p className="coming-text">{p.text}</p>
      {page !== 'missing' && <p className="coming-tag mono">This page is coming.</p>}
      <Link to={p.link[0]} className="button quiet">
        {p.link[1]}
      </Link>
    </section>
  );
}

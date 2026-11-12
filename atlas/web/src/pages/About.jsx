import { Link } from 'react-router-dom';
import { formatDate, useAtlas } from '../data.jsx';
import { AUTHOR, ISSUES_URL, REPOSITORY_PUBLIC } from '../site.js';
import { number, plural, useTitle } from './common.jsx';

// Every statement here is checked against the repository: the pipeline in ingestion/README.md,
// the terms in docs/plans/technology-graph-plan.md, the quote check in ingestion/pipeline.py
// (passage_matches) and atlas/add.py, the label call in atlas/labels.py, and the withheld lists in atlas/core/CLM/field.json and VIR/field.json.

const STAGES = [
  [
    'Research',
    'A model with web search lists the field’s candidate breakthroughs, without seeing any earlier list, and cites its sources.',
  ],
  [
    'Reconcile',
    'The same model compares its list with the field’s original list of candidates and researches further where they differ.',
  ],
  [
    'Format',
    'The notes become structured records: concept, significance, what is missing, current state, completion criteria and related concepts, with a change log.',
  ],
  [
    'Capture',
    'Every cited source is downloaded and saved, with its text extracted. No model is involved.',
  ],
  [
    'Review',
    'A second model reads each breakthrough against the saved sources and proposes corrections. Missing evidence is recorded as unresolved, not as contradicted.',
  ],
  [
    'Rewrite',
    'The reviewing model writes one final record per breakthrough from the research, the review and the source details.',
  ],
  [
    'Finish',
    'The records are validated, backed up outside the project and imported into the atlas, one field at a time.',
  ],
];

const WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine'];
const words = (n) => WORDS[n] || String(n);

const SECTIONS = [
  ['map', 'A map, not a forecast'],
  ['research', 'How a breakthrough is researched'],
  ['terms', 'What a milestone and a step mean'],
  ['sources', 'How sources are saved and quotes checked'],
  ['limits', 'What this is not, yet'],
  ['challenge', 'How to challenge an entry'],
];

export default function About() {
  const { atlas } = useAtlas();
  useTitle('Method');
  const t = atlas?.totals;
  const withheld = atlas?.withheld || [];
  return (
    <article className="page about-page">
      <header className="page-head">
        <p className="eyebrow">Method</p>
        <h1>How is this made, and what are its limits?</h1>
        <p className="lead">
          Every entry in the atlas was researched and written by language models, from sources they
          found and that were saved and checked. No person has reviewed the entries yet. This page
          says how they were made, so that each one can be judged and challenged.
        </p>
        <p className="byline">
          By <span className="byline-name">{AUTHOR}</span>
          {atlas && <> · research as of {formatDate(atlas.asOf)}</>}
        </p>
      </header>

      <div className="about-body">
        <div className="about-main">
          <section id="map" className="prose-section" aria-labelledby="map-title">
            <h2 id="map-title">A map, not a forecast</h2>
            <div className="prose">
              <p>
                The atlas is a map of breakthroughs worth working towards, now that superintelligence
                can help. It is not a forecast. It says nothing about when any breakthrough will
                arrive, or in what order.
              </p>
              <p>
                The breakthroughs and their milestones were proposed by AI research models, working
                from the literature they cite. No outside body has adopted them.
              </p>
              <p>
                A cited paper supports part of the case: a result, a measurement, a gap. It does not
                endorse the way the atlas defines the breakthrough or its milestones.
              </p>
            </div>
          </section>

          <section id="research" className="prose-section" aria-labelledby="research-title">
            <h2 id="research-title">How a breakthrough is researched</h2>
            <div className="prose">
              <p>
                The atlas covers {atlas ? atlas.fields.length : 66} fields of research in{' '}
                {atlas ? atlas.regions.length : 8} regions. Each field went through the same
                pipeline of seven stages, and each stage keeps the name of the model that did its
                work.
              </p>
            </div>
            <ol className="stages">
              {STAGES.map(([name, text], n) => (
                <li key={name}>
                  <span className="mono stage-num">{n + 1}</span>
                  <div>
                    <h3>{name}</h3>
                    <p>{text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="prose">
              <h3>Which models did what</h3>
              <p>
                Grok (<code>grok-4.7</code>) did the first research pass for 39 fields. When its
                quota ran out, Codex Terra (<code>gpt-6.1-terra</code>) researched the other 27, and
                finished the reconciliation for one of Grok’s. Breakthroughs researched by Terra
                cite fewer sources: a median of one each, against three for Grok’s. Terra also
                formatted every field. Codex Sol (<code>gpt-6.1-sol</code>) reviewed the
                breakthroughs against their saved sources and rewrote every final record, and later
                wrote the short label for each milestone from its full criterion.
              </p>
            </div>
          </section>

          <section id="terms" className="prose-section" aria-labelledby="terms-title">
            <h2 id="terms-title">What a milestone and a step mean</h2>
            <dl className="terms">
              <div>
                <dt>Breakthrough</dt>
                <dd>
                  One capability worth working towards, with a permanent ID such as{' '}
                  <code>QUA-01</code>.
                  {t && ` There are ${number(t.breakthroughs)}.`}
                </dd>
              </div>
              <div>
                <dt>Milestone</dt>
                <dd>
                  One of a breakthrough’s completion criteria, with a permanent ID such as{' '}
                  <code>QUA-01.m1</code>, a short label and the full criterion text. Milestones are
                  tests of progress along the way; a breakthrough is reached when all of them are
                  met.
                </dd>
              </div>
              <div>
                <dt>Progress</dt>
                <dd>
                  One paper judged against one milestone: it <em>advances</em>, <em>meets</em> or{' '}
                  <em>contradicts</em> it, with an exact quote.
                  {t &&
                    ` So far ${plural(t.moving + t.met, 'milestone')} ${
                      t.moving + t.met === 1 ? 'has' : 'have'
                    } moved.`}
                </dd>
              </div>
              <div>
                <dt>Step toward the whole</dt>
                <dd>
                  A paper judged to move a breakthrough forward as a whole, without advancing or
                  meeting any one milestone. It is quoted in the same way, and it warms the star.
                </dd>
              </div>
              <div>
                <dt>Not yet assessed</dt>
                <dd>
                  A milestone that no paper has been judged against. It describes the atlas, not the
                  science: almost every milestone is still in this state.
                </dd>
              </div>
            </dl>
          </section>

          <section id="sources" className="prose-section" aria-labelledby="sources-title">
            <h2 id="sources-title">How sources are saved and quotes checked</h2>
            <div className="prose">
              <p>
                A source is a paper or a page, identified by its address. When it is cited, a copy
                is downloaded and kept, identified by the SHA-256 hash of its contents, and its text
                is extracted. The saved copies are not published; this site links to the originals.
              </p>
              <p>
                When a source is judged against a milestone, the model must quote the passage that
                supports its judgement, and the quote must appear in the saved text exactly. The one
                allowance is that spacing and hyphens between letters may differ, because extracting
                text from a PDF splits and joins words; every letter, digit and other character must
                match. A judgement whose quote is not found is rejected and never reaches the atlas.
              </p>
            </div>
          </section>

          <section id="limits" className="prose-section" aria-labelledby="limits-title">
            <h2 id="limits-title">What this is not, yet</h2>
            <div className="prose">
              <p>
                <strong>These are proposals.</strong> Every breakthrough and milestone was written
                by a model and checked by another model. No person has reviewed them. Some
                breakthroughs may duplicate others in neighbouring fields, and some milestones may
                be wrong.
              </p>
              <p>
                <strong>Nothing has been edited.</strong> Until this first version is published, the
                content stands as the research pipeline produced it. Renames, merges, splits and
                reworked milestones come after, as tracked edits.
              </p>
              {withheld.length > 0 && (
                <>
                  <p>
                    <strong>
                      {withheld.length === 1
                        ? 'One concept is withheld.'
                        : `${words(withheld.length)} concepts are withheld.`}
                    </strong>{' '}
                    The provider of the reviewing model declined to review{' '}
                    {withheld.length === 1 ? 'it' : 'them'}, citing its safety rules. The pipeline
                    does not narrow a refused concept or send it to another model, so{' '}
                    {withheld.length === 1 ? 'it is' : 'these are'} left out of the atlas:
                  </p>
                  <ul className="withheld">
                    {withheld.map((w) => (
                      <li key={w.id}>
                        <span className="mono">{w.id}</span> {w.title}{' '}
                        <span className="muted">
                          (
                          <Link to={'/field/' + w.field}>
                            {atlas.field[w.field]?.name || w.field}
                          </Link>
                          )
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </section>

          <section id="challenge" className="prose-section" aria-labelledby="challenge-title">
            <h2 id="challenge-title">How to challenge an entry</h2>
            <div className="prose">
              <p>
                Every entry can be wrong in a way that can be shown: a milestone that is already
                met, a quote that does not say what it is said to say, a paper judged against the
                wrong milestone, or a breakthrough that is not one. To challenge one,{' '}
                {REPOSITORY_PUBLIC ? (
                  <a href={ISSUES_URL} target="_blank" rel="noopener noreferrer">
                    open an issue on the repository
                  </a>
                ) : (
                  'open an issue on the repository'
                )}{' '}
                with the entry’s ID and the source that shows it.
              </p>
              {!REPOSITORY_PUBLIC && (
                <p className="muted">
                  The repository is private for now; the link will appear here when it opens.
                </p>
              )}
            </div>
            <p className="page-ways">
              <Link to="/atlas" className="text-link">
                Go to the atlas
              </Link>
            </p>
          </section>
        </div>
        <aside className="about-side">
          <nav className="toc" aria-label="On this page">
            <ol>
              {SECTIONS.map(([id, title], n) => (
                <li key={id}>
                  <a href={'#' + id}>
                    <span className="mono">{String(n + 1).padStart(2, '0')}</span>
                    {title}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </aside>
      </div>
    </article>
  );
}

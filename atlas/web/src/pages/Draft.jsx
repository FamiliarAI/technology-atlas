import { StatusLabel } from '../glyphs.jsx';
import { Citations } from '../Record.jsx';
import { BriefSource, Items, Prose, Question, ResearchRecord } from './Brief.jsx';

// A trial reading order for a breakthrough page (/draft/<ID>), kept beside the current page
// (/b/<ID>) for comparison: what it is, why it matters, where we are, what is missing, how we
// will know, the papers. The definitions are written by hand for the trial pages only.

const LEAD_SOURCES = 4;

const DEFINITIONS = {
  'BME-12': [
    'Organs grown in animals, such as genetically modified pigs, become a dependable option for people who need a transplant.',
    'That means an organ that keeps working in a person for years, with treatment and risks a patient can live with, and a supply reliable enough for hospitals to count on. One successful operation would show only part of it.',
  ],
};

// Hand-written text for the trial pages. Each "now" item states a result first; the paper that
// reported it follows as a link.
const TRIAL = {
  'BME-12': {
    now: [
      { text: 'Pig kidneys have worked inside living people, but so far only for months.' },
      {
        text: 'The longest so far: a kidney from a genetically modified pig kept one patient off dialysis (machine filtering of the blood) for 271 days. It then failed, after damage to its small blood vessels, and was removed. The patient went on to receive a human kidney. No infection from the pig was found.',
        url: 'https://pubmed.ncbi.nlm.nih.gov/42692038/',
      },
      {
        text: 'In another patient, a pig kidney did a kidney’s essential jobs: clearing waste, balancing salts and concentrating urine.',
        url: 'https://www.nature.com/articles/s41467-025-63153-3.pdf',
      },
      {
        text: 'In monkeys, pig kidneys have lasted longer, up to 758 days, when the donor pigs carried added human genes.',
        url: 'https://www.nature.com/articles/s41586-023-06594-4',
      },
      { text: 'So a pig organ can work in a body. Nobody has yet shown that it works for years, or in many patients.' },
    ],
    why: [
      'Far more people need a transplant than there are human organs to give. A source of organs that can be bred and supplied on demand would mean shorter waits, and transplants earlier in an illness.',
    ],
    // Where the entry came from, stated as it is.
    origin: [
      'Nobody handed us this goal. In 2026 we asked an AI research model to survey biomedical engineering and name the advances that would change the field most. It proposed this one, and a second model reviewed it.',
      'We have not yet collected the people and organisations who have publicly made the case for it, or their own definitions of it. Until we do, the definition above is ours.',
    ],
    // A proposal for the owner to settle; the number is a placeholder.
    success: [
      'Animal organs are an ordinary treatment. For at least one kind of organ, hospitals transplant a thousand or more a year, and the people who receive them do about as well as people who receive a human organ.',
    ],
    // The owner's ladder (November 13). Each result is one plain sentence and its reference.
    ladder: [
      {
        status: 'in_progress',
        label: 'A suitable organ can be grown in an animal',
        explanation: 'An animal, bred or genetically modified for the purpose, grows an organ that a human body can accept.',
        results: [
          {
            text: 'Kidneys from pigs with added human genes kept monkeys alive for up to 758 days.',
            url: 'https://www.nature.com/articles/s41586-023-06594-4',
          },
        ],
      },
      {
        status: 'in_progress',
        label: 'The organ is transplanted into a person, and the person lives',
        explanation: 'The organ does its job inside a living person for years, with treatment and risks the person can live with.',
        results: [
          {
            text: 'A pig kidney kept one patient off dialysis (machine filtering of the blood) for 271 days. It then failed and was removed, and the patient received a human kidney.',
            url: 'https://pubmed.ncbi.nlm.nih.gov/42692038/',
          },
          {
            text: 'In another patient, a pig kidney did a kidney’s essential jobs: clearing waste, balancing salts and concentrating urine.',
            url: 'https://www.nature.com/articles/s41467-025-63153-3.pdf',
          },
        ],
      },
      {
        status: 'none',
        label: 'The organs are produced and transplanted in large numbers',
        explanation: 'Hundreds, then thousands, of transplants a year, with a supply of screened organs that hospitals can count on.',
        results: [],
      },
    ],
    // Vancouver (NLM) style; details from PubMed and Crossref, fetched November 13, 2026.
    refs: {
      'https://pubmed.ncbi.nlm.nih.gov/42692038/': {
        text: 'Riella LV, Borges TJ, Rosales IA, Avillach CT, Palsson R, Hullekes F, et al. Porcine kidney xenotransplantation as a bridge to allotransplantation: a first-in-human study. Lancet. 2026;408(10559):1029-1040.',
        doi: '10.1016/S0140-6736(26)01295-X',
      },
      'https://www.nature.com/articles/s41467-025-63153-3.pdf': {
        text: 'Lee SA, Lafargue MC, Williams WW, Safa K, Palsson R, Al Jurdi A, et al. Physiologic homeostasis in a living human after pig kidney xenotransplantation. Nat Commun. 2025;16(1):8453.',
        doi: '10.1038/s41467-025-63153-3',
      },
      'https://www.nature.com/articles/s41586-023-06594-4': {
        text: 'Anand RP, Layer JV, Heja D, Hirose T, Lassiter G, Firl DJ, et al. Design and testing of a humanized porcine donor for xenotransplantation. Nature. 2023;622(7982):393-401.',
        doi: '10.1038/s41586-023-06594-4',
      },
    },
    missing: [
      'Years of function in people. The longest so far is 271 days, in one patient.',
      'The same result again and again: in many patients, at different hospitals, with organs from different producers.',
      'A working supply: breeding the animals, checking each organ and watching patients for infection, at the scale hospitals need.',
    ],
    milestones: {
      m1: {
        label: 'Animal organs last for years in trials at several hospitals',
        explanation:
          'Trials at several hospitals would have to show the organ still working after years, with survival, infection risk and treatment load that compare acceptably with today’s care.',
      },
      m2: {
        label: 'The results repeat, and the organs can be supplied',
        explanation:
          'The same outcomes would have to appear across many patients, different surgical teams and organs from independent producers, with screening and monitoring that work in practice.',
      },
      m3: {
        label: 'Each claim of success says exactly what was shown',
        explanation:
          'A claim would have to state which animal, which organ, which patients, which treatment and how long they were followed. A kidney result would not count for other organs, and a temporary bridge to a human organ would not count as lasting replacement.',
      },
    },
  },
};

const list = (value) => (Array.isArray(value) ? value : []);
const texts = (value) => list(value).filter((t) => typeof t === 'string' && t.trim());
const said = (value) => (typeof value === 'string' && value.trim() ? value.trim() : null);

const NUMBER = ['none', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight'];
const word = (n) => NUMBER[n] || String(n);

// "Two of the three are under way. None has been shown yet."
function tally(status) {
  const total = status.length;
  const met = status.filter((s) => s === 'met').length;
  const moving = status.filter((s) => s === 'in_progress').length;
  const parts = [];
  if (met) parts.push(`${word(met)} of the ${word(total)} ${met === 1 ? 'has' : 'have'} been shown`);
  if (moving) {
    const lead = met ? word(moving) : `${word(moving)} of the ${word(total)}`;
    parts.push(`${lead} ${moving === 1 ? 'is' : 'are'} under way`);
  }
  if (!met && !moving) return 'No paper has been checked against them yet.';
  const line = parts.join(', and ') + '.';
  const first = line[0].toUpperCase() + line.slice(1);
  return met ? first : first + ' None has been shown yet.';
}

// A footnote mark: the paper's number in "What is the evidence?", linked to its entry there.
function Ref({ n }) {
  if (!n) return null;
  return (
    <sup className="draft-ref">
      <a href={`#ref-${n}`} aria-label={`Reference ${n}`}>
        {n}
      </a>
    </sup>
  );
}

// One result reported by a paper: its words, then the footnote mark.
function Result({ row, refOf }) {
  return (
    <div className="draft-result">
      <blockquote className="brief-quote">
        <p>
          “{row.quote}”
          <Ref n={refOf(row.url)} />
        </p>
      </blockquote>
    </div>
  );
}

export default function DraftBody({ brief, record, item, sources, position, judged, fade }) {
  const what = DEFINITIONS[item.id] || texts(brief.possible);
  const why = texts(brief.why);
  const trial = TRIAL[item.id] || {};
  const now = trial.now || texts(brief.shown).map((text) => ({ text }));
  const missing = trial.missing || texts(brief.missing);
  const uncertain = texts(brief.uncertain);
  const papers = list(brief.sources).filter((s) => s && typeof s === 'object');
  const milestones = list(record.milestones);
  const criteria = list(record.completion_criteria);
  const plain = new Map(list(brief.milestones).filter((m) => m?.id).map((m) => [m.id, m]));
  const whole = judged.filter((r) => position(r) === null);
  const total = item.status.length;
  const refOf = (url) => {
    const at = papers.findIndex((s) => s.url === url);
    return at >= 0 ? at + 1 : null;
  };
  const paper = (source) => (
    <BriefSource
      key={source.url}
      number={refOf(source.url)}
      citation={trial.refs?.[source.url]}
      source={source}
      entry={sources.byUrl.get(source.url)}
      forLabel="What it adds"
      notLabel="What it leaves open"
    />
  );
  if (trial.ladder) {
    return (
      <>
        <Question id="what-title" title="What is it?" fade={fade(1)}>
          <div className="brief-lead">
            <Prose items={what} />
          </div>
        </Question>
        <Question id="why-title" title="Why would it matter?" fade={fade(2)}>
          <Prose items={trial.why || why} />
        </Question>
        <Question id="origin-title" title="Where does this idea come from?" fade={fade(3)}>
          <Prose items={trial.origin} />
        </Question>
        <Question id="success-title" title="What does success look like?" fade={{}}>
          <Prose items={trial.success} />
        </Question>
        <section className="bpage-section milestones brief-q" aria-labelledby="ms-title">
          <h2 id="ms-title">Milestones on the way</h2>
          <p className="section-lead">
            The results we expect to see before success, each with the papers that have moved it so far.
          </p>
          <ol>
            {trial.ladder.map((m, n) => (
              <li key={n} className={'milestone ' + m.status} id={`m${n + 1}`}>
                <span className="milestone-num mono" aria-hidden="true">
                  {n + 1}
                </span>
                <div className="milestone-body">
                  <h3>
                    <span className="visually-hidden">Milestone {n + 1}: </span>
                    {m.label}
                  </h3>
                  <p className="milestone-explain">{m.explanation}</p>
                  <p className="draft-progress source-section">
                    {m.results.length ? 'Results so far' : 'No results yet'}
                  </p>
                  {m.results.length > 0 && (
                    <ul className="issues draft-results">
                      {m.results.map((r, k) => (
                        <li key={k}>
                          {r.text}
                          <Ref n={refOf(r.url)} />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
        <Question id="who-title" title="References" fade={{}}>
          <ol className="brief-sources">{papers.map(paper)}</ol>
        </Question>
        <ResearchRecord record={record} sources={sources} />
      </>
    );
  }

  return (
    <>
      <Question id="what-title" title="What is it?" fade={fade(1)}>
        <div className="brief-lead">
          <Prose items={what} />
        </div>
      </Question>

      {why.length > 0 && (
        <Question id="why-title" title="Why would it matter?" fade={fade(2)}>
          <Prose items={why} />
        </Question>
      )}

      {now.length > 0 && (
        <Question id="shown-title" title="Where are we now?" fade={fade(3)}>
          {now.map((p, n) => (
            <div key={n} className="record-para">
              <p>
                {p.text}
                {p.url && (
                  <>
                    <Ref n={refOf(p.url)} />
                  </>
                )}
              </p>
            </div>
          ))}
        </Question>
      )}

      {missing.length > 0 && (
        <Question id="missing-title" title="What is still missing?" fade={{}}>
          <Items items={missing} />
        </Question>
      )}

      {total > 0 && (
        <section className="bpage-section milestones brief-q" aria-labelledby="ms-title">
          <h2 id="ms-title">How will we know it has happened?</h2>
          <p className="section-lead">
            We will count it as achieved when {total === 1 ? 'this result has' : `all ${word(total)} of these results have`}{' '}
            been shown. {tally(item.status)}
          </p>
          <p className="section-note">We call these milestones. They are our own proposal.</p>
          <ol>
            {item.status.map((status, n) => {
              const m = milestones[n] || { id: `m${n + 1}`, label: null, status };
              const words = trial.milestones?.[m.id] || plain.get(m.id) || {};
              const label = said(words.label) || m.label;
              const explanation = said(words.explanation);
              const criterion = criteria[n];
              const rows = judged.filter((r) => position(r) === n + 1);
              return (
                <li key={m.id} className={'milestone ' + (m.status || status)} id={`m${n + 1}`}>
                  <span className="milestone-num mono" aria-hidden="true">
                    {n + 1}
                  </span>
                  <div className="milestone-body">
                    <StatusLabel status={m.status || status} />
                    <h3>
                      <span className="visually-hidden">Milestone {n + 1}: </span>
                      {label || criterion?.text || `Milestone ${n + 1}`}
                    </h3>
                    {explanation && <p className="milestone-explain">{explanation}</p>}
                    {criterion && (label || explanation) && (
                      <details className="criterion">
                        <summary>The exact wording</summary>
                        <p>{criterion.text}</p>
                        <Citations urls={criterion.source_urls} sources={sources} />
                      </details>
                    )}
                    {rows.length > 0 && <p className="draft-progress source-section">Results so far</p>}
                    {rows.map((r, k) => (
                      <Result key={k} row={r} refOf={refOf} />
                    ))}
                  </div>
                </li>
              );
            })}
          </ol>
          {whole.length > 0 && (
            <div className="brief-whole">
              <h3>Progress on the goal as a whole</h3>
              {whole.map((r, k) => (
                <Result key={k} row={r} refOf={refOf} />
              ))}
            </div>
          )}
        </section>
      )}

      {papers.length > 0 && (
        <Question id="who-title" title="References" note="The papers this page draws on, and what each one showed." fade={{}}>
          <ol className="brief-sources">{papers.slice(0, LEAD_SOURCES).map(paper)}</ol>
          {papers.length > LEAD_SOURCES && (
            <details className="criterion brief-more">
              <summary>
                {papers.length - LEAD_SOURCES} more {papers.length - LEAD_SOURCES === 1 ? 'paper' : 'papers'}
              </summary>
              <ol className="brief-sources">{papers.slice(LEAD_SOURCES).map(paper)}</ol>
            </details>
          )}
        </Question>
      )}

      {uncertain.length > 0 && (
        <Question id="uncertain-title" title="What is still an open question?" fade={{}}>
          <Items items={uncertain} />
        </Question>
      )}

      <ResearchRecord record={record} sources={sources} />
    </>
  );
}

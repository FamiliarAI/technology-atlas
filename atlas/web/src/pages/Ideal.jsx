import { Fragment } from 'react';

// A proposed breakthrough page (/draft/<ID>), written by hand for one entry so its order and
// content can be judged against the current page (/b/<ID>). Every figure and quotation was
// checked against its reference on November 13, 2026. Nothing here is read from the record.

const R = {
  hrsa: 1,
  iom: 2,
  ishlt: 3,
  niaid: 4,
  fda: 5,
  anand: 6,
  riella: 7,
  lee: 8,
  expand: 9,
  zhang: 10,
  ut: 11,
  egen: 12,
  umd: 13,
};

export const IDEAL = {
  'BME-12': {
    title: 'Xenotransplantation as routine clinical therapy',
    definition: [
      'Solid organs from another species are transplanted into human patients as an approved, routinely supplied treatment for end-stage organ failure, with graft survival comparable to that of organs from human donors. In current practice the source animal is a gene-edited pig.',
    ],
    need: {
      lead: 'Human donors supply fewer organs than patients need. United States figures, from the Organ Procurement and Transplantation Network:',
      head: ['Organ', 'On the waiting list, July 30, 2026', 'Transplants performed, 2025'],
      rows: [
        ['Kidney', '95,492', '27,574'],
        ['Liver', '8,776', '12,344'],
        ['Heart', '4,039', '4,587'],
      ],
      ref: R.hrsa,
      note: 'The waiting list is a count on one day; transplants are a total for the year.',
    },
    stated: {
      lead: 'Bodies that have stated clinical xenotransplantation as a goal:',
      items: [
        {
          who: 'Institute of Medicine, Committee on Xenograft Transplantation',
          year: '1996',
          quote: 'the committee concluded that the potential benefits of xenotransplants are great enough to justify this risk',
          gloss: 'The risk referred to is transmission of infection from the source animal.',
          ref: R.iom,
        },
        {
          who: 'International Society for Heart and Lung Transplantation, Xenotransplantation Advisory Committee',
          year: '2000',
          quote: 'Xenotransplantation offers the possibility of an unlimited supply of hearts and lungs that could be available electively when required.',
          ref: R.ishlt,
        },
        {
          who: 'National Institute of Allergy and Infectious Diseases, Immunobiology of Xenotransplantation Cooperative Research Program',
          year: 'programme begun 2005',
          quote: 'IXCRP’s overarching goal is to develop safe and effective strategies to enable clinical xenotransplantation.',
          ref: R.niaid,
        },
        {
          who: 'US Food and Drug Administration',
          year: 'current guidance page',
          quote: 'The development of xenotransplantation is, in part, driven by the fact that the demand for human organs for clinical transplantation far exceeds the supply.',
          ref: R.fda,
        },
      ],
      note: 'This entry was drafted by an AI research model in November 2026. It was not derived from these documents; they are cited as independent statements of the same goal.',
    },
    completion: {
      lead: 'Completion is a regulator’s decision. The breakthrough counts as achieved when a national regulator licenses a xenogeneic organ for marketing. In the United States that is approval by the Food and Drug Administration of a Biologics License Application (BLA).',
      basisTitle: 'Who set this',
      basis: [
        {
          text: 'The regulator. It is also the developers’ own stated endpoint. United Therapeutics, on its kidney trial: “we intend to use the results of this study to support a Biologics License Application (BLA) with the FDA”.',
          refs: [R.ut],
        },
        {
          text: 'We found no professional society, regulator or registered trial that defines clinical success as a number of transplants, a number of organ types or a survival time. Licensure is the only externally defined point at which a xenograft stops being investigational.',
        },
      ],
      trackedTitle: 'Measured alongside, with no threshold attached',
      tracked: [
        { measure: 'Longest xenograft function in a living person, published', value: '271 days (kidney)', refs: [R.riella] },
        { measure: 'Longest reported by a developer, not yet published', value: 'more than 9 months, ongoing (kidney)', refs: [R.egen] },
        { measure: 'Stated production capacity', value: 'up to 125 organs a year, one facility', refs: [R.ut] },
        { measure: 'For scale: US kidney transplants from human donors, 2025', value: '27,574', refs: [R.hrsa] },
      ],
    },
    organs: ['Kidney', 'Heart', 'Liver'],
    milestones: [
      {
        label: 'Preclinical survival threshold in non-human primates',
        criterion:
          'About 60% survival of life-supporting pig organs in non-human primates for at least 3 months, with at least 10 animals surviving that long, and evidence that survival beyond 6 months can be achieved.',
        setBy: 'ISHLT Xenotransplantation Advisory Committee, 2000, as its condition for considering a clinical trial. Written for heart and lung.',
        setRefs: [R.ishlt],
        evidence: [
          {
            organ: 'Kidney',
            verdict: 'partial',
            head: 'Kidney, cynomolgus monkey: median graft survival 176 days (n = 15), longest 758 days.',
            detail: 'Grafts with glycan-antigen knockouts and human transgenes (3KO.7TG, n = 8; 3KO.7TG.RI, n = 7), against a median of 24 days for knockouts alone (3KO ± RI, n = 6); P = 0.026, log-rank. Partial because the passages we hold do not state how many animals survived 3 months.',
            refs: [R.anand],
          },
        ],
      },
      {
        label: 'First use in living patients',
        criterion: 'A xenograft is transplanted into a living patient with a regulator’s authorisation, and the outcome is reported.',
        setBy: 'The regulator’s expanded-access route, under which the first kidney recipients were treated.',
        setRefs: [R.riella],
        evidence: [
          {
            organ: 'Kidney',
            verdict: 'met',
            head: 'Kidney, n = 1: dialysis independence for 271 days.',
            detail: 'EGEN-2784, transplanted January 25, 2025, under an FDA Expanded Access IND. T-cell-mediated rejection on the day-14 biopsy resolved with treatment. Function was stable for about 6 months, until immunosuppression was reduced during a bacterial infection; microvascular inflammation then progressed to thrombotic microangiopathy despite a persistently negative donor-specific crossmatch, ending in graft failure and nephrectomy. No porcine pathogen transmission detected. Human allotransplantation followed 82 days after explantation.',
            refs: [R.riella],
          },
          {
            organ: 'Kidney',
            verdict: 'met',
            head: 'Kidney, n = 5 (developer’s report, not peer reviewed): three recipients dialysis-free for more than 8 months.',
            detail: 'One has passed 9 months and remains on study. Two of the five have gone on to human-donor kidney transplants.',
            refs: [R.egen],
          },
          {
            organ: 'Kidney',
            verdict: 'met',
            head: 'Kidney, n = 1: creatinine clearance 64 mL/min/1.73 m² by postoperative day 35.',
            detail: 'Reached after treatment of rejection, in a separate living recipient.',
            refs: [R.lee],
          },
          {
            organ: 'Heart',
            verdict: 'met',
            head: 'Heart, n = 1: the recipient lived two months.',
            detail: 'Transplanted January 7, 2022. Figures are from the institution’s release on the published report.',
            refs: [R.umd],
          },
          {
            organ: 'Liver',
            verdict: 'met',
            head: 'Liver (auxiliary graft), n = 1: graft removed on day 38; the patient survived 171 days.',
            detail: 'Removal followed xenotransplantation-associated thrombotic microangiopathy. Figures are from the publisher’s release on this paper.',
            refs: [R.zhang],
          },
        ],
      },
      {
        label: 'A clinical trial is cleared and has transplanted its first participant',
        criterion: 'A regulator clears a prospective clinical trial of the xenograft, and the first participant receives one.',
        setBy: 'The regulator. In the United States, clearance of an Investigational New Drug application (IND).',
        setRefs: [R.ut],
        evidence: [
          {
            organ: 'Kidney',
            verdict: 'met',
            head: 'Kidney: EXPAND cleared January 2025; first transplant in the fourth quarter of 2025.',
            detail: 'NCT06878560, estimated enrolment 50, recruiting when checked on November 13, 2026.',
            refs: [R.ut, R.expand],
          },
          {
            organ: 'Kidney',
            verdict: 'partial',
            head: 'Kidney: RESTORE cleared, 33 patients, phase 1/2/3; expected to start in the first quarter of 2027.',
            detail: 'Developer’s report.',
            refs: [R.egen],
          },
          {
            organ: 'Heart',
            verdict: 'partial',
            head: 'Heart: EXPRESS cleared May 2026, initial cohort of up to two patients.',
            detail: 'Partial because no transplant in this study is reported in the sources we hold.',
            refs: [R.ut],
          },
        ],
      },
      {
        label: 'A trial reports its primary endpoints',
        criterion: 'Patient survival and xenograft survival at 24 weeks are reported for the trial cohort.',
        setBy: 'The EXPAND protocol. The registry record defines the endpoints, defines graft failure as nephrectomy, and sets no pass rate.',
        setRefs: [R.expand],
        evidence: [],
      },
      {
        label: 'Licensure',
        final: true,
        criterion: 'A national regulator licenses a xenogeneic organ for marketing. This is the completion criterion.',
        setBy: 'The regulator.',
        setRefs: [],
        evidence: [],
      },
    ],
    references: [
      {
        text: 'Health Resources and Services Administration. Organ donation statistics: detailed description of data [Internet]. Rockville (MD): HRSA; [reviewed 2026 Aug; cited 2026 Nov 13].',
        url: 'https://www.organdonor.gov/learn/organ-donation-statistics/detailed-description',
      },
      {
        text: 'Institute of Medicine (US) Committee on Xenograft Transplantation. Xenotransplantation: science, ethics, and public policy. Washington (DC): National Academies Press; 1996.',
        doi: '10.17226/5365',
      },
      {
        text: 'Cooper DK, Keogh AM, Brink J, Corris PA, Klepetko W, Pierson RN, et al. Report of the Xenotransplantation Advisory Committee of the International Society for Heart and Lung Transplantation: the present status of xenotransplantation and its potential role in the treatment of end-stage cardiac and pulmonary diseases. J Heart Lung Transplant. 2000;19(12):1125-65.',
        doi: '10.1016/s1053-2498(00)00224-2',
      },
      {
        text: 'National Institute of Allergy and Infectious Diseases. Immunobiology of Xenotransplantation Cooperative Research Program (IXCRP) [Internet]. Bethesda (MD): NIAID; [reviewed 2025 Aug 1; cited 2026 Nov 13].',
        url: 'https://www.niaid.nih.gov/research/immunobiology-xenotransplantation-cooperative-research-program',
      },
      {
        text: 'US Food and Drug Administration. Xenotransplantation [Internet]. Silver Spring (MD): FDA; [cited 2026 Nov 13].',
        url: 'https://www.fda.gov/vaccines-blood-biologics/xenotransplantation',
      },
      {
        text: 'Anand RP, Layer JV, Heja D, Hirose T, Lassiter G, Firl DJ, et al. Design and testing of a humanized porcine donor for xenotransplantation. Nature. 2023;622(7982):393-401.',
        doi: '10.1038/s41586-023-06594-4',
      },
      {
        text: 'Riella LV, Borges TJ, Rosales IA, Avillach CT, Palsson R, Hullekes F, et al. Porcine kidney xenotransplantation as a bridge to allotransplantation: a first-in-human study. Lancet. 2026;408(10559):1029-40.',
        doi: '10.1016/S0140-6736(26)01295-X',
      },
      {
        text: 'Lee SA, Lafargue MC, Williams WW, Safa K, Palsson R, Al Jurdi A, et al. Physiologic homeostasis in a living human after pig kidney xenotransplantation. Nat Commun. 2025;16(1):8453.',
        doi: '10.1038/s41467-025-63153-3',
      },
      {
        text: 'United Therapeutics. EXPAND: a prospective study to evaluate the safety and efficacy of the 10 GE Xenokidney in patients with end-stage renal disease (ESRD). ClinicalTrials.gov identifier: NCT06878560. [cited 2026 Nov 13].',
        url: 'https://clinicaltrials.gov/study/NCT06878560',
      },
      {
        text: 'Zhang W, Xu Q, Xu K, Jiang R, Wang S, Zheng M, et al. Genetically engineered pig-to-human liver xenotransplantation. J Hepatol. 2026;84(3):587-98.',
        doi: '10.1016/j.jhep.2025.08.044',
      },
      {
        text: 'United Therapeutics Corporation. Form 10-Q for the quarterly period ended June 30, 2026 [Internet]. Silver Spring (MD): United Therapeutics; 2026 [cited 2026 Nov 13].',
        url: 'https://ir.unither.com/~/media/Files/U/United-Therapeutics-IR/documents/events-and-presentations/uthr-10q-q2-2026.pdf',
      },
      {
        text: 'eGenesis. eGenesis announces clinical update in ongoing expanded access study of EGEN-2784 in patients with kidney failure [press release]. Cambridge (MA): eGenesis; 2026 Sep 3 [cited 2026 Nov 13].',
        url: 'https://egenesisbio.com/news-media/press-releases/egenesis-announces-clinical-update-in-ongoing-expanded-access-study-of-egen-2784-in-patients-with-kidney-failure',
      },
      {
        text: 'University of Maryland School of Medicine. University of Maryland School of Medicine faculty scientists and clinicians publish findings of world’s first successful transplant of genetically modified pig heart into human patient [press release]. Baltimore (MD): UMSOM; 2022 Jun 22 [cited 2026 Nov 13].',
        url: 'https://www.medschool.umaryland.edu/news/2022/university-of-maryland-school-of-medicine-faculty-scientists-and-clinicians-publish-findings-of-worlds-first-successful-transplant-of-genetically-modified-pig-heart-into-human-patient.html',
      },
    ],
    about:
      'Entry BME-12. First drafted by an AI research model and reviewed by a second; completion criterion, milestones and references revised November 13, 2026. Quotations are exact and every figure is taken from the reference cited beside it.',
  },
};

function Refs({ ns }) {
  if (!ns || !ns.length) return null;
  return (
    <sup className="ideal-ref">
      {ns.map((n, k) => (
        <Fragment key={n}>
          {k > 0 && ','}
          <a href={`#ref-${n}`} aria-label={`Reference ${n}`}>
            {n}
          </a>
        </Fragment>
      ))}
    </sup>
  );
}

// Progress is calculated, never written. A result is one paper's finding placed on one milestone
// for one case (here, an organ) with a verdict: 'met' (it satisfies the criterion) or 'partial'
// (it bears on the criterion without satisfying it).
//   cell(milestone, case)  = met if any result is met, else partial if any result, else none
//   milestone state        = the best cell across cases
//   furthest               = the last milestone met in any case
//   complete               = the final milestone is met
const RANK = { none: 0, partial: 1, met: 2 };
const best = (states) => states.reduce((a, b) => (RANK[b] > RANK[a] ? b : a), 'none');

export function progress(page) {
  const cells = page.milestones.map((m) =>
    page.organs.map((organ) => best(m.evidence.filter((e) => e.organ === organ).map((e) => e.verdict))),
  );
  const states = cells.map(best);
  const furthest = states.lastIndexOf('met');
  const perCase = page.organs.map((_, k) => cells.map((row) => row[k]).lastIndexOf('met') + 1);
  return {
    cells,
    states,
    furthest: furthest + 1,
    total: page.milestones.length,
    leaders: page.organs.filter((_, k) => furthest >= 0 && cells[furthest][k] === 'met'),
    perCase,
    met: states.filter((x) => x === 'met').length,
    partial: states.filter((x) => x === 'partial').length,
    gaps: states.map((x, n) => (n < furthest && x !== 'met' ? n + 1 : 0)).filter(Boolean),
    complete: states[states.length - 1] === 'met',
  };
}

const list = (items) =>
  items.length < 2 ? items.join('') : items.slice(0, -1).join(', ') + ' and ' + items[items.length - 1];

const WORD = { met: 'Met', partial: 'Partial', none: 'None' };

// One mark for one state, used everywhere a state is shown: filled, half, empty.
function Mark({ state }) {
  return (
    <svg className={'ideal-mark ' + state} viewBox="-8 -8 16 16" width="13" height="13" aria-hidden="true">
      <circle r="6" />
      {state === 'met' && <circle r="6" className="fill" />}
      {state === 'partial' && <path d="M0 -6A6 6 0 0 0 0 6Z" className="fill" />}
    </svg>
  );
}

function Section({ id, title, children }) {
  return (
    <section className="bpage-section reading ideal-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

export default function IdealBody({ page }) {
  const { need, stated, completion } = page;
  const at = progress(page);
  const next = page.milestones[at.furthest];
  return (
    <div className="ideal">
      <section className="ideal-definition" aria-label="Definition">
        {page.definition.map((text, n) => (
          <p key={n}>{text}</p>
        ))}
      </section>

      <section className="ideal-status-line" aria-label="Progress">
        <p className="ideal-track" aria-hidden="true">
          {at.states.map((state, n) => (
            <span key={n} className={'ideal-step ' + state}>
              <Mark state={state} />
              <span className="mono">{n + 1}</span>
            </span>
          ))}
        </p>
        <p className="ideal-status-main">
          {at.complete
            ? 'Complete.'
            : at.furthest
              ? `Milestone ${at.furthest} of ${at.total} met, for ${list(at.leaders).toLowerCase()}. Not complete.`
              : `No milestone met of ${at.total}.`}
        </p>
        <p className="ideal-status-sub">
          {page.organs.map((o, k) => `${o}: ${at.perCase[k]} of ${at.total}`).join(' · ')}
          {next && !at.complete && (
            <>
              {' · '}Next: <a href={`#m${at.furthest + 1}`}>{next.label.toLowerCase()}</a>
            </>
          )}
          {at.gaps.length > 0 && (
            <>
              {' · '}Earlier milestone not confirmed: <a href={`#m${at.gaps[0]}`}>{at.gaps.join(', ')}</a>
            </>
          )}
        </p>
      </section>

      <Section id="why-title" title="Why it is a goal">
        <p>{need.lead}</p>
        <table className="ideal-table">
          <thead>
            <tr>
              {need.head.map((h) => (
                <th key={h} scope="col">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {need.rows.map((row) => (
              <tr key={row[0]}>
                <th scope="row">{row[0]}</th>
                <td>{row[1]}</td>
                <td>{row[2]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="ideal-note">
          {need.note}
          <Refs ns={[need.ref]} />
        </p>
        <p>{stated.lead}</p>
        <ul className="ideal-stated">
          {stated.items.map((s) => (
            <li key={s.who}>
              <p className="ideal-who">
                {s.who}, {s.year}
              </p>
              <blockquote>
                “{s.quote}”
                <Refs ns={[s.ref]} />
              </blockquote>
              {s.gloss && <p className="ideal-note">{s.gloss}</p>}
            </li>
          ))}
        </ul>
        <p className="ideal-note">{stated.note}</p>
      </Section>

      <Section id="done-title" title="Completion criterion">
        <p className="ideal-criterion">{completion.lead}</p>
        <p className="ideal-state">
          <Mark state={at.complete ? 'met' : 'none'} /> {at.complete ? 'Reached.' : 'Not reached.'}
        </p>
        <h3 className="ideal-sub">{completion.basisTitle}</h3>
        <ul className="ideal-basis">
          {completion.basis.map((b) => (
            <li key={b.text}>
              {b.text}
              <Refs ns={b.refs} />
            </li>
          ))}
        </ul>
        <h3 className="ideal-sub">{completion.trackedTitle}</h3>
        <table className="ideal-table ideal-tracked">
          <tbody>
            {completion.tracked.map((t) => (
              <tr key={t.measure}>
                <th scope="row">{t.measure}</th>
                <td>
                  {t.value}
                  <Refs ns={t.refs} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <section className="bpage-section ideal-section ideal-milestones" aria-labelledby="ms-title">
        <h2 id="ms-title">Milestones</h2>
        <p>
          The stages a xenograft passes on the way to licensure, each defined by a body other than the
          Atlas. Every mark below is calculated from the results listed under its milestone.
        </p>
        <table className="ideal-grid">
          <thead>
            <tr>
              <th scope="col">Milestone</th>
              {page.organs.map((o) => (
                <th key={o} scope="col">
                  {o}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.milestones.map((m, n) => (
              <tr key={m.label}>
                <th scope="row">
                  <a href={m.final ? '#done-title' : `#m${n + 1}`}>
                    <span className="mono">{n + 1}</span> {m.label}
                    {m.final && ' (completion)'}
                  </a>
                </th>
                {at.cells[n].map((g, k) => (
                  <td key={k}>
                    <Mark state={g} />
                    <span className="visually-hidden">{WORD[g]}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="ideal-legend">
          <span>
            <Mark state="met" /> Met: a result satisfies the criterion.
          </span>
          <span>
            <Mark state="partial" /> Partial: a result bears on the criterion without satisfying it.
          </span>
          <span>
            <Mark state="none" /> None: no result.
          </span>
        </p>
        <ol className="ideal-ms">
          {page.milestones.map((m, n) => m.final ? null : (
            <li key={m.label} id={`m${n + 1}`}>
              <h3>
                <span className="ideal-ms-num mono">{n + 1}</span>
                {m.label}
              </h3>
              <dl className="ideal-fields">
                <div>
                  <dt>Criterion</dt>
                  <dd>{m.criterion}</dd>
                </div>
                <div>
                  <dt>Set by</dt>
                  <dd>
                    {m.setBy}
                    <Refs ns={m.setRefs} />
                  </dd>
                </div>
                {m.evidence.length > 0 ? (
                  <div>
                    <dt>Results</dt>
                    <dd>
                      <ul className="ideal-evidence">
                        {m.evidence.map((e) => (
                          <li key={e.head}>
                            <span className="ideal-verdict">
                              <Mark state={e.verdict} />
                              <span className="visually-hidden">{WORD[e.verdict]}: </span>
                            </span>
                            <span className="ideal-head">
                              {e.head}
                              <Refs ns={e.refs} />
                            </span>
                            {e.detail && <span className="ideal-detail">{e.detail}</span>}
                          </li>
                        ))}
                      </ul>
                    </dd>
                  </div>
                ) : (
                  <div>
                    <dt>Results</dt>
                    <dd className="ideal-none">None yet.</dd>
                  </div>
                )}
              </dl>
            </li>
          ))}
        </ol>
      </section>

      <Section id="refs-title" title="References">
        <ol className="ideal-refs">
          {page.references.map((r, n) => (
            <li key={n} id={`ref-${n + 1}`}>
              {r.text}{' '}
              {r.doi ? (
                <a href={'https://doi.org/' + r.doi} target="_blank" rel="noopener noreferrer">
                  doi:{r.doi}
                </a>
              ) : (
                <>
                  Available from:{' '}
                  <a href={r.url} target="_blank" rel="noopener noreferrer">
                    {r.url}
                  </a>
                </>
              )}
            </li>
          ))}
        </ol>
      </Section>

      <p className="ideal-about">{page.about}</p>
    </div>
  );
}

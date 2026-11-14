import { Fragment } from 'react';

// A breakthrough page rendered from data alone (pilot, /draft/<ID>). The data is the record's
// `page` key (atlas/core/<FIELD>/<ID>.json), served in /data/b/<ID>.json, in the shape of
// SCHEMA in atlas/page.py, written by a model and checked by code. Nothing on the page is typed
// here except labels, and nothing about progress is stored: it is calculated from `results` by
// progress() below.

const SET_BY = {
  regulator: 'Regulator',
  standards_body: 'Standards body',
  professional_society: 'Professional society',
  government_programme: 'Government programme',
  prize: 'Prize',
  protocol: 'Registered protocol',
  community_convention: 'Convention of the field',
  atlas: 'The Atlas (no outside definition found)',
};
const WORD = { met: 'Met', partial: 'Partial', none: 'None', claimed: 'Claimed, not confirmed' };
const RANK = { none: 0, partial: 1, met: 2 };
const best = (states) => states.reduce((a, b) => (RANK[b] > RANK[a] ? b : a), 'none');

// The active milestones in display order. Retired milestones keep their ids and results in the
// file but are not shown in the grid or counted.
export function activeMilestones(page) {
  const byId = Object.fromEntries(page.milestones.map((m) => [m.id, m]));
  return (page.milestone_order || page.milestones.map((m) => m.id)).map((id) => byId[id]).filter(Boolean);
}

// Progress, calculated.
//   unit                = each active milestone, and the completion test
//   counted results     = confirmed results only; an unconfirmed claim is listed and moves no mark
//   cell(unit, case)    = met if any counted result on it is met, else partial if any, else none
//   state(unit)         = the best cell across cases (one implicit case when there are none)
//   percent             = 50 × (milestones met / milestones); 100 when completion is met
//   percent for a case  = the same, using that case's cells
export function progress(page) {
  const cases = page.cases.length ? page.cases : [null];
  const units = [...activeMilestones(page).map((m) => m.id), 'completion'];
  const cells = units.map((unit) =>
    cases.map((c) =>
      best(
        page.results
          .filter((r) => r.confirmed === true && r.milestone === unit && r.case === c)
          .map((r) => r.verdict),
      ),
    ),
  );
  // Completion carries half the weight; the milestones share the other half equally. Only
  // "met" counts: a partial result shows in the grid and adds nothing to the percentage.
  const score = (states) => {
    if (states[states.length - 1] === 'met') return 100;
    const steps = states.slice(0, -1);
    return Math.round((50 * steps.filter((s) => s === 'met').length) / steps.length);
  };
  const states = cells.map(best);
  return {
    cases,
    units,
    cells,
    states,
    percent: score(states),
    perCase: cases.map((_, k) => score(cells.map((row) => row[k]))),
    met: states.filter((s) => s === 'met').length,
    partial: states.filter((s) => s === 'partial').length,
    none: states.filter((s) => s === 'none').length,
    complete: states[states.length - 1] === 'met',
    next: page.milestone_structure === 'sequence' ? states.findIndex((s) => s !== 'met') : -1,
  };
}

function Mark({ state }) {
  return (
    <svg className={'ideal-mark ' + state} viewBox="-8 -8 16 16" width="13" height="13" aria-hidden="true">
      <circle r="6" />
      {state === 'met' && <circle r="6" className="fill" />}
      {state === 'partial' && <path d="M0 -6A6 6 0 0 0 0 6Z" className="fill" />}
      {state === 'claimed' && <circle r="2.2" className="dot" />}
    </svg>
  );
}

function Ring({ percent }) {
  const r = 26;
  const length = 2 * Math.PI * r;
  return (
    <svg className="page-ring" viewBox="-32 -32 64 64" width="76" height="76" role="img" aria-label={`${percent}% complete`}>
      <circle r={r} className="page-ring-track" />
      <circle
        r={r}
        className="page-ring-fill"
        strokeDasharray={`${(length * percent) / 100} ${length}`}
        transform="rotate(-90)"
      />
      <text textAnchor="middle" dy="0.35em">
        {percent}%
      </text>
    </svg>
  );
}

function Refs({ ns }) {
  const list = [...new Set(ns || [])];
  if (!list.length) return null;
  return (
    <sup className="ideal-ref">
      {list.map((n, k) => (
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

function Section({ id, title, children, className = '' }) {
  return (
    <section className={'bpage-section ideal-section ' + className} aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

const stop = (text) => (text ? text.replace(/[.\s]+$/, '') + '.' : '');

// Vancouver (NLM) style, from the reference's fields.
function Reference({ r, accessed }) {
  const journal = r.kind === 'journal' || r.kind === 'preprint';
  const issue = r.volume ? `;${r.volume}${r.issue ? `(${r.issue})` : ''}${r.pages ? `:${r.pages}` : ''}` : '';
  return (
    <li id={`ref-${r.id}`}>
      {stop(r.authors)} {stop(r.title + (journal ? '' : ' [Internet]'))}{' '}
      {journal
        ? stop(`${r.container || ''}. ${r.year}${issue}`.replace(/^\. /, ''))
        : stop(`${r.container ? r.container + '; ' : ''}${r.year} [cited ${accessed}]`)}{' '}
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
  );
}

function Results({ items }) {
  if (!items.length) return <span className="ideal-none">None yet.</span>;
  return (
    <ul className="ideal-evidence">
      {items.map((e, k) => (
        <li key={k} className={e.confirmed === true ? '' : 'page-claimed'}>
          <span className="ideal-verdict">
            <Mark state={e.confirmed === true ? e.verdict : 'claimed'} />
            <span className="visually-hidden">{e.confirmed === true ? WORD[e.verdict] : WORD.claimed}: </span>
          </span>
          <span className="ideal-head">
            {e.case && <span className="page-case">{e.case}. </span>}
            {e.finding}
            <Refs ns={[e.ref]} />
          </span>
          {e.confirmed !== true && (
            <span className="ideal-detail page-flag">
              Claimed, not confirmed{e.verdict === 'partial' ? ' (partial)' : ''}.
            </span>
          )}
          {e.detail && <span className="ideal-detail">{e.detail}</span>}
          {e.quote && e.checked !== false && <span className="ideal-detail page-quote">“{e.quote}”</span>}
          {e.quote && e.checked === false && <span className="ideal-detail page-flag">Quotation not confirmed.</span>}
          {!e.peer_reviewed && <span className="ideal-detail page-flag">Not peer reviewed.</span>}
        </li>
      ))}
    </ul>
  );
}

// The passage that states a threshold, from the setting body's own document. A threshold is
// unconfirmed when its quotation is missing (unless the Atlas set it) or was not found.
function Threshold({ unit }) {
  const quote = unit.threshold_quote;
  const unconfirmed = (!quote && unit.set_by_kind !== 'atlas') || unit.threshold_checked === false;
  return (
    <>
      {quote && unit.threshold_checked !== false && (
        <span className="ideal-detail page-quote">
          “{quote}”
          <Refs ns={[unit.threshold_ref]} />
        </span>
      )}
      {unconfirmed && <span className="ideal-detail page-flag">Threshold not confirmed from its source.</span>}
    </>
  );
}

// A measure: its name, then the value alone at body size and the conditions beneath it. A value
// longer than a headline (an entry written before value and note were separated) is shown as
// the note, full width, with no headline value.
const HEADLINE = 40;

function Measure({ item }) {
  const headline = item.value && item.value.length <= HEADLINE ? item.value : null;
  const note = [headline ? null : item.value, item.note].filter(Boolean).join(' ');
  return (
    <li className={headline ? '' : 'page-measure-long'}>
      <span className="page-measure-name">{item.measure}</span>
      <span className="page-measure-body">
        {headline && (
          <span className="page-measure-value">
            {headline}
            <Refs ns={[item.ref]} />
          </span>
        )}
        {note && (
          <span className="page-measure-note">
            {note}
            {!headline && <Refs ns={[item.ref]} />}
          </span>
        )}
      </span>
    </li>
  );
}

function Unit({ number, id, title, criterion, setBy, kind, refs, results, basis, unit }) {
  return (
    <li id={id}>
      <h3>
        {number && <span className="ideal-ms-num mono">{number}</span>}
        <span>{title}</span>
      </h3>
      <dl className="ideal-fields">
        <div>
          <dt>Criterion</dt>
          <dd>{criterion}</dd>
        </div>
        <div>
          <dt>Set by</dt>
          <dd>
            {setBy}
            <Refs ns={refs} />
            <span className="ideal-detail">{SET_BY[kind]}</span>
            <Threshold unit={unit} />
          </dd>
        </div>
        {basis && (
          <div>
            <dt>Basis</dt>
            <dd>{basis}</dd>
          </div>
        )}
        <div>
          <dt>Results</dt>
          <dd>
            <Results items={results} />
          </dd>
        </div>
      </dl>
    </li>
  );
}

export default function PageBody({ page }) {
  const at = progress(page);
  const { goal, completion } = page;
  const sequence = page.milestone_structure === 'sequence';
  const hasCases = page.cases.length > 0;
  const milestones = activeMilestones(page);
  const retired = page.milestones.filter((m) => m.status === 'retired');
  const titles = [...milestones.map((m) => m.title), completion.title];
  const anchor = (n) => (n === milestones.length ? '#done' : `#${milestones[n].id}`);
  const on = (unit) => page.results.filter((r) => r.milestone === unit);
  return (
    <div className="ideal">
      <section className="ideal-definition" aria-label="Definition">
        <p>{page.definition.replace(/\s*\[\d+(,\s*\d+)*\]/g, '')}</p>
      </section>

      <section className="ideal-status-line page-status" aria-label="Progress">
        <Ring percent={at.percent} />
        <div>
          <p className="ideal-status-main">
            {at.complete ? 'Complete.' : `${at.met} of ${at.units.length} met, ${at.partial} partial, ${at.none} with no result.`}
          </p>
          <p className="ideal-status-sub">
            {hasCases && (
              <>
                By {page.case_label.toLowerCase()}: {page.cases.map((c, k) => `${c} ${at.perCase[k]}%`).join(' · ')}.{' '}
              </>
            )}
            {at.next >= 0 && !at.complete && (
              <>
                First not met: <a href={anchor(at.next)}>{titles[at.next]}</a>{' '}
              </>
            )}
          </p>
          <p className="ideal-status-sub">
            Calculated from the results below. Completion counts for 50%; the {milestones.length}{' '}
            milestones share the other 50% equally. A partial result adds nothing, and only confirmed
            results count.
          </p>
        </div>
      </section>

      <Section id="why-title" title="Why it is a goal">
        <p>
          {goal.need}
          <Refs ns={goal.need_refs} />
        </p>
        {goal.figures && (
          <>
            <table className="ideal-table">
              <caption>
                {goal.figures.caption}
                <Refs ns={[goal.figures.ref]} />
              </caption>
              <thead>
                <tr>
                  {goal.figures.columns.map((h) => (
                    <th key={h} scope="col">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {goal.figures.rows.map((row, n) => (
                  <tr key={n}>
                    {row.map((cell, k) => (k === 0 ? <th key={k} scope="row">{cell}</th> : <td key={k}>{cell}</td>))}
                  </tr>
                ))}
              </tbody>
            </table>
            {goal.figures.note && <p className="ideal-note">{goal.figures.note}</p>}
          </>
        )}
        <h3 className="ideal-sub">Who has stated it as a goal</h3>
        <ul className="ideal-stated">
          {goal.statements.map((s, n) => (
            <li key={n}>
              <p className="ideal-who">
                {s.body}, {s.year}
              </p>
              {s.checked === false ? (
                <p className="ideal-note page-flag">
                  Quotation not confirmed.
                  <Refs ns={[s.ref]} />
                </p>
              ) : (
                <blockquote>
                  “{s.quote}”
                  <Refs ns={[s.ref]} />
                </blockquote>
              )}
              {s.context && <p className="ideal-note">{s.context}</p>}
            </li>
          ))}
        </ul>
      </Section>

      <Section id="done-title" title="Completion test">
        <ol className="ideal-ms page-done">
          <Unit
            id="done"
            title={completion.title}
            criterion={completion.criterion}
            setBy={completion.set_by}
            kind={completion.set_by_kind}
            refs={completion.refs}
            basis={completion.basis}
            unit={completion}
            results={on('completion')}
          />
        </ol>
        {page.measures.length > 0 && (
          <>
            <h3 className="ideal-sub">Measured alongside, with no threshold attached</h3>
            <ul className="page-measures">
              {page.measures.map((t, n) => (
                <Measure key={n} item={t} />
              ))}
            </ul>
          </>
        )}
      </Section>

      <section className="bpage-section ideal-section ideal-milestones" aria-labelledby="ms-title">
        <h2 id="ms-title">Milestones</h2>
        <p>
          {sequence
            ? 'Results that normally come in this order on the way to completion.'
            : 'Separate parts of the problem. They can be reached in any order.'}{' '}
          Every mark is calculated from the results listed under its milestone.
        </p>
        <table className="ideal-grid">
          <thead>
            <tr>
              <th scope="col">Milestone</th>
              {hasCases ? page.cases.map((c) => <th key={c} scope="col">{c}</th>) : <th scope="col">State</th>}
            </tr>
          </thead>
          <tbody>
            {titles.map((title, n) => {
              const last = n === titles.length - 1;
              return (
                <tr key={n} className={last ? 'page-grid-done' : ''}>
                  <th scope="row">
                    <a href={anchor(n)}>
                      {sequence && !last && <span className="mono">{n + 1}</span>}
                      {last && <span className="mono">Completion</span>}
                      {title}
                    </a>
                  </th>
                  {at.cells[n].map((g, k) => (
                    <td key={k}>
                      <Mark state={g} />
                      <span className="visually-hidden">{WORD[g]}</span>
                    </td>
                  ))}
                </tr>
              );
            })}
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
            <Mark state="none" /> None: no confirmed result.
          </span>
          <span>
            <Mark state="claimed" /> Claimed, not confirmed: listed under its milestone; changes no mark.
          </span>
        </p>
        <ol className="ideal-ms">
          {milestones.map((m, n) => (
            <Unit
              key={m.id}
              id={m.id}
              number={sequence ? n + 1 : null}
              title={m.title}
              criterion={m.criterion}
              setBy={m.set_by}
              kind={m.set_by_kind}
              refs={m.refs}
              unit={m}
              results={on(m.id)}
            />
          ))}
        </ol>
        {retired.length > 0 && (
          <p className="ideal-note page-retired">
            Retired:{' '}
            {retired.map((m, k) => (
              <Fragment key={m.id}>
                {k > 0 && '; '}
                {m.title}
                {m.replaced_by.length > 0 &&
                  ` (replaced by ${m.replaced_by
                    .map((id) => page.milestones.find((x) => x.id === id)?.title || id)
                    .join('; ')})`}
              </Fragment>
            ))}
            .
          </p>
        )}
      </section>

      {page.not_found.length > 0 && (
        <Section id="gaps-title" title="Searched for and not found">
          <p className="ideal-note">
            A mark of “none” above may reflect a gap in this entry and not in the field.
          </p>
          <ul className="ideal-basis">
            {page.not_found.map((text, n) => (
              <li key={n}>{text}</li>
            ))}
          </ul>
        </Section>
      )}

      <Section id="refs-title" title="References">
        <ol className="ideal-refs">
          {page.references.map((r) => (
            <Reference key={r.id} r={r} accessed={page.accessed} />
          ))}
        </ol>
      </Section>

      <Section id="log-title" title="Entry log">
        <p className="ideal-note">Version {page.version || 1}.</p>
        <table className="ideal-table page-log">
          <tbody>
            {page.log.map((entry, n) => (
              <tr key={n}>
                <th scope="row" className="mono">
                  {entry.date}
                </th>
                <td className="mono">{entry.actor}</td>
                <td>{entry.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}

"""The breakthrough page as data (pilot): a base version, improved over time, never regenerated.

python3 -m atlas.page define ID [ID ...] [--replace] [--out DIR] [--model M] [--effort E]
    The base: one Codex Sol call with web search writes everything except results, given the
    record file and every source the atlas already holds. It refuses an entry that already has
    a definition unless --replace is given.
python3 -m atlas.page results ID [ID ...] [--all] [--model M] [--effort E]
    Incremental. Sources the entry already uses are judged, from saved copies, against the
    milestones they have not been judged against in their current wording (`judged` records
    each source, milestone and criterion hash); then one search call looks for the gaps and
    each new candidate is judged against its one milestone. Re-judging a pair replaces that
    pair's rows only. --all re-judges everything.
python3 -m atlas.page add ID URL [URL ...]
    Saves each URL (if not held) and judges it against every active milestone. No search.
python3 -m atlas.page revise ID [--note TEXT] [--model M] [--effort E]
    One Sol call with search proposes operations (add, edit, retire, split, merge or reorder
    milestones; edit completion, statements, text, cases, gaps), stored under
    atlas/data/page/<ID>-revise-<stamp>/proposal.json and printed; nothing is applied.
python3 -m atlas.page revise ID --apply [PATH]
    Applies the latest (or the named) proposal: each operation validated on its own, one log
    row each, version + 1. Milestone ids are permanent; retired milestones keep their results.
python3 -m atlas.page check [ID ...]
    Validates stored entries, including hand edits (a supported way to change an entry).
python3 -m atlas.page migrate ID [ID ...]
    One-off: brings round-2 entries to this shape without a model call.

Code fills citations from registries (Crossref, PubMed, arXiv), merges references with the same
DOI, checks every quotation against a saved copy with ingestion.pipeline.passage_matches, and
writes the log. A quotation that is not found, or a field over its length, is noted and kept.
Nothing about progress is written: the site calculates it from `results`.

Pages are written to atlas/web/src/pages/drafts/<ID>.json and shown at /draft/<ID>. The record
files in atlas/core are not changed.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ingestion.pipeline import passage_matches
from ingestion.providers import Models, ProviderTimeout
from ingestion.sources import EFETCH, UA, Archive, pubmed_id, request_url

from . import batch as batches, brief as briefs, core as records, store
from .batch import ARCHIVE_LOCK
from .copies import ADDED, Copy, choose, known_copies, normal
from .core import CORE
from .store import CONFIG, DB, ROOT, connect

# Pilot pages before they moved into the records; read once by `migrate`.
DRAFTS = ROOT / 'atlas/web/src/pages/drafts'
CALLS = ROOT / 'atlas/data/page'
ENTRY = {'provider': 'codex', 'model': 'gpt-6.1-sol', 'effort': 'high', 'search': True}
CANDIDATES = 24
# Characters of a source the judge reads. Regulator labels and WHO position papers put the
# deciding section (clinical studies, recommendations) past 60,000 characters, where an earlier
# limit cut it off (HLT-01, HLT-09, 16 November 2026).
JUDGE_TEXT = 150000
JUDGES = 4
DEFINITION = [
    'title',
    'definition',
    'goal',
    'completion',
    'case_label',
    'cases',
    'milestone_structure',
    'milestones',
    'measures',
    'not_found',
]

SET_BY = [
    'regulator',
    'standards_body',
    'professional_society',
    'government_programme',
    'prize',
    'protocol',
    'community_convention',
    'atlas',
]
KINDS = ['journal', 'preprint', 'book', 'report', 'web', 'registry', 'filing', 'press_release']
LIMITS = {
    'title': 70,
    'definition': 420,
    'need': 600,
    'criterion': 700,
    'basis': 600,
    'milestone_title': 110,
    'finding': 200,
    'detail': 420,
    'quote': 320,
    'measure_value': 40,
    'measure_note': 200,
}


def obj(properties):
    return {
        'type': 'object',
        'properties': properties,
        'required': list(properties),
        'additionalProperties': False,
    }


def array(items):
    return {'type': 'array', 'items': items}


TEXT = {'type': 'string'}
MAYBE = {'type': ['string', 'null']}
REF = {'type': 'integer'}
MAYBE_REF = {'type': ['integer', 'null']}
REFS = array(REF)
KIND = {'type': 'string', 'enum': KINDS}
FLAG = {'type': 'boolean'}
# The answers to NEED_GUIDE's ten questions that goal.need is written from. Kept with the call,
# not in the page.
NEED_QUESTIONS = {
    'held_back': 'Who or what is held back without this breakthrough: which people, industry or '
    'science? Name them; not the researchers working on it.',
    'how_much': 'How big is that, in numbers: people, deaths, cost, energy, or share of a '
    "field's work?",
    'relied_on_now': 'What do they rely on instead today, and where exactly does it fall short?',
    'what_changes': 'What would be different for them if it existed: cheaper, safer, faster, or '
    'available to whom? A benefit to people, not a property of the device.',
    'newly_possible': 'What would become possible that is not possible now? For an open '
    'question, what would each possible answer mean?',
    'depends_on_it': 'Which fields, technologies or other breakthroughs depend on it?',
    'uses': 'If it has several uses, which do the people working on it pursue it for? Name '
    'each, the main one first.',
    'conditions': 'What has to be true for the benefit to happen?',
    'not_do': 'What would it not do that a reader might assume?',
    'why_this': 'Why can the present approach not simply be improved instead? What does only '
    'this breakthrough provide?',
}
ANSWER = {
    'type': 'object',
    'properties': {
        'answer': {
            'type': ['string', 'null'],
            'description': 'One sentence that answers the question asked, or null when no '
            'source answers it.',
        },
        'ref': {
            'type': ['integer', 'null'],
            'description': 'The reference the answer rests on, or null.',
        },
        'quote': {
            'type': ['string', 'null'],
            'description': 'A passage of at most 300 characters copied exactly from that '
            'reference that supports the answer, or null.',
        },
    },
    'required': ['answer', 'ref', 'quote'],
    'additionalProperties': False,
}
# The answers goal.need is written from, one named property per question, each described by its
# question. Kept with the call, not in the page.
NEED_ANSWERS = {
    'type': 'object',
    'description': 'Answer every question before writing goal.need; goal.need is written from '
    'these answers alone.',
    'properties': {key: {**ANSWER, 'description': q} for key, q in NEED_QUESTIONS.items()},
    'required': list(NEED_QUESTIONS),
    'additionalProperties': False,
}

SCHEMA = obj(
    {
        'need_answers': NEED_ANSWERS,
        'title': TEXT,
        'definition': TEXT,
        'goal': obj(
            {
                'need': {
                    'type': 'string',
                    'description': 'Why it is a goal: one coherent paragraph written from '
                    'need_answers, not a summary of sources and not a list of answers.',
                },
                'need_refs': REFS,
                'figures': {
                    'anyOf': [
                        {'type': 'null'},
                        obj(
                            {
                                'caption': TEXT,
                                'columns': array(TEXT),
                                'rows': array(array(TEXT)),
                                'note': MAYBE,
                                'ref': REF,
                            }
                        ),
                    ]
                },
                'statements': array(
                    obj({'body': TEXT, 'year': TEXT, 'quote': TEXT, 'context': MAYBE, 'ref': REF})
                ),
            }
        ),
        'completion': obj(
            {
                'title': TEXT,
                'criterion': TEXT,
                'set_by': TEXT,
                'set_by_kind': {'type': 'string', 'enum': SET_BY},
                'threshold_quote': MAYBE,
                'threshold_ref': MAYBE_REF,
                'basis': TEXT,
                'refs': REFS,
            }
        ),
        'case_label': MAYBE,
        'cases': array(TEXT),
        'milestone_structure': {'type': 'string', 'enum': ['sequence', 'parallel']},
        'milestones': array(
            obj(
                {
                    'id': TEXT,
                    'title': TEXT,
                    'criterion': TEXT,
                    'set_by': TEXT,
                    'set_by_kind': {'type': 'string', 'enum': SET_BY},
                    'threshold_quote': MAYBE,
                    'threshold_ref': MAYBE_REF,
                    'refs': REFS,
                }
            )
        ),
        'measures': array(obj({'measure': TEXT, 'value': TEXT, 'note': MAYBE, 'ref': REF})),
        'not_found': array(TEXT),
        'references': array(
            obj(
                {
                    'id': REF,
                    'kind': KIND,
                    'url': TEXT,
                    'doi': MAYBE,
                    'title': TEXT,
                    'authors': TEXT,
                    'container': MAYBE,
                    'year': TEXT,
                }
            )
        ),
    }
)

FIND_SCHEMA = obj(
    {
        'candidates': array(
            obj({'url': TEXT, 'title': TEXT, 'milestone': TEXT, 'case': MAYBE, 'why': TEXT})
        )
    }
)

# What the judge says about the document itself, for its reference and its results.
SOURCE = {'kind': KIND, 'doi': MAYBE}
FINDING = {
    'finding': TEXT,
    'detail': MAYBE,
    'quote': MAYBE,
    'confirmed': FLAG,
    'peer_reviewed': FLAG,
}
JUDGE_SCHEMA = obj(
    {
        'verdict': {'type': 'string', 'enum': ['met', 'partial', 'not_relevant']},
        **FINDING,
        **SOURCE,
    }
)
HELD_SCHEMA = obj(
    {
        **SOURCE,
        'rows': array(
            obj(
                {
                    'milestone': TEXT,
                    'case': MAYBE,
                    'verdict': {'type': 'string', 'enum': ['met', 'partial']},
                    **FINDING,
                }
            )
        ),
    }
)

NEED_GUIDE = """\
need, shown under the heading "Why it is a goal", tells a reader why the world would be better
with this breakthrough. It is not a summary of the sources. First fill need_answers: each of
its properties is a question, and each answer is one sentence that answers that question, with
the reference it rests on and a passage copied exactly from that reference; null when no source
answers it.
Then write need from those answers alone, as one coherent, well-written paragraph, not a list
of answers: the problem and its size, what would change, the conditions and limits. Use the
answers that matter most for this breakthrough; a reader should finish knowing what is at stake
and why this particular breakthrough, rather than a general improvement, is needed. Write from
the reader's side: what is at stake and for whom.
Never "researchers pursue", "X proposes" or "X cautions", and no names of authors or
institutions. Leave out what other parts carry: what it is (definition), how it will be judged
achieved (completion), who has named it a goal (statements), prize amounts and the history of
attempts. Plain declarative sentences, at most 600 characters; need_refs lists the references
behind it.

An example of the kind, for an imaginary entry on printing books from movable metal type, as
it would read before the printing press (its figures are illustrative; a real entry takes every
figure from a cited source):
  Books are copied by hand. One Bible takes a scribe more than a year, so a book costs as much
  as a farm and few people outside monasteries and universities own one. Every copy adds
  errors, so no two readers can be sure they hold the same text. Printing from reusable metal
  type would produce hundreds of identical copies in the time a scribe makes one, lowering the
  price of books and giving readers in many cities the same words on the same pages. That
  depends on cheap paper and on people who can read; printing alone teaches no one to read.
"""

PROMPT = """\
You are writing one entry of the Technology Atlas, a public reference that maps breakthroughs
worth working towards. For each breakthrough an entry states what it is, who has set it as a
goal, the test by which it will count as achieved, the milestones on the way, and the published
results that bear on each. Its readers hold doctorates and check details. Some are experts in
this entry's field and the rest are experts in another field. Every statement must be exact and
sourced.

You are given the Atlas's existing draft of this entry: a working title, a description, and the
sources it already cites. Use the draft to understand the topic. Do not treat it as authority:
its milestones were invented by a model, and you are replacing them.

The sources listed after the draft have already been read and checked by the Atlas: their saved
text was read, and the quotations shown with them were found in it. Use them first, and search
only for what they do not cover, chiefly who has set this as a goal and the thresholds that
outside bodies have published.

Use web search throughout. Open every page you cite, and cite only pages you opened in this
session. Prefer primary documents: papers, society and academy reports, agency and regulator
pages, standards, prize rules, trial registries, company filings. A press release may be cited
for a result that has no paper yet; mark such a result as not peer reviewed.

The principle that governs the whole entry: thresholds are set by someone other than the Atlas.
The completion test and every milestone must be a test that an outside body has published or
that the field demonstrably uses, such as a regulator's licence, a standards body's definition,
a society's or committee's published criterion, a government programme's stated target, a
prize's rules, the endpoint of a registered protocol, or a convention the field applies (a
5-sigma observation, a proof accepted after peer review, independent replication). Your work is
to find those tests and report them with their source. Do not invent thresholds.

Write these parts.

title
  The capability, named in the field's own terms, as a noun phrase of at most 70 characters.
  No qualifier that lacks a definition, such as "dependable", "practical" or "scalable".

definition
  One or two sentences, at most 420 characters, stating what would exist or be true. Define in
  passing any term that an expert in another field would not know.

goal
  need and need_refs: see "Why it is a goal" below.
  figures: a small table (at most 4 columns and 5 rows) when two or three numbers make the need
    plain, with a caption, an optional note on how to read it, and its reference. Otherwise null.
  statements: 2 to 5 statements by bodies with standing in the field (an academy, a professional
    society, a government agency or programme, a standards body, a decadal survey or roadmap
    committee, a prize committee, or a leading developer) that set this as a goal. For each:
    the body, the year, one passage quoted exactly, its reference, and context only when the
    quotation cannot be understood without it.

{need_guide}
completion
  The single test by which the breakthrough counts as achieved.
  title: the test as a sentence that can be read alone, at most 110 characters.
  criterion: the test in full, with its numbers, at most 700 characters.
  set_by: the body that set it, and where. set_by_kind: one of the listed kinds.
  threshold_quote: one passage, copied exactly from the setting body's own document, that
    states the threshold or test. null only when set_by_kind is "atlas", or when the body's
    document states it only in a table or figure; then say so in set_by.
  threshold_ref: the reference of that document; null when threshold_quote is null.
  basis: why this is the right test, in at most 600 characters, quoting the source where you can.
  The test must not be one that published results already satisfy, unless the breakthrough has
  in fact been achieved. If, after searching, you find that no outside body has defined such a
  test, set set_by_kind to "atlas", state in basis exactly what you searched for and did not
  find, and give the narrowest test consistent with the statements you quoted.

cases
  If the field pursues this separately in distinct sub-cases that a reader would want tracked
  apart (organ types, material classes, hardware platforms, problem classes), list 2 to 5 of
  them and give case_label, the singular noun for one of them, such as "Organ". Name each case
  in at most 4 words, such as "Kidney" or "Magnetic confinement". Otherwise cases is empty and
  case_label is null.

milestones
  3 to 6 results that mark progress before completion. Together they should span the distance
  from the first demonstration in the laboratory to the step just before completion, so that a
  reader can see where the field stands: include the stages the field or its regulator already
  recognises (for a medical product, for example, the preclinical bar, first use in people, a
  cleared trial, a trial reporting its endpoints). Do not include the completion test itself.
  The last milestone must be the result just before completion, so that the milestones do not
  stop far short of the goal.
  Each must be set by an outside body in the sense above, with set_by, set_by_kind and refs;
  use "atlas" only as completion does, and say so in set_by. A milestone is a result in the
  world, never a rule about how results should be reported.
  When there are cases, every milestone applies to every case: state it for the general
  subject ("a pig organ", not "a pig heart"), and record each case's progress through results.
  If the published threshold was written for one case, say so in set_by.
  id: m1, m2, and so on.
  title: one sentence, at most 110 characters, that states what has to be achieved, including
    its object and its threshold, so that it can be read alone. Not "Preclinical survival
    threshold in non-human primates" but "Pig organs keep about 60% of non-human primates
    alive for 3 months".
  criterion: the exact test, with numbers and conditions, at most 700 characters.
  threshold_quote and threshold_ref: as for completion.
  milestone_structure: "sequence" if each milestone normally follows the one before, "parallel"
    if they are separate parts of the problem that can be reached in any order.

measures
  Always an empty list.

not_found
  What you searched for and could not find or could not open, one short sentence each, so that a
  reader can tell a gap in this entry from a gap in the science. Empty if nothing.

references
  Every source cited, numbered from 1 in order of first citation; every reference must be cited
  and every citation must have a reference. For each: id, kind, url (the page you opened), doi
  where it exists (otherwise null), and title as printed. The Atlas fills authors, journal,
  volume, issue and pages from Crossref, PubMed and arXiv. Give authors (in Vancouver form, or
  the organisation's name), container (the journal's abbreviated title, or the publisher or
  site) and year as well; they are used only when no registry holds the document.

Rules for all text
- Quotations are exact, character for character, at most 320 characters, with nothing omitted
  inside them.
- No citation marks such as [1] inside any text field; references attach through the ref
  fields.
- Give sample sizes, units and dates. Write dates in full. Name the thing: "a trial of a pig
  kidney", not "a trial".
- No praise, no forecasts, no dates by which anything will happen, and nothing about how this
  entry was produced.
- Plain declarative sentences. Say each thing once.

Draft entry {id}: {title}

{record}

Sources the Atlas has already read and checked:
{sources}
"""

FIND_PROMPT = """\
You are finding published results for one entry of the Technology Atlas, a public reference
that maps breakthroughs worth working towards. The entry's definition, its completion test and
its milestones are below; the Atlas has set them and they are not to be changed. Its readers
hold doctorates and check details.

Search the web for the strongest published result on every milestone and on the completion
test, in every case. The Atlas already holds the sources listed at the end and has judged them;
the cells that already have a confirmed result meeting the criterion are listed. Look only for
the gaps: the other cells, and stronger results than the ones held. Do not return a source the
Atlas already holds.

Prefer primary documents that report the result: papers, trial registry records, regulator
decisions, company filings. A preprint or press release may be returned for a result that has
no paper yet. Prefer a page whose full text is readable without logging in (PubMed Central, an
open-access publisher page, arXiv) to a pubmed.ncbi.nlm.nih.gov abstract page.

Open every page before you return it, and return it only if it reports the result you
describe. Return at most {limit} candidates. Fewer good candidates are better than more weak
ones; an empty list is a valid answer.

For each candidate:
- url: the page you opened.
- title: the document's title as printed.
- milestone: the milestone's id (m1, m2, ...) or "completion".
- case: one of the cases exactly as written, or null when the entry has no cases.
- why: one sentence giving the result and the number that bears on the criterion.

Entry {id}: {title}

{entry}

Cells that already have a confirmed result meeting the criterion:
{done}

Sources the Atlas already holds:
{held}
"""

JUDGE_RULES = """\
Rules
- Judge only from the text given, not from what you know from elsewhere.
- verdict "met" only if the finding satisfies the criterion as written; "partial" if it bears
  on the criterion without satisfying it. Never "partial" on the completion test: a result on
  completion is "met", or it is not relevant.
- finding: one line of at most 200 characters giving the subject, the sample size and the one
  number that bears on the criterion.
- detail: at most 420 characters on conditions, failure mode, or why the verdict is partial.
  null if nothing needs adding.
- quote: one passage copied exactly, character for character, from the text given, that states
  the finding; at most 320 characters, with nothing omitted inside it. null if the text gives
  the finding only in a table or figure.
- confirmed: true when the finding is established by a peer-reviewed paper, by independent
  replication, by an official record of fact (a regulator's decision, a trial registry, a
  company's statutory filing reporting a regulator's action), or, for a mathematical result, by
  a proof checked in a proof assistant (Lean, Coq, Isabelle or similar) whose formal statement
  is the result claimed; false when it is a claim by its own authors not yet reviewed (a
  preprint, a press release, a blog) and not machine-checked. When a mathematical criterion
  requires a prize body's ruling or the community's acceptance that has not been recorded, and
  the text reports a complete proof of the result checked in a proof assistant, the verdict is
  met with confirmed false: the proof is in hand, the ruling is still to come. The same holds
  when the authors report a complete proof with a proof-assistant formalization but say that a
  certificate or a computation it relies on is still to be released or is checked outside the
  proof assistant: the verdict is met with confirmed false, and the detail says what is pending.
- peer_reviewed: true for a paper in a peer-reviewed journal; false for a preprint, registry
  record, filing or release.
- kind: what the document is: journal, preprint, book, report, web, registry, filing or
  press_release.
- doi: the document's own DOI when the text states it, otherwise null.
"""

JUDGE_PROMPT = (
    """\
You are judging whether one source reports a result on one milestone of an entry in the
Technology Atlas, a public reference that maps breakthroughs worth working towards.

Entry: {title}
{definition}

{unit}: {unit_title}
Criterion: {criterion}
Case: {case}

Return verdict "not_relevant" if the source reports no result on this milestone{for_case}; a
source that only mentions, motivates or reviews the topic is not relevant. Then the other fields
may be empty or null.

"""
    + JUDGE_RULES
    + """
Source: {source_title} ({url})
<<<
{text}
>>>
"""
)

HELD_PROMPT = (
    """\
You are judging which milestones of an entry in the Technology Atlas one source reports a
result on. The Atlas is a public reference that maps breakthroughs worth working towards.

Entry: {title}
{definition}

{units}
{cases}
Return one row for every milestone (its id, or "completion") and case on which the source
reports a result, and no row for one it only mentions, motivates or reviews. Most sources bear
on one or two milestones; zero rows is a valid answer. case is one of the cases exactly as
written, or null when the entry has no cases.

"""
    + JUDGE_RULES
    + """
Source: {source_title} ({url})
<<<
{text}
>>>
"""
)


def today():
    return f'{datetime.now(timezone.utc):%Y-%m-%d}'


def config():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def writer_entry(model=None, effort=None):
    """The writer entry (define, the results search, revise), with --model / --effort applied."""
    entry = dict(ENTRY)
    if model:
        entry['model'] = model
        # A model named provider/name (deepseek/..., anthropic/...) runs through OpenRouter;
        # opus, sonnet or claude-... through the signed-in Claude Code CLI.
        if '/' in model:
            entry['provider'] = 'openrouter'
        elif model in ('opus', 'sonnet') or model.startswith('claude-'):
            entry['provider'] = 'claude'
    if effort:
        entry['effort'] = effort
    return entry


JUDGE = {}  # --judge MODEL: replaces the config's judge for this run


def judge_entry(settings, writer=ENTRY['model']):
    """The `format` entry of the atlas config, without search; another format model of the
    config when the `format` model is the one that wrote the definition. --judge overrides."""
    if JUDGE.get('model'):
        entry = writer_entry(JUDGE['model'])
        entry.pop('search', None)
        entry.pop('effort', None)
        return entry
    entry = {'provider': 'codex', **settings['format']}
    if entry['model'] == writer:
        others = [e for e in settings.get('stages', {}).get('format', []) if e['model'] != writer]
        if others:
            entry = dict(others[0])
    entry.pop('search', None)
    return entry


# The atlas's own research for a breakthrough.

_core = {}
_core_lock = threading.Lock()


def load_core():
    with _core_lock:
        if 'data' not in _core:
            _core['data'] = records.load(CORE)
        return _core['data']


def held_sources(identifier):
    """(record, sources): the record file and every source attached to the breakthrough, each
    {url, title, text (saved text, '' when none is readable), quotes (its progress rows)},
    read the way atlas.brief reads them, from copies already saved."""
    data = load_core()
    with closing(connect(DB)) as db:
        return data['breakthroughs'][identifier], briefs.gather(data, identifier, db)


def flat(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def describe(record):
    """The whole record as the define prompt shows it, with its reader's version."""
    parts = [briefs.describe(record)]
    brief = record.get('brief') or {}
    for key, label in [
        ('possible', "Reader's version, what would be possible"),
        ('why', "Reader's version, why it matters"),
        ('shown', "Reader's version, what has been shown"),
        ('missing', "Reader's version, what is missing"),
        ('uncertain', "Reader's version, what is uncertain"),
    ]:
        if brief.get(key):
            parts.append(label + ':\n' + '\n'.join(brief[key]))
    return '\n\n'.join(parts)


def show_held(record, held):
    briefed = {s['url']: s for s in (record.get('brief') or {}).get('sources', [])}
    lines = []
    for n, source in enumerate(held, 1):
        lines.append(f'{n}. {source["url"]}')
        if source['title']:
            lines.append(f'   Title: {flat(source["title"])}')
        said = briefed.get(source['url'])
        if said and said.get('showed'):
            lines.append(f'   Shown: {flat(said["showed"])}')
        if said and said.get('checked') and said.get('quote'):
            lines.append(f'   Checked quote: "{flat(said["quote"])}"')
        for row in source['quotes']:
            where = f'draft milestone {row["milestone"]}' if row['milestone'] else 'the whole'
            lines.append(f'   Judged passage ({row["verdict"]}, {where}): "{flat(row["quote"])}"')
        if not source['text']:
            lines.append('   (The Atlas holds no readable saved copy of this source.)')
    return '\n'.join(lines) or '(none)'


# Saved copies.

_texts = {}


def read(url, title='', capture=True):
    """Text of the copy atlas.copies.choose picks for url, or None when no copy is readable.
    Copies the atlas or its archive already holds are used as they are; the page is captured
    through the archive (PDFs included) only when the archive holds nothing for it."""
    if url in _texts:
        return _texts[url]
    data = load_core()
    source = dict(data['sources'].get(url) or {'url': url, 'title': title})
    with closing(connect(DB)) as db:
        found = known_copies(source, db)
    chosen = choose(source, found)
    if chosen is None:
        try:
            with ARCHIVE_LOCK:
                ADDED.mkdir(parents=True, exist_ok=True)
                archive = Archive(ADDED)
                held = url in archive.state and archive.state[url]['artifacts']
                if capture and not held:
                    archive.capture(url)
                    archive.pubmed(url)
                if capture and url in archive.state:
                    # A paywall, cookie wall or page built in the browser: a free full copy
                    # (Europe PMC, the ClinicalTrials.gov API) when one exists.
                    archive.open_access(url, title or source.get('title', ''))
                items = archive.evidence(url) if url in archive.state else []
        except ValueError:
            items = []
        known = {c.sha256 for c in found}
        for item in items:
            if item['sha256'] not in known:
                path = str((ADDED / item['path']).resolve())
                found.append(
                    Copy(item['sha256'], path, item['text'], item['kind'], item.get('resolved_url'))
                )
        chosen = choose(source, found)
    _texts[url] = chosen.text if chosen else None
    return _texts[url]


def check(quote, text):
    """True: found in the saved copy. False: copy read, passage not in it. None: no copy."""
    if text is None:
        return None
    return passage_matches(quote, text)


def check_definition(page, only_new=False):
    """Check goal statements and threshold quotes against saved copies of their references;
    with only_new, only those not checked before (new or changed by a revision)."""
    refs = {r['id']: r for r in page['references']}
    counts = [0, 0, 0]
    items = [(s, 'quote', 'ref', 'checked') for s in page['goal']['statements']]
    for unit in [page['completion']] + page['milestones']:
        items.append((unit, 'threshold_quote', 'threshold_ref', 'threshold_checked'))
    for item, quote, ref, flag in items:
        if only_new and flag in item:
            continue
        if not item[quote]:
            item[flag] = None
            continue
        reference = refs.get(item[ref])
        text = read(reference['url'], reference['title']) if reference else None
        item[flag] = check(item[quote], text)
        counts[2 if item[flag] is None else 0 if item[flag] else 1] += 1
    return counts


def check_answers(answers, references):
    """Mark each answer's quote checked (True), not found (False) or unreadable (None) against
    the saved copy of its reference."""
    refs = {r['id']: r for r in references}
    for item in (answers or {}).values():
        reference = refs.get(item['ref'])
        if not item['quote'] or reference is None:
            item['checked'] = None
            continue
        item['checked'] = check(item['quote'], read(reference['url'], reference['title']))
    return answers


# Citations from registries.


def fetch(url):
    request = urllib.request.Request(request_url(url), headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read(4_000_000)


def initials(given):
    return ''.join(part[0].upper() for part in re.split(r'[\s.\-]+', given or '') if part)


def vancouver(names):
    """names: (family, given) pairs or organisation strings."""
    shown = [
        name if isinstance(name, str) else f'{name[0]} {initials(name[1])}'.strip()
        for name in names
    ]
    return ', '.join(shown[:6]) + (', et al.' if len(shown) > 6 else '')


def crossref(doi):
    message = json.loads(fetch('https://api.crossref.org/works/' + urllib.parse.quote(doi)))[
        'message'
    ]
    names = [
        (a['family'], a.get('given')) if a.get('family') else a.get('name')
        for a in message.get('author', [])
        if a.get('family') or a.get('name')
    ]
    date = None
    for key in ('published-print', 'published-online', 'issued'):
        parts = (message.get(key) or {}).get('date-parts') or [[None]]
        if parts[0][0]:
            date = str(parts[0][0])
            break
    container = (message.get('short-container-title') or message.get('container-title') or [None])[
        0
    ]
    return {
        'authors': vancouver(names),
        'container': container,
        'year': date,
        'volume': message.get('volume'),
        'issue': message.get('issue'),
        'pages': message.get('page'),
        'doi': message.get('DOI'),
    }


PMC = re.compile(
    r'^https?://(?:pmc\.ncbi\.nlm\.nih\.gov|(?:www\.)?ncbi\.nlm\.nih\.gov/pmc)/articles/PMC(\d+)'
)
ESUMMARY_PMC = (
    'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id={}&retmode=json'
)


def pubmed(url):
    identifier = pubmed_id(url)
    match = PMC.match(url.strip())
    if identifier is None and match:
        summary = json.loads(fetch(ESUMMARY_PMC.format(match.group(1))))['result']
        ids = summary[match.group(1)].get('articleids', [])
        identifier = next((i['value'] for i in ids if i['idtype'] == 'pmid'), None)
    if not identifier:
        return None
    root = ET.fromstring(fetch(EFETCH.format(identifier)))
    article = root.find('.//Article')
    if article is None:
        return None
    names = []
    for author in article.findall('./AuthorList/Author'):
        if author.findtext('LastName'):
            names.append((author.findtext('LastName'), author.findtext('Initials') or ''))
        elif author.findtext('CollectiveName'):
            names.append(author.findtext('CollectiveName'))
    names = [n if isinstance(n, str) else f'{n[0]} {n[1]}'.strip() for n in names]
    issue = article.find('./Journal/JournalIssue')
    year = issue.findtext('./PubDate/Year') if issue is not None else None
    if not year and issue is not None:
        year = (re.findall(r'\d{4}', issue.findtext('./PubDate/MedlineDate') or '') or [None])[0]
    doi = root.findtext(".//ArticleIdList/ArticleId[@IdType='doi']") or article.findtext(
        "./ELocationID[@EIdType='doi']"
    )
    return {
        'authors': ', '.join(names[:6]) + (', et al.' if len(names) > 6 else ''),
        'container': article.findtext('./Journal/ISOAbbreviation'),
        'year': year,
        'volume': issue.findtext('Volume') if issue is not None else None,
        'issue': issue.findtext('Issue') if issue is not None else None,
        'pages': article.findtext('./Pagination/MedlinePgn'),
        'doi': doi,
    }


ARXIV = re.compile(r'arxiv\.org/(?:abs|pdf|html)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?/?(?:[?#].*)?$')
ATOM = '{http://www.w3.org/2005/Atom}'


def arxiv(url, doi=None):
    match = ARXIV.search(url) or re.search(r'10\.48550/arxiv\.([^?#\s]+)', f'{doi} {url}', re.I)
    if not match:
        return None
    root = ET.fromstring(fetch('https://export.arxiv.org/api/query?id_list=' + match.group(1)))
    entry = root.find(ATOM + 'entry')
    if entry is None or entry.find(ATOM + 'published') is None:
        return None
    names = []
    for author in entry.findall(ATOM + 'author'):
        parts = (author.findtext(ATOM + 'name') or '').split()
        if parts:
            names.append((parts[-1], ' '.join(parts[:-1])))
    return {
        'authors': vancouver(names),
        'container': 'arXiv',
        'year': entry.findtext(ATOM + 'published')[:4],
        'volume': None,
        'issue': None,
        'pages': None,
        'doi': None,
    }


def cite(reference):
    """Fill a reference's authors, container, year, volume, issue and pages from the first
    registry that holds it; otherwise keep the model's authors, container and year."""
    for name, lookup in [
        ('crossref', lambda: crossref(reference['doi']) if reference.get('doi') else None),
        ('pubmed', lambda: pubmed(reference['url'])),
        ('arxiv', lambda: arxiv(reference['url'], reference.get('doi'))),
    ]:
        try:
            found = lookup()
        except Exception:
            found = None
        if found and found.get('year'):
            for key, value in found.items():
                if value and (key != 'doi' or not reference.get('doi')):
                    reference[key] = value
                elif key in ('volume', 'issue', 'pages'):
                    reference[key] = value
            reference['citation_source'] = name
            return name
    for key in ('volume', 'issue', 'pages'):
        reference.setdefault(key, None)
    reference['citation_source'] = 'model'
    return 'model'


def cite_all(references):
    counts = {'crossref': 0, 'pubmed': 0, 'arxiv': 0, 'model': 0}
    for reference in references:
        counts[cite(reference)] += 1
    return counts


def cited_row(counts):
    return {
        'date': today(),
        'actor': 'atlas.page',
        'action': 'Filled citations from registries: '
        f'{counts["crossref"]} from Crossref, {counts["pubmed"]} from PubMed, '
        f'{counts["arxiv"]} from arXiv, {counts["model"]} as the model gave them.',
    }


def checked_row(counts, what):
    good, bad, unread = counts
    return {
        'date': today(),
        'actor': 'atlas.page',
        'action': f'Checked {what} against saved copies: {good} found, {bad} not found, '
        f'{unread} with no readable copy.',
    }


# Contract.


def criterion_hash(text):
    """Identifies the criterion a source was judged against; a changed criterion is re-judged."""
    return hashlib.sha256((text or '').encode()).hexdigest()[:12]


def active(page):
    """Active milestones in display order."""
    by_id = {m['id']: m for m in page['milestones']}
    return [by_id[i] for i in page.get('milestone_order', []) if i in by_id]


def ref_slots(page):
    """Every place a definition cites a reference: (container, key, is_list)."""
    slots = [(page['goal'], 'need_refs', True), (page['completion'], 'refs', True)]
    slots.append((page['completion'], 'threshold_ref', False))
    if page['goal']['figures']:
        slots.append((page['goal']['figures'], 'ref', False))
    slots += [(s, 'ref', False) for s in page['goal']['statements']]
    for milestone in page['milestones']:
        slots += [(milestone, 'refs', True), (milestone, 'threshold_ref', False)]
    slots += [(m, 'ref', False) for m in page['measures']]
    slots += [(r, 'ref', False) for r in page.get('results', [])]
    if page.get('completed'):
        slots.append((page['completed'], 'ref', False))
    return slots


def cited_refs(page):
    used = set()
    for holder, key, many in ref_slots(page):
        value = holder.get(key)
        if many:
            used |= set(value or [])
        elif value is not None:
            used.add(value)
    return used


def problems(page):
    """Every structural way the base definition breaks the contract; an empty list passes."""
    found = []
    references = [r['id'] for r in page['references']]
    if references != list(range(1, len(references) + 1)):
        found.append('references must be numbered 1..n in order')
    used = cited_refs(page)
    if used - set(references):
        found.append(f'citations with no reference: {sorted(used - set(references))}')
    if set(references) - used:
        found.append(f'references never cited: {sorted(set(references) - used)}')
    ids = [m['id'] for m in page['milestones']]
    if ids != [f'm{n + 1}' for n in range(len(ids))]:
        found.append('milestone ids must be m1, m2, ... in order')
    if not 3 <= len(ids) <= 6:
        found.append(f'{len(ids)} milestones; 3 to 6 are required')
    if not 2 <= len(page['goal']['statements']) <= 5:
        found.append('goal.statements needs 2 to 5 items')
    if page['cases'] and not page['case_label']:
        found.append('cases given without case_label')
    return found


def validate(page):
    """Every structural fault of a stored entry, including one made by hand."""
    found = []
    for key in DEFINITION + ['id', 'references', 'results', 'log', 'version', 'judged']:
        if key not in page:
            found.append(f'missing field {key}')
    if found:
        return found
    references = [r.get('id') for r in page['references']]
    if references != list(range(1, len(references) + 1)):
        found.append('references must be numbered 1..n in order')
    for reference in page['references']:
        if not reference.get('url'):
            found.append(f'reference {reference.get("id")} has no url')
    used = cited_refs(page)
    if used - set(references):
        found.append(f'citations with no reference: {sorted(used - set(references))}')
    if set(references) - used:
        found.append(f'references never cited: {sorted(set(references) - used)}')
    ids = [m.get('id') for m in page['milestones']]
    if len(ids) != len(set(ids)):
        found.append(f'milestone ids repeat: {ids}')
    for milestone in page['milestones']:
        name = milestone.get('id')
        if not re.fullmatch(r'm[1-9]\d*', str(name)):
            found.append(f'milestone id {name!r} is not m<number>')
        if milestone.get('status') not in ('active', 'retired'):
            found.append(f'{name}: status must be active or retired')
        for other in milestone.get('replaced_by', []):
            if other not in ids:
                found.append(f'{name}: replaced_by names unknown milestone {other}')
        if milestone.get('status') == 'active' and milestone.get('replaced_by'):
            found.append(f'{name}: an active milestone cannot be replaced')
        for key in ('title', 'criterion', 'set_by', 'set_by_kind', 'refs'):
            if key not in milestone:
                found.append(f'{name}: missing {key}')
        if milestone.get('set_by_kind') not in SET_BY:
            found.append(f'{name}: set_by_kind must be one of {SET_BY}')
    order = page.get('milestone_order')
    live = [m.get('id') for m in page['milestones'] if m.get('status') == 'active']
    if (
        not isinstance(order, list)
        or sorted(order) != sorted(live)
        or len(set(order)) != len(order)
    ):
        found.append(f'milestone_order {order} must list each active milestone once: {live}')
    if not live:
        found.append('no active milestones')
    if page['milestone_structure'] not in ('sequence', 'parallel'):
        found.append('milestone_structure must be sequence or parallel')
    if not 2 <= len(page['goal']['statements']) <= 5:
        found.append('goal.statements needs 2 to 5 items')
    if page['cases'] and not page['case_label']:
        found.append('cases given without case_label')
    if len(set(page['cases'])) != len(page['cases']):
        found.append('cases repeat')
    for n, result in enumerate(page['results']):
        if result.get('milestone') not in ids + ['completion']:
            found.append(f'results[{n}] is on unknown milestone {result.get("milestone")!r}')
        if page['cases'] and result.get('case') not in page['cases']:
            found.append(f'results[{n}] is on unknown case {result.get("case")!r}')
        if not page['cases'] and result.get('case') is not None:
            found.append(f'results[{n}] names a case but the entry has none')
        if result.get('verdict') not in ('met', 'partial'):
            found.append(f'results[{n}] verdict must be met or partial')
        if not isinstance(result.get('confirmed'), bool):
            found.append(f'results[{n}] confirmed must be true or false')
    if not isinstance(page['version'], int) or page['version'] < 1:
        found.append('version must be a whole number from 1')
    for n, row in enumerate(page['judged']):
        if not {'url', 'milestone', 'hash'} <= set(row):
            found.append(f'judged[{n}] needs url, milestone and hash')
    return found


def over_length(page, results=None):
    """(field, length, limit) for every text over its limit; kept, and written to the log."""
    sizes = []
    if results is None:
        sizes += [
            ('title', page['title'], 'title'),
            ('definition', page['definition'], 'definition'),
            ('goal.need', page['goal']['need'], 'need'),
            ('completion.title', page['completion']['title'], 'milestone_title'),
            ('completion.criterion', page['completion']['criterion'], 'criterion'),
            ('completion.basis', page['completion']['basis'], 'basis'),
            ('completion.threshold_quote', page['completion']['threshold_quote'], 'quote'),
        ]
        for n, statement in enumerate(page['goal']['statements']):
            sizes.append((f'goal.statements[{n}].quote', statement['quote'], 'quote'))
        for n, measure in enumerate(page['measures']):
            sizes.append((f'measures[{n}].value', measure['value'], 'measure_value'))
            sizes.append((f'measures[{n}].note', measure.get('note'), 'measure_note'))
        for milestone in page['milestones']:
            name = milestone['id']
            sizes.append((f'{name}.title', milestone['title'], 'milestone_title'))
            sizes.append((f'{name}.criterion', milestone['criterion'], 'criterion'))
            sizes.append((f'{name}.threshold_quote', milestone['threshold_quote'], 'quote'))
    for result in results or []:
        name = f'result on {result["milestone"]} from reference {result["ref"]}'
        sizes.append((f'{name}: finding', result['finding'], 'finding'))
        sizes.append((f'{name}: detail', result['detail'], 'detail'))
        sizes.append((f'{name}: quote', result['quote'], 'quote'))
    return [
        (name, len(text), LIMITS[limit])
        for name, text, limit in sizes
        if text and len(text) > LIMITS[limit]
    ]


def row(actor, action):
    return {'date': today(), 'actor': actor, 'action': action}


def length_rows(found):
    return [
        row('atlas.page', f'{name} is {size} characters, over its limit of {limit}; kept.')
        for name, size, limit in found
    ]


def folder(identifier, step):
    stamp = datetime.now(timezone.utc)
    return CALLS / f'{identifier}-{step}-{stamp:%Y%m%dT%H%M%S%fZ}'


def model_call(schema, entry, directory, stop=None):
    def call(text):
        if stop is not None and stop.is_set():
            raise batches.Stopped()
        directory.mkdir(parents=True, exist_ok=True)
        return Models(config()).call('format', text, schema, directory, entry=entry)

    return call


def path_of(identifier, out):
    return Path(out) / f'{identifier}.json'


def record_file(identifier, core=None):
    paths = list(Path(core or CORE).glob(f'*/{identifier}.json'))
    if len(paths) != 1:
        raise ValueError(f'{identifier}: expected exactly one breakthrough file')
    return paths[0]


def stored_page(identifier, out=None):
    """The stored entry: the record's `page` key, or the file in out. None when there is none."""
    if out:
        path = path_of(identifier, out)
        return json.loads(path.read_text()) if path.exists() else None
    return json.loads(record_file(identifier).read_text(encoding='utf-8')).get('page')


def load(identifier, out=None):
    page = stored_page(identifier, out)
    if page is None:
        raise ValueError(f'{identifier}: has no page; run define first')
    return page


def dump_record(value):
    return json.dumps(value, indent=1, ensure_ascii=False) + '\n'


def write_record(identifier, page, model=None, core=None):
    """Store page as the record's `page` key (added last), and models.page when model is given;
    every other byte of the record file stays the same, as atlas.brief writes `brief`."""
    path = record_file(identifier, core)
    source = path.read_text(encoding='utf-8')
    item = json.loads(source)
    # Record files are written by atlas.core in this exact form. Adding keys at the end of an
    # object then leaves every other key's bytes as they were.
    if dump_record(item) != source:
        raise ValueError(f'{identifier}: record file is not in the written format; not changed')
    if model:
        item.setdefault('models', {})['page'] = model
    item.pop('page', None)
    item['page'] = page  # always the last key
    records.replace_text(path, dump_record(item))


def save(page, out=None, model=None):
    """Write page to its record (or, with out, to a JSON file in that folder)."""
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        text = json.dumps(page, indent=2, ensure_ascii=False) + '\n'
        path_of(page['id'], out).write_text(text)
    else:
        write_record(page['id'], page, model)


# References.


def remap(page, mapping):
    """Point every citation of page at mapping[old id] (ids missing from mapping stay)."""
    for holder, key, many in ref_slots(page):
        value = holder.get(key)
        if many:
            holder[key] = list(dict.fromkeys(mapping.get(n, n) for n in value or []))
        elif value is not None:
            holder[key] = mapping.get(value, value)


def merge_duplicates(page):
    """Merge references that name the same DOI into the first; renumber 1..n. Returns the
    merged pairs (kept id, dropped id) in the old numbering."""
    first = {}
    merged = []
    for reference in page['references']:
        doi = (reference.get('doi') or '').lower().strip()
        if doi and doi in first:
            merged.append((first[doi], reference['id']))
        elif doi:
            first[doi] = reference['id']
    if not merged:
        return []
    dropped = {gone: kept for kept, gone in merged}
    remap(page, dropped)
    page['references'] = [r for r in page['references'] if r['id'] not in dropped]
    compact(page)
    return merged


def compact(page):
    """Renumber references 1..n in their order and point every citation at the new number."""
    numbers = {r['id']: n for n, r in enumerate(page['references'], 1)}
    for reference in page['references']:
        reference['id'] = numbers[reference['id']]
    remap(page, numbers)


def merged_row(merged):
    pairs = ', '.join(f'{gone} into {kept}' for kept, gone in merged)
    return row('atlas.page', f'Merged references with the same DOI ({pairs}); renumbered.')


def refer(references, url, title, kind, doi, text):
    """The id of url's reference, appending one for a new source."""
    for reference in references:
        same_doi = doi and (reference.get('doi') or '').lower() == doi.lower()
        if normal(reference['url']) == normal(url) or same_doi:
            return reference['id']
    # A DOI the judge reports is kept only when the saved text states it.
    if doi and doi.lower() not in (text or '').lower():
        doi = None
    references.append(
        {
            'id': len(references) + 1,
            'kind': kind,
            'url': url,
            'doi': doi,
            'title': flat(title) or url,
            'authors': '',
            'container': None,
            'year': '',
        }
    )
    return references[-1]['id']


# Pass 1: the base definition.


def define(
    identifier, call=None, replace=False, writer=None, out=None, store=None, stop=None, stats=None
):
    """Write the base definition of one breakthrough's page. An entry that already has one is
    left alone unless replace is set; change it with revise, add or a hand edit instead."""
    old = None
    writer = writer or ENTRY
    old = stored_page(identifier, out)
    if old is not None:
        if old.get('definition') and not replace:
            return (
                f'{identifier}: already has a definition (version {old.get("version", 1)}); '
                'nothing written. Change it with revise, add or a hand edit, or pass --replace '
                'to discard it and its results and write a new base.'
            )
    record, held = held_sources(identifier)
    text = PROMPT.format(
        need_guide=NEED_GUIDE,
        id=identifier,
        title=record['title'],
        record=describe(record),
        sources=show_held(record, held),
    )
    calls = folder(identifier, 'define')
    attempts = 0
    answer = None
    wrong = []
    while attempts < 2:
        attempts += 1
        ask = text
        if wrong:
            ask += '\n\nYour previous answer was rejected for these reasons. Fix every one:\n'
            ask += '\n'.join(f'- {w}' for w in wrong)
        run = call or model_call(SCHEMA, writer, calls / f'attempt-{attempts}', stop)
        answer = run(ask)
        wrong = problems(answer)
        if not wrong:
            break
    if stats is not None:
        stats['attempts'] = attempts
    if wrong:
        return f'{identifier}: rejected after {attempts} attempts: {"; ".join(wrong)}'
    for milestone in answer['milestones']:
        milestone.update(status='active', replaced_by=[])
    answers = answer.pop('need_answers', None)
    check_answers(answers, answer['references'])
    calls.mkdir(parents=True, exist_ok=True)
    (calls / 'need_answers.json').write_text(
        json.dumps(answers, indent=2, ensure_ascii=False) + '\n'
    )
    page = {
        'id': identifier,
        **answer,
        'milestone_order': [m['id'] for m in answer['milestones']],
        'results': [],
        'judged': [],
        'version': 1,
        'accessed': today(),
    }
    citations = cite_all(page['references'])
    merged = merge_duplicates(page)
    quotes = check_definition(page)
    unsure = [
        unit.get('id', 'completion')
        for unit in [page['completion']] + page['milestones']
        if unit['threshold_quote'] and unit['threshold_ref'] is None
    ]
    page['log'] = []
    if old and old.get('definition'):
        page['log'].append(
            row(
                'atlas.page',
                f'Replaced version {old.get("version", 1)} and its results (--replace).',
            )
        )
    page['log'] += [
        row(
            writer['model'], f'Wrote the base definition from web research ({attempts} attempt(s)).'
        ),
        cited_row(citations),
        checked_row(quotes, 'goal statements and threshold quotations'),
    ]
    if merged:
        page['log'].append(merged_row(merged))
    if unsure:
        page['log'].append(
            row(
                'atlas.page',
                'Threshold quotation given without its reference, not checked: '
                + ', '.join(unsure)
                + '.',
            )
        )
    page['log'] += length_rows(over_length(page))
    if store is not None:
        store(page)
    else:
        save(page, out, writer['model'])
    if stats is not None:
        stats['page'] = page
    confirmed = sum(
        1 for unit in [page['completion']] + page['milestones'] if unit['threshold_checked']
    )
    return (
        f'{identifier}: {page["title"]} | completion set by {page["completion"]["set_by_kind"]} | '
        f'{len(page["milestones"])} milestones ({page["milestone_structure"]}), '
        f'{len(page["references"])} references, thresholds confirmed {confirmed} of '
        f'{len(page["milestones"]) + 1}, quotes {quotes[0]} found / {quotes[1]} not found / '
        f'{quotes[2]} unreadable, citations {citations}, {attempts} attempt(s)'
    )


# Judging sources.


def units(page):
    """(id, label, title, criterion) for each active milestone and the completion test."""
    out = [(m['id'], f'Milestone {m["id"]}', m['title'], m['criterion']) for m in active(page)]
    completion = page['completion']
    out.append(('completion', 'Completion test', completion['title'], completion['criterion']))
    return out


def show_entry(page):
    lines = [page['definition'], '']
    for unit, label, title, criterion in units(page):
        lines.append(f'{label} ({unit}): {title}\n  Criterion: {criterion}')
    if page['cases']:
        lines.append(f'\n{page["case_label"]} cases: ' + '; '.join(page['cases']))
    else:
        lines.append('\nThe entry has no cases.')
    return '\n'.join(lines)


def judge_held(page, source, call, only=None):
    """Ask which of the units (all active ones, or those in only) one source bears on."""
    listing = '\n'.join(
        f'{unit} ({label}): {title}\n  Criterion: {criterion}'
        for unit, label, title, criterion in units(page)
        if only is None or unit in only
    )
    cases = (
        f'{page["case_label"]} cases: ' + '; '.join(page['cases']) + '\n'
        if page['cases']
        else 'The entry has no cases.\n'
    )
    return call(
        HELD_PROMPT.format(
            title=page['title'],
            definition=page['definition'],
            units=listing,
            cases=cases,
            source_title=flat(source['title']) or source['url'],
            url=source['url'],
            text=source['text'][:JUDGE_TEXT],
        )
    )


def judge_one(page, candidate, text, call):
    unit = {u[0]: u for u in units(page)}[candidate['milestone']]
    return call(
        JUDGE_PROMPT.format(
            title=page['title'],
            definition=page['definition'],
            unit=unit[1],
            unit_title=unit[2],
            criterion=unit[3],
            case=candidate['case'] or 'none (the entry has no cases)',
            for_case=f' for the case "{candidate["case"]}"' if candidate['case'] else '',
            source_title=flat(candidate['title']) or candidate['url'],
            url=candidate['url'],
            text=text[:JUDGE_TEXT],
        )
    )


def resolve_case(value, cases):
    """The listed case a model's answer names: the case itself, or the one case whose text
    starts with the answer (a model may shorten "Inertial confinement: fuel targets ..." to
    "Inertial confinement"). '' when it names none; None when the entry has no cases."""
    if not cases:
        return None if not value else ''
    if value in cases:
        return value
    short = (value or '').strip().rstrip('.').lower()
    found = [case for case in cases if short and case.lower().startswith(short)]
    return found[0] if len(found) == 1 else ''


def snapshot(page):
    return copy.deepcopy({key: page[key] for key in DEFINITION})


def hashes(page):
    return {unit: criterion_hash(criterion) for unit, _, _, criterion in units(page)}


def judged_pairs(page):
    return {(normal(j['url']), j['milestone'], j['hash']) for j in page['judged']}


def pending(page, url, everything=False):
    """The active units url has not been judged against in their current wording."""
    done = judged_pairs(page)
    return [
        unit
        for unit, digest in hashes(page).items()
        if everything or (normal(url), unit, digest) not in done
    ]


class Judgement:
    """Collects the rows of one run and writes them into the page: re-judging a (source,
    milestone) pair replaces that pair's rows only."""

    def __init__(self, page, judged_by):
        self.page = page
        self.judged_by = judged_by
        self.references = page['references']
        self.ids = [u[0] for u in units(page)]
        self.digest = hashes(page)
        self.cases = page['cases']
        self.added = []
        self.replaced = 0
        self.dropped = {
            'not relevant': 0,
            'partial on completion': 0,
            'unknown milestone or case': 0,
        }
        self.counted = {'held': 0, 'new': 0}
        self.first_new_ref = len(self.references) + 1
        self.timeouts = 0

    def covered(self, url, unit_ids):
        """Record that url was judged against unit_ids and clear its earlier rows on them."""
        urls = {r['id']: normal(r['url']) for r in self.references}
        before = len(self.page['results'])
        self.page['results'] = [
            r
            for r in self.page['results']
            if not (urls.get(r['ref']) == normal(url) and r['milestone'] in unit_ids)
        ]
        self.replaced += before - len(self.page['results'])
        self.page['judged'] = [
            j
            for j in self.page['judged']
            if not (normal(j['url']) == normal(url) and j['milestone'] in unit_ids)
        ]
        for unit in unit_ids:
            self.page['judged'].append(
                {
                    'url': url,
                    'milestone': unit,
                    'hash': self.digest[unit],
                    'date': today(),
                    'by': self.judged_by,
                }
            )

    def place(self, answer_row, source, text, origin, allowed):
        answer_row = {**answer_row, 'case': resolve_case(answer_row['case'], self.cases)}
        if answer_row['milestone'] not in allowed or answer_row['case'] == '':
            self.dropped['unknown milestone or case'] += 1
            return
        if answer_row['verdict'] == 'not_relevant':
            self.dropped['not relevant'] += 1
            return
        if answer_row['verdict'] == 'partial' and answer_row['milestone'] == 'completion':
            self.dropped['partial on completion'] += 1
            return
        ref = refer(
            self.references, source['url'], source['title'], source['kind'], source['doi'], text
        )
        result = {
            'milestone': answer_row['milestone'],
            'case': answer_row['case'],
            'verdict': answer_row['verdict'],
            'finding': answer_row['finding'],
            'detail': answer_row['detail'] or None,
            'quote': answer_row['quote'] or None,
            'checked': check(answer_row['quote'], text) if answer_row['quote'] else None,
            'confirmed': answer_row['confirmed'],
            'peer_reviewed': answer_row['peer_reviewed'],
            'ref': ref,
            'judged_by': self.judged_by,
            'judged_on': today(),
        }
        self.page['results'].append(result)
        self.added.append(result)
        self.counted[origin] += 1

    def finish(self, actor_rows):
        """Fill new citations, merge duplicates, and log; returns the summary counts."""
        citations = cite_all(self.references[self.first_new_ref - 1 :])
        merged = merge_duplicates(self.page)
        quotes = [0, 0, 0]
        for result in self.added:
            if result['quote']:
                quotes[2 if result['checked'] is None else 0 if result['checked'] else 1] += 1
        log = actor_rows + [cited_row(citations), checked_row(quotes, 'result quotations')]
        if merged:
            log.append(merged_row(merged))
        # A reference added for a candidate whose row was then dropped (not relevant) or
        # replaced is cited by nothing; it goes, and the rest are renumbered.
        unused = sorted({r['id'] for r in self.page['references']} - cited_refs(self.page))
        if unused:
            self.page['references'] = [
                r for r in self.page['references'] if r['id'] not in set(unused)
            ]
            compact(self.page)
            log.append(
                row('atlas.page', f'Removed {len(unused)} references no longer cited; renumbered.')
            )
        self.page['log'] += log + length_rows(over_length(self.page, self.added))
        return citations, quotes

    def drops(self):
        return '; '.join(f'{n} {why}' for why, n in self.dropped.items() if n) or 'none'


def entry_sources(page, held):
    """Sources the entry already uses: the atlas's held sources, then every source a result
    or a judgement names, each {url, title, text or None}."""
    out = {}
    for source in held:
        out[normal(source['url'])] = {
            'url': source['url'],
            'title': source['title'],
            'text': source['text'] or None,
        }
    titles = {normal(r['url']): r['title'] for r in page['references']}
    urls = {r['id']: r['url'] for r in page['references']}
    known = [urls[r['ref']] for r in page['results'] if r['ref'] in urls]
    known += [j['url'] for j in page['judged']]
    for url in known:
        if normal(url) not in out:
            out[normal(url)] = {'url': url, 'title': titles.get(normal(url), ''), 'text': 'read'}
    return list(out.values())


def judge_sources(
    page, sources, work, judge, entry, calls, everything=False, origin='held', stop=None
):
    """Judge each source against the active units it has not been judged against (all of them
    with everything). Sources without readable text are skipped; a call that times out is
    skipped and not recorded as judged, so a later run asks again. Returns (calls made,
    skipped [(url, why)])."""
    skipped = []
    todo = []
    for source in sources:
        units_left = pending(page, source['url'], everything)
        if not units_left:
            continue
        text = source['text']
        if text == 'read':
            text = read(source['url'], source['title'], capture=False)
        if not text:
            skipped.append((source['url'], 'no readable saved copy'))
            continue
        todo.append(({**source, 'text': text}, units_left))

    def ask(item):
        n, (source, units_left) = item
        run = judge or model_call(HELD_SCHEMA, entry, calls / f'{origin}-{n}', stop)
        try:
            return judge_held(page, source, run, only=set(units_left))
        except ProviderTimeout:
            return None

    with ThreadPoolExecutor(JUDGES) as pool:
        answers = list(pool.map(ask, enumerate(todo, 1)))
    for (source, units_left), answer in zip(todo, answers):
        if answer is None:
            skipped.append((source['url'], 'model timed out'))
            work.timeouts += 1
            continue
        work.covered(source['url'], units_left)
        about = {**source, 'kind': answer['kind'], 'doi': answer['doi']}
        for answer_row in answer['rows']:
            work.place(answer_row, about, source['text'], origin, set(units_left))
    return len(todo), skipped


def skip_text(skipped):
    reasons = {}
    for _, why in skipped:
        reasons[why] = reasons.get(why, 0) + 1
    return '; '.join(f'{n} {why}' for why, n in reasons.items()) or 'none'


# Pass 2: results, incremental.


def results(
    identifier,
    search=None,
    judge=None,
    held=None,
    everything=False,
    writer=None,
    store=None,
    stop=None,
):
    """Judge what has not been judged against the current wording of each active milestone:
    the sources the entry already uses first, then a search for the gaps. Earlier results are
    kept; re-judging a (source, milestone) pair replaces that pair's rows only."""
    page = load(identifier)
    before = snapshot(page)
    writer = writer or ENTRY
    entry = judge_entry(config(), writer['model'])
    judged_by = entry['model']
    calls = folder(identifier, 'results')
    if held is None:
        _, held = held_sources(identifier)
    work = Judgement(page, judged_by)

    # a. Sources already held or already used, from their saved copies: no search, no capture.
    known = entry_sources(page, held)
    made, skipped = judge_sources(page, known, work, judge, entry, calls, everything, 'held', stop)

    # b. Search only for the gaps.
    live = set(work.ids)
    done = sorted(
        {
            (r['milestone'], r['case'])
            for r in page['results']
            if r['confirmed'] and r['verdict'] == 'met' and r['milestone'] in live
        }
    )
    known_urls = {normal(s['url']) for s in known}
    find = search or model_call(FIND_SCHEMA, writer, calls / 'find', stop)
    found = find(
        FIND_PROMPT.format(
            id=identifier,
            title=page['title'],
            entry=show_entry(page),
            limit=CANDIDATES,
            done='\n'.join(f'- {m}' + (f', {c}' if c else '') for m, c in done) or '(none)',
            held='\n'.join(f'- {s["url"]}' for s in known) or '(none)',
        )
    )['candidates']
    offered = len(found)
    candidates = []
    seen = set()
    already = 0
    pairs = judged_pairs(page)
    for candidate in found[:CANDIDATES]:
        candidate = {**candidate, 'case': resolve_case(candidate['case'], work.cases)}
        key = (normal(candidate['url']), candidate['milestone'], candidate['case'])
        digest = work.digest.get(candidate['milestone'])
        if normal(candidate['url']) in known_urls:
            already += 1
        elif key in seen:
            skipped.append((candidate['url'], 'duplicate candidate'))
        elif candidate['milestone'] not in live or candidate['case'] == '':
            skipped.append((candidate['url'], 'unknown milestone or case'))
        elif not everything and (key[0], candidate['milestone'], digest) in pairs:
            skipped.append((candidate['url'], 'already judged against this wording'))
        else:
            seen.add(key)
            candidates.append(candidate)

    # c. Judge each new candidate against its one milestone, from a copy saved in the archive.
    def new_call(item):
        n, candidate = item
        text = read(candidate['url'], candidate['title'])
        if not text:
            return text, None
        run = judge or model_call(JUDGE_SCHEMA, entry, calls / f'judge-{n}', stop)
        try:
            return text, judge_one(page, candidate, text, run)
        except ProviderTimeout:
            return text, 'timeout'

    with ThreadPoolExecutor(JUDGES) as pool:
        answers = list(pool.map(new_call, enumerate(candidates, 1)))
    judged = 0
    for candidate, (text, answer) in zip(candidates, answers):
        if answer is None:
            skipped.append((candidate['url'], 'no readable saved copy'))
            continue
        if answer == 'timeout':
            skipped.append((candidate['url'], 'model timed out'))
            work.timeouts += 1
            continue
        judged += 1
        work.covered(candidate['url'], [candidate['milestone']])
        about = {**candidate, 'kind': answer['kind'], 'doi': answer['doi']}
        answer_row = {**answer, 'milestone': candidate['milestone'], 'case': candidate['case']}
        work.place(answer_row, about, text, 'new', {candidate['milestone']})

    # The definition is read, never changed.
    assert snapshot(page) == before, 'results must not change the definition'
    citations, quotes = work.finish(
        [
            row(
                judged_by,
                f'Judged {made} sources the entry already uses against the milestones they had '
                f'not been judged against{" (all, --all)" if everything else ""}, without search.',
            ),
            row(
                writer['model'],
                f'Searched for results on the open cells: {offered} candidates returned, '
                f'{already} dropped as sources already used, {len(candidates)} to judge.',
            ),
            row(
                judged_by,
                f'Judged {judged} of {len(candidates)} new candidates, without search. '
                f'Skipped: {skip_text(skipped)}. Dropped rows: {work.drops()}. '
                f'Replaced {work.replaced} earlier rows. Added {len(work.added)} results: '
                f'{work.counted["held"]} from sources already used, {work.counted["new"]} from '
                'newly found sources.',
            ),
        ]
    )
    if work.timeouts:
        page['log'].append(
            row('atlas.page', f'{work.timeouts} judge calls timed out; the next run asks again.')
        )
    else:
        # The results pass completed for this version of the entry (read by results --missing).
        page['results_run'] = today()
    if store is not None:
        store(page)
    else:
        save(page)
    return (
        f'{identifier}: re-judged {made} known sources, candidates {offered} ({already} already '
        f'used), judged {judged}, added {len(work.added)} ({work.counted["held"]} known / '
        f'{work.counted["new"]} new), replaced {work.replaced}, skipped {len(skipped)} '
        f'({skip_text(skipped)}), dropped {work.drops()}; total results {len(page["results"])}; '
        f'quotes {quotes[0]} found / {quotes[1]} not found / {quotes[2]} unreadable; '
        f'citations {citations}; judged by {judged_by}'
    )


# add: judge named sources against every active milestone.


def add(identifier, urls, judge=None, titles=None, note=None):
    """Save each URL through the archive (if not held) and judge it against all active
    milestones and cases. No search. titles: {url: title} for sources the page does not cite
    yet (the title helps choose the saved copy); note: a log row to add, as (actor, text)."""
    page = load(identifier)
    before = snapshot(page)
    entry = judge_entry(config())
    calls = folder(identifier, 'add')
    work = Judgement(page, entry['model'])
    titles = {normal(url): title for url, title in (titles or {}).items()} | {
        normal(r['url']): r['title'] for r in page['references']
    }
    sources = []
    skipped = []
    for url in urls:
        text = read(url, titles.get(normal(url), ''))
        if text:
            sources.append({'url': url, 'title': titles.get(normal(url), ''), 'text': text})
        else:
            skipped.append((url, 'no readable saved copy'))
    made, more = judge_sources(page, sources, work, judge, entry, calls, True, 'new')
    skipped += more
    assert snapshot(page) == before, 'add must not change the definition'
    citations, quotes = work.finish(
        [
            row(
                entry['model'],
                f'Added {len(urls)} named sources: judged {made} against every active milestone, '
                f'without search. Skipped: {skip_text(skipped)}. Dropped rows: {work.drops()}. '
                f'Replaced {work.replaced} earlier rows; added {len(work.added)} results.',
            )
        ]
        + ([row(*note)] if note else [])
    )
    save(page)
    return (
        f'{identifier}: judged {made} of {len(urls)} sources, added {len(work.added)} results, '
        f'replaced {work.replaced}, skipped {skip_text(skipped)}, dropped {work.drops()}; '
        f'quotes {quotes[0]} found / {quotes[1]} not found / {quotes[2]} unreadable; '
        f'citations {citations}'
    )


# dates: when a met completion test was first met.

DATE_SCHEMA = obj(
    {
        'date': TEXT,
        'precision': {'type': 'string', 'enum': ['day', 'month', 'year']},
        'event': TEXT,
        'url': TEXT,
        'title': TEXT,
        'kind': KIND,
        'quote': MAYBE,
    }
)

DATE_PROMPT = """\
A breakthrough in the Technology Atlas has met its completion test. Find the date on which the
test was first met, as accurately as the record allows.

Breakthrough: {title}
Completion test: {criterion}
Set by: {set_by}

Results the Atlas holds that meet it:
{results}

Rules:
- The date is when the event the test names happened: an award announced, an approval granted,
  a proof completed and made public, a result published. For a test met by publication or peer
  review, it is the publication date (online first, if earlier). For a ruling or approval, the
  date of the ruling. If the results above are later than the first event that meets the test,
  find the first. When every result above is claimed (the ruling or confirmation the test names
  is still to come), date the claim instead: when the claimed result was first made public; the
  Atlas marks such a date as claimed.
- date: YYYY-MM-DD when a source states the day; YYYY-MM when only the month; YYYY when only
  the year. precision: day, month or year to match. Never guess a finer date than a source
  states.
- event: one line saying what happened on that date, with who and where.
- url and title: the source that states the date, best first: the deciding body's own record,
  the journal's page, then a reputable report. kind: its kind.
- quote: one passage copied exactly, character for character, from that source, that states
  the date (or the month or year); at most 320 characters. null only if the source gives the
  date in a form that cannot be quoted (a metadata field).
"""


def completion_results(page):
    return [
        r
        for r in page.get('results', [])
        if r['milestone'] == 'completion' and r['verdict'] == 'met'
    ]


def date_completion(identifier, call=None, writer=None):
    """Find and store when the page's met completion test was first met: page['completed'] =
    {date, precision, event, ref, quote, checked}. Searches with the writer model; the quote is
    checked against a saved copy of the source; its source becomes a cited reference. Returns
    a line."""
    page = load(identifier)
    met = completion_results(page)
    if not met:
        return f'{identifier}: completion not met; no date'
    refs = {r['id']: r for r in page['references']}
    text = DATE_PROMPT.format(
        title=page['title'],
        criterion=page['completion']['criterion'],
        set_by=page['completion']['set_by'],
        results='\n'.join(
            f'- {r["finding"]} ({refs[r["ref"]]["url"]}; '
            f'{"confirmed" if r.get("confirmed") else "claimed"})'
            for r in met
        ),
    )
    entry = dict(writer or ENTRY)
    entry['search'] = True
    answer = (call or model_call(DATE_SCHEMA, entry, folder(identifier, 'date')))(text)
    shape = {'day': r'\d{4}-\d{2}-\d{2}', 'month': r'\d{4}-\d{2}', 'year': r'\d{4}'}
    if not re.fullmatch(shape[answer['precision']], answer['date']):
        raise ValueError(
            f'{identifier}: date {answer["date"]} does not match {answer["precision"]}'
        )
    source = read(answer['url'], answer['title'])
    checked = check(answer['quote'], source) if answer['quote'] and source else None
    before = snapshot(page)
    first_new = len(page['references']) + 1
    ref = refer(page['references'], answer['url'], answer['title'], answer['kind'], None, source)
    citations = cite_all(page['references'][first_new - 1 :])
    page['completed'] = {
        'date': answer['date'],
        'precision': answer['precision'],
        'event': flat(answer['event']),
        'ref': ref,
        'quote': answer['quote'],
        'checked': checked,
        'by': entry['model'],
    }
    assert snapshot(page) == before, 'dating must not change the definition'
    state = {True: 'quotation found', False: 'quotation not found', None: 'no readable copy'}[
        checked
    ]
    page['log'].append(
        row(
            entry['model'],
            f'Dated the completion: {answer["date"]} ({answer["precision"]}); {state}.',
        )
    )
    if citations:
        page['log'].append(cited_row(citations))
    save(page)
    return f'{identifier}: completed {answer["date"]} ({answer["precision"]}); {state}; {answer["event"]}'


# recover: sources an earlier search proposed that could not be read then.


def recoverable(identifier, page, calls=None):
    """{url: title} of the candidates every earlier results search proposed for identifier
    that the page neither cites nor has judged: the ones skipped for having no readable
    saved copy. Candidates that were judged (including those dropped as not relevant) are
    left out, so nothing is judged twice."""
    calls = Path(calls or CALLS)
    seen = {normal(j['url']) for j in page.get('judged', [])}
    seen |= {normal(r['url']) for r in page['references']}
    out = {}
    for path in sorted(calls.glob(f'{identifier}-results-*/find/response.json')):
        try:
            candidates = json.loads(path.read_text()).get('candidates', [])
        except ValueError:
            continue
        for candidate in candidates:
            url = candidate.get('url')
            if url and normal(url) not in seen and url not in out:
                out[url] = candidate.get('title') or ''
    return out


def recover(identifier, judge=None):
    """Try the skipped sources again, now that unreadable pages fall back to open-access copies
    (Europe PMC, the ClinicalTrials.gov API), and judge each one that reads against every
    active milestone (add). A source still unreadable costs no judge call. Returns a line."""
    urls = recoverable(identifier, load(identifier))
    if not urls:
        return f'{identifier}: nothing to recover'
    note = (
        'atlas.page',
        f'Recovery: {len(urls)} sources an earlier search proposed but could not read were '
        'tried again through open-access copies.',
    )
    return add(identifier, list(urls), judge, urls, note)


# merge: a breakthrough marked as a duplicate (atlas.review, state merge) gives its evidence to
# the page it merges into.


def merge(identifier, judge=None, core=None):
    """Judge the sources behind identifier's results against the kept page's own milestones and
    cases (through add: the judge model, no search, saved copies). A result is a verdict
    against one page's criterion, so rows are never copied as they stand; the evidence is
    judged again. Sources the kept page already cites are left out. Marks the merged record's
    review with `copied` and the date. Returns a line."""
    core = Path(core or CORE)
    data = records.load(core)
    item = data['breakthroughs'].get(identifier)
    review = (item or {}).get('review') or {}
    if review.get('state') != 'merge':
        raise ValueError(f'{identifier}: not marked merge (atlas.review merge ... --into ...)')
    into = review['into']
    with claimed('results', identifier) as mine, claimed('results', into) as theirs:
        if not (mine and theirs):
            raise batches.Stopped('another run is working on one of the two pages')
        source = item.get('page') or {}
        keep = load(into)
        cited = {normal(r['url']) for r in keep['references']}
        by_id = {r['id']: r for r in source.get('references', [])}
        urls, titles = [], {}
        for result in source.get('results', []):
            reference = by_id.get(result.get('ref'))
            if reference and normal(reference['url']) not in cited:
                if reference['url'] not in titles:
                    urls.append(reference['url'])
                titles[reference['url']] = reference.get('title') or ''
        if urls:
            note = (
                'atlas.page',
                f'Merged from {identifier}: {len(urls)} sources behind its results judged against '
                'this page’s milestones.',
            )
            line = add(into, urls, judge, titles, note)
        else:
            line = f'{into}: nothing new; every source behind {identifier}’s results is cited'
        # Record on the merged breakthrough that its evidence has gone across.
        fresh = records.load(core)['breakthroughs'][identifier]
        fresh['review']['copied'] = today()
        fresh['review'].setdefault('log', []).append(
            {'date': today(), 'state': 'merge', 'copied': len(urls), 'into': into}
        )
        records.write_breakthrough(fresh, core)
    return f'{identifier} -> {line}'


def pending_merges(data):
    """Breakthroughs marked merge whose evidence has not gone across, whose target is kept."""
    items = data['breakthroughs']
    out = []
    for identifier, item in sorted(items.items()):
        review = item.get('review') or {}
        target = items.get(review.get('into'), {})
        if (
            review.get('state') == 'merge'
            and not review.get('copied')
            and item.get('page')
            and target.get('page')
            and (target.get('review') or {}).get('state') != 'merge'
        ):
            out.append(identifier)
    return out


# revise: proposed operations, applied by code.

MILESTONE = obj(
    {
        'title': TEXT,
        'criterion': TEXT,
        'set_by': TEXT,
        'set_by_kind': {'type': 'string', 'enum': SET_BY},
        'threshold_quote': MAYBE,
        'threshold_ref': MAYBE_REF,
        'refs': REFS,
    }
)
FIELDS = obj(
    {
        'title': MAYBE,
        'criterion': MAYBE,
        'set_by': MAYBE,
        'set_by_kind': {'type': ['string', 'null'], 'enum': SET_BY + [None]},
        'threshold_quote': MAYBE,
        'threshold_ref': MAYBE_REF,
        'basis': MAYBE,
        'refs': {'type': ['array', 'null'], 'items': REF},
    }
)
OPERATIONS = [
    'add_milestone',
    'edit_milestone',
    'retire_milestone',
    'split_milestone',
    'merge_milestones',
    'reorder_milestones',
    'set_structure',
    'edit_completion',
    'add_statement',
    'remove_statement',
    'edit_text',
    'add_case',
    'rename_case',
    'add_not_found',
    'remove_not_found',
]
REVISE_SCHEMA = obj(
    {
        'need_answers': {
            'anyOf': [
                {'type': 'null', 'description': 'null when goal.need is not changed.'},
                NEED_ANSWERS,
            ]
        },
        'operations': array(
            obj(
                {
                    'op': {'type': 'string', 'enum': OPERATIONS},
                    'reason': TEXT,
                    'id': MAYBE,
                    'ids': array(TEXT),
                    'after': MAYBE,
                    'milestone': {'anyOf': [{'type': 'null'}, MILESTONE]},
                    'into': array(MILESTONE),
                    'fields': {'anyOf': [{'type': 'null'}, FIELDS]},
                    'order': array(TEXT),
                    'structure': {
                        'type': ['string', 'null'],
                        'enum': ['sequence', 'parallel', None],
                    },
                    'statement': {
                        'anyOf': [
                            {'type': 'null'},
                            obj(
                                {
                                    'body': TEXT,
                                    'year': TEXT,
                                    'quote': TEXT,
                                    'context': MAYBE,
                                    'ref': REF,
                                }
                            ),
                        ]
                    },
                    'index': MAYBE_REF,
                    'field': {
                        'type': ['string', 'null'],
                        'enum': ['title', 'definition', 'goal.need', None],
                    },
                    'value': MAYBE,
                    'rename_from': MAYBE,
                    'rename_to': MAYBE,
                }
            )
        ),
        'new_references': array(
            obj(
                {
                    'id': REF,
                    'kind': KIND,
                    'url': TEXT,
                    'doi': MAYBE,
                    'title': TEXT,
                    'authors': TEXT,
                    'container': MAYBE,
                    'year': TEXT,
                }
            )
        ),
    }
)

REVISE_PROMPT = """\
You are revising one entry of the Technology Atlas, a public reference that maps breakthroughs
worth working towards. For each breakthrough an entry states what it is, who has set it as a
goal, the test by which it will count as achieved, the milestones on the way, and the published
results that bear on each. Its readers hold doctorates and check details. Some are experts in
this entry's field and the rest are experts in another field. Every statement must be exact and
sourced.

The entry below is the current version. It is improved over time and is never rewritten from
the start. You do not return the entry. You return a list of operations, each a single change
with a one-sentence reason, and the Atlas applies them. An empty list is a valid answer.

How to revise
- Keep what is sound. Propose a change only when a source supports it, and say plainly in
  reason what the change fixes: an error, a gap, a missing stage, a threshold with no source,
  an unclear sentence.
- Prefer editing or adding a milestone to retiring one. Retire a milestone only when it is
  wrong or no longer marks progress; split one that joins two separate results; merge two that
  test the same result. Results stay attached to milestone ids, so a milestone that is edited
  keeps its id and its results are judged again against the new wording.
- Thresholds are set by someone other than the Atlas: a regulator, a standards body, a society
  or committee, a government programme, a prize, a registered protocol, or a convention the
  field demonstrably applies. Every new or changed threshold needs threshold_quote, one passage
  copied exactly from that body's own document that states it, and threshold_ref, its
  reference. Use set_by_kind "atlas" only when no outside body has defined the test, and say so
  in set_by.
- Milestones together should run from the first demonstration in the laboratory to the result
  just before completion. A milestone title is one sentence of at most 110 characters that
  states what has to be achieved, with its object and threshold. A criterion is the exact test,
  with numbers and conditions, at most 700 characters, and contains no results.
- Use web search. Open every page you cite, and cite only pages you opened in this session. A
  reference already in the entry is cited by its number. A new source goes in new_references,
  numbered from {next_ref} on in order of first citation, with kind, url, doi (or null), title,
  and authors, container and year as printed; cite it by that number.
- Quotations are exact, character for character, at most 320 characters. No citation marks
  such as [1] inside any text. No praise, no forecasts, and nothing about how the entry was
  produced. Plain declarative sentences.

{note}

When you write or change goal.need (otherwise need_answers is null):
{need_guide}
Operations. Every operation has op and reason; fill only the fields its op uses and set the
others to null or an empty list.
- add_milestone: milestone (title, criterion, set_by, set_by_kind, threshold_quote,
  threshold_ref, refs) and after, the id it follows in display order (null to put it first).
- edit_milestone: id, and fields with the values that change (null leaves a field as it is).
- retire_milestone: id.
- split_milestone: id, and into, the milestones that replace it, in display order.
- merge_milestones: ids, and milestone, the one that replaces them.
- reorder_milestones: order, every active milestone id in the new display order.
- set_structure: structure, "sequence" if each milestone normally follows the one before,
  "parallel" if they are separate parts of the problem that can be reached in any order.
- edit_completion: fields with the values that change (basis may change too).
- add_statement: statement (body, year, quote, context, ref). remove_statement: index, from 0.
- edit_text: field ("title", "definition" or "goal.need") and value.
- add_case: value, a case name of at most 4 words. rename_case: rename_from and rename_to.
- add_not_found: value, one short sentence. remove_not_found: index, from 0.
Milestone ids are permanent: never reuse one, and refer to milestones only by id.

Current entry {id}, version {version}:

{entry}
"""


def show_current(page):
    """The current entry as the revise prompt shows it."""
    lines = [f'Title: {page["title"]}', f'Definition: {page["definition"]}']
    lines.append(f'Why it is a goal: {page["goal"]["need"]} (refs {page["goal"]["need_refs"]})')
    for n, s in enumerate(page['goal']['statements']):
        lines.append(f'Statement {n}: {s["body"]}, {s["year"]}: "{s["quote"]}" (ref {s["ref"]})')
    c = page['completion']
    lines.append(
        f'\nCompletion test: {c["title"]}\n  Criterion: {c["criterion"]}\n  Set by: {c["set_by"]}'
        f' ({c["set_by_kind"]}); threshold quote: {json.dumps(c["threshold_quote"])} '
        f'(ref {c["threshold_ref"]}); refs {c["refs"]}\n  Basis: {c["basis"]}'
    )
    lines.append(f'\nMilestone structure: {page["milestone_structure"]}')
    lines.append(
        f'Cases ({page["case_label"]}): ' + ('; '.join(page['cases']) if page['cases'] else 'none')
    )
    tally = {}
    for r in page['results']:
        key = (r['milestone'], r['case'])
        word = r['verdict'] if r['confirmed'] else 'claimed'
        tally.setdefault(key, []).append(word)
    lines.append('\nActive milestones, in display order:')
    for m in active(page):
        lines.append(
            f'{m["id"]}: {m["title"]}\n  Criterion: {m["criterion"]}\n  Set by: {m["set_by"]} '
            f'({m["set_by_kind"]}); threshold quote: {json.dumps(m["threshold_quote"])} '
            f'(ref {m["threshold_ref"]}); refs {m["refs"]}'
        )
    retired = [m for m in page['milestones'] if m['status'] == 'retired']
    if retired:
        lines.append('\nRetired milestones (ids not to be reused):')
        lines += [f'{m["id"]}: {m["title"]} (replaced by {m["replaced_by"]})' for m in retired]
    lines.append('\nResults so far (milestone, case: verdicts; claimed = not confirmed):')
    for (unit, case), words in sorted(tally.items(), key=lambda kv: str(kv[0])):
        lines.append(f'- {unit}' + (f', {case}' if case else '') + ': ' + ', '.join(words))
    if not tally:
        lines.append('(none)')
    lines.append('\nSearched for and not found:')
    lines += [f'{n}. {text}' for n, text in enumerate(page['not_found'])] or ['(none)']
    lines.append('\nReferences:')
    lines += [f'{r["id"]}. {r["title"]} {r["url"]}' for r in page['references']]
    return '\n'.join(lines)


def revise(identifier, note=None, call=None, writer=None):
    """Ask for proposed operations and store them; applies nothing. Returns (line, path)."""
    page = load(identifier)
    text = REVISE_PROMPT.format(
        need_guide=NEED_GUIDE,
        id=identifier,
        version=page['version'],
        next_ref=len(page['references']) + 1,
        note=f"The owner's note on this entry:\n{note}" if note else 'The owner left no note.',
        entry=show_current(page),
    )
    calls = folder(identifier, 'revise')
    writer = writer or ENTRY
    run = call or model_call(REVISE_SCHEMA, writer, calls / 'call')
    proposal = run(text)
    proposal.setdefault('need_answers', None)
    check_answers(proposal['need_answers'], page['references'] + proposal['new_references'])
    calls.mkdir(parents=True, exist_ok=True)
    stored = {
        'id': identifier,
        'version': page['version'],
        'note': note,
        'model': writer['model'],
        'effort': writer.get('effort'),
        'proposed_on': today(),
        **proposal,
    }
    path = calls / 'proposal.json'
    path.write_text(json.dumps(stored, indent=2, ensure_ascii=False) + '\n')
    return show_proposal(stored), path


def describe_op(op):
    kind = op['op']
    if kind == 'add_milestone':
        m = op['milestone'] or {}
        return f'add milestone after {op["after"]}: "{m.get("title")}"'
    if kind == 'edit_milestone':
        changed = {k: v for k, v in (op['fields'] or {}).items() if v is not None}
        return f'edit {op["id"]}: ' + '; '.join(
            f'{k} = {json.dumps(v)}' for k, v in changed.items()
        )
    if kind == 'retire_milestone':
        return f'retire {op["id"]}'
    if kind == 'split_milestone':
        return f'split {op["id"]} into ' + ' | '.join(f'"{m["title"]}"' for m in op['into'])
    if kind == 'merge_milestones':
        return f'merge {op["ids"]} into "{(op["milestone"] or {}).get("title")}"'
    if kind == 'reorder_milestones':
        return f'reorder to {op["order"]}'
    if kind == 'set_structure':
        return f'structure = {op["structure"]}'
    if kind == 'edit_completion':
        changed = {k: v for k, v in (op['fields'] or {}).items() if v is not None}
        return 'edit completion: ' + '; '.join(f'{k} = {json.dumps(v)}' for k, v in changed.items())
    if kind == 'add_statement':
        s = op['statement'] or {}
        return f'add statement by {s.get("body")}, {s.get("year")}: "{s.get("quote")}"'
    if kind == 'remove_statement':
        return f'remove statement {op["index"]}'
    if kind == 'edit_text':
        return f'{op["field"]} = {json.dumps(op["value"])}'
    if kind == 'add_case':
        return f'add case "{op["value"]}"'
    if kind == 'rename_case':
        return f'rename case "{op["rename_from"]}" to "{op["rename_to"]}"'
    if kind == 'add_not_found':
        return f'add not found: "{op["value"]}"'
    return f'remove not found {op["index"]}'


def show_proposal(stored):
    lines = [f'{stored["id"]}: proposal on version {stored["version"]}']
    for n, op in enumerate(stored['operations'], 1):
        lines.append(f'{n}. {describe_op(op)}\n   Reason: {op["reason"]}')
    for r in stored['new_references']:
        lines.append(f'   New reference {r["id"]}: {r["title"]} ({r["url"]})')
    marks = {True: 'quote found', False: 'QUOTE NOT FOUND', None: 'no quote checked'}
    for key, item in (stored.get('need_answers') or {}).items():
        if item['answer'] is None:
            lines.append(f'   {key}: not found')
        else:
            where = f'ref {item["ref"]}, {marks[item.get("checked")]}'
            lines.append(f'   {key}: {item["answer"]} ({where})')
    if not stored['operations']:
        lines.append('(no operations proposed)')
    return '\n'.join(lines)


def latest_proposal(identifier):
    found = sorted(CALLS.glob(f'{identifier}-revise-*/proposal.json'))
    if not found:
        raise ValueError(f'{identifier}: no stored proposal; run revise first')
    return found[-1]


class Invalid(Exception):
    pass


def apply(identifier, path=None):
    """Apply a stored proposal's operations to the entry, each validated on its own."""
    path = Path(path) if path else latest_proposal(identifier)
    stored = json.loads(Path(path).read_text())
    page = load(identifier)
    actor = stored.get('model', ENTRY['model'])
    log = []
    if stored['version'] != page['version']:
        log.append(
            row(
                'atlas.page',
                f'The proposal was made on version {stored["version"]}; the entry is at version '
                f'{page["version"]}. Each operation is checked against the current entry.',
            )
        )
    # New references: an existing one with the same address or DOI is reused.
    numbers = {}
    first_new = len(page['references']) + 1
    for reference in stored['new_references']:
        numbers[reference['id']] = refer(
            page['references'],
            reference['url'],
            reference['title'],
            reference['kind'],
            reference['doi'],
            reference['doi'] or '',
        )
        made = page['references'][numbers[reference['id']] - 1]
        if made['id'] >= first_new:
            made.update(
                authors=reference['authors'],
                container=reference['container'],
                year=reference['year'],
            )
    citations = cite_all(page['references'][first_new - 1 :])
    applied = 0
    rejudge = []
    for n, op in enumerate(stored['operations'], 1):
        trial = copy.deepcopy(page)
        try:
            changed = operate(trial, op, numbers)
        except (Invalid, KeyError, TypeError, ValueError, IndexError) as error:
            log.append(
                row(
                    'atlas.page',
                    f'Skipped proposed operation {n} ({describe_op(op)}): {error}. '
                    f'Its reason: {op["reason"]}',
                )
            )
            continue
        page.clear()
        page.update(trial)
        applied += 1
        rejudge += changed
        log.append(row(actor, f'{describe_op(op)}. Reason: {op["reason"]}'))
    if applied:
        page['version'] += 1
    if rejudge:
        page.pop('results_run', None)
    unused = [
        r['id'] for r in page['references'][first_new - 1 :] if r['id'] not in cited_refs(page)
    ]
    if unused:
        # A new reference that only a skipped operation cited is dropped again.
        page['references'] = [r for r in page['references'] if r['id'] not in unused]
        compact(page)
    merged = merge_duplicates(page)
    quotes = check_definition(page, only_new=True)
    log.append(
        row(
            'atlas.page',
            f'Applied {applied} of {len(stored["operations"])} proposed '
            f'operations from {Path(path).parent.name}; now version {page["version"]}.',
        )
    )
    if rejudge:
        log.append(
            row(
                'atlas.page',
                'Criteria new or changed, to be judged by the next results run: '
                + ', '.join(dict.fromkeys(rejudge))
                + '.',
            )
        )
    log += [cited_row(citations), checked_row(quotes, 'new or changed quotations')]
    if merged:
        log.append(merged_row(merged))
    left = validate({**page, 'log': page['log']})
    if left:
        log.append(row('atlas.page', 'Structural problems after applying: ' + '; '.join(left)))
    page['log'] += log + length_rows(over_length(page))
    save(page)
    return (
        f'{identifier}: applied {applied} of {len(stored["operations"])} operations; version '
        f'{page["version"]}; to re-judge: {", ".join(dict.fromkeys(rejudge)) or "none"}; '
        f'problems: {"; ".join(left) or "none"}'
    )


def next_id(page):
    return f'm{max(int(m["id"][1:]) for m in page["milestones"]) + 1}'


def new_milestone(page, spec, numbers):
    milestone = {
        'id': next_id(page),
        'title': spec['title'],
        'criterion': spec['criterion'],
        'set_by': spec['set_by'],
        'set_by_kind': spec['set_by_kind'],
        'threshold_quote': spec['threshold_quote'],
        'threshold_ref': renumber(spec['threshold_ref'], numbers),
        'refs': [renumber(n, numbers) for n in spec['refs']],
        'status': 'active',
        'replaced_by': [],
    }
    check_refs(page, milestone['refs'] + [milestone['threshold_ref']])
    page['milestones'].append(milestone)
    return milestone['id']


def renumber(value, numbers):
    return numbers.get(value, value) if value is not None else None


def check_refs(page, refs):
    known = {r['id'] for r in page['references']}
    bad = [n for n in refs if n is not None and n not in known]
    if bad:
        raise Invalid(f'cites references that do not exist: {bad}')


def live_milestone(page, identifier):
    for milestone in page['milestones']:
        if milestone['id'] == identifier:
            if milestone['status'] != 'active':
                raise Invalid(f'{identifier} is retired')
            return milestone
    raise Invalid(f'no milestone {identifier}')


def edit_fields(target, fields, numbers, page, allowed):
    changed = {k: v for k, v in (fields or {}).items() if v is not None}
    if not changed:
        raise Invalid('no field to change')
    for key in changed:
        if key not in allowed:
            raise Invalid(f'{key} cannot be changed here')
    if 'set_by_kind' in changed and changed['set_by_kind'] not in SET_BY:
        raise Invalid('unknown set_by_kind')
    if 'threshold_ref' in changed:
        changed['threshold_ref'] = renumber(changed['threshold_ref'], numbers)
    if 'refs' in changed:
        changed['refs'] = [renumber(n, numbers) for n in changed['refs']]
    check_refs(page, changed.get('refs', []) + [changed.get('threshold_ref')])
    target.update(changed)
    if 'threshold_quote' in changed or 'threshold_ref' in changed:
        target.pop('threshold_checked', None)
    return 'criterion' in changed


def retire(page, identifier, replaced_by):
    milestone = live_milestone(page, identifier)
    milestone['status'] = 'retired'
    milestone['replaced_by'] = replaced_by
    page['milestone_order'].remove(identifier)


def operate(page, op, numbers):
    """Apply one operation to page in place; returns the milestone ids to re-judge."""
    kind = op['op']
    order = page['milestone_order']
    if kind == 'add_milestone':
        if not op['milestone']:
            raise Invalid('no milestone given')
        if op['after'] is not None and op['after'] not in order:
            raise Invalid(f'after names {op["after"]}, which is not an active milestone')
        new = new_milestone(page, op['milestone'], numbers)
        order.insert(order.index(op['after']) + 1 if op['after'] else 0, new)
        return [new]
    if kind == 'edit_milestone':
        milestone = live_milestone(page, op['id'])
        allowed = {'title', 'criterion', 'set_by', 'set_by_kind', 'threshold_quote'}
        allowed |= {'threshold_ref', 'refs'}
        return [op['id']] if edit_fields(milestone, op['fields'], numbers, page, allowed) else []
    if kind == 'retire_milestone':
        retire(page, op['id'], [])
        if not order:
            raise Invalid('it would leave no active milestone')
        return []
    if kind == 'split_milestone':
        if len(op['into']) < 2:
            raise Invalid('a split needs at least two milestones')
        at = order.index(live_milestone(page, op['id'])['id'])
        new = [new_milestone(page, spec, numbers) for spec in op['into']]
        retire(page, op['id'], new)
        order[at:at] = new
        return new
    if kind == 'merge_milestones':
        if len(set(op['ids'])) < 2 or not op['milestone']:
            raise Invalid('a merge needs two or more ids and the milestone that replaces them')
        for identifier in op['ids']:
            live_milestone(page, identifier)
        at = min(order.index(i) for i in op['ids'])
        new = new_milestone(page, op['milestone'], numbers)
        for identifier in op['ids']:
            retire(page, identifier, [new])
        order.insert(min(at, len(order)), new)
        return [new]
    if kind == 'reorder_milestones':
        if sorted(op['order']) != sorted(order) or len(set(op['order'])) != len(order):
            raise Invalid(f'order must list every active milestone once: {order}')
        order[:] = op['order']
        return []
    if kind == 'set_structure':
        if op['structure'] not in ('sequence', 'parallel'):
            raise Invalid('structure must be sequence or parallel')
        page['milestone_structure'] = op['structure']
        return []
    if kind == 'edit_completion':
        allowed = {'title', 'criterion', 'set_by', 'set_by_kind', 'threshold_quote'}
        allowed |= {'threshold_ref', 'refs', 'basis'}
        changed = edit_fields(page['completion'], op['fields'], numbers, page, allowed)
        return ['completion'] if changed else []
    if kind == 'add_statement':
        statement = dict(op['statement'] or {})
        if not statement:
            raise Invalid('no statement given')
        if len(page['goal']['statements']) >= 5:
            raise Invalid('the entry already has 5 statements')
        statement['ref'] = renumber(statement['ref'], numbers)
        check_refs(page, [statement['ref']])
        page['goal']['statements'].append(statement)
        return []
    if kind == 'remove_statement':
        if len(page['goal']['statements']) <= 2:
            raise Invalid('the entry needs at least 2 statements')
        page['goal']['statements'].pop(op['index'])
        return []
    if kind == 'edit_text':
        if not op['value']:
            raise Invalid('no value given')
        if op['field'] == 'goal.need':
            page['goal']['need'] = op['value']
        elif op['field'] in ('title', 'definition'):
            page[op['field']] = op['value']
        else:
            raise Invalid(f'{op["field"]} cannot be edited as text')
        return []
    if kind == 'add_case':
        if not op['value'] or op['value'] in page['cases']:
            raise Invalid('the case is empty or already listed')
        if not page['case_label']:
            raise Invalid('the entry has no case_label; cases cannot start here')
        page['cases'].append(op['value'])
        return []
    if kind == 'rename_case':
        old, new = op['rename_from'], op['rename_to']
        if old not in page['cases'] or not new or new in page['cases']:
            raise Invalid('rename_from must be a case and rename_to a new name')
        page['cases'][page['cases'].index(old)] = new
        for result in page['results']:
            if result['case'] == old:
                result['case'] = new
        return []
    if kind == 'add_not_found':
        if not op['value']:
            raise Invalid('no text given')
        page['not_found'].append(op['value'])
        return []
    if kind == 'remove_not_found':
        page['not_found'].pop(op['index'])
        return []
    raise Invalid(f'unknown operation {kind}')


# check and migrate.


def check_entries(identifiers=None):
    """Validate the stored page of each named breakthrough, or of every record that has one."""
    if identifiers:
        paths = [record_file(identifier) for identifier in identifiers]
    else:
        paths = sorted(Path(CORE).glob('*/*.json'))
    lines = []
    for path in paths:
        if path.name == 'field.json':
            continue
        try:
            page = json.loads(path.read_text(encoding='utf-8')).get('page')
            if page is None:
                if identifiers:
                    lines.append(f'{path.stem}: has no page')
                continue
            found = validate(page)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            found = [f'cannot be read: {type(error).__name__}: {error}']
        lines.append(f'{path.stem}: ' + ('ok' if not found else '; '.join(found)))
    return lines or ['no pages stored']


def migrate(page, held_urls=()):
    """Bring a round-2 entry to the improvable shape without changing anything it holds:
    milestone status and replaced_by, milestone_order, version 1, and the judged list (a held
    source was judged against every unit; any other source against the unit of its rows)."""
    page = copy.deepcopy(page)
    for milestone in page['milestones']:
        milestone.setdefault('status', 'active')
        milestone.setdefault('replaced_by', [])
    page.setdefault('milestone_order', [m['id'] for m in page['milestones']])
    page.setdefault('version', 1)
    if 'judged' not in page:
        digest = hashes(page)
        urls = {r['id']: r['url'] for r in page['references']}
        pairs = {}
        for url in held_urls:
            for unit in digest:
                pairs[(url, unit)] = None
        for result in page['results']:
            pairs[(urls[result['ref']], result['milestone'])] = result.get('judged_by')
        page['judged'] = [
            {
                'url': url,
                'milestone': unit,
                'hash': digest[unit],
                'date': page['accessed'],
                'by': by or judge_entry(config())['model'],
            }
            for (url, unit), by in pairs.items()
        ]
    return page


def migrate_files(identifiers, drafts=None):
    """One-off: bring each pilot entry to the improvable shape and store it in its record. A
    pilot file in the drafts folder is read when present, otherwise the record's own page."""
    lines = []
    for identifier in identifiers:
        draft = Path(drafts or DRAFTS) / f'{identifier}.json'
        old = json.loads(draft.read_text()) if draft.exists() else load(identifier)
        _, held = held_sources(identifier)
        page = migrate(old, [s['url'] for s in held])
        notes = []
        if page != old:
            notes.append(
                'Migrated to the improvable shape: milestone status, milestone_order, version 1 '
                f'and a judged list of {len(page["judged"])} pairs from the stored results.'
            )
        merged = merge_duplicates(page)
        page['log'] += [row('atlas.page', note) for note in notes]
        if merged:
            page['log'].append(merged_row(merged))
        if draft.exists():
            page['log'].append(row('atlas.page', 'Moved into the record file as its page key.'))
        writer = next((r['actor'] for r in page['log'] if r['actor'] != 'atlas.page'), None)
        write_record(identifier, page, writer)
        lines.append(f'{identifier}: stored; ' + '; '.join(validate(page) or ['check ok']))
    return lines


# Batch runs over many breakthroughs.

EXHAUSTED = 75
COMMIT_EVERY = 25
GIVE_UP = 3  # --missing skips an entry that has failed this many times in a row
TRAILER = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
FAILURES = 'failures.json'
WORKERS = 'workers.json'  # the worker count `--workers auto` settled on


LOCKS = 'locks'


@contextmanager
def claimed(step, identifier, folder=None):
    """Claim one entry for one pass across processes, so two runs (the unattended loop and a
    field run started by hand) never work on it at once. Yields False when a live process
    holds it. A claim left by a process that has died is taken over."""
    folder = Path(folder or CALLS / LOCKS)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{step}-{identifier}.lock'
    for _ in range(2):
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                os.kill(int(path.read_text() or 0), 0)
            except PermissionError:
                pass  # alive, owned by another user
            except (ValueError, OSError):
                path.unlink(missing_ok=True)  # its process is gone
                continue
            yield False
            return
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        try:
            yield True
        finally:
            path.unlink(missing_ok=True)
        return
    yield False


def worker_count(text):
    """--workers: a number, or `auto` to find the most the provider allows (atlas.batch)."""
    if text == 'auto':
        return text
    value = int(text)
    if value < 1:
        raise ValueError(text)
    return value


def select(step, data, missing=False, every=False, fields=(), limit=None, failures=None):
    """Active breakthroughs in ID order: for define, those with no page (--missing) or all; for
    results, those with a page whose results pass has not completed (--missing) or all with a
    page. --missing leaves out an entry that has failed GIVE_UP times. Returns (chosen,
    given up)."""
    chosen = []
    given_up = []
    for identifier, item in sorted(data['breakthroughs'].items()):
        if item.get('status') != 'active' or (fields and item.get('field') not in fields):
            continue
        page = item.get('page')
        if step == 'define':
            wanted = every or (missing and page is None)
        else:
            wanted = page is not None and (every or (missing and not page.get('results_run')))
        if not wanted:
            continue
        if missing and (failures or {}).get(f'{step}:{identifier}', 0) >= GIVE_UP:
            given_up.append(identifier)
            continue
        chosen.append(identifier)
    return (chosen[:limit] if limit else chosen), given_up


def run_batch(step, identifiers, writer, workers=3, commit=True, replace=False, rejudge=False):
    """Run define or results over identifiers through one Writer: each finished entry is
    written to its record under the lock, atlas/core is committed every COMMIT_EVERY entries
    and at the end, and the database is rebuilt once. Returns the exit code: 0, 1 when an
    entry failed, EXHAUSTED when a provider reported exhaustion."""
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    runs = CALLS / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    log_path = runs / f'{stamp}-{step}.log'
    failures_path = CALLS / FAILURES
    failures = json.loads(failures_path.read_text()) if failures_path.exists() else {}
    lock = threading.Lock()
    verb = 'Write page' if step == 'define' else 'Judge results'

    def message(done):
        return (
            f'{verb} for {len(done)} breakthroughs ({done[0]} to {done[-1]})\n\n'
            f'Model: {writer["model"]} ({writer.get("effort")}); '
            f'judge: {judge_entry(config(), writer["model"])["model"]}\n'
            f'Calls: {CALLS.relative_to(ROOT) if CALLS.is_relative_to(ROOT) else CALLS}\n\n'
            f'{TRAILER}'
        )

    commits = batches.Writer(COMMIT_EVERY, commit, message, CORE)
    stats = {}

    def work(identifier, stop):
        with claimed(step, identifier) as mine:
            if not mine:
                # Another run is on this entry now: not started here, not a failure; it stays
                # to do, and a later pass takes it if the other run does not finish it.
                raise batches.Stopped('another run is working on it')
            return work_on(identifier, stop)

    def work_on(identifier, stop):
        info = {}

        def keep(page):
            model = writer['model'] if step == 'define' else None
            commits.write(identifier, lambda: write_record(identifier, page, model))

        if step == 'define':
            line = define(
                identifier, replace=replace, writer=writer, store=keep, stop=stop, stats=info
            )
            if 'page' not in info:
                raise RuntimeError(line)
        else:
            line = results(identifier, everything=rejudge, writer=writer, store=keep, stop=stop)
        stats[identifier] = info
        return line

    def report(identifier, outcome):
        status, value = outcome
        text = {
            'done': value,
            'failed': f'{identifier}: failed: {value}',
            'stopped': f'{identifier}: not started ({value or "stopping"})',
        }[status]
        print(text, flush=True)
        with lock:
            with log_path.open('a') as handle:
                handle.write(f'{datetime.now(timezone.utc).isoformat()} {text}\n')
            key = f'{step}:{identifier}'
            if status == 'done':
                failures.pop(key, None)
            elif status == 'failed' and 'stopping the run' not in str(value):
                failures[key] = failures.get(key, 0) + 1
            failures_path.write_text(json.dumps(failures, indent=1, sort_keys=True) + '\n')

    if workers == 'auto':

        def note(text):
            print(text, flush=True)
            with lock, log_path.open('a') as handle:
                handle.write(f'{datetime.now(timezone.utc).isoformat()} {text}\n')

        workers = batches.Adaptive(path=CALLS / WORKERS, log=note)
    outcomes, exhausted = batches.run(identifiers, work, workers, report)
    done = [i for i, (status, _) in outcomes.items() if status == 'done']
    failed = sum(1 for status, _ in outcomes.values() if status == 'failed')
    stopped = sum(1 for status, _ in outcomes.values() if status == 'stopped')
    if done:
        store.rebuild(core=CORE, path=DB)
    commits.flush()
    summary = f'Done: {len(done)} written, {failed} failed, {stopped} not started'
    if step == 'define':
        attempts = [stats[i].get('attempts', 1) for i in done]
        units_ = [
            unit
            for i in done
            for unit in [stats[i]['page']['completion']] + stats[i]['page']['milestones']
        ]
        confirmed = sum(1 for unit in units_ if unit.get('threshold_checked'))
        share = f'{100 * confirmed / len(units_):.0f}%' if units_ else 'n/a'
        summary += (
            f'; {sum(attempts)} attempts ({sum(1 for a in attempts if a > 1)} needed the retry)'
            f'; thresholds confirmed {confirmed} of {len(units_)} ({share})'
        )
    if exhausted:
        summary += '. Stopped: a provider reported exhaustion.'
    print(summary, flush=True)
    with log_path.open('a') as handle:
        handle.write(f'{datetime.now(timezone.utc).isoformat()} {summary}\n')
    if exhausted:
        return EXHAUSTED
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Breakthrough pages as data (pilot).')
    steps = parser.add_subparsers(dest='step', required=True)

    def writer_options(sub):
        sub.add_argument(
            '--model',
            help=f'writer model (default {ENTRY["model"]}); provider/name runs through OpenRouter',
        )
        sub.add_argument('--effort', help=f'writer effort (default {ENTRY["effort"]})')
        sub.add_argument('--judge', help='judge model for this run (default: the config)')

    def batch_options(sub):
        sub.add_argument('ids', nargs='*', metavar='ID')
        sub.add_argument('--missing', action='store_true', help='only entries not yet done')
        sub.add_argument('--all', action='store_true', help='every active breakthrough')
        sub.add_argument('--field', action='append', default=[], help='only this field')
        sub.add_argument('--limit', type=int, help='at most this many entries')
        sub.add_argument(
            '--workers',
            type=worker_count,
            default=3,
            help='parallel calls, or auto: rise until throttled, then settle 20%% below',
        )
        sub.add_argument('--no-commit', action='store_true')
        writer_options(sub)

    one = steps.add_parser('define', help='write the base definition')
    batch_options(one)
    one.add_argument('--replace', action='store_true', help='discard an existing entry')
    one.add_argument('--out', help='write JSON files to this folder; records are not touched')
    two = steps.add_parser('results', help='judge what has not been judged')
    batch_options(two)
    two.add_argument('--rejudge', action='store_true', help='re-judge every source')
    three = steps.add_parser('add', help='judge named sources against every milestone')
    three.add_argument('id')
    three.add_argument('urls', nargs='+')
    four = steps.add_parser('revise', help='propose changes; --apply applies a proposal')
    four.add_argument('id')
    four.add_argument('--note')
    four.add_argument('--apply', nargs='?', const='latest', default=None, metavar='PATH')
    writer_options(four)
    five = steps.add_parser('check', help='validate stored pages')
    five.add_argument('ids', nargs='*')
    six = steps.add_parser('migrate', help='one-off: move the pilot entries into their records')
    six.add_argument('ids', nargs='+')
    seven = steps.add_parser(
        'merge', help='judge a merged breakthrough’s sources into the page it merges into'
    )
    seven.add_argument('ids', nargs='*', metavar='ID', help='breakthroughs marked merge')
    seven.add_argument('--pending', action='store_true', help='every merge not yet carried over')
    seven.add_argument('--no-commit', action='store_true')
    eight = steps.add_parser(
        'recover', help='judge sources skipped earlier as unreadable, via open-access copies'
    )
    eight.add_argument('ids', nargs='*', metavar='ID')
    eight.add_argument('--all', action='store_true', help='every breakthrough with a page')
    eight.add_argument('--workers', type=int, default=4)
    eight.add_argument('--judge', help='judge model for this run (default: the config)')
    eight.add_argument('--no-commit', action='store_true')
    nine = steps.add_parser('dates', help='date each met completion test (search call each)')
    nine.add_argument('ids', nargs='*', metavar='ID')
    nine.add_argument('--missing', action='store_true', help='complete pages with no date yet')
    nine.add_argument('--all', action='store_true', help='every complete page, again')
    nine.add_argument('--workers', type=int, default=4)
    nine.add_argument('--no-commit', action='store_true')
    writer_options(nine)
    args = parser.parse_args(argv)
    if args.step == 'dates':
        writer = writer_entry(args.model, args.effort)
        data = records.load(CORE)
        identifiers = args.ids or [
            identifier
            for identifier, item in sorted(data['breakthroughs'].items())
            if item.get('status') == 'active'
            and item.get('page')
            and completion_results(item['page'])
            and (args.all or (args.missing and not item['page'].get('completed')))
        ]
        if not identifiers:
            print('Nothing to date.')
            return 0

        def work(identifier, stop):
            with claimed('results', identifier) as mine:
                if not mine:
                    raise batches.Stopped('another run is working on it')
                return date_completion(identifier, writer=writer)

        def report(identifier, outcome):
            status, value = outcome
            print(value if status == 'done' else f'{identifier}: {status}: {value}', flush=True)

        outcomes, exhausted = batches.run(identifiers, work, args.workers, report)
        failed = sum(1 for status, _ in outcomes.values() if status == 'failed')
        problems_ = records.check(records.load(CORE))
        if problems_:
            print('atlas/core check failed:\n' + '\n'.join(problems_))
            return 1
        if not args.no_commit:
            records.commit(f'Date completion for {len(identifiers)} breakthroughs\n\n{TRAILER}')
        return EXHAUSTED if exhausted else (1 if failed else 0)
    if args.step == 'recover':
        if args.judge:
            JUDGE['model'] = args.judge
        data = records.load(CORE)
        identifiers = args.ids or [
            identifier
            for identifier, item in sorted(data['breakthroughs'].items())
            if args.all and item.get('status') == 'active' and item.get('page')
        ]
        if not identifiers:
            parser.error('name breakthroughs, or pass --all')

        def work(identifier, stop):
            with claimed('results', identifier) as mine:
                if not mine:
                    raise batches.Stopped('another run is working on it')
                return recover(identifier)

        def report(identifier, outcome):
            status, value = outcome
            print(value if status == 'done' else f'{identifier}: {status}: {value}', flush=True)

        outcomes, exhausted = batches.run(identifiers, work, args.workers, report)
        failed = sum(1 for status, _ in outcomes.values() if status == 'failed')
        problems_ = records.check(records.load(CORE))
        if problems_:
            print('atlas/core check failed:\n' + '\n'.join(problems_))
            return 1
        if not args.no_commit:
            records.commit(
                f'Recover sources skipped as unreadable for {len(identifiers)} breakthroughs\n\n'
                f'Judge: {judge_entry(config())["model"]}\n\n{TRAILER}'
            )
        print(f'Done: {len(identifiers)} breakthroughs, {failed} failed', flush=True)
        return EXHAUSTED if exhausted else (1 if failed else 0)
    if args.step == 'merge':
        identifiers = args.ids or (pending_merges(records.load(CORE)) if args.pending else [])
        if not identifiers:
            print('Nothing to merge.')
            return 0
        done, failed = [], 0
        for identifier in identifiers:
            try:
                print(merge(identifier), flush=True)
                done.append(identifier)
            except batches.Stopped as error:
                print(f'{identifier}: not merged now ({error})', flush=True)
            except Exception as error:  # noqa: BLE001 - one merge must not stop the rest
                print(f'{identifier}: failed: {type(error).__name__}: {error}', flush=True)
                failed += 1
        if done:
            problems_ = records.check(records.load(CORE))
            if problems_:
                print('atlas/core check failed:\n' + '\n'.join(problems_))
                return 1
            if not args.no_commit:
                records.commit(
                    f'Merge evidence of {len(done)} duplicates into the pages they merge into\n\n'
                    f'{", ".join(done)}\n\n{TRAILER}'
                )
        return 1 if failed else 0
    writer = writer_entry(getattr(args, 'model', None), getattr(args, 'effort', None))
    if getattr(args, 'judge', None):
        JUDGE['model'] = args.judge
    if args.step in ('define', 'results'):
        if args.step == 'define' and args.out:
            # A comparison run: files in --out, nothing written to the records.
            def work(identifier):
                return define(identifier, replace=args.replace, writer=writer, out=args.out)

            fixed = 3 if args.workers == 'auto' else args.workers
            with ThreadPoolExecutor(fixed) as pool:
                for line in pool.map(lambda identifier: safely(work, identifier), args.ids):
                    print(line, flush=True)
            return 0
        data = records.load(CORE)
        unknown = [i for i in args.ids if i not in data['breakthroughs']]
        if unknown:
            parser.error('unknown breakthrough: ' + ', '.join(unknown))
        identifiers = list(dict.fromkeys(args.ids))
        if args.missing or args.all:
            failures_path = CALLS / FAILURES
            failures = json.loads(failures_path.read_text()) if failures_path.exists() else {}
            chosen, given_up = select(
                args.step, data, args.missing, args.all, args.field, None, failures
            )
            identifiers = [i for i in identifiers if i in chosen] if identifiers else chosen
            if given_up:
                print(f'Left out after {GIVE_UP} failures: {", ".join(given_up)}', flush=True)
        elif not identifiers:
            parser.error('name breakthroughs, or pass --missing or --all')
        if args.limit:
            identifiers = identifiers[: args.limit]
        if not identifiers:
            print(f'Nothing to do: no breakthroughs need {args.step}.', flush=True)
            return 0
        print(
            f'{args.step}: {len(identifiers)} breakthroughs with {writer["model"]} '
            f'({writer["effort"]})',
            flush=True,
        )
        return run_batch(
            args.step,
            identifiers,
            writer,
            args.workers,
            not args.no_commit,
            getattr(args, 'replace', False),
            getattr(args, 'rejudge', False),
        )
    if args.step == 'add':
        print(safely(lambda identifier: add(identifier, args.urls), args.id))
    elif args.step == 'revise':
        if args.apply:
            target = None if args.apply == 'latest' else args.apply
            print(safely(lambda identifier: apply(identifier, target), args.id))
        else:
            line, path = revise(args.id, args.note, writer=writer)
            print(line)
            print(f'Stored at {path}. Nothing applied; run with --apply to apply it.')
    elif args.step == 'check':
        lines = check_entries(args.ids)
        print('\n'.join(lines))
        return 0 if all(line.endswith(': ok') for line in lines) else 1
    else:
        print('\n'.join(migrate_files(args.ids)))
    return 0


def safely(work, identifier):
    try:
        return work(identifier)
    except Exception as error:
        return f'{identifier}: failed: {type(error).__name__}: {error}'


if __name__ == '__main__':
    raise SystemExit(main())

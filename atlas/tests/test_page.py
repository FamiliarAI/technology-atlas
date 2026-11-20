"""The page passes (atlas.page define, results, add, revise, check, migrate), with stubbed model
calls and network."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ingestion.providers import ProviderExhausted

from atlas import core, page as pages
from atlas.store import breakthrough_data, connect, rebuild

PAGE_TEXT = (
    'The committee sets the bar: survival of 60% of recipients for six months. '
    'We report that four of six recipients survived for six months after transplantation. '
) + ' Methods follow.' * 100
THRESHOLD = 'survival of 60% of recipients for six months'
FOUND = 'four of six recipients survived for six months after transplantation'


def unit(identifier, quote=THRESHOLD, ref=2):
    return {
        'id': identifier,
        'title': f'Milestone {identifier} is reached',
        'criterion': 'Survival of 60% of recipients for six months.',
        'set_by': 'A society',
        'set_by_kind': 'professional_society',
        'threshold_quote': quote,
        'threshold_ref': ref,
        'refs': [2],
    }


def definition():
    completion = unit('x', quote=None, ref=None)
    del completion['id']
    completion['set_by_kind'] = 'atlas'
    completion['basis'] = 'No outside test was found.'
    return {
        'title': 'Pig organ transplantation',
        'definition': 'Pig organs replace failing human organs.',
        'goal': {
            'need': 'Many people wait for organs.',
            'need_refs': [1],
            'figures': None,
            'statements': [
                {
                    'body': 'A society',
                    'year': '2025',
                    'quote': 'The committee sets the bar',
                    'context': None,
                    'ref': 2,
                },
                {
                    'body': 'An agency',
                    'year': '2024',
                    'quote': 'a sentence the page never contains',
                    'context': None,
                    'ref': 1,
                },
            ],
        },
        'completion': completion,
        'case_label': 'Organ',
        'cases': ['Kidney', 'Heart'],
        'milestone_structure': 'sequence',
        'milestones': [
            unit('m1'),
            unit('m2', quote='a threshold the page never states'),
            unit('m3', quote=None, ref=None),
        ],
        'measures': [],
        'not_found': [],
        'references': [
            {
                'id': 1,
                'kind': 'web',
                'url': 'https://agency.example/stats',
                'doi': None,
                'title': 'Statistics',
                'authors': 'An Agency',
                'container': 'agency.example',
                'year': '2026',
            },
            {
                'id': 2,
                'kind': 'journal',
                'url': 'https://journal.example/paper',
                'doi': '10.1000/xyz',
                'title': 'Criteria',
                'authors': 'Someone A',
                'container': 'J Ex',
                'year': '2020',
            },
        ],
    }


CROSSREF = {
    'message': {
        'author': [{'family': f'Family{n}', 'given': 'Anne B.'} for n in range(8)],
        'short-container-title': ['J Ex Med'],
        'issued': {'date-parts': [[2021, 3]]},
        'volume': '12',
        'issue': '3',
        'page': '100-110',
        'DOI': '10.1000/xyz',
    }
}
PUBMED = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation><Article>
<Journal><JournalIssue><Volume>7</Volume><Issue>2</Issue><PubDate><Year>2019</Year></PubDate>
</JournalIssue><ISOAbbreviation>Nat Med</ISOAbbreviation></Journal>
<Pagination><MedlinePgn>45-50</MedlinePgn></Pagination>
<AuthorList><Author><LastName>Riella</LastName><Initials>LV</Initials></Author>
<Author><CollectiveName>Xeno Group</CollectiveName></Author></AuthorList>
</Article></MedlineCitation><PubmedData><ArticleIdList>
<ArticleId IdType="doi">10.1/pm</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""
ARXIV = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<published>2024-05-01T00:00:00Z</published>
<author><name>Ada M. Lovelace</name></author><author><name>Alan Turing</name></author>
</entry></feed>"""


def network(url):
    if 'api.crossref.org' in url:
        return json.dumps(CROSSREF).encode()
    if 'efetch' in url:
        return PUBMED
    if 'export.arxiv.org' in url:
        return ARXIV
    raise OSError('offline')


def held_row(milestone='m1', case='Kidney', verdict='met', confirmed=True, quote=FOUND):
    return {
        'milestone': milestone,
        'case': case,
        'verdict': verdict,
        'finding': 'Six pig kidneys; four recipients alive at six months.',
        'detail': None,
        'quote': quote,
        'confirmed': confirmed,
        'peer_reviewed': confirmed,
    }


def new_spec(title, criterion='A new criterion.'):
    return {
        'title': title,
        'criterion': criterion,
        'set_by': 'A society',
        'set_by_kind': 'professional_society',
        'threshold_quote': THRESHOLD,
        'threshold_ref': 2,
        'refs': [2],
    }


def op(kind, reason='It fixes a gap.', **fields):
    base = {
        'op': kind,
        'reason': reason,
        'id': None,
        'ids': [],
        'after': None,
        'milestone': None,
        'into': [],
        'fields': None,
        'order': [],
        'structure': None,
        'statement': None,
        'index': None,
        'field': None,
        'value': None,
        'rename_from': None,
        'rename_to': None,
    }
    return {**base, **fields}


def fields(**changes):
    keys = ['title', 'criterion', 'set_by', 'set_by_kind', 'threshold_quote', 'threshold_ref']
    return {**{k: None for k in keys + ['basis', 'refs']}, **changes}


class PageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.core = root / 'core'
        (self.core / 'BME').mkdir(parents=True)
        self.record_path = self.core / 'BME' / 'BME-99.json'
        self.calls = root / 'calls'
        self.texts = {
            'https://journal.example/paper': PAGE_TEXT,
            'https://agency.example/stats': PAGE_TEXT,
            'https://held.example/a': PAGE_TEXT,
            'https://new.example/good': PAGE_TEXT,
            'https://new.example/also': PAGE_TEXT,
            'https://added.example/x': PAGE_TEXT,
        }

        def read(url, title='', capture=True):
            return self.texts.get(url)

        self.held = [
            {
                'url': 'https://held.example/a',
                'title': 'Held paper',
                'text': PAGE_TEXT,
                'quotes': [{'milestone': 'm1', 'verdict': 'advances', 'quote': FOUND}],
            },
            {'url': 'https://held.example/empty', 'title': 'Unreadable', 'text': '', 'quotes': []},
        ]
        record = {
            'id': 'BME-99',
            'field': 'BME',
            'title': 'Draft title',
            'status': 'active',
            'models': {'research': 'grok'},
            'brief': {},
        }
        self.record_path.write_text(pages.dump_record(record))
        self.record_text = self.record_path.read_text()
        settings = {
            'format': {'model': 'gpt-6.1-terra', 'effort': 'high'},
            'stages': {'format': [{'provider': 'codex', 'model': 'gpt-6.1-terra'}]},
        }
        for target, value in [
            ('CORE', self.core),
            ('CALLS', self.calls),
            ('read', read),
            ('fetch', network),
            ('held_sources', lambda identifier: (record, self.held)),
            ('describe', lambda record: 'Record text.'),
            ('config', lambda: settings),
        ]:
            patcher = patch.object(pages, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def stored(self):
        return json.loads(self.record_path.read_text())['page']

    def write(self, page):
        pages.write_record('BME-99', page)

    def define(self, answer=None, **options):
        prompts = []

        def call(text):
            prompts.append(text)
            return copy.deepcopy(answer or definition())

        line = pages.define('BME-99', call=call, **options)
        return line, prompts

    def run_results(self, rows=None, candidates=None, single=None, everything=False):
        prompts = {'held': [], 'find': [], 'one': []}

        def judge(text):
            if 'which milestones of an entry' in text:
                prompts['held'].append(text)
                return {'kind': 'journal', 'doi': None, 'rows': copy.deepcopy(rows or [])}
            prompts['one'].append(text)
            return copy.deepcopy(single(text))

        def search(text):
            prompts['find'].append(text)
            return {'candidates': copy.deepcopy(candidates or [])}

        line = pages.results('BME-99', search=search, judge=judge, everything=everything)
        return line, prompts

    def propose(self, operations, new_references=(), need_answers=None):
        def call(text):
            self.revise_prompt = text
            return {
                'operations': operations,
                'new_references': list(new_references),
                'need_answers': need_answers,
            }

        line, path = pages.revise('BME-99', note='Add the missing stage.', call=call)
        return line, path

    # define

    def test_define_writes_the_base_and_refuses_to_overwrite_it(self):
        line, prompts = self.define()
        self.assertIn('BME-99: Pig organ transplantation', line)
        self.assertIn('already been read and checked by the Atlas', prompts[0])
        self.assertIn(f'Judged passage (advances, draft milestone m1): "{FOUND}"', prompts[0])
        self.assertIn('in at most 4 words', prompts[0])
        page = self.stored()
        self.assertEqual(page['results'], [])
        self.assertEqual(page['version'], 1)
        self.assertEqual(page['milestone_order'], ['m1', 'm2', 'm3'])
        self.assertEqual({m['status'] for m in page['milestones']}, {'active'})
        self.assertEqual(pages.validate(page), [])
        page['results'] = [{'milestone': 'm1'}]
        self.write(page)
        line, prompts = self.define()
        self.assertIn('already has a definition (version 1); nothing written', line)
        self.assertEqual(prompts, [])
        self.assertEqual(self.stored()['results'], [{'milestone': 'm1'}])
        line, _ = self.define(replace=True)
        page = self.stored()
        self.assertEqual(page['results'], [])
        self.assertIn('Replaced version 1', page['log'][0]['action'])

    def test_define_takes_a_writer_model_and_an_output_folder(self):
        other = Path(self.tmp.name) / 'comparison'
        writer = pages.writer_entry('gpt-6.1-luna', 'medium')
        self.assertEqual(writer['effort'], 'medium')
        self.assertTrue(writer['search'])
        self.define(writer=writer, out=other)
        page = json.loads((other / 'BME-99.json').read_text())
        self.assertEqual(page['log'][0]['actor'], 'gpt-6.1-luna')
        self.assertNotIn('page', json.loads(self.record_path.read_text()))

    def test_missing_quote_and_over_length_text_do_not_reject(self):
        answer = definition()
        answer['definition'] = 'D' * 900
        line, _ = self.define(answer)
        self.assertNotIn('rejected', line)
        page = self.stored()
        self.assertEqual(page['definition'], 'D' * 900)
        statements = page['goal']['statements']
        self.assertTrue(statements[0]['checked'])
        self.assertFalse(statements[1]['checked'])
        milestones = page['milestones']
        self.assertTrue(milestones[0]['threshold_checked'])
        self.assertFalse(milestones[1]['threshold_checked'])
        self.assertIsNone(milestones[2]['threshold_checked'])
        actions = ' '.join(row['action'] for row in page['log'])
        self.assertIn('definition is 900 characters, over its limit of 420; kept', actions)
        self.assertIn('2 found, 2 not found, 0 with no readable copy', actions)

    def test_structural_faults_still_reject(self):
        answer = definition()
        answer['milestones'][0]['refs'] = [9]
        line, prompts = self.define(answer)
        self.assertIn('rejected after 2 attempts', line)
        self.assertIn('citations with no reference: [9]', prompts[1])
        self.assertNotIn('page', json.loads(self.record_path.read_text()))

    # references

    def test_citations_come_from_registries(self):
        references = [
            {'url': 'https://x.example/a', 'doi': '10.1000/xyz', 'authors': 'M', 'year': '1'},
            {'url': 'https://pubmed.ncbi.nlm.nih.gov/123/', 'doi': None, 'authors': 'M'},
            {'url': 'https://arxiv.org/abs/2405.00001v2', 'doi': None, 'authors': 'M'},
            {'url': 'https://agency.example/', 'doi': None, 'authors': 'An Agency', 'year': '2'},
            {'url': 'https://doi.org/10.48550/arXiv.2405.00001', 'doi': None, 'authors': ''},
        ]
        counts = pages.cite_all(references)
        self.assertEqual(counts, {'crossref': 1, 'pubmed': 1, 'arxiv': 2, 'model': 1})
        crossref, pubmed, arxiv, model, by_doi = references
        self.assertEqual(
            crossref['authors'],
            'Family0 AB, Family1 AB, Family2 AB, Family3 AB, Family4 AB, Family5 AB, et al.',
        )
        self.assertEqual(
            (crossref['container'], crossref['year'], crossref['volume'], crossref['pages']),
            ('J Ex Med', '2021', '12', '100-110'),
        )
        self.assertEqual(pubmed['authors'], 'Riella LV, Xeno Group')
        self.assertEqual((pubmed['container'], pubmed['doi']), ('Nat Med', '10.1/pm'))
        self.assertEqual(arxiv['authors'], 'Lovelace AM, Turing A')
        self.assertEqual(
            (model['authors'], model['year'], model['volume']), ('An Agency', '2', None)
        )
        self.assertEqual(model['citation_source'], 'model')
        self.assertEqual(by_doi['citation_source'], 'arxiv')

    def test_references_with_the_same_doi_are_merged_and_citations_follow(self):
        self.define()
        page = self.stored()
        page['references'].append({**page['references'][1], 'id': 3, 'url': 'https://pmc.example/'})
        page['results'] = [{**held_row(), 'ref': 3, 'checked': True}]
        page['goal']['need_refs'] = [1, 3]
        merged = pages.merge_duplicates(page)
        self.assertEqual(merged, [(2, 3)])
        self.assertEqual([r['id'] for r in page['references']], [1, 2])
        self.assertEqual(page['results'][0]['ref'], 2)
        self.assertEqual(page['goal']['need_refs'], [1, 2])
        self.assertEqual(pages.validate(page), [])

    # results

    def candidates(self):
        found = [
            {'url': 'https://held.example/a', 'title': 'Held', 'milestone': 'm2', 'case': 'Heart'},
            {'url': 'https://new.example/good', 'title': 'New', 'milestone': 'm2', 'case': 'Heart'},
            {
                'url': 'https://new.example/also',
                'title': 'Also',
                'milestone': 'm3',
                'case': 'Heart',
            },
            {
                'url': 'https://new.example/none',
                'title': 'Gone',
                'milestone': 'm3',
                'case': 'Heart',
            },
            {'url': 'https://new.example/odd', 'title': 'Odd', 'milestone': 'm9', 'case': 'Heart'},
        ]
        return [{**c, 'why': 'A result.'} for c in found]

    @staticmethod
    def single(text):
        relevant = 'Source: New' in text
        return {
            'verdict': 'partial' if relevant else 'not_relevant',
            'finding': 'A preprint claims two heart recipients.' if relevant else '',
            'detail': None,
            'quote': 'a passage the judge invented' if relevant else None,
            'confirmed': False,
            'peer_reviewed': False,
            'kind': 'preprint',
            'doi': None,
        }

    def test_results_judge_held_first_then_the_gaps_and_never_change_the_definition(self):
        self.define()
        before = self.stored()
        rows = [held_row(), held_row('completion', verdict='partial', quote=None)]
        line, prompts = self.run_results(rows, self.candidates(), self.single)
        page = self.stored()
        for key in pages.DEFINITION:
            self.assertEqual(page[key], before[key])
        self.assertEqual(page['references'][:2], before['references'])
        self.assertEqual(len(prompts['held']), 1)
        self.assertIn('m3 (Milestone m3)', prompts['held'][0])
        self.assertIn('- m1, Kidney', prompts['find'][0])
        self.assertIn('- https://held.example/a', prompts['find'][0])
        self.assertEqual(len(prompts['one']), 2)
        results = page['results']
        self.assertEqual(
            [(r['milestone'], r['verdict']) for r in results], [('m1', 'met'), ('m2', 'partial')]
        )
        held, claimed = results
        self.assertTrue(held['checked'])
        self.assertEqual(held['judged_by'], 'gpt-6.1-terra')
        self.assertFalse(claimed['confirmed'])
        self.assertFalse(claimed['checked'])
        actions = ' '.join(row['action'] for row in page['log'])
        self.assertIn(
            '5 candidates returned, 1 dropped as sources already used, 3 to judge', actions
        )
        self.assertIn('1 from sources already used, 1 from newly found sources', actions)
        self.assertIn('1 partial on completion', actions)
        self.assertIn('1 not relevant', actions)
        self.assertEqual(pages.validate(page), [])
        # judged: the held source against all four units, and two new candidates.
        self.assertEqual(len(page['judged']), 6)

    def test_results_is_incremental_and_rejudges_only_a_changed_criterion(self):
        self.define()
        rows = [held_row()]
        self.run_results(rows, self.candidates(), self.single)
        first = self.stored()
        self.assertEqual(len(first['results']), 2)
        # Sources found by search were judged on one milestone only; the next run judges them
        # on the others, and the run after that has nothing left to judge.
        line, prompts = self.run_results([], self.candidates(), self.single)
        self.assertEqual(len(prompts['held']), 2)
        self.assertNotIn('m2 (Milestone m2)', prompts['held'][0])
        self.assertEqual(prompts['one'], [])
        self.assertEqual(self.stored()['results'], first['results'])
        line, prompts = self.run_results(rows, self.candidates(), self.single)
        self.assertEqual(prompts['held'], [])
        self.assertEqual(prompts['one'], [])
        self.assertEqual(self.stored()['results'], first['results'])
        self.assertIn(
            '5 candidates returned, 3 dropped as sources already used, 1 to judge',
            ' '.join(row['action'] for row in self.stored()['log']),
        )
        # A changed criterion is judged again for every source the entry uses, and only it.
        page = self.stored()
        page['milestones'][0]['criterion'] = 'Survival of 70% of recipients for a year.'
        self.write(page)
        line, prompts = self.run_results([held_row(verdict='partial')], [], self.single)
        self.assertEqual(len(prompts['held']), 3)
        for text in prompts['held']:
            self.assertIn('m1 (Milestone m1)', text)
            self.assertNotIn('m2 (Milestone m2)', text)
        results = self.stored()['results']
        # The stub answers every source with one m1 row; the earlier m1 'met' row is replaced
        # and the m2 row, on a milestone that did not change, is kept as it was.
        self.assertEqual(
            {(r['milestone'], r['verdict']) for r in results},
            {('m1', 'partial'), ('m2', 'partial')},
        )
        self.assertIn([r for r in first['results'] if r['milestone'] == 'm2'][0], results)
        self.assertIn('replaced 1', line)
        # --all re-judges everything.
        _, prompts = self.run_results([held_row()], [], self.single, everything=True)
        self.assertIn('m2 (Milestone m2)', prompts['held'][0])

    def test_add_judges_named_sources_against_every_active_milestone_without_search(self):
        self.define()
        prompts = []

        def judge(text):
            prompts.append(text)
            return {'kind': 'journal', 'doi': '10.1000/xyz', 'rows': [held_row('m3', 'Heart')]}

        line = pages.add('BME-99', ['https://added.example/x', 'https://nowhere.example/'], judge)
        self.assertEqual(len(prompts), 1)
        for unit in ('m1', 'm2', 'm3', 'completion'):
            self.assertIn(f'{unit} (', prompts[0])
        page = self.stored()
        self.assertEqual(page['results'][0]['milestone'], 'm3')
        # The DOI matches an existing reference, so no new reference is made.
        self.assertEqual(page['results'][0]['ref'], 2)
        self.assertEqual(len(page['references']), 2)
        self.assertIn('1 no readable saved copy', line)
        self.assertEqual(
            len([j for j in page['judged'] if j['url'].startswith('https://added')]), 4
        )

    def test_merge_judges_the_duplicates_sources_against_the_kept_page(self):
        self.define()
        duplicate = {
            'id': 'BME-98',
            'field': 'BME',
            'title': 'A duplicate',
            'status': 'active',
            'review': {'state': 'merge', 'into': 'BME-99', 'note': 'same', 'log': []},
            'page': {
                'references': [
                    {'id': 1, 'url': 'https://added.example/x', 'title': 'Added paper'},
                    {'id': 2, 'url': 'https://journal.example/paper', 'title': 'Cited already'},
                ],
                'results': [{'ref': 1, 'milestone': 'm1'}, {'ref': 2, 'milestone': 'm2'}],
            },
        }
        (self.core / 'BME' / 'BME-98.json').write_text(pages.dump_record(duplicate))
        prompts = []

        def judge(text):
            prompts.append(text)
            return {'kind': 'journal', 'doi': None, 'rows': [held_row('m3', 'Heart')]}

        self.assertEqual(pages.pending_merges(core.load(self.core)), ['BME-98'])
        line = pages.merge('BME-98', judge, core=self.core)
        self.assertIn('BME-98 -> BME-99: judged 1 of 1 sources', line)
        # Only the source the kept page does not cite yet is judged, against its own milestones.
        self.assertEqual(len(prompts), 1)
        self.assertIn('m3 (', prompts[0])
        page = self.stored()
        urls = {r['id']: r['url'] for r in page['references']}
        self.assertIn('https://added.example/x', [urls[r['ref']] for r in page['results']])
        self.assertTrue(any('Merged from BME-98' in r['action'] for r in page['log']))
        merged = core.load(self.core)['breakthroughs']['BME-98']['review']
        self.assertTrue(merged['copied'])
        self.assertEqual(pages.pending_merges(core.load(self.core)), [])

    def test_recover_takes_only_candidates_never_cited_nor_judged(self):
        self.define()
        page = self.stored()
        page['judged'] = [{'url': 'https://dropped.example/x', 'milestone': 'm1', 'hash': 'h'}]
        self.write(page)
        run = self.calls / 'BME-99-results-20261115T000000Z' / 'find'
        run.mkdir(parents=True)
        candidates = [
            {'url': 'https://added.example/x', 'title': 'Readable now'},
            {'url': 'https://dropped.example/x', 'title': 'Judged, dropped'},
            {'url': page['references'][0]['url'], 'title': 'Already cited'},
        ]
        (run / 'response.json').write_text(json.dumps({'candidates': candidates}))
        self.assertEqual(
            pages.recoverable('BME-99', self.stored()), {'https://added.example/x': 'Readable now'}
        )
        prompts = []

        def judge(text):
            prompts.append(text)
            return {'kind': 'journal', 'doi': None, 'rows': [held_row('m3', 'Heart')]}

        line = pages.recover('BME-99', judge)
        self.assertEqual(len(prompts), 1)
        self.assertIn('judged 1 of 1 sources', line)
        self.assertTrue(any('Recovery:' in r['action'] for r in self.stored()['log']))
        self.assertEqual(pages.recover('BME-99', judge), 'BME-99: nothing to recover')

    # revise

    def test_revise_stores_a_proposal_and_applies_nothing(self):
        self.define()
        before = self.stored()
        line, path = self.propose([op('retire_milestone', id='m2')])
        self.assertIn('1. retire m2', line)
        self.assertIn("The owner's note on this entry:\nAdd the missing stage.", self.revise_prompt)
        self.assertIn('m3: Milestone m3 is reached', self.revise_prompt)
        self.assertEqual(self.stored(), before)
        self.assertTrue(path.is_file())
        self.assertEqual(pages.latest_proposal('BME-99'), path)

    def test_revise_shows_the_answers_behind_a_new_goal_and_checks_their_quotes(self):
        self.define()
        empty = {'answer': None, 'ref': None, 'quote': None}
        answers = {key: dict(empty) for key in pages.NEED_QUESTIONS}
        answers['held_back'] = {'answer': 'Recipients wait.', 'ref': 2, 'quote': FOUND}
        answers['how_much'] = {'answer': 'Many wait.', 'ref': 2, 'quote': 'nowhere in it at all'}
        operations = [op('edit_text', field='goal.need', value='Why it matters.')]
        line, path = self.propose(operations, need_answers=answers)
        self.assertIn('movable metal type', self.revise_prompt)
        self.assertIn('held_back: Recipients wait. (ref 2, quote found)', line)
        self.assertIn('how_much: Many wait. (ref 2, QUOTE NOT FOUND)', line)
        self.assertIn('why_this: not found', line)
        stored = json.loads(path.read_text())['need_answers']
        self.assertEqual(
            [stored['held_back']['checked'], stored['how_much']['checked']], [True, False]
        )
        schema = pages.REVISE_SCHEMA['properties']['need_answers']['anyOf'][1]
        self.assertEqual(list(schema['properties']), list(pages.NEED_QUESTIONS))
        self.assertIn('Who or what is held back', schema['properties']['held_back']['description'])

    def test_apply_runs_every_operation_and_keeps_ids_permanent(self):
        self.define()
        page = self.stored()
        page['results'] = [{**held_row('m2', 'Heart'), 'ref': 2, 'checked': True}]
        self.write(page)
        new_ref = {
            'id': 3,
            'kind': 'journal',
            'url': 'https://new.example/good',
            'doi': None,
            'title': 'A new paper',
            'authors': 'Doe J',
            'container': 'J New',
            'year': '2026',
        }
        statement = {'body': 'A body', 'year': '2026', 'quote': FOUND, 'context': None, 'ref': 3}
        operations = [
            op('add_milestone', milestone=new_spec('Brain-dead recipient stage', 'x'), after='m1'),
            op('edit_milestone', id='m1', fields=fields(criterion='Survival of 70%.')),
            op('retire_milestone', id='m3'),
            op('split_milestone', id='m2', into=[new_spec('Part one'), new_spec('Part two')]),
            op('add_milestone', milestone=new_spec('Late stage'), after=None),
            op('merge_milestones', ids=['m6', 'm7'], milestone=new_spec('Both parts')),
            op('reorder_milestones', order=['m1', 'm4', 'm8', 'm5']),
            op('set_structure', structure='parallel'),
            op('edit_completion', fields=fields(basis='A better basis.')),
            op('add_statement', statement=statement),
            op('remove_statement', index=0),
            op('edit_text', field='definition', value='A sharper definition.'),
            op('add_case', value='Liver'),
            op('rename_case', rename_from='Heart', rename_to='Cardiac'),
            op('add_not_found', value='No registry record was found.'),
            op('remove_not_found', index=0),
            op('retire_milestone', id='m3', reason='Already retired, so invalid.'),
            op('edit_milestone', id='m1', fields=fields(refs=[99])),
        ]
        self.propose(operations, [new_ref])
        line = pages.apply('BME-99')
        self.assertIn('applied 16 of 18 operations; version 2', line)
        page = self.stored()
        self.assertEqual(page['version'], 2)
        by_id = {m['id']: m for m in page['milestones']}
        self.assertEqual(sorted(by_id), ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8'])
        self.assertEqual(by_id['m4']['title'], 'Brain-dead recipient stage')
        self.assertEqual(by_id['m2']['status'], 'retired')
        self.assertEqual(by_id['m2']['replaced_by'], ['m5', 'm6'])
        self.assertEqual((by_id['m3']['status'], by_id['m3']['replaced_by']), ('retired', []))
        self.assertEqual(by_id['m6']['replaced_by'], ['m8'])
        self.assertEqual(by_id['m7']['replaced_by'], ['m8'])
        self.assertEqual(page['milestone_order'], ['m1', 'm4', 'm8', 'm5'])
        self.assertEqual(by_id['m1']['criterion'], 'Survival of 70%.')
        self.assertEqual(page['milestone_structure'], 'parallel')
        self.assertEqual(page['completion']['basis'], 'A better basis.')
        self.assertEqual(page['definition'], 'A sharper definition.')
        self.assertEqual(page['cases'], ['Kidney', 'Cardiac', 'Liver'])
        self.assertEqual(page['results'][0]['case'], 'Cardiac')
        self.assertEqual(page['results'][0]['milestone'], 'm2')
        self.assertEqual(page['not_found'], [])
        self.assertEqual(page['goal']['statements'][-1]['ref'], 3)
        self.assertTrue(page['goal']['statements'][-1]['checked'])
        self.assertEqual(page['references'][2]['authors'], 'Doe J')
        actions = [row['action'] for row in page['log']]
        self.assertTrue(any(a.startswith('Skipped proposed operation 17') for a in actions))
        self.assertTrue(any('do not exist: [99]' in a for a in actions))
        self.assertTrue(any('Reason: It fixes a gap.' in a for a in actions))
        self.assertTrue(any(a.startswith('Criteria new or changed') and 'm1' in a for a in actions))
        self.assertEqual(pages.validate(page), [])
        # A further milestone takes the next unused number, never a retired one.
        self.propose([op('add_milestone', milestone=new_spec('Another'), after='m5')])
        pages.apply('BME-99')
        page = self.stored()
        self.assertEqual(page['milestone_order'][-1], 'm9')
        self.assertEqual(page['version'], 3)

    def test_an_edited_criterion_is_judged_again_by_the_next_results_run(self):
        self.define()
        self.run_results([held_row()], [], self.single)
        self.propose([op('edit_milestone', id='m3', fields=fields(criterion='Changed.'))])
        pages.apply('BME-99')
        _, prompts = self.run_results([], [], self.single)
        self.assertEqual(len(prompts['held']), 1)
        self.assertIn('m3 (Milestone m3)', prompts['held'][0])
        self.assertNotIn('m1 (Milestone m1)', prompts['held'][0])
        self.assertEqual(self.stored()['results'][0]['milestone'], 'm1')

    # check and migrate

    def test_check_catches_a_broken_hand_edit(self):
        self.define()
        self.assertEqual(pages.check_entries(['BME-99']), ['BME-99: ok'])
        page = self.stored()
        page['milestone_order'] = ['m1', 'm2']
        page['results'] = [{**held_row('m7'), 'ref': 2}]
        page['milestones'][0]['id'] = 'm2'
        self.write(page)
        (line,) = pages.check_entries(['BME-99'])
        self.assertIn('milestone ids repeat', line)
        self.assertIn('milestone_order', line)
        self.assertIn("unknown milestone 'm7'", line)

    def test_migration_adds_the_new_fields_and_loses_nothing(self):
        self.define()
        old = self.stored()
        for key in ('milestone_order', 'version', 'judged'):
            del old[key]
        for milestone in old['milestones']:
            del milestone['status'], milestone['replaced_by']
        old['results'] = [
            {**held_row('m2', 'Heart'), 'ref': 1, 'checked': True, 'judged_by': 'gpt-6.1-terra'}
        ]
        new = pages.migrate(old, ['https://journal.example/paper'])
        self.assertEqual(new['version'], 1)
        self.assertEqual(new['milestone_order'], ['m1', 'm2', 'm3'])
        self.assertEqual(len(new['judged']), 5)
        stripped = copy.deepcopy(new)
        for key in ('milestone_order', 'version', 'judged'):
            del stripped[key]
        for milestone in stripped['milestones']:
            del milestone['status'], milestone['replaced_by']
        self.assertEqual(stripped, old)
        self.assertEqual(pages.validate(new), [])
        self.assertEqual(pages.migrate(new), new)

    def test_a_shortened_case_name_resolves_to_its_one_listed_case(self):
        cases = ['Inertial confinement: targets are compressed.', 'Magnetic confinement: fields.']
        self.assertEqual(pages.resolve_case('Inertial confinement', cases), cases[0])
        self.assertEqual(pages.resolve_case(cases[1], cases), cases[1])
        self.assertEqual(pages.resolve_case('confinement', cases), '')
        self.assertEqual(pages.resolve_case(None, cases), '')
        self.assertIsNone(pages.resolve_case(None, []))

    def test_judge_is_not_the_definition_writer(self):
        settings = {
            'format': {'model': 'gpt-6.1-sol'},
            'stages': {
                'format': [
                    {'provider': 'codex', 'model': 'gpt-6.1-sol'},
                    {'provider': 'claude', 'model': 'opus'},
                ]
            },
        }
        self.assertEqual(pages.judge_entry(settings)['model'], 'opus')
        settings['format']['model'] = 'gpt-6.1-terra'
        self.assertEqual(
            pages.judge_entry(settings), {'provider': 'codex', 'model': 'gpt-6.1-terra'}
        )


def built_page(identifier):
    """A valid stored page, without a model call."""
    page = definition()
    page.update(id=identifier, results=[], accessed='2026-11-14', log=[])
    return pages.migrate(page)


def research_record(identifier):
    item = {
        'id': identifier,
        'title': f'Breakthrough {identifier}',
        'change_log': [],
        'unresolved_issues': [],
        'provenance': {},
        'sources': [],
    }
    for section in ['concept', 'significance', 'missing_breakthrough', 'current_state']:
        item[section] = [{'text': 'Text ' * 40, 'source_urls': []}]
    item['completion_criteria'] = [{'text': 'A criterion.', 'source_urls': []}]
    item['related_concepts'] = [{'text': 'Related.', 'source_urls': []}]
    return item


class PageRecordTests(unittest.TestCase):
    """The page stored in atlas/core, the site data, and batch runs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.core = root / 'core'
        self.db = root / 'atlas.sqlite3'
        self.runs = root / 'runs'
        folder = self.runs / 'QUA'
        (folder / 'sources').mkdir(parents=True)
        value = {
            'field': {'prefix': 'QUA', 'field': 'Quantum', 'boundaries': 'Quantum.'},
            'created_at': '2026-11-01T00:00:00+00:00',
            'innovations': [research_record(f'QUA-0{n}') for n in (1, 2, 3)],
        }
        (folder / 'final-innovations.json').write_text(json.dumps(value))
        core.import_field(folder, self.core)
        self.ids = ['QUA-01', 'QUA-02', 'QUA-03']
        settings = {'format': {'model': 'gpt-6.1-terra', 'effort': 'high'}, 'stages': {}}
        self.rebuilds = []
        for target, value in [
            ('CORE', self.core),
            ('DB', self.db),
            ('CALLS', root / 'calls'),
            ('config', lambda: settings),
        ]:
            patcher = patch.object(pages, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(pages.store, 'rebuild', lambda **kw: self.rebuilds.append(kw))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, identifier):
        return self.core / 'QUA' / f'{identifier}.json'

    def test_the_page_is_added_to_the_record_and_no_other_byte_changes(self):
        before = self.path('QUA-01').read_text()
        pages.write_record('QUA-01', built_page('QUA-01'), 'gpt-6.1-sol')
        item = json.loads(self.path('QUA-01').read_text())
        self.assertEqual(list(item)[-1], 'page')
        self.assertEqual(item['models']['page'], 'gpt-6.1-sol')
        del item['page']
        del item['models']['page']
        if not item['models']:
            del item['models']
        self.assertEqual(pages.dump_record(item), before)
        self.assertEqual(pages.load('QUA-01')['id'], 'QUA-01')
        # A second write replaces the page in place; it stays the last key.
        page = pages.load('QUA-01')
        page['version'] = 2
        pages.write_record('QUA-01', page)
        self.assertEqual(json.loads(self.path('QUA-01').read_text())['page']['version'], 2)

    def test_core_check_validates_a_stored_page(self):
        pages.write_record('QUA-01', built_page('QUA-01'), 'gpt-6.1-sol')
        self.assertEqual(core.check(core.load(self.core)), [])
        page = built_page('QUA-01')
        page['milestone_order'] = ['m1']
        pages.write_record('QUA-01', page)
        problems = core.check(core.load(self.core))
        self.assertTrue(any(p.startswith('Page: QUA-01: milestone_order') for p in problems))
        self.assertIn('QUA-01: milestone_order', pages.check_entries(['QUA-01'])[0])

    def test_the_site_data_carries_the_page_without_its_bookkeeping(self):
        pages.write_record('QUA-01', built_page('QUA-01'), 'gpt-6.1-sol')
        rebuild(self.core, self.db, roots=[self.runs])
        with connect(self.db) as db:
            data = breakthrough_data(db, 'QUA-01')
            other = breakthrough_data(db, 'QUA-02')
        self.assertEqual(data['page']['milestone_order'], ['m1', 'm2', 'm3'])
        self.assertNotIn('judged', data['page'])
        self.assertNotIn('page', other)

    def test_missing_selects_what_is_not_done_and_skips_repeated_failures(self):
        pages.write_record('QUA-01', built_page('QUA-01'))
        data = core.load(self.core)
        self.assertEqual(pages.select('define', data, missing=True)[0], ['QUA-02', 'QUA-03'])
        self.assertEqual(pages.select('results', data, missing=True)[0], ['QUA-01'])
        self.assertEqual(pages.select('define', data, every=True)[0], self.ids)
        self.assertEqual(
            pages.select('define', data, missing=True, failures={'define:QUA-02': 3}),
            (['QUA-03'], ['QUA-02']),
        )
        page = pages.load('QUA-01')
        page['results_run'] = '2026-11-14'
        pages.write_record('QUA-01', page)
        data = core.load(self.core)
        self.assertEqual(pages.select('results', data, missing=True)[0], [])
        self.assertEqual(pages.select('results', data, every=True)[0], ['QUA-01'])
        self.assertEqual(pages.select('define', data, missing=True, fields=['ZZZ'])[0], [])

    def run_define(self, args, exhausted=()):
        written = []

        def define(identifier, store=None, stats=None, stop=None, **_):
            if identifier in exhausted:
                raise ProviderExhausted('codex', 'usage exhausted')
            page = built_page(identifier)
            page['milestones'][0]['threshold_checked'] = True
            stats.update(attempts=1, page=page)
            store(page)
            written.append(identifier)
            return f'{identifier}: written'

        messages = []
        output = io.StringIO()
        with (
            patch.object(pages, 'define', define),
            patch('atlas.core.commit', side_effect=messages.append),
            patch.object(pages, 'COMMIT_EVERY', 2),
            redirect_stdout(output),
        ):
            code = pages.main(['define', *args])
        return code, written, messages, output.getvalue()

    def test_a_batch_commits_in_groups_stops_on_exhaustion_and_resumes(self):
        code, written, messages, output = self.run_define(
            ['--missing', '--workers', '1'], exhausted={'QUA-03'}
        )
        self.assertEqual(code, pages.EXHAUSTED)
        self.assertEqual(written, ['QUA-01', 'QUA-02'])
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith('Write page for 2 breakthroughs (QUA-01 to QUA-02)'))
        self.assertTrue(messages[0].endswith(pages.TRAILER))
        self.assertIn('Stopped: a provider reported exhaustion', output)
        self.assertIn('thresholds confirmed 2 of 8', output)
        self.assertEqual(len(self.rebuilds), 1)
        self.assertEqual(core.check(core.load(self.core)), [])
        # Exhaustion does not count against the entry; a rerun picks up where it stopped.
        code, written, messages, output = self.run_define(['--missing', '--workers', '1'])
        self.assertEqual((code, written), (0, ['QUA-03']))
        self.assertEqual(len(messages), 1)
        code, written, _, output = self.run_define(['--missing'])
        self.assertEqual((code, written), (0, []))
        self.assertIn('Nothing to do', output)

    def test_a_failure_is_logged_and_the_run_continues(self):
        def define(identifier, store=None, stats=None, **_):
            if identifier == 'QUA-02':
                raise ValueError('broken answer')
            page = built_page(identifier)
            stats.update(attempts=2, page=page)
            store(page)
            return f'{identifier}: written'

        output = io.StringIO()
        with (
            patch.object(pages, 'define', define),
            patch('atlas.core.commit'),
            redirect_stdout(output),
        ):
            code = pages.main(['define', '--all', '--limit', '3', '--field', 'QUA'])
        self.assertEqual(code, 1)
        self.assertIn('QUA-02: failed: ValueError: broken answer', output.getvalue())
        self.assertIn('Done: 2 written, 1 failed, 0 not started', output.getvalue())
        failures = json.loads((pages.CALLS / pages.FAILURES).read_text())
        self.assertEqual(failures, {'define:QUA-02': 1})
        logs = list((pages.CALLS / 'runs').glob('*-define.log'))
        self.assertIn('broken answer', logs[0].read_text())


if __name__ == '__main__':
    unittest.main()


class ClaimTests(unittest.TestCase):
    def test_an_entry_claimed_by_a_live_process_is_skipped_and_a_dead_claim_is_taken(self):
        import os
        import subprocess
        import tempfile

        from atlas.page import claimed

        with tempfile.TemporaryDirectory() as folder:
            with claimed('results', 'BME-01', folder) as first:
                self.assertTrue(first)
                with claimed('results', 'BME-01', folder) as second:
                    self.assertFalse(second)
                with claimed('results', 'BME-02', folder) as other:
                    self.assertTrue(other)
            self.assertEqual(os.listdir(folder), [])
            # A claim whose process has exited is taken over.
            gone = subprocess.Popen(['true'])
            gone.wait()
            (Path(folder) / 'results-BME-03.lock').write_text(str(gone.pid))
            with claimed('results', 'BME-03', folder) as taken:
                self.assertTrue(taken)

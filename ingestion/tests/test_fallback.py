"""Fallback lists, exhaustion, timeouts, refusals and withheld concepts."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ingestion.field_workflow import (
    FRESH_RECONCILE,
    AccountExhausted,
    FieldWorkflow,
    SafetyReviewBlocked,
)
from ingestion.pipeline import fingerprint
from ingestion.providers import (
    Models,
    ProviderExhausted,
    ProviderState,
    ProviderTimeout,
    attempt_model,
    cache_model,
    stage_entries,
)
from ingestion.sources import write_json

GROK = {'provider': 'grok', 'model': 'grok-4.7', 'effort': 'high', 'timeout_s': 2400}
TERRA = {'provider': 'codex', 'model': 'gpt-6.1-terra', 'effort': 'high', 'search': True}
OPUS = {'provider': 'claude', 'model': 'opus'}
REFUSAL = {
    'type': 'turn.failed',
    'error': {
        'message': "Invalid prompt: we've limited access to this content for safety reasons."
    },
}


def refuse(folder):
    (folder / 'stdout.log').write_text(json.dumps(REFUSAL) + '\n')
    raise RuntimeError('Model CLI exited 1')


def fake_cli(stdout='', stderr='', code=0, response=None):
    def execute(cmd, directory, stdin=None, timeout=3600, cwd=None, check=True):
        execute.commands.append(cmd)
        (directory / 'stdout.log').write_text(stdout)
        (directory / 'stderr.log').write_text(stderr)
        if response is not None:
            Path(cmd[cmd.index('-o') + 1]).write_text(response)
        return code

    execute.commands = []
    return execute


class StageFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.flow = FieldWorkflow(self.root, config={})
        self.used = []

    def stage(self, behaviour, retries=0, entries=(GROK, TERRA, OPUS)):
        def call(folder, error, entry):
            self.used.append(entry['provider'])
            return behaviour(folder, entry)

        return self.flow.stage(
            'research', {'prompt': 'p'}, call, lambda v: None, retries, list(entries)
        )

    def test_exhaustion_moves_to_the_next_entry_and_cools_grok_down(self):
        def behaviour(folder, entry):
            if entry['provider'] == 'grok':
                raise ProviderExhausted('grok', 'Grok usage exhausted')
            return {'text': 'notes'}

        value, folder = self.stage(behaviour)
        self.assertEqual(value, {'text': 'notes'})
        self.assertEqual(self.used, ['grok', 'codex'])
        receipt = json.loads((folder / 'receipt.json').read_text())
        self.assertEqual((receipt['provider'], receipt['model']), ('codex', 'gpt-6.1-terra'))
        self.assertFalse(self.flow.state.available('grok'))
        self.assertTrue(self.flow.state.available('codex'))

    def test_timeout_moves_on_without_a_cooldown(self):
        def behaviour(folder, entry):
            if entry['provider'] == 'grok':
                raise ProviderTimeout('grok', 'timed out')
            return {'text': 'notes'}

        self.stage(behaviour)
        self.assertEqual(self.used, ['grok', 'codex'])
        self.assertTrue(self.flow.state.available('grok'))

    def test_other_failures_retry_the_same_model_and_never_fall_back(self):
        def behaviour(folder, entry):
            raise ValueError('invalid output')

        with self.assertRaisesRegex(ValueError, 'invalid output'):
            self.stage(behaviour, retries=1)
        self.assertEqual(self.used, ['grok', 'grok'])

    def test_a_refusal_is_terminal_for_every_model(self):
        with self.assertRaises(SafetyReviewBlocked):
            self.stage(lambda folder, entry: refuse(folder))
        self.assertEqual(self.used, ['grok'])
        with self.assertRaises(SafetyReviewBlocked):
            self.stage(lambda folder, entry: {'text': 'notes'})
        self.assertEqual(self.used, ['grok'])

    def test_every_cache_is_checked_before_any_call(self):
        def behaviour(folder, entry):
            if entry['provider'] == 'grok':
                raise ProviderExhausted('grok', 'Grok usage exhausted')
            return {'text': 'from codex'}

        self.stage(behaviour)
        resumed = FieldWorkflow(self.root, config={})
        self.used = []

        def call(folder, error, entry):
            self.used.append(entry['provider'])
            return {'text': 'new'}

        value, _ = resumed.stage(
            'research', {'prompt': 'p'}, call, lambda v: None, 0, [GROK, TERRA, OPUS]
        )
        self.assertEqual(value, {'text': 'from codex'})
        self.assertEqual(self.used, [])

    def test_cache_key_is_the_old_inputs_plus_model_and_effort(self):
        self.stage(lambda folder, entry: {'text': 'notes'})
        old_key = fingerprint({'prompt': 'p', 'model': {'model': 'grok-4.7', 'effort': 'high'}})
        self.assertTrue((self.root / 'workflow-cache' / f'research-{old_key}.json').exists())
        self.assertEqual(cache_model(GROK), {'model': 'grok-4.7', 'effort': 'high'})

    def test_cooldown_skips_grok_for_a_day(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=2)
        self.flow.state = ProviderState({'grok': {'exhausted_at': recent.isoformat()}})
        self.stage(lambda folder, entry: {'text': 'notes'})
        self.assertEqual(self.used, ['codex'])
        later = recent + timedelta(hours=24, minutes=1)
        self.assertTrue(self.flow.state.available('grok', at=later))

    def test_all_entries_exhausted_stops_the_batch(self):
        def behaviour(folder, entry):
            raise ProviderExhausted(entry['provider'], entry['provider'] + ' usage exhausted')

        with self.assertRaisesRegex(AccountExhausted, 'No provider could run research'):
            self.stage(behaviour)
        self.assertEqual(self.used, ['grok', 'codex', 'claude'])


class FakeModels:
    def __init__(self, research=None, structured=None):
        self.research_calls = []
        self.structured_calls = []
        self.on_research = research
        self.on_call = structured

    def research(self, entry, text, folder, session=None, resume=False, workdir=None):
        self.research_calls.append((entry['provider'], entry.get('mode'), session, resume, text))
        return self.on_research(entry, text, session)

    def call(self, role, text, schema, folder, entry=None):
        self.structured_calls.append((role, entry['provider'], folder))
        return self.on_call(role, text, folder, entry)


SPEC = {'field': 'Physics', 'prefix': 'PHY', 'as_of': '2026-11-01', 'boundaries': 'Physics'}
NOTES = '**PHY-01. One**\nnotes\n'


class ReconcileTests(unittest.TestCase):
    def test_grok_research_is_continued_in_the_same_grok_session(self):
        def research(entry, text, session):
            return {'session_id': session, 'text': NOTES}

        models = FakeModels(research=research)
        with tempfile.TemporaryDirectory() as directory:
            config = {'stages': {'research': [GROK, TERRA], 'reconcile': [GROK, TERRA]}}
            FieldWorkflow(directory, config=config, models=models).research(SPEC, 'original')
        first, second = models.research_calls
        self.assertEqual(second[:4], ('grok', 'resume', first[2], True))
        self.assertNotIn(FRESH_RECONCILE, second[4])

    def test_codex_research_gets_a_fresh_reconcile_with_the_extra_wording(self):
        def research(entry, text, session):
            if entry['provider'] == 'grok':
                raise ProviderExhausted('grok', 'Grok usage exhausted')
            return {'text': NOTES}

        models = FakeModels(research=research)
        with tempfile.TemporaryDirectory() as directory:
            config = {'stages': {'research': [GROK, TERRA], 'reconcile': [GROK, TERRA]}}
            flow = FieldWorkflow(directory, config=config, models=models)
            flow.research(SPEC, 'original')
            receipts = [
                json.loads(path.read_text())
                for path in Path(directory).glob('attempts/reconcile-*/receipt.json')
            ]
        # Grok is cooling down after the research attempt, so it is not tried again.
        self.assertEqual(
            [call[:2] for call in models.research_calls],
            [('grok', None), ('codex', None), ('codex', 'fresh')],
        )
        self.assertFalse(models.research_calls[-1][3])
        self.assertTrue(models.research_calls[-1][4].endswith(FRESH_RECONCILE))
        self.assertEqual([receipt['mode'] for receipt in receipts], ['fresh'])


def review_doc(count):
    return {
        'problems': [
            {'id': f'PHY-{i:02d}', 'claims': [{'id': f'PHY-{i:02d}-problem', 'citations': []}]}
            for i in range(1, count + 1)
        ],
        'sources': [],
    }


def review_value(text):
    payload = json.loads(text[text.index('{') : text.rindex('}') + 1])
    return {
        'concept_assessment': {
            'summary': 'Keep',
            'revolutionary_significance': 'Broad capability',
            'scope_and_overlap': 'Distinct',
        },
        'corrections': [],
        'evidence_review': {
            'claims': [
                {'id': c['id'], 'status': 'unresolved', 'reason': 'None', 'evidence': []}
                for c in payload['problem']['claims']
            ]
        },
    }


class WithheldTests(unittest.TestCase):
    def reviewer(self, refused=(), failing=()):
        def call(role, text, folder, entry):
            identifier = json.loads((folder / 'input.json').read_text())['problem']['id']
            if identifier in refused:
                refuse(folder)
            if identifier in failing:
                raise ValueError('invalid review')
            return review_value(text)

        return FakeModels(structured=call)

    def config(self):
        return {'stages': {'review': [{'provider': 'codex', 'model': 'sol'}, OPUS]}}

    def test_a_refused_concept_is_withheld_and_never_sent_to_another_model(self):
        models = self.reviewer(refused={'PHY-02'})
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(directory, config=self.config(), models=models)
            results = flow.review(review_doc(3), {}, {})
            self.assertEqual(results['PHY-02']['status'], 'withheld')
            self.assertEqual(results['PHY-02']['stage'], 'review-PHY-02')
            self.assertIn('limited access', results['PHY-02']['reason'])
            self.assertNotIn('/', results['PHY-02']['reason'].split('safety reasons')[0])
            self.assertEqual(results['PHY-01']['status'], 'complete')
            refused_calls = [c for c in models.structured_calls if 'PHY-02' in str(c[2])]
            self.assertEqual([c[1] for c in refused_calls], ['codex'])
            # A resumed run respects the marker without any call.
            before = len(models.structured_calls)
            again = FieldWorkflow(directory, config=self.config(), models=models)
            self.assertEqual(again.review(review_doc(3), {}, {})['PHY-02']['status'], 'withheld')
            self.assertEqual(len(models.structured_calls), before)

    def test_other_review_failures_still_block_the_field(self):
        models = self.reviewer(refused={'PHY-02'}, failing={'PHY-03'})
        with tempfile.TemporaryDirectory() as directory:
            flow = FieldWorkflow(directory, config=self.config(), models=models)
            with self.assertRaisesRegex(ValueError, 'blocked by failed reviews: PHY-03$'):
                flow.review(review_doc(3), {}, {})
            reviews = json.loads((Path(directory) / 'reconciled-reviews.json').read_text())
            self.assertEqual(reviews['PHY-02']['status'], 'withheld')
            self.assertEqual(reviews['PHY-03']['status'], 'failed')


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_codex_exhaustion_comes_from_error_events_not_model_text(self):
        event = {'type': 'turn.failed', 'error': {'message': 'You’ve hit your usage limit.'}}
        cli = fake_cli(stdout=json.dumps(event) + '\n', code=1)
        with patch('ingestion.providers.execute', cli):
            with self.assertRaises(ProviderExhausted):
                Models({}).call('review', 'text', {}, self.folder, entry=TERRA)
        answer = {'type': 'item.completed', 'item': {'text': 'usage limit reached'}}
        cli = fake_cli(stdout=json.dumps(answer) + '\n', code=1)
        with patch('ingestion.providers.execute', cli):
            with self.assertRaisesRegex(RuntimeError, 'Codex exited 1'):
                Models({}).call('review', 'text', {}, self.folder, entry=TERRA)

    def test_codex_research_searches_and_returns_plain_text(self):
        cli = fake_cli(response='**PHY-01. One**\n')
        with patch('ingestion.providers.execute', cli):
            value = Models({'codex': 'codex'}).research(TERRA, 'research', self.folder)
        self.assertEqual(value, {'text': '**PHY-01. One**\n'})
        command = cli.commands[0]
        self.assertLess(command.index('--search'), command.index('exec'))
        self.assertNotIn('--output-schema', command)
        self.assertEqual(attempt_model(self.folder), 'gpt-6.1-terra')

    def test_claude_reports_exhaustion_timeout_and_its_served_model(self):
        failure = {'is_error': True, 'api_error_status': 429, 'result': 'Request failed'}
        with patch('ingestion.providers.execute', fake_cli(stdout=json.dumps(failure), code=1)):
            with self.assertRaises(ProviderExhausted):
                Models({}).call('review', 'text', {}, self.folder, entry=OPUS)

        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired('claude', 1)

        with patch('ingestion.providers.execute', slow):
            with self.assertRaises(ProviderTimeout):
                Models({}).call('review', 'text', {}, self.folder, entry=OPUS)
        success = {
            'is_error': False,
            'result': '',
            'structured_output': {'ok': True},
            'modelUsage': {
                'claude-opus-5-5': {'outputTokens': 900},
                'claude-haiku-4-5': {'outputTokens': 20},
            },
        }
        cli = fake_cli(stdout=json.dumps(success))
        with patch('ingestion.providers.execute', cli):
            self.assertEqual(
                Models({}).call('review', 'text', {}, self.folder, entry=OPUS), {'ok': True}
            )
        self.assertIn('--json-schema', cli.commands[0])
        self.assertEqual(cli.commands[0][cli.commands[0].index('--tools') + 1], '')
        self.assertEqual(attempt_model(self.folder), 'claude-opus-5-5')

    def test_saved_attempts_name_their_model(self):
        write_json(self.folder / 'model.json', {'model': 'gpt-6.1-sol', 'effort': 'medium'})
        (self.folder / 'stdout.log').write_text('{"type":"thread.started"}\n{"type":"x"}\n')
        self.assertEqual(attempt_model(self.folder), 'gpt-6.1-sol')
        (self.folder / 'model.json').unlink()
        usage = {'modelUsage': {'grok-4.7-build': {'outputTokens': 3}}}
        (self.folder / 'stdout.log').write_text(json.dumps(usage))
        self.assertEqual(attempt_model(self.folder), 'grok-4.7-build')
        (self.folder / 'stdout.log').unlink()
        self.assertIsNone(attempt_model(self.folder))

    def test_old_config_keys_still_give_one_entry_per_stage(self):
        config = {
            'research': {'model': 'grok-4.7', 'effort': 'high'},
            'format': {'model': 'gpt-6.1-terra', 'effort': 'high'},
            'review': {'model': 'gpt-6.1-sol', 'effort': 'medium'},
        }
        self.assertEqual(
            stage_entries(config, 'reconcile'), [{'provider': 'grok', **config['research']}]
        )
        self.assertEqual(
            stage_entries(config, 'rewrite'), [{'provider': 'codex', **config['review']}]
        )


class ConfigTests(unittest.TestCase):
    def test_first_entries_keep_todays_cache_keys_and_old_keys_remain(self):
        from ingestion.sources import read_json

        config = read_json(Path(__file__).parents[1] / 'config.json')
        first = {stage: cache_model(stage_entries(config, stage)[0]) for stage in config['stages']}
        self.assertEqual(first['research'], config['research'])
        self.assertEqual(first['reconcile'], config['research'])
        self.assertEqual(first['format'], config['format'])
        self.assertEqual(first['review'], config['review'])
        self.assertEqual(first['rewrite'], config['review'])
        self.assertEqual(
            [e['provider'] for e in config['stages']['research']],
            ['grok', 'codex', 'codex', 'claude'],
        )
        for key in ('grok', 'codex'):
            self.assertIsInstance(config[key], str)


if __name__ == '__main__':
    unittest.main()

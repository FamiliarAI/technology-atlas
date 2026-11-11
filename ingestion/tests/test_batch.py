import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ingestion.batch import group_fields, backup_valid, run, finish_field
from ingestion.sources import digest, write_json


class BatchTests(unittest.TestCase):
    def test_roster_keeps_field_identity_and_rejects_prefix_collision(self):
        rows = [
            {'id': 'A-01', 'field': 'Alpha'},
            {'id': 'B-01', 'field': 'Beta'},
            {'id': 'A-02', 'field': 'Alpha'},
        ]
        result = group_fields(rows)
        self.assertEqual([g['field'] for g in result], ['Alpha', 'Beta'])
        self.assertEqual(len(result[0]['entries']), 2)
        with self.assertRaises(ValueError):
            group_fields(rows + [{'id': 'A-03', 'field': 'Gamma'}])

    def test_backup_reverification_detects_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = b'original final'
            (root / 'final-innovations.json').write_bytes(data)
            sha = digest(data)
            write_json(
                root / 'backup-verification.json',
                {'source': '/source', 'files': {'final-innovations.json': sha}},
            )
            entry = {'backup': str(root), 'root': '/source', 'final_sha256': sha}
            self.assertTrue(backup_valid(entry))
            (root / 'final-innovations.json').write_text('tampered')
            self.assertFalse(backup_valid(entry))

    def make_manifest(self, root, count):
        fields = [
            {'field': f'Field{i}', 'root': str(root / f'F{i}'), 'status': 'pending'}
            for i in range(count)
        ]
        write_json(
            root / 'batch.json',
            {'fields': fields, 'status': 'prepared', 'revision': 'test', 'as_of': '2026-11-01'},
        )
        return fields

    def test_three_slots_refill_and_failure_does_not_claim_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_manifest(root, 7)
            guard = threading.Lock()
            active = 0
            peak = 0
            seen = []

            def work(entry, *args, **kwargs):
                nonlocal active, peak
                with guard:
                    active += 1
                    peak = max(peak, active)
                    seen.append(entry['field'])
                time.sleep(0.03)
                with guard:
                    active -= 1
                if entry['field'] == 'Field1':
                    raise ValueError('bad review')
                return {'concepts': 10, 'backup': 'fake', 'final_sha256': 'fake'}

            with patch('ingestion.batch.finish_field', side_effect=work):
                result = run(
                    root,
                    root / 'outside',
                    runner=lambda *args, **kwargs: None,
                    importer=lambda entry: None,
                )
            self.assertEqual(len(seen), 7)
            self.assertEqual(peak, 3)
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(sum(e['status'] == 'complete' for e in result['fields']), 6)
            self.assertNotIn('aggregate', result)
            self.assertFalse((root / 'final-innovations.json').exists())
            self.assertFalse((root / 'final-innovations.next.json').exists())

    def test_smaller_batch_completes_per_field_without_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_manifest(root, 2)
            with patch(
                'ingestion.batch.finish_field',
                return_value={'concepts': 10, 'backup': 'fake', 'final_sha256': 'fake'},
            ) as finish:
                result = run(
                    root,
                    root / 'outside',
                    runner=lambda *args, **kwargs: None,
                    importer=lambda entry: None,
                )
            self.assertEqual(finish.call_count, 2)
            self.assertEqual(result['status'], 'complete')
            self.assertTrue(all(e['status'] == 'complete' for e in result['fields']))
            self.assertNotIn('aggregate', result)
            self.assertNotIn('aggregate_error', result)
            self.assertFalse((root / 'final-innovations.json').exists())
            self.assertFalse((root / 'final-innovations.next.json').exists())

    def test_account_exhaustion_stops_new_fields(self):
        from ingestion.field_workflow import AccountExhausted

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_manifest(root, 7)
            seen = []

            def work(entry, *args, **kwargs):
                seen.append(entry['field'])
                if entry['field'] == 'Field0':
                    raise AccountExhausted('switch account')
                time.sleep(0.05)
                return {'concepts': 10}

            with patch('ingestion.batch.finish_field', side_effect=work):
                result = run(
                    root,
                    root / 'outside',
                    runner=lambda *args, **kwargs: None,
                    importer=lambda entry: None,
                )
            self.assertLessEqual(len(seen), 3)
            self.assertEqual(result['status'], 'account_required')
            self.assertEqual(sum(e['status'] == 'pending' for e in result['fields']), 4)

    def test_successful_runner_without_final_artifacts_is_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / 'original.md'
            original.write_text('original')
            entry = {
                'root': str(root / 'field'),
                'original_path': str(original),
                'field': 'Test',
                'prefix': 'TEST',
                'boundaries': 'Test scope',
                'original_sha256': digest(original.read_bytes()),
                'original_prefix': 'TEST',
            }
            with self.assertRaises(ValueError):
                finish_field(entry, '2026-11-01', root / 'backup', lambda *args, **kwargs: None)


def final_document(prefix, text='A proposed capability.'):
    paragraph = [{'text': text, 'source_urls': ['https://example.org']}]
    record = {
        'id': prefix + '-01',
        'title': 'Breakthrough',
        'change_log': [],
        'unresolved_issues': [],
        'sources': [{'url': 'https://example.org', 'title': 'Paper', 'status': 'saved'}],
        'provenance': {},
        'models': {'research': 'grok-4.7-build', 'rewrite': 'gpt-6.1-sol'},
    }
    for section in (
        'concept',
        'significance',
        'missing_breakthrough',
        'current_state',
        'completion_criteria',
        'related_concepts',
    ):
        record[section] = paragraph
    return {
        'field': {'prefix': prefix, 'field': 'Field ' + prefix},
        'created_at': '2026-11-11',
        'innovations': [record],
        'withheld': [
            {
                'id': prefix + '-02',
                'title': 'Refused',
                'stage': 'review-' + prefix + '-02',
                'reason': 'Provider safety refusal',
            }
        ],
    }


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.core = self.root / 'core'
        self.core.mkdir()
        (self.core / 'sources.jsonl').write_text('')
        fields = []
        for prefix in ('AAA', 'BBB', 'CCC', 'DDD'):
            folder = self.root / prefix
            folder.mkdir()
            write_json(folder / 'final-innovations.json', final_document(prefix))
            fields.append(
                {
                    'field': 'Field ' + prefix,
                    'prefix': prefix,
                    'root': str(folder),
                    'status': 'pending',
                }
            )
        write_json(
            self.root / 'batch.json',
            {'fields': fields, 'status': 'prepared', 'revision': 'test', 'as_of': '2026-11-01'},
        )

    def run_batch(self, importer, only=None, work=None):
        def finish(entry, *args, **kwargs):
            time.sleep(0.01)
            if work:
                work(entry, kwargs['state'])
            return {'concepts': 1, 'backup': 'fake', 'final_sha256': 'fake'}

        with patch('ingestion.batch.finish_field', side_effect=finish):
            return run(
                self.root,
                self.root / 'outside',
                runner=lambda *args, **kwargs: None,
                importer=importer,
                only=only,
            )

    def test_import_runs_in_controller_one_field_at_a_time_and_is_idempotent(self):
        from atlas import core as records
        from ingestion.batch import import_to_atlas

        active = 0
        seen = []
        messages = []

        def importer(entry):
            nonlocal active
            active += 1
            self.assertEqual(active, 1)
            self.assertIs(threading.current_thread(), threading.main_thread())
            try:
                return import_to_atlas(entry, self.core)
            finally:
                active -= 1
                seen.append(entry['prefix'])

        with (
            patch('atlas.store.rebuild') as rebuild,
            patch('atlas.core.commit', side_effect=messages.append) as commit,
        ):
            self.run_batch(importer)
            self.assertEqual(sorted(seen), ['AAA', 'BBB', 'CCC', 'DDD'])
            self.assertEqual(commit.call_count, 4)
            self.assertEqual(rebuild.call_count, 4)
            snapshot = {p: p.read_bytes() for p in self.core.rglob('*') if p.is_file()}
            # Already imported is not an error and changes nothing.
            for entry in json.loads((self.root / 'batch.json').read_text())['fields']:
                self.assertIsNone(import_to_atlas(entry, self.core))
            self.assertEqual(commit.call_count, 4)
        self.assertEqual({p: p.read_bytes() for p in self.core.rglob('*') if p.is_file()}, snapshot)
        data = records.load(self.core)
        self.assertEqual(records.check(data), [])
        self.assertEqual(data['breakthroughs']['AAA-01']['models']['rewrite'], 'gpt-6.1-sol')
        self.assertEqual(data['fields']['AAA']['withheld'][0]['id'], 'AAA-02')
        self.assertEqual(len({field['color'] for field in data['fields'].values()}), 4)
        self.assertIn('Import Field AAA (AAA) into atlas/core', '\n'.join(messages))
        self.assertIn('rewrite: gpt-6.1-sol', messages[0])
        self.assertIn('Withheld: ', messages[0])

    def test_failed_check_undoes_the_import_and_keeps_the_batch_going(self):
        from ingestion.batch import import_to_atlas

        write_json(self.root / 'BBB/final-innovations.json', final_document('BBB', '/Users/x'))
        before = (self.core / 'sources.jsonl').read_bytes()
        with patch('atlas.store.rebuild'), patch('atlas.core.commit') as commit:
            result = self.run_batch(lambda entry: import_to_atlas(entry, self.core), only=['BBB'])
        entry = next(e for e in result['fields'] if e['prefix'] == 'BBB')
        self.assertEqual(entry['status'], 'complete')
        self.assertIn('Absolute path', entry['import_error'])
        self.assertFalse((self.core / 'BBB').exists())
        self.assertEqual((self.core / 'sources.jsonl').read_bytes(), before)
        commit.assert_not_called()

    def test_only_runs_the_named_fields(self):
        result = self.run_batch(lambda entry: None, only=['CCC', 'AAA'])
        statuses = {e['prefix']: e['status'] for e in result['fields']}
        self.assertEqual(
            statuses, {'AAA': 'complete', 'BBB': 'pending', 'CCC': 'complete', 'DDD': 'pending'}
        )
        with self.assertRaisesRegex(ValueError, 'Unknown field'):
            self.run_batch(lambda entry: None, only=['ZZZ'])

    def test_grok_exhaustion_is_saved_in_the_manifest_and_honoured_next_run(self):
        from ingestion.providers import ProviderState

        self.run_batch(
            lambda entry: None, only=['AAA'], work=lambda entry, state: state.exhausted('grok')
        )
        saved = json.loads((self.root / 'batch.json').read_text())['providers']
        self.assertIn('exhausted_at', saved['grok'])
        seen = []
        self.run_batch(
            lambda entry: None,
            only=['BBB'],
            work=lambda entry, state: seen.append(state.available('grok')),
        )
        self.assertEqual(seen, [False])
        self.assertTrue(ProviderState(saved).available('codex'))

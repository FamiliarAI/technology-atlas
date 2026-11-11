import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ingestion.batch import group_fields, backup_valid, run, finish_field, write_aggregate
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

            def work(entry, *args):
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
                result = run(root, root / 'outside', runner=lambda *args: None)
            self.assertEqual(len(seen), 7)
            self.assertEqual(peak, 3)
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(sum(e['status'] == 'complete' for e in result['fields']), 6)

    def test_account_exhaustion_stops_new_fields(self):
        from ingestion.field_workflow import AccountExhausted

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_manifest(root, 7)
            seen = []

            def work(entry, *args):
                seen.append(entry['field'])
                if entry['field'] == 'Field0':
                    raise AccountExhausted('switch account')
                time.sleep(0.05)
                return {'concepts': 10}

            with patch('ingestion.batch.finish_field', side_effect=work):
                result = run(root, root / 'outside', runner=lambda *args: None)
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
                finish_field(entry, '2026-11-01', root / 'backup', lambda *args: None)

    def test_aggregate_requires_all_66_and_preserves_field_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = []
            for i in range(66):
                field = root / str(i)
                field.mkdir()
                output = {
                    'innovations': [{'id': f'F{i}-01'}],
                    'original_dispositions': [{'original_number': 1}],
                }
                write_json(field / 'final-innovations.json', output)
                entries.append(
                    {
                        'field': f'Field{i}',
                        'prefix': f'F{i}',
                        'root': str(field),
                        'status': 'complete',
                        'backup': 'verified-backup',
                        'final_sha256': digest((field / 'final-innovations.json').read_bytes()),
                    }
                )
            manifest = {'fields': entries, 'revision': 'original', 'as_of': '2026-11-01'}
            aggregate = write_aggregate(root, manifest)
            self.assertEqual(aggregate['field_count'], 66)
            self.assertEqual(aggregate['innovation_count'], 66)
            self.assertEqual(aggregate['fields'][3]['innovations'][0]['id'], 'F3-01')
            entries[2]['status'] = 'failed'
            with self.assertRaises(ValueError):
                write_aggregate(root, manifest)
            entries[2]['status'] = 'complete'
            (root / '2/final-innovations.json').write_text('{}')
            with self.assertRaises(ValueError):
                write_aggregate(root, manifest)

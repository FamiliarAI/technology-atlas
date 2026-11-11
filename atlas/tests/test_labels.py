import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from atlas import labels


class LabelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.core = self.root / 'core'
        self.calls = self.root / 'atlas/data/labels'
        self.item = {
            'id': 'SWE-01',
            'field': 'SWE',
            'status': 'active',
            'title': 'Verified compilation',
            'concept': [{'text': 'First concept paragraph'}, {'text': 'Second paragraph'}],
            'label': 'Proposed demonstration',
            'completion_criteria': [
                {'id': 'm1', 'text': 'Show decreasing error.', 'label': 'Proposed demonstration'},
                {'label': 'Optional result', 'text': 'Report all assumptions.', 'id': 'm2'},
            ],
            'other': {'label': 'Optional result', 'text': 'Unicode: café'},
        }
        self.file = self.write(self.item)
        self.reply = {'milestones': [
            {'id': 'm2', 'label': 'All assumptions explicitly reported'},
            {'id': 'm1', 'label': 'Error decreases with distance'},
        ]}

    def write(self, item):
        path = self.core / item['field'] / (item['id'] + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(item, indent=3, ensure_ascii=True).replace('\n', '\r\n')
        path.write_bytes((raw + '\r\n').encode())
        return path

    def test_relabel_changes_only_label_bytes_and_uses_one_prompt(self):
        before = self.file.read_bytes()
        call = Mock(return_value=self.reply)
        with patch('atlas.labels.store.rebuild') as rebuild:
            with patch('atlas.labels.records.commit') as commit:
                changes = labels.relabel('SWE-01', call=call, core=self.core)
        rebuild.assert_not_called()
        commit.assert_not_called()
        self.assertEqual(changes, [
            ('m1', 'Proposed demonstration', 'Error decreases with distance'),
            ('m2', 'Optional result', 'All assumptions explicitly reported'),
        ])
        expected = before.replace(
            b'"text": "Show decreasing error.",\r\n'
            b'         "label": "Proposed demonstration"',
            b'"text": "Show decreasing error.",\r\n'
            b'         "label": "Error decreases with distance"',
        ).replace(
            b'"label": "Optional result",\r\n         "text": "Report all assumptions."',
            b'"label": "All assumptions explicitly reported",\r\n'
            b'         "text": "Report all assumptions."',
        )
        self.assertNotEqual(before, expected)
        self.assertEqual(self.file.read_bytes(), expected)
        call.assert_called_once_with(labels.PROMPT.format(
            title=self.item['title'],
            concept='First concept paragraph',
            milestones='m1: Show decreasing error.\nm2: Report all assumptions.',
        ))

    def test_validation_rejects_whole_answer_without_writing(self):
        bad_labels = [
            (' '.join(['word'] * 13), '12 words'),
            ('a' * 95 + ' two three', '100 characters'),
            ('Too short', '3 words'),
            ('pRoPoSeD working gate set', 'first word'),
            ('OPTIONAL working gate set', 'first word'),
            ('Working universal gate set.', 'full stop'),
            ('ALL ASSUMPTIONS EXPLICITLY REPORTED', 'duplicate label'),
        ]
        cases = []
        for label, reason in bad_labels:
            reply = copy.deepcopy(self.reply)
            reply['milestones'][1]['label'] = label
            cases.append((reply, reason))
        cases.extend([
            ({'milestones': self.reply['milestones'][:1]}, 'milestone ids'),
            ({'milestones': self.reply['milestones'] * 2}, 'milestone ids'),
            ({'milestones': [{'id': 'unknown', 'label': 'Working universal gate set'}]},
             'milestone ids'),
            ({'milestones': [{'id': 'm1', 'label': 42}]}, 'schema'),
            ({'milestones': self.reply['milestones'], 'extra': True}, 'schema'),
            ({'milestones': [dict(self.reply['milestones'][0], extra=True)]}, 'schema'),
            ({'milestones': 'bad'}, 'schema'),
            ({}, 'schema'),
            (None, 'schema'),
        ])
        before = self.file.read_bytes()
        for reply, reason in cases:
            with self.subTest(reply=reply):
                with self.assertRaisesRegex(ValueError, 'SWE-01:.*' + reason):
                    labels.relabel('SWE-01', call=lambda prompt: reply, core=self.core)
                self.assertEqual(self.file.read_bytes(), before)

    def test_label_boundaries_and_stronger_prefix_are_accepted(self):
        self.reply['milestones'][0]['label'] = 'Stronger: fully reproduced result'
        self.reply['milestones'][1]['label'] = ' '.join(['a'] * 11 + ['b' * 78])
        self.assertEqual(len(self.reply['milestones'][1]['label']), 100)
        labels.relabel('SWE-01', call=lambda prompt: self.reply, core=self.core)

    def start_patch(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def prepare_main(self):
        item = copy.deepcopy(self.item)
        for identifier, status in [('SWE-02', 'retired'), ('SWE-03', 'active')]:
            item.update(id=identifier, status=status)
            self.write(item)
        (self.core / 'SWE/field.json').write_text('{"id": "SWE"}')
        factory = self.start_patch('atlas.labels._call')
        factory.side_effect = lambda identifier: (
            self.calls / identifier, Mock(return_value=self.reply)
        )
        self.start_patch('atlas.labels.ROOT', new=self.root)
        rebuild = self.start_patch('atlas.labels.store.rebuild')
        git = self.start_patch('subprocess.run')
        self.start_patch('builtins.print')
        return factory, rebuild, git

    def test_field_expansion_deduplicates_and_no_commit_skips_git(self):
        factory, rebuild, git = self.prepare_main()
        result = labels.main(['SWE', 'SWE-01', '--no-commit'], core=self.core)
        self.assertEqual(result, 0)
        self.assertEqual(sorted(c.args[0] for c in factory.call_args_list),
                         ['SWE-01', 'SWE-03'])
        rebuild.assert_called_once_with(core=self.core)
        git.assert_not_called()
        retired = json.loads((self.core / 'SWE/SWE-02.json').read_bytes())
        self.assertEqual(retired['completion_criteria'], self.item['completion_criteria'])

    def test_main_commits_once_with_model_and_relative_call_folders(self):
        _, rebuild, git = self.prepare_main()
        with patch('atlas.labels.records.commit', wraps=labels.records.commit) as commit:
            self.assertEqual(labels.main(['SWE'], core=self.core), 0)
        rebuild.assert_called_once_with(core=self.core)
        commit.assert_called_once_with(
            'Relabel milestones for SWE (2 breakthroughs)\n\nModel: grok-4.7\n'
            'Calls:\natlas/data/labels/SWE-01\natlas/data/labels/SWE-03'
        )
        self.assertEqual(git.call_count, 3)
        self.assertEqual(git.call_args_list[0].args[0], ['git', 'add', 'atlas/core'])

    def test_main_reports_failure_continues_and_rebuilds_once(self):
        factory, rebuild, git = self.prepare_main()
        factory.side_effect = lambda identifier: (
            self.calls / identifier,
            Mock(return_value={} if identifier == 'SWE-01' else self.reply),
        )
        before = self.file.read_bytes()
        with patch('builtins.print') as output:
            result = labels.main(['SWE', '--no-commit'], core=self.core)
        self.assertEqual(result, 1)
        self.assertTrue(any('SWE-01:' in str(c) for c in output.call_args_list))
        self.assertEqual(self.file.read_bytes(), before)
        updated = json.loads((self.core / 'SWE/SWE-03.json').read_bytes())
        self.assertEqual(updated['completion_criteria'][0]['label'],
                         'Error decreases with distance')
        rebuild.assert_called_once_with(core=self.core)
        git.assert_not_called()

    def test_main_limits_model_calls_to_four_threads(self):
        _, _, _ = self.prepare_main()
        for n in range(4, 10):
            self.write(dict(self.item, id=f'SWE-{n:02}'))
        barrier = threading.Barrier(4, timeout=5)
        lock = threading.Lock()
        active = 0
        peak = 0
        calls = 0

        def call(prompt):
            nonlocal active, peak, calls
            with lock:
                active += 1
                calls += 1
                peak = max(peak, active)
            barrier.wait()
            with lock:
                active -= 1
            return self.reply

        with patch('atlas.labels._call', side_effect=lambda identifier: (
            self.calls / identifier, call
        )):
            self.assertEqual(labels.main(['SWE', '--no-commit'], core=self.core), 0)
        self.assertEqual((calls, peak), (8, 4))

    def test_real_call_records_cli_output_and_checks_envelope(self):
        config = self.root / 'config.json'
        config.write_text('{"grok": "~/.grok/bin/grok"}')
        with patch('atlas.labels.CONFIG', config), patch('atlas.labels.CALLS', self.calls):
            folder, call = labels._call('SWE-01')
        envelope = {'structuredOutput': self.reply, 'structuredOutputError': None,
                    'stopReason': 'end_turn'}
        raw = json.dumps(envelope).encode()
        with patch('subprocess.run', return_value=Mock(stdout=raw, returncode=0)) as run:
            self.assertEqual(call('the prompt'), self.reply)
        command = run.call_args.args[0]
        self.assertEqual(command[0], str(Path('~/.grok/bin/grok').expanduser()))
        self.assertEqual(command[1:14], [
            '-m', 'grok-4.7', '--reasoning-effort', 'high', '--tools', '',
            '--disable-web-search', '--no-subagents', '--no-plan', '--max-turns', '1',
            '--output-format', 'json',
        ])
        self.assertEqual(run.call_args.kwargs['cwd'], folder)
        self.assertEqual((folder / 'prompt.md').read_text(), 'the prompt')
        self.assertEqual(json.loads((folder / 'schema.json').read_text()), labels.SCHEMA)
        self.assertEqual((folder / 'raw.json').read_bytes(), raw)
        self.assertEqual(command[-2:], ['--prompt-file', str(folder / 'prompt.md')])
        self.assertEqual(json.loads(command[command.index('--json-schema') + 1]),
                         labels.SCHEMA)
        for changed in [
            {'structuredOutputError': 'invalid schema'}, {'stopReason': 'max_turns'},
            {'structuredOutput': None},
        ]:
            with self.subTest(changed=changed):
                stdout = json.dumps(dict(envelope, **changed)).encode()
                with patch('subprocess.run', return_value=Mock(stdout=stdout, returncode=0)):
                    with self.assertRaisesRegex(ValueError, 'SWE-01:'):
                        call('the prompt')
        for stdout, code in [(b'not JSON', 0), (b'failed output', 1)]:
            with patch('subprocess.run', return_value=Mock(stdout=stdout, returncode=code)):
                with self.assertRaisesRegex(ValueError, 'SWE-01:'):
                    call('the prompt')
            self.assertEqual((folder / 'raw.json').read_bytes(), stdout)


if __name__ == '__main__':
    unittest.main()

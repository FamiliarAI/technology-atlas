"""The OpenRouter provider: request shape, structured answers, exhaustion, and the key."""

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from ingestion import providers


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class OpenRouterTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        patcher = patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_search_effort_and_schema_are_sent_and_the_json_answer_returned(self):
        sent = {}

        def urlopen(request, timeout):
            sent.update(json.loads(request.data), auth=request.headers['Authorization'])
            reply = {'choices': [{'message': {'content': '```json\n{"a": 1}\n```'}}]}
            return Response(json.dumps(reply).encode())

        entry = {'model': 'deepseek/x', 'effort': 'high', 'search': True}
        with patch('urllib.request.urlopen', urlopen):
            answer = providers.openrouter({}, entry, 'Q', self.folder, {'type': 'object'})
        self.assertEqual(answer, {'a': 1})
        self.assertEqual(sent['plugins'][0]['id'], 'web')
        self.assertEqual(sent['reasoning'], {'effort': 'high'})
        self.assertTrue(sent['response_format']['json_schema']['strict'])
        self.assertEqual(sent['auth'], 'Bearer test-key')
        # The key is never logged.
        for path in self.folder.iterdir():
            self.assertNotIn('test-key', path.read_text())

    def test_no_credit_is_exhaustion(self):
        def urlopen(request, timeout):
            raise urllib.error.HTTPError(
                providers.OPENROUTER_URL, 402, 'Payment', {}, io.BytesIO(b'{"error": "credits"}')
            )

        with patch('urllib.request.urlopen', urlopen):
            with self.assertRaises(providers.ProviderExhausted):
                providers.openrouter({}, {'model': 'deepseek/x'}, 'Q', self.folder)

    def test_a_model_named_with_a_slash_runs_through_openrouter(self):
        from atlas import page

        self.assertEqual(page.writer_entry('deepseek/x')['provider'], 'openrouter')
        self.assertEqual(page.writer_entry('gpt-6.1-sol')['provider'], 'codex')


if __name__ == '__main__':
    unittest.main()

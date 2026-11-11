"""Model command-line tools, ordered fallback lists and exhaustion detection.

Each pipeline stage has an ordered list of entries in config.json under `stages`, such as
{"provider": "codex", "model": "gpt-6.1-terra", "effort": "high", "search": true}. A stage
moves to the next entry only when the provider positively reports exhaustion or the call
times out. Exhaustion is read from the tool's own error output, never from model text.
"""

import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading

from .sources import now, read_json, write_json

DEFAULT_TIMEOUT_S = 3600

# Exhaustion that is remembered across fields (in batch.json) and for how long.
COOLDOWN = {'grok': timedelta(hours=24)}

# Stage -> (config key used before `stages` existed, provider).
LEGACY_STAGES = {
    'research': ('research', 'grok'),
    'reconcile': ('research', 'grok'),
    'format': ('format', 'codex'),
    'review': ('review', 'codex'),
    'rewrite': ('review', 'codex'),
}

# Wording that means an account is out of quota for now, by provider. Matched only against
# a tool's own error output (error events, stderr, error envelopes), never model text.
# Grok's wording was observed in this project's runs. Codex's comes from the strings in
# the bundled CLI binary and Claude's from the Claude Code binary; neither has been seen
# in a real failure yet. Add new wording here.
EXHAUSTION = {
    'grok': (
        r'credits? (?:exhausted|depleted)',
        r'insufficient credits',
        r'usage limit',
        r'quota (?:exceeded|exhausted)',
        r'rate limit exceeded',
        r'not logged in',
        r'authentication (?:failed|required)',
        r'unauthorized',
        r'subscription required',
        r'\bsubscription:free-usage-exhausted\b',
        r'\bGrok Build usage balance (?:exhausted|depleted)\b',
        r'\bresponses API error[^\n]*\bstatus=402\b',
    ),
    'codex': (
        r"You[’']ve hit your usage limit",
        r'Quota exceeded\. Check your plan',
        r'\busage_limit_exceeded\b',
        r'\busage_limit_reached\b',
        r'\bcredits_depleted\b',
        r'exceeded retry limit, last status: 429',
    ),
    'claude': (
        r"You[’']ve hit your (?:usage )?limit",
        r'usage limit reached',
        r'Credit balance is too low',
        r"You[’']re out of extra usage",
        r'\brate_limit_error\b',
    ),
}

# Credentials in the environment would bypass the signed-in accounts. A parent Claude Code
# session's variables would route a child `claude` through that session instead.
SCRUBBED = ('OPENAI_API_KEY', 'CODEX_API_KEY', 'XAI_API_KEY', 'GROK_API_KEY', 'CLAUDECODE')
SCRUBBED_PREFIXES = ('ANTHROPIC_', 'CLAUDE_CODE_')


class ProviderUnavailable(RuntimeError):
    """This entry cannot run now; the stage may try its next entry."""

    def __init__(self, provider, reason, message):
        super().__init__(message)
        self.provider = provider
        self.reason = reason


class ProviderExhausted(ProviderUnavailable):
    def __init__(self, provider, message):
        super().__init__(provider, 'exhausted', message)


class ProviderTimeout(ProviderUnavailable):
    def __init__(self, provider, message):
        super().__init__(provider, 'timeout', message)


def exhausted(provider, message):
    return any(re.search(pattern, message, re.I) for pattern in EXHAUSTION.get(provider, ()))


def stage_entries(config, stage):
    """The ordered fallback list for a stage, from `stages` or the older single keys."""
    if stage in config.get('stages', {}):
        return copy.deepcopy(config['stages'][stage])
    key, provider = LEGACY_STAGES[stage]
    return [{'provider': provider, **config[key]}]


def cache_model(entry):
    """The part of an entry that enters a cache key: unchanged from before fallback lists."""
    return {key: entry[key] for key in ('model', 'effort') if key in entry}


def describe(entry):
    return ' '.join(str(entry[key]) for key in ('provider', 'model', 'effort') if key in entry)


def binary(config, provider):
    configured = config.get('providers', {}).get(provider, {}).get('bin')
    legacy = config.get(provider) if isinstance(config.get(provider), str) else None
    return str(Path(configured or legacy or provider).expanduser())


class ProviderState:
    """Provider exhaustion shared by a batch's fields. The controller saves it."""

    def __init__(self, saved=None):
        self.lock = threading.Lock()
        self.saved = copy.deepcopy(saved or {})

    def available(self, provider, at=None):
        stamp = self.saved.get(provider, {}).get('exhausted_at')
        if provider not in COOLDOWN or not stamp:
            return True
        at = at or datetime.now(timezone.utc)
        return at - datetime.fromisoformat(stamp) >= COOLDOWN[provider]

    def exhausted(self, provider):
        if provider in COOLDOWN:
            with self.lock:
                self.saved.setdefault(provider, {})['exhausted_at'] = now()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.saved)


def environment():
    env = dict(os.environ)
    for key in list(env):
        if key in SCRUBBED or key.startswith(SCRUBBED_PREFIXES):
            env.pop(key)
    return env


def execute(cmd, directory, stdin=None, timeout=DEFAULT_TIMEOUT_S, cwd=None, check=True):
    """Keep logs, stop child processes on timeout/interrupt, never use API-key env auth."""
    with (
        tempfile.TemporaryDirectory(prefix='atlas-model-') as scratch,
        open(directory / 'stdout.log', 'w') as out,
        open(directory / 'stderr.log', 'w') as err,
    ):
        process = subprocess.Popen(
            cmd,
            cwd=cwd or scratch,
            env=environment(),
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            text=True,
            start_new_session=True,
        )
        try:
            process.communicate(stdin, timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                pass
            raise
    if check and process.returncode:
        raise RuntimeError(
            f'Model CLI exited {process.returncode}; inspect {directory / "stderr.log"}'
        )
    return process.returncode


def _logs(directory):
    def read(name):
        path = Path(directory) / name
        return path.read_text(errors='replace') if path.exists() else ''

    return read('stdout.log'), read('stderr.log')


def codex_errors(directory):
    """Messages from Codex error events plus its stderr log; no model output."""
    stdout, stderr = _logs(directory)
    messages = [stderr]
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'error':
            messages.append(json.dumps(event, ensure_ascii=False))
        elif event.get('type') == 'turn.failed':
            messages.append(json.dumps(event.get('error'), ensure_ascii=False))
    return '\n'.join(messages)


def codex(config, entry, text, directory, schema=None, timeout=DEFAULT_TIMEOUT_S):
    command = [binary(config, 'codex')]
    if entry.get('search'):
        command.append('--search')
    command += [
        'exec',
        '--ignore-user-config',
        '--skip-git-repo-check',
        '--ephemeral',
        '-s',
        'read-only',
        '-m',
        entry['model'],
    ]
    if entry.get('effort'):
        command += ['-c', f'model_reasoning_effort="{entry["effort"]}"']
    if schema is not None:
        write_json(directory / 'schema.json', schema)
        output = directory / 'response.json'
        command += ['--output-schema', str(directory / 'schema.json')]
    else:
        output = directory / 'response.md'
    command += ['-o', str(output), '--json', '-']
    code = execute(command, directory, text, timeout, check=False)
    if code:
        if exhausted('codex', codex_errors(directory)):
            raise ProviderExhausted('codex', f'Codex {entry["model"]} usage exhausted')
        raise RuntimeError(f'Codex exited {code}; inspect {directory / "stderr.log"}')
    if schema is not None:
        return read_json(output)
    notes = output.read_text() if output.exists() else ''
    if not notes.strip():
        raise ValueError('Codex returned no text')
    return {'text': notes}


def claude(config, entry, text, directory, schema=None, timeout=DEFAULT_TIMEOUT_S):
    tools = 'WebSearch,WebFetch' if entry.get('search') else ''
    command = [
        binary(config, 'claude'),
        '-p',
        '--model',
        entry['model'],
        '--output-format',
        'json',
        '--no-session-persistence',
        '--strict-mcp-config',
        '--setting-sources',
        '',
        '--disable-slash-commands',
        '--permission-mode',
        'dontAsk',
        '--tools',
        tools,
    ]
    if tools:
        command += ['--allowedTools', tools]
    if entry.get('effort'):
        command += ['--effort', entry['effort']]
    if schema is not None:
        write_json(directory / 'schema.json', schema)
        command += ['--json-schema', json.dumps(schema)]
    code = execute(command, directory, text, timeout, check=False)
    stdout, stderr = _logs(directory)
    try:
        envelope = json.loads(stdout)
    except ValueError:
        envelope = None
    if code or not isinstance(envelope, dict) or envelope.get('is_error'):
        # With is_error set, `result` holds the tool's error message, not model text.
        error = stderr
        if isinstance(envelope, dict):
            error += '\n' + str(envelope.get('result', ''))
        if (isinstance(envelope, dict) and envelope.get('api_error_status') == 429) or exhausted(
            'claude', error
        ):
            raise ProviderExhausted('claude', f'Claude {entry["model"]} usage exhausted')
        raise RuntimeError(f'Claude exited {code}; inspect {directory / "stdout.log"}')
    if schema is None:
        if not str(envelope.get('result', '')).strip():
            raise ValueError('Claude returned no text')
        return {'text': envelope['result']}
    value = envelope.get('structured_output')
    if not isinstance(value, dict):
        value = json.loads(envelope.get('result', ''))
    write_json(directory / 'response.json', value)
    return value


def grok(config, entry, text, directory, session, resume, workdir, timeout):
    (directory / 'prompt.md').write_text(text)
    command = [
        binary(config, 'grok'),
        '--resume' if resume else '--session-id',
        session,
        '-m',
        entry['model'],
        '--reasoning-effort',
        entry['effort'],
        '--tools',
        'web_search,web_fetch',
        '--no-subagents',
        '--no-plan',
        '--max-turns',
        '150',
        '--output-format',
        'json',
        '--prompt-file',
        str(directory / 'prompt.md'),
    ]
    code = execute(command, directory, timeout=timeout, cwd=workdir, check=False)
    stdout, stderr = _logs(directory)
    message = 'Grok usage exhausted'
    if code:
        if exhausted('grok', stdout + '\n' + stderr):
            raise ProviderExhausted('grok', message)
        raise RuntimeError('Grok exited unsuccessfully; inspect ' + str(directory / 'stderr.log'))
    try:
        raw = json.loads(stdout)
    except ValueError:
        if exhausted('grok', stdout + '\n' + stderr):
            raise ProviderExhausted('grok', message) from None
        raise
    notes = str(raw.get('text', ''))
    # Grok has returned its quota notice as the answer text; real research has headings.
    if exhausted('grok', notes) and not re.search(r'\*\*[A-Z][A-Z0-9_-]*-\d+\.', notes):
        raise ProviderExhausted('grok', message)
    if raw.get('sessionId') != session:
        raise ValueError('Grok returned a different conversation ID')
    if raw.get('stopReason') != 'end_turn' or not notes.strip():
        if exhausted('grok', stdout + '\n' + stderr):
            raise ProviderExhausted('grok', message)
        raise ValueError('Grok did not finish with usable research')
    return {'session_id': session, 'text': raw['text']}


class Models:
    """Run one entry. Without an entry, the older single config key for the role is used."""

    def __init__(self, config):
        self.config = config

    def call(self, role, text, schema, directory, entry=None):
        entry = entry or {'provider': 'codex', **self.config[role]}
        (directory / 'prompt.md').write_text(text)
        write_json(directory / 'model.json', entry)
        timeout = entry.get('timeout_s', DEFAULT_TIMEOUT_S)
        provider = entry.get('provider', 'codex')
        calls = {'codex': codex, 'claude': claude}
        if provider not in calls:
            raise ValueError(f'{provider} cannot run the {role} stage')
        try:
            return calls[provider](self.config, entry, text, directory, schema, timeout)
        except subprocess.TimeoutExpired as error:
            raise ProviderTimeout(provider, f'{describe(entry)} timed out') from error

    def research(self, entry, text, directory, session=None, resume=False, workdir=None):
        """Plain-text research with web tools; only Grok continues an earlier session."""
        write_json(directory / 'model.json', entry)
        timeout = entry.get('timeout_s', DEFAULT_TIMEOUT_S)
        provider = entry['provider']
        try:
            if provider == 'grok':
                return grok(self.config, entry, text, directory, session, resume, workdir, timeout)
            (directory / 'prompt.md').write_text(text)
            if provider == 'codex':
                return codex(self.config, entry, text, directory, None, timeout)
            if provider == 'claude':
                return claude(self.config, entry, text, directory, None, timeout)
        except subprocess.TimeoutExpired as error:
            raise ProviderTimeout(provider, f'{describe(entry)} timed out') from error
        raise ValueError(f'Unknown provider: {provider}')


def served_model(usage, requested=None):
    """The model a tool reports it used; with several, the requested one or the busiest."""
    names = [name for name in usage if isinstance(name, str)]
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    matching = [name for name in names if requested and requested in name]
    if len(matching) == 1:
        return matching[0]
    return max(names, key=lambda name: (usage[name] or {}).get('outputTokens', 0))


def attempt_model(folder):
    """The model a saved attempt used, from its own records; None when they do not say."""
    folder = Path(folder)
    settings = read_json(folder / 'model.json', None)
    receipt = read_json(folder / 'receipt.json', {})
    requested = None
    for value in (settings, receipt.get('model'), receipt):
        if isinstance(value, dict) and isinstance(value.get('model'), str):
            requested = value['model']
            break
        if isinstance(value, str):
            requested = value
            break
    stdout = folder / 'stdout.log'
    if stdout.is_file():
        try:
            envelope = json.loads(stdout.read_text(errors='replace'))
        except ValueError:
            envelope = None
        if isinstance(envelope, dict) and isinstance(envelope.get('modelUsage'), dict):
            name = served_model(envelope['modelUsage'], requested)
            if name:
                return name
    return requested


# Saved attempt folder prefixes and the run file each stage's result must equal.
STAGE_ATTEMPTS = {
    'research': (('independent-research', 'research'), 'research-notes.md'),
    'reconcile': (('reconcile',), 'reconciled-research.md'),
    'format': (('format-reconciled',), 'reconciled-structured.json'),
}


def stage_model(root, stage):
    """The model whose saved result is this field's current output for a stage."""
    root = Path(root)
    prefixes, output = STAGE_ATTEMPTS[stage]
    path = root / output
    if not path.is_file():
        return None
    if output.endswith('.json'):
        wanted = read_json(path)
    else:
        wanted = path.read_text()
    found = set()
    for folder in sorted((root / 'attempts').glob('*-*')):
        name = folder.name.rsplit('-', 1)[0]
        result = folder / 'result.json'
        if name not in prefixes or not result.is_file():
            continue
        value = read_json(result)
        if output.endswith('.md'):
            # Older runs saved the text itself; the saved notes may end in one newline.
            value = value.get('text') if isinstance(value, dict) else value
            matches = isinstance(value, str) and value.rstrip('\n') == wanted.rstrip('\n')
        else:
            matches = value == wanted
        if matches:
            found.add(attempt_model(folder))
    found.discard(None)
    return found.pop() if len(found) == 1 else None

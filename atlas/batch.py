"""Shared machinery for passes run over many breakthroughs at once.

Model calls and network fetches run in worker threads; every write to atlas/core, every
rebuild and every commit goes through one Writer, which holds a single lock. A provider that
reports exhaustion sets `stop`: workers not yet started return without calling a model, the
run keeps what is done and commits it.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from ingestion.providers import ProviderExhausted

from . import core as records

# The capture archive (atlas/data/added/captures.json) is one file rewritten whole on every
# change, so captures from several threads take turns.
ARCHIVE_LOCK = threading.RLock()


class Stopped(Exception):
    """The run is stopping after a provider reported exhaustion."""


class Writer:
    """Serialises writes; commits atlas/core every `every` completed breakthroughs."""

    def __init__(self, every, commit, message, core=records.CORE):
        self.lock = threading.RLock()
        self.every = every
        self.commit = commit
        self.message = message
        self.core = core
        self.pending = []
        self.done = []

    def write(self, identifier, action):
        """Run action() under the lock and count identifier as done."""
        with self.lock:
            result = action()
            self.pending.append(identifier)
            self.done.append(identifier)
            if self.commit and len(self.pending) >= self.every:
                self.flush()
            return result

    def flush(self):
        """Check atlas/core and commit what is pending."""
        with self.lock:
            if not self.pending:
                return
            problems = records.check(records.load(self.core))
            if problems:
                raise ValueError('atlas/core check failed:\n' + '\n'.join(problems))
            if self.commit:
                records.commit(self.message(self.pending))
            self.pending = []


PRINT_LOCK = threading.Lock()


def run(identifiers, work, workers, report=None):
    """Call work(identifier, stop) for each identifier on `workers` threads, and
    report(identifier, outcome) as each finishes. Returns ({identifier: outcome} in input
    order, whether a provider reported exhaustion). An outcome is ('done', value),
    ('failed', message) or ('stopped', None). One failure does not stop the others."""
    stop = threading.Event()
    outcomes = {}

    def attempt(identifier):
        if stop.is_set():
            return 'stopped', None
        try:
            return 'done', work(identifier, stop)
        except Stopped:
            return 'stopped', None
        except ProviderExhausted as error:
            stop.set()
            return 'failed', f'{error}; stopping the run'
        except Exception as error:  # noqa: BLE001 - one breakthrough must not end the run
            return 'failed', f'{type(error).__name__}: {error}'

    def one(identifier):
        outcome = attempt(identifier)
        if report is not None:
            with PRINT_LOCK:
                report(identifier, outcome)
        return outcome

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {identifier: pool.submit(one, identifier) for identifier in identifiers}
        for identifier, future in futures.items():
            outcomes[identifier] = future.result()
    return outcomes, stop.is_set()

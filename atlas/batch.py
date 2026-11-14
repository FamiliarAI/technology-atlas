"""Shared machinery for passes run over many breakthroughs at once.

Model calls and network fetches run in worker threads; every write to atlas/core, every
rebuild and every commit goes through one Writer, which holds a single lock. A provider that
reports exhaustion sets `stop`: workers not yet started return without calling a model, the
run keeps what is done and commits it.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

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


class Adaptive:
    """A worker count that finds its own level.

    Starts at `start` and, while no call is throttled, adds a quarter (at least 2) each time
    as many calls have finished as there are workers, up to `most`. When `trigger` calls have
    been throttled since the last change (the provider refused or limited connections), or the
    machine's load passes twice its processors, that level is the failure point: the count
    drops to `share` of it and stays there. Throttling again at the lower level lowers it
    again by the same share. The level settled on is saved to `path`, and a later run starts
    there instead of climbing again; delete the file to search afresh.
    """

    def __init__(
        self,
        start=6,
        most=48,
        share=0.8,
        trigger=2,
        path=None,
        throttled=None,
        load=None,
        log=print,
    ):
        from ingestion.providers import throttled as counted

        self.most = most
        self.share = share
        self.trigger = trigger
        self.path = Path(path) if path else None
        self.throttled = throttled or counted
        self.load = load or self._load
        self.log = log
        self.condition = threading.Condition()
        self.active = 0
        self.settled = False
        self.ceiling = None
        saved = self._saved()
        if saved:
            self.limit = min(saved['workers'], most)
            self.ceiling = saved.get('ceiling')
            self.settled = True
            self.log(f'Workers: {self.limit}, settled earlier (failure point {self.ceiling})')
        else:
            self.limit = min(start, most)
            self.log(f'Workers: starting at {self.limit}, rising to at most {most}')
        self.base = self.throttled()
        self.finished = 0

    @staticmethod
    def _load():
        try:
            return os.getloadavg()[0] / (os.cpu_count() or 1)
        except OSError:
            return 0

    def _saved(self):
        if not self.path or not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text())
        except ValueError:
            return None
        return value if isinstance(value.get('workers'), int) and value['workers'] > 0 else None

    def _save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            value = {
                'workers': self.limit,
                'ceiling': self.ceiling,
                'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            }
            self.path.write_text(json.dumps(value, indent=1) + '\n')

    def acquire(self):
        with self.condition:
            while self.active >= self.limit:
                self.condition.wait()
            self.active += 1

    def release(self):
        """One call finished: free its place and decide whether to change the count."""
        with self.condition:
            self.active -= 1
            self.finished += 1
            throttled = self.throttled() - self.base
            # Load is a minute's average: judge it only once calls at the current level finish.
            overloaded = self.finished >= max(1, self.limit // 2) and self.load() > 2
            if throttled >= self.trigger or overloaded:
                reason = (
                    f'{throttled} calls throttled' if throttled >= self.trigger else 'load high'
                )
                self.ceiling = self.limit
                self.limit = max(1, int(self.ceiling * self.share))
                self.settled = True
                self._save()
                self.log(
                    f'Workers: {reason} at {self.ceiling}; '
                    f'settling at {self.limit} ({round(100 * (1 - self.share))}% below)'
                )
                self._restart()
            elif not self.settled and self.finished >= self.limit and self.limit < self.most:
                self.limit = min(self.most, self.limit + max(2, self.limit // 4))
                self.log(f'Workers: no throttling; rising to {self.limit}')
                self._restart()
            self.condition.notify_all()

    def _restart(self):
        self.base = self.throttled()
        self.finished = 0


def run(identifiers, work, workers, report=None):
    """Call work(identifier, stop) for each identifier on `workers` threads (a number, or an
    Adaptive that changes the count as it goes), and report(identifier, outcome) as each
    finishes. Returns ({identifier: outcome} in input order, whether a provider reported
    exhaustion). An outcome is ('done', value), ('failed', message) or ('stopped', None). One
    failure does not stop the others."""
    stop = threading.Event()
    outcomes = {}
    adaptive = workers if isinstance(workers, Adaptive) else None

    def attempt(identifier):
        if adaptive is not None:
            adaptive.acquire()
            try:
                return attempt_one(identifier)
            finally:
                adaptive.release()
        return attempt_one(identifier)

    def attempt_one(identifier):
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

    threads = adaptive.most if adaptive is not None else workers
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {identifier: pool.submit(one, identifier) for identifier in identifiers}
        for identifier, future in futures.items():
            outcomes[identifier] = future.result()
    return outcomes, stop.is_set()

"""Live notebook activity bars, elapsed time and bounded log tails; no widgets needed.

An indeterminate bar means the tool has not supplied a trustworthy overall
percentage. Only successful completion fills the bar. Nested tasks share a row.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import html
import re
import threading
import time
from pathlib import Path

_ACTIVE = ContextVar('atum_notebook_progress', default=None)


def _notebook_display():
    try:
        from IPython import get_ipython
        shell = get_ipython()
        if shell is not None and getattr(shell, 'kernel', None) is not None:
            from IPython.display import HTML, display
            return HTML, display
    except ImportError:
        pass
    return None


class Activity:
    def __init__(self, title, logs=(), interval=1.):
        self.title = title
        self.phase = title
        self.detail = ''
        self.logs = list(dict.fromkeys(map(Path, logs)))
        self.interval = interval
        self.started = time.monotonic()
        self.started_unix = time.time()
        self.status = 'RUNNING'
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._thread = None
        self._handle = None
        self._display = _notebook_display()
        self._last_console = -10.

    def watch(self, *paths):
        with self._lock:
            for path in map(Path, paths):
                if path not in self.logs:
                    self.logs.append(path)

    def message(self, detail):
        with self._lock:
            self.detail = str(detail)

    def _latest_log(self):
        candidates = []
        for path in self.logs:
            try:
                stamp = path.stat().st_mtime
                if stamp >= self.started_unix:
                    candidates.append((stamp, path))
            except OSError:
                pass
        for _, path in sorted(candidates, reverse=True):
            try:
                with path.open('rb') as stream:
                    stream.seek(0, 2)
                    stream.seek(max(0, stream.tell()-8192))
                    tail = stream.read(8192).decode(errors='replace').splitlines()
                lines = [re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line).strip() for line in tail]
                line = next((line for line in reversed(lines) if line), '')
                if line:
                    return line[-220:], path
            except OSError:
                pass
        return '', self.logs[0] if self.logs else None

    def markup(self):
        with self._lock:
            elapsed = time.monotonic()-self.started
            line, log = self._latest_log()
            detail = self.detail or line or 'Working — waiting for the tool to report its next result.'
            color = {'RUNNING':'#52dfdd','DONE':'#52b788','FAILED':'#ef7777','CANCELLED':'#e8b55b'}[self.status]
            value = '' if self.status == 'RUNNING' else ' value="1"' if self.status == 'DONE' else ' value="0"'
            esc = html.escape
            log_html = '<div style="margin-top:5px;overflow-wrap:anywhere">Log: <code>'+esc(str(log))+'</code></div>' if log else ''
            return (f'<div role="status" aria-live="polite" style="border:1px solid {color};border-radius:8px;padding:12px;margin:8px 0;font:14px system-ui">'
                    f'<strong>{esc(self.title)}</strong> · <span style="font-weight:700">{self.status}</span> · {elapsed:.1f} s elapsed'
                    f'<progress max="1"{value} aria-label="{esc(self.title,quote=True)}" style="display:block;width:100%;height:15px;margin:8px 0;accent-color:{color}"></progress>'
                    f'<div>{esc(self.phase)}</div><div style="margin-top:5px;white-space:pre-wrap;overflow-wrap:anywhere">{esc(detail)}</div>{log_html}</div>')

    def _render(self, final=False):
        if self._display:
            HTML, display = self._display
            if self._handle is None:
                self._handle = display(HTML(self.markup()), display_id=True)
            else:
                self._handle.update(HTML(self.markup()))
        else:
            elapsed = time.monotonic()-self.started
            if final or elapsed-self._last_console >= 10:
                line, log = self._latest_log()
                detail = self.detail or line
                print(f'{self.title}: {self.status} · {elapsed:.1f}s · {self.phase}'+(f' · {detail}' if detail else '')+(f' · log: {log}' if log else ''), flush=True)
                self._last_console = elapsed

    def __enter__(self):
        try:
            self._render()
        except Exception:
            self._display = None
            self._render()
        def heartbeat():
            while not self._stop.wait(self.interval):
                try:
                    self._render()
                except Exception:
                    # A frontend disconnect must not fail a running Quartus command.
                    pass
        self._thread = threading.Thread(target=heartbeat, name='notebook-progress', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, kind, error, traceback):
        self._stop.set()
        self._thread.join(timeout=2)
        self.status = 'DONE' if kind is None else 'CANCELLED' if issubclass(kind, KeyboardInterrupt) else 'FAILED'
        self.detail = 'Completed successfully.' if kind is None else str(error) or self.status
        try:
            self._render(final=True)
        except Exception:
            self._display = None
            self._render(final=True)
        return False


@contextmanager
def progress(title, logs=()):
    """Wrap a cell or a stage; one updating output survives nested calls."""
    parent = _ACTIVE.get()
    if parent is not None:
        previous = parent.phase, parent.detail
        parent.phase, parent.detail = title, ''
        parent.watch(*logs)
        try:
            yield parent
        finally:
            parent.phase, parent.detail = previous
    else:
        activity = Activity(title, logs)
        token = _ACTIVE.set(activity)
        try:
            with activity:
                yield activity
        finally:
            _ACTIVE.reset(token)


def task(title):
    """Add feedback without changing the wrapped API or its return value."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with progress(title):
                return function(*args, **kwargs)
        return wrapped
    return decorate

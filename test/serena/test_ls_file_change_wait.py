"""
The poll that notifies the language servers of external file changes waits until they have processed them.

A server rebuilds its cross-file state asynchronously after ``workspace/didChangeWatchedFiles`` and answers the
requests that arrive meanwhile from the part rebuilt so far: after a git checkout moving ~900 files, pyrefly answered
a references request 50 ms into its recheck with the defining file alone (2 references of 104).
"""

import os
import threading
import time
from pathlib import Path

import pytest

from serena.ls_manager import LanguageServerFileChangeNotifier
from solidlsp.language_servers.pyrefly_server import PyreflyLanguageServer


class _FakeProject:
    def __init__(self, root: Path, files: list[str]):
        self.project_root = str(root)
        self._files = files

    def gather_source_files(self) -> list[str]:
        return self._files


class _RecordingLanguageServer:
    """Records, in one shared journal, the calls the notifier makes on it."""

    def __init__(self, name: str, journal: list[str]):
        self.ls_id = name
        self._journal = journal
        self.server = self
        self.notify = self

    def expect_watched_files_processing(self) -> None:
        self._journal.append(f"expect {self.ls_id}")

    def did_change_watched_files(self, params: dict) -> None:
        self._journal.append(f"notify {self.ls_id} ({len(params['changes'])})")

    def wait_for_watched_files_processing(self) -> None:
        self._journal.append(f"wait {self.ls_id}")


class _FakeManager:
    def __init__(self, servers: list[_RecordingLanguageServer]):
        self._servers = servers

    def iter_language_servers(self):
        yield from self._servers


def test_poll_notifies_every_server_before_waiting_for_any(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    journal: list[str] = []
    servers = [_RecordingLanguageServer("python", journal), _RecordingLanguageServer("typescript", journal)]
    notifier = LanguageServerFileChangeNotifier(_FakeProject(tmp_path, ["a.py"]), _FakeManager(servers))
    later = time.time() + 10
    os.utime(tmp_path / "a.py", (later, later))

    assert notifier.poll_and_notify() == 1

    # every server rebuilds concurrently, so all are notified before the first wait; and every one is waited for,
    # because the next tool's poll finds nothing to notify and would answer from a server still rebuilding
    assert journal == [
        "expect python",
        "notify python (1)",
        "expect typescript",
        "notify typescript (1)",
        "wait python",
        "wait typescript",
    ]


def test_poll_without_changes_waits_for_nothing(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    journal: list[str] = []
    notifier = LanguageServerFileChangeNotifier(
        _FakeProject(tmp_path, ["a.py"]),
        _FakeManager([_RecordingLanguageServer("python", journal)]),
    )

    assert notifier.poll_and_notify() == 0
    assert journal == []


def _pyrefly_without_process(monkeypatch: pytest.MonkeyPatch, start_grace: float = 0.2) -> PyreflyLanguageServer:
    server = object.__new__(PyreflyLanguageServer)
    server._indexing_complete = threading.Event()
    server._indexing_complete.set()
    server._active_progress_tokens = set()
    monkeypatch.setattr(PyreflyLanguageServer, "WATCHED_FILES_PROGRESS_START_GRACE", start_grace)
    return server


def _report_progress(server: PyreflyLanguageServer, token: str, begin_after: float, end_after: float) -> threading.Thread:
    """Plays pyrefly's $/progress handler: a recheck begins, then ends and drains the tokens."""

    def recheck() -> None:
        time.sleep(begin_after)
        server._active_progress_tokens.add(token)
        time.sleep(end_after)
        server._active_progress_tokens.discard(token)
        server._indexing_complete.set()

    thread = threading.Thread(target=recheck)
    thread.start()
    return thread


def test_pyrefly_wait_lasts_until_the_recheck_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _pyrefly_without_process(monkeypatch)
    server.expect_watched_files_processing()
    recheck = _report_progress(server, "pyrefly-progress-2", begin_after=0.05, end_after=0.5)

    started = time.monotonic()
    server.wait_for_watched_files_processing()
    waited = time.monotonic() - started
    recheck.join()

    assert waited >= 0.5, f"returned {waited:.2f} s into a 0.55 s recheck"
    assert not server._active_progress_tokens


def test_pyrefly_wait_returns_at_once_when_the_recheck_already_ended(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _pyrefly_without_process(monkeypatch, start_grace=5.0)
    server.expect_watched_files_processing()
    _report_progress(server, "pyrefly-progress-2", begin_after=0, end_after=0).join()

    started = time.monotonic()
    server.wait_for_watched_files_processing()

    assert time.monotonic() - started < 1.0


def test_pyrefly_wait_gives_up_on_a_recheck_that_never_begins(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _pyrefly_without_process(monkeypatch, start_grace=0.2)
    server.expect_watched_files_processing()

    started = time.monotonic()
    server.wait_for_watched_files_processing()
    waited = time.monotonic() - started

    assert 0.2 <= waited < 1.0
    # the next startup-style wait must not block on a notification that started nothing
    assert server._indexing_complete.is_set()

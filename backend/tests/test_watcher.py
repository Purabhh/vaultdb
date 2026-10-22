import threading
import time
from pathlib import Path

import pytest

from vaultdb.watcher import VaultWatcher

DEBOUNCE = 0.6


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str]] = []
        self.lock = threading.Lock()

    def __call__(self, vault: str, path: str, kind: str) -> None:
        with self.lock:
            self.events.append((vault, path, kind))

    def wait_for(self, n: int, timeout: float = 6.0) -> list[tuple[str, str, str]]:
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                if len(self.events) >= n:
                    return list(self.events)
            time.sleep(0.05)
        return list(self.events)


@pytest.fixture
def watched(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    rec = Recorder()
    w = VaultWatcher(rec, debounce=DEBOUNCE)
    w.watch("V", str(root))
    time.sleep(0.5)  # let the OS watcher settle
    yield root, rec, w
    w.stop()


def test_debounces_rapid_writes(watched) -> None:
    root, rec, _ = watched
    note = root / "a.md"
    for i in range(5):
        note.write_text(f"v{i}", encoding="utf-8")
        time.sleep(0.1)
    events = rec.wait_for(1)
    time.sleep(DEBOUNCE * 3)
    events = [e for e in rec.events if e[1] == str(note)]
    assert len(events) == 1 and events[0][0] == "V" and events[0][2] in ("create", "modify")


def test_reports_paths_in_the_watched_root_style(watched) -> None:
    root, rec, _ = watched
    (root / "b.md").write_text("x", encoding="utf-8")
    events = rec.wait_for(1)
    assert events and events[0][1] == str(root / "b.md")


def test_ignores_non_markdown_and_trash(watched) -> None:
    root, rec, _ = watched
    (root / "image.png").write_bytes(b"x")
    (root / ".trash").mkdir()
    (root / ".trash" / "old.md").write_text("x", encoding="utf-8")
    time.sleep(DEBOUNCE + 1.5)
    assert rec.events == []


def test_delete_reported_with_delete_kind(watched) -> None:
    root, rec, _ = watched
    note = root / "c.md"
    note.write_text("x", encoding="utf-8")
    rec.wait_for(1)
    time.sleep(DEBOUNCE)
    note.unlink()
    events = rec.wait_for(2)
    assert events[-1][1] == str(note) and events[-1][2] == "delete"


def test_unwatch_stops_events(watched) -> None:
    root, rec, w = watched
    w.unwatch("V")
    (root / "d.md").write_text("x", encoding="utf-8")
    time.sleep(DEBOUNCE + 1.5)
    assert rec.events == []

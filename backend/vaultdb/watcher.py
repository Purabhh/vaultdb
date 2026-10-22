"""Watch vault folders and report .md changes after a quiet period (port of watcher.rs)."""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

OnChange = Callable[[str, str, str], None]  # (vault_name, path, kind) with kind in create/modify/delete


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "VaultWatcher", vault: str, root: str) -> None:
        self.watcher, self.vault, self.root = watcher, vault, root
        self.real_root = os.path.realpath(root)

    def _display(self, path: str) -> str:
        """Report paths in the same form as the vault's source_path (FSEvents may resolve symlinks)."""
        if path.startswith(self.real_root) and self.real_root != self.root:
            return self.root + path[len(self.real_root):]
        return path

    def _queue(self, path: str, kind: str) -> None:
        if not path.endswith(".md") or ".trash" in path:
            return
        self.watcher._queue(self.vault, self._display(path), kind)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._queue(event.src_path, "create")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._queue(event.src_path, "modify")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._queue(event.src_path, "delete")

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._queue(event.src_path, "delete")
            self._queue(event.dest_path, "create")


class VaultWatcher:
    def __init__(self, on_change: OnChange, debounce: float = 2.0) -> None:
        self.on_change = on_change
        self.debounce = debounce
        self._observer = Observer()
        self._observer.daemon = True
        self._started = False
        self._watches: dict[str, object] = {}
        self._pending: dict[tuple[str, str], tuple[str, float]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._flusher = threading.Thread(target=self._flush_loop, daemon=True)
        self._flusher.start()

    def watch(self, vault_name: str, source_path: str) -> None:
        self.unwatch(vault_name)
        handler = _Handler(self, vault_name, source_path)
        self._watches[vault_name] = self._observer.schedule(handler, source_path, recursive=True)
        if not self._started:
            self._observer.start()
            self._started = True

    def unwatch(self, vault_name: str) -> None:
        watch = self._watches.pop(vault_name, None)
        if watch is not None:
            self._observer.unschedule(watch)
        with self._lock:
            for key in [k for k in self._pending if k[0] == vault_name]:
                del self._pending[key]

    def stop(self) -> None:
        self._stop.set()
        if self._started:
            self._observer.stop()
            self._observer.join(timeout=5)

    def _queue(self, vault: str, path: str, kind: str) -> None:
        if vault not in self._watches:
            return
        with self._lock:
            self._pending[(vault, path)] = (kind, time.monotonic())

    def _flush_loop(self) -> None:
        while not self._stop.wait(0.1):
            now = time.monotonic()
            with self._lock:
                ready = [(k, v[0]) for k, v in self._pending.items() if now - v[1] >= self.debounce]
                for k, _ in ready:
                    del self._pending[k]
            for (vault, path), kind in ready:
                try:
                    self.on_change(vault, path, kind)
                except Exception:  # a failing callback must not kill the watcher
                    pass

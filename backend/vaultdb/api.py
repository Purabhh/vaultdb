"""The bridge pywebview exposes to the React UI as window.pywebview.api.

The UI keeps calling `invoke(command, args)` with the same command names and camelCase
argument keys it used with Tauri; this maps them onto VaultService.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

from .config import import_legacy_echidna, load_vaults
from .service import VaultError, VaultService


class Api:
    def __init__(self, service: VaultService, watcher=None, window=None) -> None:
        # Underscored so pywebview does not expose these objects to JavaScript.
        self._service = service
        self._watcher = watcher
        self._window = window
        self._lock = threading.Lock()
        # Paths the app itself just wrote: the watcher reports them ~2 s later, and treating
        # those as outside edits would reload the open note and re-embed it a second time.
        self._own_writes: dict[str, float] = {}
        s = service
        self._handlers: dict[str, Callable[[dict], Any]] = {
            "init_manager": lambda a: self._init_manager(),
            "list_vaults": lambda a: s.list_vaults(),
            "create_vault": lambda a: s.create_vault(a["name"], a["sourcePath"]),
            "create_new_vault": lambda a: s.create_new_vault(a["name"], a["parentDir"]),
            "delete_vault": lambda a: self._delete_vault(a["name"]),
            "search_vault": lambda a: s.search_vault(a["vaultName"], a["query"], a.get("limit") or 10),
            "get_graph": lambda a: s.get_graph(a["vaultName"]),
            "get_file_tree": lambda a: s.get_file_tree(a["vaultName"]),
            "get_note_detail": lambda a: s.get_note_detail(a["vaultName"], a["notePath"]),
            "save_note": lambda a: self._wrote(a["notePath"], s.save_note(a["vaultName"], a["notePath"], a["content"])),
            "reembed_note": lambda a: s.reembed_note(a["vaultName"], a["notePath"]),
            "create_note": lambda a: self._wrote_result(s.create_note(a["vaultName"], a["parentDir"], a["fileName"])),
            "delete_note": lambda a: self._wrote(a["notePath"], s.delete_note(a["vaultName"], a["notePath"])),
            "create_folder": lambda a: s.create_folder(a["vaultName"], a["parentDir"], a["folderName"]),
            "delete_folder": lambda a: s.delete_folder(a["vaultName"], a["folderPath"]),
            "rename_item": lambda a: self._wrote_result(
                s.rename_item(a["vaultName"], a["oldPath"], a["newName"]), also=a["oldPath"]),
            "watch_vault": lambda a: self._watch(a["vaultName"]),
            "pick_folder": lambda a: self._pick_folder(),
        }

    # --- exposed to JavaScript -----------------------------------------------------------
    def invoke(self, command: str, args: dict | None = None) -> Any:
        handler = self._handlers.get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        if command == "pick_folder":  # a modal dialog; don't hold the lock while it is open
            return handler(args or {})
        with self._lock:
            try:
                return handler(args or {})
            except VaultError as e:
                raise Exception(str(e)) from None

    def commands(self) -> list[str]:
        return sorted(self._handlers)

    # --- called from Python (underscored so pywebview does not expose them to JavaScript) -----
    _OWN_WRITE_WINDOW_S = 5.0

    def _set_window(self, window) -> None:
        self._window = window

    def _emit(self, event: str, payload: dict) -> None:
        if self._window is not None:
            self._window.evaluate_js(
                f"window.__vaultdbEmit && window.__vaultdbEmit({json.dumps(event)}, {json.dumps(payload)})")

    def _on_file_change(self, vault_name: str, path: str, kind: str) -> None:
        wrote_at = self._own_writes.get(path)
        if wrote_at is not None and time.monotonic() - wrote_at < self._OWN_WRITE_WINDOW_S:
            return
        self._emit("vault-file-change", {"vault_name": vault_name, "path": path, "kind": kind})

    def _wrote(self, path: str, result=None):
        self._own_writes[path] = time.monotonic()
        return result

    def _wrote_result(self, new_path: str, also: str | None = None) -> str:
        if also:
            self._wrote(also)
        return self._wrote(new_path, new_path)

    # --- handlers --------------------------------------------------------------------------
    def _init_manager(self) -> None:
        """Import the old echidna vault list once, then bring every vault's index up to date."""
        if import_legacy_echidna():
            self._service.vaults = load_vaults()
        for name in list(self._service.vaults):
            try:
                self._service.refresh_vault(name)
            except VaultError:
                pass  # e.g. folder moved; the vault stays listed and its commands report the error

    def _delete_vault(self, name: str) -> None:
        if self._watcher is not None:
            self._watcher.unwatch(name)
        self._service.delete_vault(name)

    def _watch(self, vault_name: str) -> None:
        info = self._service.vaults.get(vault_name)
        if info is None:
            raise VaultError(f"Vault '{vault_name}' not found")
        if self._watcher is not None:
            self._watcher.watch(vault_name, info.source_path)

    def _pick_folder(self) -> str | None:
        if self._window is None:
            return None
        import webview  # imported lazily so tests and the MCP server never need a GUI

        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None

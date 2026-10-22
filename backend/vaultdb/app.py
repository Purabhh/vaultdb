"""VaultDB desktop app: the React UI in a native window (pywebview), backed by the Python core.

    uv run vaultdb          # uses the built UI in dist/ (run `npm run build` first)
    uv run vaultdb --dev    # uses the Vite dev server on http://localhost:5173
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .api import Api
from .config import db_path, import_legacy_echidna
from .embedder import Embedder
from .service import VaultService
from .store import Store
from .watcher import VaultWatcher

DEV_URL = "http://localhost:5173"


def _frontend_roots() -> list[Path]:
    """Where dist/ can live: inside a PyInstaller bundle, or at the repo root."""
    roots = []
    if hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS))
    roots.append(Path(__file__).resolve().parents[2])
    return roots


def frontend_url(dev: bool) -> str:
    if dev:
        return DEV_URL
    for root in _frontend_roots():
        index = root / "dist" / "index.html"
        if index.is_file():
            return str(index)
    raise SystemExit("VaultDB: the UI is not built. Run `npm run build` in the repo, or start with --dev.")


def main(argv: list[str] | None = None) -> None:
    import webview

    parser = argparse.ArgumentParser(description="VaultDB desktop app")
    parser.add_argument("--dev", action="store_true", help="load the Vite dev server instead of dist/")
    args = parser.parse_args(argv)

    url = frontend_url(args.dev)
    import_legacy_echidna()
    service = VaultService(Store(db_path()), Embedder())
    api = Api(service)
    watcher = VaultWatcher(api._on_file_change)
    api._watcher = watcher
    window = webview.create_window("VaultDB", url, js_api=api, width=1200, height=800, min_size=(900, 600))
    api._set_window(window)
    try:
        webview.start()
    finally:
        watcher.stop()
        service.store.close()


if __name__ == "__main__":
    main()

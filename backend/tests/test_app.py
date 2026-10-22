from pathlib import Path

import pytest

from vaultdb import app


def test_dev_mode_uses_vite_server() -> None:
    assert app.frontend_url(dev=True) == "http://localhost:5173"


def test_built_frontend_is_found(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<html></html>")
    monkeypatch.setattr(app, "_frontend_roots", lambda: [tmp_path])
    assert app.frontend_url(dev=False) == str(tmp_path / "dist" / "index.html")


def test_missing_build_is_a_clear_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app, "_frontend_roots", lambda: [tmp_path])
    with pytest.raises(SystemExit, match="npm run build"):
        app.frontend_url(dev=False)

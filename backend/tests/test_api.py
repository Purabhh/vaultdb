import json
import shutil
from pathlib import Path

import pytest

from vaultdb.api import Api
from vaultdb.service import VaultService
from vaultdb.store import Store

FRONTEND_COMMANDS = {
    "init_manager", "list_vaults", "get_graph", "get_file_tree", "watch_vault", "create_vault",
    "create_new_vault", "delete_vault", "search_vault", "get_note_detail", "create_note", "delete_note",
    "create_folder", "delete_folder", "rename_item", "save_note", "reembed_note", "pick_folder",
}


class StubWindow:
    def __init__(self, folder: str | None = None) -> None:
        self.js: list[str] = []
        self.folder = folder

    def evaluate_js(self, code: str) -> None:
        self.js.append(code)

    def create_file_dialog(self, dialog_type, **kwargs):
        return (self.folder,) if self.folder else None


class StubWatcher:
    def __init__(self) -> None:
        self.watched: dict[str, str] = {}

    def watch(self, vault: str, path: str) -> None:
        self.watched[vault] = path

    def unwatch(self, vault: str) -> None:
        self.watched.pop(vault, None)


@pytest.fixture
def api(tmp_path: Path, data_dir: Path, fake_embedder):
    window = StubWindow(folder=str(tmp_path))
    a = Api(VaultService(Store(tmp_path / "db.sqlite3"), fake_embedder), watcher=StubWatcher(), window=window)
    return a


def test_every_frontend_command_is_mapped(api) -> None:
    assert FRONTEND_COMMANDS <= set(api.commands())


def test_camelcase_args_reach_service(api, fixture_vault: Path) -> None:
    info = api.invoke("create_vault", {"name": "V", "sourcePath": str(fixture_vault)})
    assert info["name"] == "V" and api.invoke("list_vaults", None) == [info]
    hits = api.invoke("search_vault", {"vaultName": "V", "query": "glass button", "limit": 3})
    assert len(hits) <= 3 and hits
    note = api.invoke("create_note", {"vaultName": "V", "parentDir": str(fixture_vault), "fileName": "x"})
    assert Path(note).exists()
    detail = api.invoke("get_note_detail", {"vaultName": "V", "notePath": str(fixture_vault / "Notes/alpha.md")})
    assert detail["title"] == "alpha"


def test_watch_and_delete_vault_drive_the_watcher(api, fixture_vault: Path) -> None:
    api.invoke("create_vault", {"name": "V", "sourcePath": str(fixture_vault)})
    api.invoke("watch_vault", {"vaultName": "V"})
    assert api._watcher.watched == {"V": str(fixture_vault)}
    api.invoke("delete_vault", {"name": "V"})
    assert api._watcher.watched == {}


def test_pick_folder_returns_path_or_none(api, tmp_path: Path) -> None:
    assert api.invoke("pick_folder", {}) == str(tmp_path)
    api._window.folder = None
    assert api.invoke("pick_folder", {}) is None


def test_unknown_command_raises(api) -> None:
    with pytest.raises(ValueError, match="Unknown command: nope"):
        api.invoke("nope", {})


def test_service_errors_surface_as_plain_messages(api) -> None:
    with pytest.raises(Exception, match="Vault 'Missing' not found"):
        api.invoke("get_file_tree", {"vaultName": "Missing"})


def test_watcher_event_is_emitted_to_window(api) -> None:
    api._on_file_change("V", "/v/a.md", "modify")
    [code] = api._window.js
    assert "vault-file-change" in code
    payload = json.loads(code.split("vault-file-change\", ", 1)[1].rsplit(")", 1)[0])
    assert payload == {"vault_name": "V", "path": "/v/a.md", "kind": "modify"}


def test_init_manager_imports_legacy_echidna(api, data_dir: Path, fixture_vault: Path) -> None:
    legacy = data_dir.parent / "echidna"
    legacy.mkdir()
    (legacy / "vaults.json").write_text(json.dumps(
        {"vaults": {"Old": {"name": "Old", "source_path": str(fixture_vault), "note_count": 1}}}))
    api.invoke("init_manager", None)
    assert [v["name"] for v in api.invoke("list_vaults", None)] == ["Old"]
    # imported vaults are indexed on startup, so graph and search work right away
    assert api.invoke("get_graph", {"vaultName": "Old"})["nodes"]
    assert api.invoke("search_vault", {"vaultName": "Old", "query": "glass button"})


def test_init_manager_refreshes_notes_changed_while_closed(api, fixture_vault: Path) -> None:
    api.invoke("create_vault", {"name": "V", "sourcePath": str(fixture_vault)})
    (fixture_vault / "Notes" / "added-later.md").write_text("# Later\n\nabout quokkas\n", encoding="utf-8")
    api.invoke("init_manager", None)
    hits = api.invoke("search_vault", {"vaultName": "V", "query": "quokkas"})
    assert hits and hits[0]["path"].endswith("added-later.md")


def test_init_manager_survives_a_missing_vault_folder(api, tmp_path: Path, fixture_vault: Path) -> None:
    gone = tmp_path / "gone"
    shutil.copytree(fixture_vault, gone)
    api.invoke("create_vault", {"name": "Gone", "sourcePath": str(gone)})
    shutil.rmtree(gone)
    api.invoke("init_manager", None)  # does not raise
    assert [v["name"] for v in api.invoke("list_vaults", None)] == ["Gone"]


def test_app_own_save_does_not_bounce_back_as_external_change(api, fixture_vault: Path) -> None:
    api.invoke("create_vault", {"name": "V", "sourcePath": str(fixture_vault)})
    note = str(fixture_vault / "Notes/beta.md")
    api.invoke("save_note", {"vaultName": "V", "notePath": note, "content": "# Beta\nedited in app\n"})
    api._on_file_change("V", note, "modify")  # the watcher sees the app's own write
    assert api._window.js == []
    api._on_file_change("V", str(fixture_vault / "Notes/alpha.md"), "modify")  # a real outside edit
    assert len(api._window.js) == 1


def test_only_invoke_and_commands_are_exposed_to_js(api) -> None:
    public = {n for n in dir(api) if not n.startswith("_")}
    assert public == {"invoke", "commands"}

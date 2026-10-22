# PyInstaller spec for the VaultDB desktop app.
# Build (from backend/):  npm run build --prefix ..  &&  uv run pyinstaller ../vaultdb.spec --noconfirm
import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "backend" / "vaultdb_launcher.py")],
    pathex=[str(ROOT / "backend")],
    datas=[(str(ROOT / "dist"), "dist")],  # the built React UI
    hiddenimports=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VaultDB", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="VaultDB")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="VaultDB.app", bundle_identifier="com.purabh.vaultdb")

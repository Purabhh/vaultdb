"""Entry point for the packaged app (PyInstaller needs a plain script, not a package module)."""
from vaultdb.app import main

if __name__ == "__main__":
    main()

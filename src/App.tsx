import { useEffect, useState, useCallback, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import { Sidebar } from "./components/Sidebar";
import { GraphView } from "./components/GraphView";
import { SearchPanel } from "./components/SearchPanel";
import { NoteViewer } from "./components/NoteViewer";
import { VaultInfo, GraphData, SearchResult, FileTreeNode, NoteDetail } from "./types";
import "./App.css";

type View = "graph" | "search" | "note";

function App() {
  const [vaults, setVaults] = useState<VaultInfo[]>([]);
  const [activeVault, setActiveVault] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [fileTree, setFileTree] = useState<FileTreeNode | null>(null);
  const [noteDetail, setNoteDetail] = useState<NoteDetail | null>(null);
  const [selectedNotePath, setSelectedNotePath] = useState<string | null>(null);
  const [currentView, setCurrentView] = useState<View>("graph");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const unlistenRef = useRef<UnlistenFn | null>(null);

  useEffect(() => {
    initApp();

    // Listen for file changes from the Rust watcher
    let cancelled = false;
    listen<{ vault_name: string; path: string; kind: string }>(
      "vault-file-change",
      (event) => {
        if (cancelled) return;
        const { vault_name, path, kind } = event.payload;
        console.log(`[watcher] ${kind}: ${path}`);

        // Refresh file tree on any change
        refreshFileTree();

        // If the currently viewed note was modified externally, reload it
        if (kind === "modify" && path === selectedNotePath) {
          handleSelectNote(path);
        }

        // If deleted and it's the current note, clear it
        if (kind === "delete" && path === selectedNotePath) {
          setNoteDetail(null);
          setSelectedNotePath(null);
          setCurrentView("graph");
        }

        // Auto re-embed modified notes in background
        if (kind === "modify" || kind === "create") {
          invoke("reembed_note", { vaultName: vault_name, notePath: path }).catch(() => {});
        }
      }
    ).then((fn) => {
      if (!cancelled) unlistenRef.current = fn;
    });

    return () => {
      cancelled = true;
      unlistenRef.current?.();
    };
  }, []);

  async function initApp() {
    try {
      await invoke("init_manager");
      const v = await invoke<VaultInfo[]>("list_vaults");
      setVaults(v);
      if (v.length > 0) {
        selectVault(v[0].name);
      }
    } catch (e) {
      setError(`Failed to initialize: ${e}`);
    }
  }

  async function selectVault(name: string) {
    setActiveVault(name);
    setLoading(true);
    setError(null);
    setNoteDetail(null);
    setSelectedNotePath(null);
    try {
      const [graph, tree] = await Promise.all([
        invoke<GraphData>("get_graph", { vaultName: name }),
        invoke<FileTreeNode>("get_file_tree", { vaultName: name }),
      ]);
      setGraphData(graph);
      setFileTree(tree);
      setCurrentView("graph");
      // Start watching this vault for external file changes
      invoke("watch_vault", { vaultName: name }).catch(console.error);
    } catch (e) {
      setError(`Failed to load vault: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  async function refreshFileTree() {
    if (!activeVault) return;
    try {
      const tree = await invoke<FileTreeNode>("get_file_tree", { vaultName: activeVault });
      setFileTree(tree);
    } catch (e) {
      console.error("Failed to refresh file tree:", e);
    }
  }

  async function refreshVaults() {
    const v = await invoke<VaultInfo[]>("list_vaults");
    setVaults(v);
  }

  async function handleCreateVault(name: string, path: string) {
    setLoading(true);
    setError(null);
    try {
      const info = await invoke<VaultInfo>("create_vault", { name, sourcePath: path });
      setVaults((prev) => [...prev, info]);
      selectVault(name);
    } catch (e) {
      setError(`Failed to create vault: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateNewVault(name: string, parentDir: string) {
    setLoading(true);
    setError(null);
    try {
      const info = await invoke<VaultInfo>("create_new_vault", { name, parentDir });
      setVaults((prev) => [...prev, info]);
      selectVault(info.name);
    } catch (e) {
      setError(`Failed to create vault: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteVault(name: string) {
    try {
      await invoke("delete_vault", { name });
      setVaults((prev) => prev.filter((v) => v.name !== name));
      if (activeVault === name) {
        setActiveVault(null);
        setGraphData(null);
        setFileTree(null);
        setNoteDetail(null);
      }
    } catch (e) {
      setError(`Failed to delete vault: ${e}`);
    }
  }

  async function handleSearch(query: string) {
    if (!activeVault || !query.trim()) return;
    setLoading(true);
    try {
      const results = await invoke<SearchResult[]>("search_vault", {
        vaultName: activeVault,
        query,
        limit: 20,
      });
      setSearchResults(results);
      setCurrentView("search");
    } catch (e) {
      setError(`Search failed: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectNote(path: string) {
    if (!activeVault) return;
    setSelectedNotePath(path);
    setLoading(true);
    setError(null);
    try {
      const detail = await invoke<NoteDetail>("get_note_detail", {
        vaultName: activeVault,
        notePath: path,
      });
      setNoteDetail(detail);
      setCurrentView("note");
    } catch (e) {
      setError(`Failed to load note: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  const handleCreateNote = useCallback(async (parentDir: string) => {
    if (!activeVault) return;
    const fileName = prompt("Note name:");
    if (!fileName?.trim()) return;
    try {
      const fullPath = await invoke<string>("create_note", {
        vaultName: activeVault,
        parentDir,
        fileName: fileName.trim(),
      });
      await refreshFileTree();
      await refreshVaults();
      handleSelectNote(fullPath);
    } catch (e) {
      setError(`Failed to create note: ${e}`);
    }
  }, [activeVault]);

  const handleDeleteNote = useCallback(async (notePath: string) => {
    if (!activeVault) return;
    const name = notePath.split("/").pop()?.replace(".md", "") ?? notePath;
    if (!confirm(`Delete "${name}"?`)) return;
    try {
      await invoke("delete_note", { vaultName: activeVault, notePath });
      await refreshFileTree();
      await refreshVaults();
      if (selectedNotePath === notePath) {
        setNoteDetail(null);
        setSelectedNotePath(null);
        setCurrentView("graph");
      }
    } catch (e) {
      setError(`Failed to delete note: ${e}`);
    }
  }, [activeVault, selectedNotePath]);

  const handleCreateFolder = useCallback(async (parentDir: string) => {
    if (!activeVault) return;
    const folderName = prompt("Folder name:");
    if (!folderName?.trim()) return;
    try {
      await invoke<string>("create_folder", {
        vaultName: activeVault,
        parentDir,
        folderName: folderName.trim(),
      });
      await refreshFileTree();
    } catch (e) {
      setError(`Failed to create folder: ${e}`);
    }
  }, [activeVault]);

  const handleDeleteFolder = useCallback(async (folderPath: string) => {
    if (!activeVault) return;
    const name = folderPath.split("/").pop() ?? folderPath;
    if (!confirm(`Delete folder "${name}" and all its contents?`)) return;
    try {
      await invoke("delete_folder", { vaultName: activeVault, folderPath });
      await refreshFileTree();
      await refreshVaults();
    } catch (e) {
      setError(`Failed to delete folder: ${e}`);
    }
  }, [activeVault]);

  const handleRename = useCallback(async (oldPath: string, currentName: string) => {
    if (!activeVault) return;
    const newName = prompt("Rename to:", currentName);
    if (!newName?.trim() || newName.trim() === currentName) return;
    try {
      await invoke<string>("rename_item", {
        vaultName: activeVault,
        oldPath,
        newName: newName.trim(),
      });
      await refreshFileTree();
    } catch (e) {
      setError(`Failed to rename: ${e}`);
    }
  }, [activeVault]);

  const handleNoteUpdated = useCallback((updated: NoteDetail) => {
    setNoteDetail(updated);
  }, []);

  // Cmd+N shortcut to create a new note in the vault root
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "n") {
        e.preventDefault();
        if (!activeVault || !fileTree) return;
        handleCreateNote(fileTree.path);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [activeVault, fileTree, handleCreateNote]);

  return (
    <div className="app">
      <Sidebar
        vaults={vaults}
        activeVault={activeVault}
        onSelectVault={selectVault}
        onCreateVault={handleCreateVault}
        onCreateNewVault={handleCreateNewVault}
        onDeleteVault={handleDeleteVault}
        currentView={currentView}
        onViewChange={setCurrentView}
        fileTree={fileTree}
        onSelectNote={handleSelectNote}
        selectedNotePath={selectedNotePath}
        onCreateNote={handleCreateNote}
        onDeleteNote={handleDeleteNote}
        onCreateFolder={handleCreateFolder}
        onDeleteFolder={handleDeleteFolder}
        onRename={handleRename}
      />
      <main className="main-content">
        {error && <div className="error-banner">{error}</div>}
        {loading && <div className="loading">Loading...</div>}

        {!loading && currentView === "graph" && graphData && (
          <GraphView data={graphData} />
        )}
        {!loading && currentView === "search" && (
          <SearchPanel
            results={searchResults}
            onSearch={handleSearch}
          />
        )}
        {!loading && currentView === "note" && noteDetail && activeVault && (
          <NoteViewer
            note={noteDetail}
            loading={false}
            vaultName={activeVault}
            onNoteUpdated={handleNoteUpdated}
          />
        )}
        {!loading && !activeVault && (
          <div className="empty-state">
            <h2>Welcome to VaultDB</h2>
            <p>Create a vault to get started.</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;

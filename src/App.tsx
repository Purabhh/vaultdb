import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
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

  useEffect(() => {
    initApp();
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
    } catch (e) {
      setError(`Failed to load vault: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateVault(name: string, path: string) {
    setLoading(true);
    setError(null);
    try {
      const info = await invoke<VaultInfo>("create_vault", {
        name,
        sourcePath: path,
      });
      setVaults((prev) => [...prev, info]);
      selectVault(name);
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

  return (
    <div className="app">
      <Sidebar
        vaults={vaults}
        activeVault={activeVault}
        onSelectVault={selectVault}
        onCreateVault={handleCreateVault}
        onDeleteVault={handleDeleteVault}
        currentView={currentView}
        onViewChange={setCurrentView}
        fileTree={fileTree}
        onSelectNote={handleSelectNote}
        selectedNotePath={selectedNotePath}
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
        {!loading && currentView === "note" && noteDetail && (
          <NoteViewer note={noteDetail} loading={false} />
        )}
        {!loading && !activeVault && (
          <div className="empty-state">
            <h2>Welcome to VaultDB</h2>
            <p>Create a vault from an Obsidian directory to get started.</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;

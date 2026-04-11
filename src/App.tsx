import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Sidebar } from "./components/Sidebar";
import { GraphView } from "./components/GraphView";
import { SearchPanel } from "./components/SearchPanel";
import { VaultInfo, GraphData, SearchResult } from "./types";
import "./App.css";

type View = "graph" | "search";

function App() {
  const [vaults, setVaults] = useState<VaultInfo[]>([]);
  const [activeVault, setActiveVault] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
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
    try {
      const graph = await invoke<GraphData>("get_graph", { vaultName: name });
      setGraphData(graph);
    } catch (e) {
      setError(`Failed to load graph: ${e}`);
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

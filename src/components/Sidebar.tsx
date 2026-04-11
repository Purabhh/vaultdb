import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { VaultInfo } from "../types";

interface SidebarProps {
  vaults: VaultInfo[];
  activeVault: string | null;
  onSelectVault: (name: string) => void;
  onCreateVault: (name: string, path: string) => void;
  onDeleteVault: (name: string) => void;
  currentView: "graph" | "search";
  onViewChange: (view: "graph" | "search") => void;
}

export function Sidebar({
  vaults,
  activeVault,
  onSelectVault,
  onCreateVault,
  onDeleteVault,
  currentView,
  onViewChange,
}: SidebarProps) {
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPath, setNewPath] = useState("");

  async function pickFolder() {
    const selected = await open({ directory: true });
    if (selected) {
      setNewPath(selected as string);
    }
  }

  function handleCreate() {
    if (newName.trim() && newPath.trim()) {
      onCreateVault(newName.trim(), newPath.trim());
      setNewName("");
      setNewPath("");
      setShowCreate(false);
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1 className="app-title">VaultDB</h1>
      </div>

      <div className="sidebar-section">
        <div className="section-header">
          <span>Vaults</span>
          <button
            className="btn-icon"
            onClick={() => setShowCreate(!showCreate)}
            title="New vault"
          >
            +
          </button>
        </div>

        {showCreate && (
          <div className="create-form">
            <input
              type="text"
              placeholder="Vault name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <div className="path-picker">
              <input
                type="text"
                placeholder="Source folder"
                value={newPath}
                readOnly
              />
              <button onClick={pickFolder}>Browse</button>
            </div>
            <button className="btn-primary" onClick={handleCreate}>
              Create & Ingest
            </button>
          </div>
        )}

        <ul className="vault-list">
          {vaults.map((v) => (
            <li
              key={v.name}
              className={`vault-item ${activeVault === v.name ? "active" : ""}`}
            >
              <button
                className="vault-name"
                onClick={() => onSelectVault(v.name)}
              >
                {v.name}
                <span className="note-count">{v.note_count} notes</span>
              </button>
              <button
                className="btn-delete"
                onClick={() => onDeleteVault(v.name)}
                title="Delete vault"
              >
                x
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="sidebar-section">
        <div className="section-header">View</div>
        <div className="view-toggle">
          <button
            className={currentView === "graph" ? "active" : ""}
            onClick={() => onViewChange("graph")}
          >
            Graph
          </button>
          <button
            className={currentView === "search" ? "active" : ""}
            onClick={() => onViewChange("search")}
          >
            Search
          </button>
        </div>
      </div>
    </aside>
  );
}

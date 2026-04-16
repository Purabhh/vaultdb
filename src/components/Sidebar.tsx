import { useState, useEffect, useRef } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { VaultInfo, FileTreeNode } from "../types";
import { FileTree } from "./FileTree";
import { ChevronDown } from "lucide-react";

type View = "graph" | "search" | "note";

interface SidebarProps {
  vaults: VaultInfo[];
  activeVault: string | null;
  onSelectVault: (name: string) => void;
  onCreateVault: (name: string, path: string) => void;
  onCreateNewVault: (name: string, parentDir: string) => void;
  onDeleteVault: (name: string) => void;
  currentView: View;
  onViewChange: (view: View) => void;
  fileTree: FileTreeNode | null;
  onSelectNote: (path: string) => void;
  selectedNotePath: string | null;
  onCreateNote?: (parentDir: string) => void;
  onDeleteNote?: (path: string) => void;
  onCreateFolder?: (parentDir: string) => void;
  onDeleteFolder?: (path: string) => void;
  onRename?: (path: string, currentName: string) => void;
}

export function Sidebar({
  vaults,
  activeVault,
  onSelectVault,
  onCreateVault,
  onCreateNewVault,
  onDeleteVault,
  currentView,
  onViewChange,
  fileTree,
  onSelectNote,
  selectedNotePath,
  onCreateNote,
  onDeleteNote,
  onCreateFolder,
  onDeleteFolder,
  onRename,
}: SidebarProps) {
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [createMode, setCreateMode] = useState<"existing" | "new">("new");
  const [newName, setNewName] = useState("");
  const [newPath, setNewPath] = useState("");
  const switcherRef = useRef<HTMLDivElement>(null);

  const activeInfo = vaults.find((v) => v.name === activeVault);

  // Close switcher on click outside
  useEffect(() => {
    if (!showSwitcher) return;
    const close = (e: MouseEvent) => {
      if (switcherRef.current && !switcherRef.current.contains(e.target as Node)) {
        setShowSwitcher(false);
        setShowCreate(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setShowSwitcher(false); setShowCreate(false); }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [showSwitcher]);

  async function pickFolder() {
    const selected = await open({ directory: true });
    if (selected) {
      setNewPath(selected as string);
    }
  }

  function handleCreate() {
    if (!newName.trim() || !newPath.trim()) return;
    if (createMode === "existing") {
      onCreateVault(newName.trim(), newPath.trim());
    } else {
      onCreateNewVault(newName.trim(), newPath.trim());
    }
    setNewName("");
    setNewPath("");
    setShowCreate(false);
    setShowSwitcher(false);
  }

  function switchTo(name: string) {
    onSelectVault(name);
    setShowSwitcher(false);
  }

  return (
    <aside className="sidebar">
      {/* Vault switcher header */}
      <div className="sidebar-header" ref={switcherRef}>
        <button
          className="vault-switcher-btn"
          onClick={() => setShowSwitcher(!showSwitcher)}
        >
          <div className="vault-switcher-info">
            <h1 className="app-title">{activeVault || "VaultDB"}</h1>
            {activeInfo && (
              <span className="vault-switcher-meta">{activeInfo.note_count} notes</span>
            )}
          </div>
          <ChevronDown
            size={16}
            className={`vault-switcher-chevron ${showSwitcher ? "open" : ""}`}
          />
        </button>

        {showSwitcher && (
          <div className="vault-switcher-dropdown">
            {vaults.map((v) => (
              <div
                key={v.name}
                className={`vault-switcher-item ${v.name === activeVault ? "active" : ""}`}
              >
                <button
                  className="vault-switcher-item-name"
                  onClick={() => switchTo(v.name)}
                >
                  {v.name}
                  <span className="vault-switcher-item-count">{v.note_count} notes</span>
                </button>
                <button
                  className="vault-switcher-item-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Remove vault "${v.name}"? (Files on disk are not deleted)`)) {
                      onDeleteVault(v.name);
                    }
                  }}
                  title="Remove vault"
                >
                  &times;
                </button>
              </div>
            ))}

            <div className="vault-switcher-divider" />

            {!showCreate ? (
              <button
                className="vault-switcher-add"
                onClick={() => setShowCreate(true)}
              >
                + Open or create vault
              </button>
            ) : (
              <div className="vault-switcher-create">
                <div className="create-mode-toggle">
                  <button
                    className={createMode === "new" ? "active" : ""}
                    onClick={() => setCreateMode("new")}
                  >
                    Create New
                  </button>
                  <button
                    className={createMode === "existing" ? "active" : ""}
                    onClick={() => setCreateMode("existing")}
                  >
                    Open Existing
                  </button>
                </div>
                <input
                  type="text"
                  placeholder="Vault name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
                  autoFocus
                />
                <div className="path-picker">
                  <input
                    type="text"
                    placeholder={createMode === "new" ? "Parent folder" : "Source folder"}
                    value={newPath}
                    readOnly
                  />
                  <button onClick={pickFolder}>Browse</button>
                </div>
                <button className="btn-primary" onClick={handleCreate}>
                  {createMode === "new" ? "Create" : "Open & Ingest"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* View toggle */}
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

      {/* File tree */}
      {activeVault && fileTree && (
        <div className="sidebar-section sidebar-files">
          <div className="section-header">
            <span>Files</span>
          </div>
          <FileTree
            tree={fileTree}
            onSelectNote={(path) => {
              onSelectNote(path);
              onViewChange("note");
            }}
            selectedPath={selectedNotePath}
            onCreateNote={onCreateNote}
            onDeleteNote={onDeleteNote}
            onCreateFolder={onCreateFolder}
            onDeleteFolder={onDeleteFolder}
            onRename={onRename}
          />
        </div>
      )}
    </aside>
  );
}

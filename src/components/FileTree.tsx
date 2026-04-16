import { useState, useCallback, useEffect, useRef } from "react";
import { FileTreeNode } from "../types";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  Folder,
  FolderOpen,
  File as FileIcon,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

interface ContextMenu {
  x: number;
  y: number;
  type: "folder" | "file";
  path: string;
  name: string;
}

interface FileTreeProps {
  tree: FileTreeNode;
  onSelectNote: (path: string) => void;
  selectedPath: string | null;
  onCreateNote?: (parentDir: string) => void;
  onDeleteNote?: (path: string) => void;
  onCreateFolder?: (parentDir: string) => void;
  onDeleteFolder?: (path: string) => void;
  onRename?: (path: string, currentName: string) => void;
}

function TreeNode({
  node,
  depth,
  onSelectNote,
  selectedPath,
  expanded,
  onToggle,
  onContextMenu,
}: {
  node: FileTreeNode;
  depth: number;
  onSelectNote: (path: string) => void;
  selectedPath: string | null;
  expanded: Record<string, boolean>;
  onToggle: (path: string) => void;
  onContextMenu: (e: React.MouseEvent, type: "folder" | "file", path: string, name: string) => void;
}) {
  if (node.is_dir) {
    const isOpen = expanded[node.path] ?? depth < 1;

    return (
      <div>
        <div
          role="treeitem"
          aria-expanded={isOpen}
          className={cn(
            "group flex items-center gap-1.5 rounded-md cursor-pointer transition-colors",
            "hover:bg-[var(--bg-tertiary)]",
            "text-[var(--text-primary)]"
          )}
          style={{ paddingLeft: depth * 14 + 6, paddingTop: 4, paddingBottom: 4, paddingRight: 6 }}
          onClick={() => onToggle(node.path)}
          onContextMenu={(e) => onContextMenu(e, "folder", node.path, node.name)}
        >
          <button
            aria-label={isOpen ? "collapse" : "expand"}
            onClick={(e) => {
              e.stopPropagation();
              onToggle(node.path);
            }}
            className="inline-flex items-center justify-center w-4 h-4 shrink-0 text-[var(--text-secondary)]"
          >
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
          {isOpen ? (
            <FolderOpen size={15} className="shrink-0 text-[var(--accent-hover)]" />
          ) : (
            <Folder size={15} className="shrink-0 text-[var(--accent-hover)]" />
          )}
          <span className="flex-1 text-[13px] truncate">{node.name}</span>
          <span className="text-[10px] text-[var(--text-secondary)] opacity-0 group-hover:opacity-100 transition-opacity">
            {node.children.length}
          </span>
        </div>
        {isOpen && (
          <div role="group">
            {node.children.map((child) => (
              <TreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                onSelectNote={onSelectNote}
                selectedPath={selectedPath}
                expanded={expanded}
                onToggle={onToggle}
                onContextMenu={onContextMenu}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const displayName = node.name.replace(/\.md$/, "");
  const isSelected = node.path === selectedPath;

  return (
    <div
      role="treeitem"
      className={cn(
        "group flex items-center gap-1.5 rounded-md cursor-pointer transition-colors",
        isSelected
          ? "bg-[var(--vdb-accent)] text-white"
          : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
      )}
      style={{ paddingLeft: depth * 14 + 24, paddingTop: 3, paddingBottom: 3, paddingRight: 6 }}
      onClick={() => onSelectNote(node.path)}
      onContextMenu={(e) => onContextMenu(e, "file", node.path, node.name)}
    >
      <FileIcon size={14} className={cn("shrink-0", isSelected ? "text-white/70" : "text-[var(--text-secondary)]")} />
      <span className="flex-1 text-[13px] truncate">{displayName}</span>
    </div>
  );
}

export function FileTree({
  tree,
  onSelectNote,
  selectedPath,
  onCreateNote,
  onDeleteNote,
  onCreateFolder,
  onDeleteFolder,
  onRename,
}: FileTreeProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [contextMenu, setContextMenu] = useState<ContextMenu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const toggle = (path: string) => {
    setExpanded((prev) => ({ ...prev, [path]: !(prev[path] ?? true) }));
  };

  const collapseAll = () => setExpanded({});

  const handleContextMenu = useCallback((e: React.MouseEvent, type: "folder" | "file", path: string, name: string) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, type, path, name });
  }, []);

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [contextMenu]);

  return (
    <TooltipProvider>
      <div role="tree" className="space-y-0.5">
        {tree.children.map((child) => (
          <TreeNode
            key={child.path}
            node={child}
            depth={0}
            onSelectNote={onSelectNote}
            selectedPath={selectedPath}
            expanded={expanded}
            onToggle={toggle}
            onContextMenu={handleContextMenu}
          />
        ))}
      </div>
      {tree.children.length > 3 && (
        <button
          onClick={collapseAll}
          className="flex items-center gap-1 mt-2 px-2 py-1 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <ChevronRight size={12} />
          Collapse all
        </button>
      )}

      {contextMenu && (
        <div
          ref={menuRef}
          className="context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
        >
          {contextMenu.type === "folder" && (
            <>
              {onCreateNote && (
                <button
                  className="context-menu-item"
                  onClick={() => { onCreateNote(contextMenu.path); setContextMenu(null); }}
                >
                  New Note
                </button>
              )}
              {onCreateFolder && (
                <button
                  className="context-menu-item"
                  onClick={() => { onCreateFolder(contextMenu.path); setContextMenu(null); }}
                >
                  New Folder
                </button>
              )}
              {onRename && (
                <button
                  className="context-menu-item"
                  onClick={() => { onRename(contextMenu.path, contextMenu.name); setContextMenu(null); }}
                >
                  Rename
                </button>
              )}
              {onDeleteFolder && (
                <button
                  className="context-menu-item context-menu-item--danger"
                  onClick={() => { onDeleteFolder(contextMenu.path); setContextMenu(null); }}
                >
                  Delete Folder
                </button>
              )}
            </>
          )}
          {contextMenu.type === "file" && (
            <>
              {onRename && (
                <button
                  className="context-menu-item"
                  onClick={() => { onRename(contextMenu.path, contextMenu.name); setContextMenu(null); }}
                >
                  Rename
                </button>
              )}
              {onDeleteNote && (
                <button
                  className="context-menu-item context-menu-item--danger"
                  onClick={() => { onDeleteNote(contextMenu.path); setContextMenu(null); }}
                >
                  Delete
                </button>
              )}
            </>
          )}
        </div>
      )}
    </TooltipProvider>
  );
}

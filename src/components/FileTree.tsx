import { useState } from "react";
import { FileTreeNode } from "../types";

interface FileTreeProps {
  tree: FileTreeNode;
  onSelectNote: (path: string) => void;
  selectedPath: string | null;
}

function TreeNode({
  node,
  depth,
  onSelectNote,
  selectedPath,
}: {
  node: FileTreeNode;
  depth: number;
  onSelectNote: (path: string) => void;
  selectedPath: string | null;
}) {
  const [expanded, setExpanded] = useState(depth < 1);

  if (node.is_dir) {
    return (
      <div className="tree-dir">
        <button
          className="tree-dir-name"
          onClick={() => setExpanded(!expanded)}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          <span className={`tree-arrow ${expanded ? "expanded" : ""}`}>
            {"\u25B6"}
          </span>
          <span className="tree-folder-icon">{"\uD83D\uDCC1"}</span>
          {node.name}
        </button>
        {expanded && (
          <div className="tree-children">
            {node.children.map((child) => (
              <TreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                onSelectNote={onSelectNote}
                selectedPath={selectedPath}
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
    <button
      className={`tree-file ${isSelected ? "selected" : ""}`}
      onClick={() => onSelectNote(node.path)}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
    >
      <span className="tree-file-icon">{"\uD83D\uDCC4"}</span>
      {displayName}
    </button>
  );
}

export function FileTree({ tree, onSelectNote, selectedPath }: FileTreeProps) {
  return (
    <div className="file-tree">
      {tree.children.map((child) => (
        <TreeNode
          key={child.path}
          node={child}
          depth={0}
          onSelectNote={onSelectNote}
          selectedPath={selectedPath}
        />
      ))}
    </div>
  );
}

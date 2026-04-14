export interface VaultInfo {
  name: string;
  source_path: string;
  note_count: number;
}

export interface SearchResult {
  title: string;
  path: string;
  chunk: string;
  score: number;
}

export interface GraphNode {
  id: string;
  title: string;
  path: string;
  tags: string[];
  link_count: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  edge_type: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface FileTreeNode {
  name: string;
  path: string;
  is_dir: boolean;
  children: FileTreeNode[];
}

export interface SimilarNote {
  title: string;
  chunk: string;
  score: number;
}

export interface ChunkDetail {
  index: number;
  text: string;
  similar_notes: SimilarNote[];
}

export interface NoteDetail {
  title: string;
  path: string;
  raw_content: string;
  tags: string[];
  links: string[];
  chunks: ChunkDetail[];
}

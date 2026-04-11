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

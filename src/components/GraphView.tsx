import { GraphData } from "../types";

interface GraphViewProps {
  data: GraphData;
}

export function GraphView({ data }: GraphViewProps) {
  return (
    <div className="graph-placeholder">
      <h2>Graph View</h2>
      <p>Coming soon — full physics-based knowledge graph with draggable nodes, zoom, and pan.</p>
      <div className="graph-placeholder-stats">
        <span>{data.nodes.length} nodes</span>
        <span>{data.edges.length} edges</span>
      </div>
    </div>
  );
}

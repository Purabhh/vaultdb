import { useRef, useEffect, useCallback } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import { GraphData } from "../types";

interface GraphViewProps {
  data: GraphData;
}

interface FGNode {
  id: string;
  title: string;
  tags: string[];
  link_count: number;
  x?: number;
  y?: number;
}

interface FGLink {
  source: string | FGNode;
  target: string | FGNode;
  edge_type: string;
  weight: number;
}

const TAG_COLORS: Record<string, string> = {};
const PALETTE = [
  "#c49b2a", "#a67c52", "#d4a853", "#8b6914", "#e8c97a",
  "#b08d57", "#6b4f2e", "#deb887", "#c4956a", "#9c7a3c",
];

function getTagColor(tag: string): string {
  if (!TAG_COLORS[tag]) {
    const idx = Object.keys(TAG_COLORS).length % PALETTE.length;
    TAG_COLORS[tag] = PALETTE[idx];
  }
  return TAG_COLORS[tag];
}

export function GraphView({ data }: GraphViewProps) {
  const fgRef = useRef<ForceGraphMethods<FGNode, FGLink>>(undefined);

  // Only include edges where both source and target exist as nodes
  const nodeIds = new Set(data.nodes.map((n) => n.id));
  const validEdges = data.edges.filter(
    (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
  );

  const graphData = {
    nodes: data.nodes.map((n) => ({
      id: n.id,
      title: n.title,
      tags: n.tags,
      link_count: n.link_count,
    })),
    links: validEdges.map((e) => ({
      source: e.source,
      target: e.target,
      edge_type: e.edge_type,
      weight: e.weight,
    })),
  };

  useEffect(() => {
    if (fgRef.current) {
      fgRef.current.d3Force("charge")?.strength(-200);
      fgRef.current.d3Force("link")?.distance((link: FGLink) =>
        link.edge_type === "semantic" ? 150 : 80
      );
    }
  }, [data]);

  const nodeCanvasObject = useCallback(
    (node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const radius = Math.max(4, Math.sqrt(node.link_count + 1) * 4);
      const color =
        node.tags.length > 0 ? getTagColor(node.tags[0]) : "#c49b2a";

      // Glow
      ctx.shadowColor = color;
      ctx.shadowBlur = 12;

      // Node circle
      ctx.beginPath();
      ctx.arc(node.x!, node.y!, radius, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      // Border
      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.shadowBlur = 0;

      // Label
      const fontSize = Math.max(10, 12 / globalScale);
      ctx.font = `${fontSize}px Inter, -apple-system, sans-serif`;
      ctx.fillStyle = "#f0ece8";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(node.title, node.x!, node.y! + radius + 4);
    },
    []
  );

  const linkCanvasObject = useCallback(
    (link: FGLink, ctx: CanvasRenderingContext2D) => {
      const source = link.source as FGNode;
      const target = link.target as FGNode;
      if (!source.x || !target.x) return;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y!);
      ctx.lineTo(target.x, target.y!);

      if (link.edge_type === "semantic") {
        // Dotted pink line for semantic edges
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = `rgba(166, 124, 82, ${0.15 + link.weight * 0.4})`;
        ctx.lineWidth = 1;
      } else {
        // Solid gold line for explicit links
        ctx.setLineDash([]);
        ctx.strokeStyle = "rgba(196, 155, 42, 0.5)";
        ctx.lineWidth = 1.5;
      }

      ctx.stroke();
      ctx.setLineDash([]);
    },
    []
  );

  return (
    <div className="graph-container">
      <div className="graph-legend">
        <span className="legend-item">
          <span className="legend-line legend-link"></span> Wikilink
        </span>
        <span className="legend-item">
          <span className="legend-line legend-semantic"></span> Semantic
        </span>
      </div>
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeCanvasObject={nodeCanvasObject}
        linkCanvasObject={linkCanvasObject}
        backgroundColor="#0a0a0a"
        width={window.innerWidth - 560}
        height={window.innerHeight}
        cooldownTicks={100}
        enableNodeDrag={true}
        enableZoomInteraction={true}
      />
    </div>
  );
}

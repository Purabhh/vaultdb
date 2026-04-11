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
  "#6366f1", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6",
  "#ef4444", "#06b6d4", "#84cc16", "#f97316", "#a855f7",
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

  const graphData = {
    nodes: data.nodes.map((n) => ({
      id: n.id,
      title: n.title,
      tags: n.tags,
      link_count: n.link_count,
    })),
    links: data.edges.map((e) => ({
      source: e.source,
      target: e.target,
      edge_type: e.edge_type,
      weight: e.weight,
    })),
  };

  useEffect(() => {
    if (fgRef.current) {
      fgRef.current.d3Force("charge")?.strength(-120);
      fgRef.current.d3Force("link")?.distance(80);
    }
  }, [data]);

  const nodeCanvasObject = useCallback(
    (node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const radius = Math.max(3, Math.sqrt(node.link_count + 1) * 3);
      const color =
        node.tags.length > 0 ? getTagColor(node.tags[0]) : "#6366f1";

      // Node circle
      ctx.beginPath();
      ctx.arc(node.x!, node.y!, radius, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      // Glow
      ctx.shadowColor = color;
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.shadowBlur = 0;

      // Label
      const fontSize = Math.max(10, 12 / globalScale);
      ctx.font = `${fontSize}px Inter, sans-serif`;
      ctx.fillStyle = "#e2e8f0";
      ctx.textAlign = "center";
      ctx.fillText(node.title, node.x!, node.y! + radius + fontSize);
    },
    []
  );

  const linkColor = useCallback((link: FGLink) => {
    return link.edge_type === "link"
      ? "rgba(99, 102, 241, 0.3)"
      : "rgba(236, 72, 153, 0.15)";
  }, []);

  return (
    <div className="graph-container">
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeCanvasObject={nodeCanvasObject}
        linkColor={linkColor}
        linkWidth={(link: FGLink) => (link.edge_type === "link" ? 1.5 : 0.5)}
        linkDirectionalParticles={(link: FGLink) =>
          link.edge_type === "link" ? 2 : 0
        }
        linkDirectionalParticleWidth={2}
        backgroundColor="#0f172a"
        width={window.innerWidth - 260}
        height={window.innerHeight}
        cooldownTicks={100}
      />
    </div>
  );
}

import { useRef, useEffect } from "react";
import * as d3 from "d3";
import { GraphData } from "../types";

interface GraphViewProps {
  data: GraphData;
}

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  title: string;
  tags: string[];
  link_count: number;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
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
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Clean up any previous canvas
    container.querySelectorAll("canvas").forEach((c) => c.remove());

    // Create canvas
    const canvas = document.createElement("canvas");
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    container.appendChild(canvas);

    const ctx = canvas.getContext("2d")!;

    // Sizing function
    function resize() {
      const rect = container!.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      // Don't set style width/height — CSS 100% handles it
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return { width: rect.width, height: rect.height };
    }

    let { width, height } = resize();

    // Filter edges to only those with valid nodes
    const nodeIds = new Set(data.nodes.map((n) => n.id));
    const validEdges = data.edges.filter(
      (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
    );

    // Create simulation data
    const nodes: SimNode[] = data.nodes.map((n) => ({
      id: n.id,
      title: n.title,
      tags: [...n.tags],
      link_count: n.link_count,
    }));

    const links: SimLink[] = validEdges.map((e) => ({
      source: e.source,
      target: e.target,
      edge_type: e.edge_type,
      weight: e.weight,
    }));

    // Transform state for pan/zoom
    let transform = d3.zoomIdentity;

    // Simulation
    const simulation = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance((d) => (d.edge_type === "semantic" ? 180 : 100))
      )
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(30))
      .on("tick", draw);

    function draw() {
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      // Background
      ctx.fillStyle = "#0a0a0a";
      ctx.fillRect(0, 0, width, height);

      // Apply pan/zoom transform
      ctx.translate(transform.x, transform.y);
      ctx.scale(transform.k, transform.k);

      // Draw links
      for (const link of links) {
        const source = link.source as SimNode;
        const target = link.target as SimNode;
        if (source.x == null || target.x == null) continue;

        ctx.beginPath();
        ctx.moveTo(source.x, source.y!);
        ctx.lineTo(target.x, target.y!);

        if (link.edge_type === "semantic") {
          ctx.setLineDash([4, 4]);
          ctx.strokeStyle = `rgba(166, 124, 82, ${0.2 + link.weight * 0.4})`;
          ctx.lineWidth = 1;
        } else {
          ctx.setLineDash([]);
          ctx.strokeStyle = "rgba(196, 155, 42, 0.6)";
          ctx.lineWidth = 1.5;
        }
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Draw nodes
      for (const node of nodes) {
        if (node.x == null || node.y == null) continue;
        const radius = Math.max(4, Math.sqrt(node.link_count + 1) * 4);
        const color =
          node.tags.length > 0 ? getTagColor(node.tags[0]) : "#c49b2a";

        // Glow
        ctx.shadowColor = color;
        ctx.shadowBlur = 12;

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();

        ctx.shadowBlur = 0;
        ctx.strokeStyle = "rgba(255,255,255,0.15)";
        ctx.lineWidth = 0.5;
        ctx.stroke();

        // Label
        ctx.font = "11px Inter, -apple-system, sans-serif";
        ctx.fillStyle = "#f0ece8";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillText(node.title, node.x, node.y + radius + 4);
      }
    }

    // Zoom/pan
    const zoom = d3
      .zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.1, 5])
      .on("zoom", (event) => {
        transform = event.transform;
        draw();
      });

    d3.select(canvas).call(zoom);

    // Drag
    let dragNode: SimNode | null = null;

    function findNode(mx: number, my: number): SimNode | null {
      const tx = (mx - transform.x) / transform.k;
      const ty = (my - transform.y) / transform.k;
      for (const node of nodes) {
        if (node.x == null || node.y == null) continue;
        const r = Math.max(4, Math.sqrt(node.link_count + 1) * 4) + 8;
        const dx = tx - node.x;
        const dy = ty - node.y;
        if (dx * dx + dy * dy < r * r) return node;
      }
      return null;
    }

    canvas.addEventListener("mousedown", (e) => {
      const rect = canvas.getBoundingClientRect();
      dragNode = findNode(e.clientX - rect.left, e.clientY - rect.top);
      if (dragNode) {
        simulation.alphaTarget(0.3).restart();
        dragNode.fx = dragNode.x;
        dragNode.fy = dragNode.y;
        d3.select(canvas).on(".zoom", null);
      }
    });

    canvas.addEventListener("mousemove", (e) => {
      if (!dragNode) return;
      const rect = canvas.getBoundingClientRect();
      dragNode.fx = (e.clientX - rect.left - transform.x) / transform.k;
      dragNode.fy = (e.clientY - rect.top - transform.y) / transform.k;
    });

    canvas.addEventListener("mouseup", () => {
      if (dragNode) {
        simulation.alphaTarget(0);
        dragNode.fx = null;
        dragNode.fy = null;
        dragNode = null;
        d3.select(canvas).call(zoom);
      }
    });

    // Resize handler
    const ro = new ResizeObserver(() => {
      const dims = resize();
      width = dims.width;
      height = dims.height;
      simulation.force("center", d3.forceCenter(width / 2, height / 2));
      simulation.alpha(0.3).restart();
    });
    ro.observe(container);

    return () => {
      simulation.stop();
      ro.disconnect();
      canvas.remove();
    };
  }, [data]);

  return (
    <div className="graph-container" ref={containerRef}>
      <div className="graph-legend">
        <span className="legend-item">
          <span className="legend-line legend-link"></span> Wikilink
        </span>
        <span className="legend-item">
          <span className="legend-line legend-semantic"></span> Semantic
        </span>
      </div>
    </div>
  );
}

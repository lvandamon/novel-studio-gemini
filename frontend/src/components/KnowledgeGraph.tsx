import React, { useEffect, useState, useRef } from 'react';
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d';
import { api } from '../api';

interface ForceGraphData {
  nodes: any[];
  links: any[];
}

const NODE_COLORS: Record<string, string> = {
  Character: '#60a5fa', // Blue-400
  Event: '#ef4444',     // Red-500
  Location: '#34d399',  // Emerald-400
  Item: '#fbbf24',      // Amber-400
  Organization: '#a78bfa', // Violet-400
  Unknown: '#9ca3af'    // Gray-400
};

const KnowledgeGraph: React.FC = () => {
  const [data, setData] = useState<ForceGraphData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(false);
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  const [dimensions, setDimensions] = useState({ w: 800, h: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Responsive Resize
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        setDimensions({
          w: entries[0].contentRect.width,
          h: entries[0].contentRect.height
        });
      }
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, []);

  const refreshGraph = async () => {
    setLoading(true);
    try {
      // Fetch data from backend
      // Backend returns { nodes: [...], edges: [...] }
      // But react-force-graph expects { nodes: [...], links: [...] }
      const rawData = await api.getGraphData(200);
      
      // Adapt data structure
      const adaptedData = {
        nodes: rawData.nodes.map((n: any) => ({
          id: n.id,
          name: n.label,
          group: n.group,
          val: n.group === 'Event' ? 2 : 5 // Size
        })),
        links: rawData.edges.map((e: any) => ({
          source: e.from,
          target: e.to,
          label: e.label
        }))
      };

      setData(adaptedData);
      
      // Auto-zoom after data load
      setTimeout(() => {
          fgRef.current?.d3Force('charge')?.strength(-100);
          fgRef.current?.zoomToFit(400);
      }, 500);
      
    } catch (e) {
      console.error("Graph Load Failed", e);
    }
    setLoading(false);
  };

  // Load on mount
  useEffect(() => {
    refreshGraph();
  }, []);

  return (
    <div className="relative h-full w-full bg-gray-900 rounded-xl overflow-hidden shadow-inner border border-gray-700" ref={containerRef}>
      
      {/* Control Overlay */}
      <div className="absolute top-4 right-4 z-10 flex gap-2">
        <button 
          onClick={refreshGraph}
          className="bg-gray-800 hover:bg-gray-700 text-white px-3 py-1 rounded text-xs font-mono border border-gray-600"
        >
          {loading ? 'SYNCING...' : 'REFRESH'}
        </button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-10 bg-gray-900/80 p-3 rounded border border-gray-700 backdrop-blur-sm pointer-events-none">
        <h4 className="text-gray-400 text-xs font-bold mb-2 uppercase">Legend</h4>
        <div className="space-y-1">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }}></span>
              <span className="text-xs text-gray-300 font-mono">{type}</span>
            </div>
          ))}
        </div>
      </div>

      <ForceGraph2D
        ref={fgRef}
        width={dimensions.w}
        height={dimensions.h}
        graphData={data}
        nodeLabel="name"
        nodeColor={(node: any) => NODE_COLORS[node.group] || NODE_COLORS.Unknown}
        linkColor={() => '#4b5563'} // Gray-600
        nodeRelSize={6}
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={1}
        linkCurvature={0.1}
        
        // Particles for active links (Optional Visual Flair)
        linkDirectionalParticles={1}
        linkDirectionalParticleSpeed={0.005}
        
        onNodeClick={node => {
            // Zoom to node on click
            fgRef.current?.centerAt(node.x, node.y, 1000);
            fgRef.current?.zoom(4, 2000);
        }}
      />
      
      {data.nodes.length === 0 && !loading && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-500 font-mono text-sm pointer-events-none">
          NO GRAPH DATA AVAILABLE
        </div>
      )}
    </div>
  );
};

export default KnowledgeGraph;

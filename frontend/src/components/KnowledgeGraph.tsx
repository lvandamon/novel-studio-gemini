import React, { useEffect, useState, useRef } from 'react';
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d';
import { api } from '../api';
import { Search, Clock, RefreshCw, Filter, ZoomIn, ZoomOut } from 'lucide-react';

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

  // 🔥 New Filter State
  const [filters, setFilters] = useState({
    startChapter: 0,
    endChapter: 200, // Default window
    focusNode: ''
  });
  
  // UI State for panel collapse
  const [showPanel, setShowPanel] = useState(true);

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
      // Pass filters to API
      const focus = filters.focusNode.trim() || undefined;
      const rawData = await api.getGraphData(
        300, // Increased limit for fuller views
        filters.startChapter,
        filters.endChapter,
        focus
      );
      
      // Adapt data structure
      const adaptedData = {
        nodes: rawData.nodes.map((n: any) => ({
          id: n.id,
          name: n.label,
          group: n.group,
          val: n.group === 'Event' ? 2 : (n.id === focus ? 15 : 5), // Highlight focus node
          color: n.id === focus ? '#ffffff' : undefined // Highlight focus node color
        })),
        links: rawData.edges.map((e: any) => ({
          source: e.from,
          target: e.to,
          label: e.label
        }))
      };

      setData(adaptedData);
      
      // Auto-zoom logic
      setTimeout(() => {
        if (filters.focusNode && adaptedData.nodes.find(n => n.id === filters.focusNode)) {
           // If focusing, center on that node is handled by highlighting? 
           // Better to let physics settle then zoom.
        } else {
           fgRef.current?.d3Force('charge')?.strength(-100);
           fgRef.current?.zoomToFit(400);
        }
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

  const handleNodeClick = (node: any) => {
    // Click sets focus node input (but doesn't auto-refresh, user decides)
    setFilters(prev => ({ ...prev, focusNode: node.id }));
    fgRef.current?.centerAt(node.x, node.y, 1000);
    fgRef.current?.zoom(4, 2000);
  };

  return (
    <div className="relative h-full w-full bg-gray-950 rounded-xl overflow-hidden shadow-2xl border border-gray-800" ref={containerRef}>
      
      {/* --- Filter Panel --- */}
      <div className={`absolute top-4 left-4 z-20 transition-all duration-300 ${showPanel ? 'w-80' : 'w-12'}`}>
        <div className="bg-gray-900/90 backdrop-blur-md border border-gray-700 rounded-lg shadow-xl overflow-hidden">
          
          {/* Header / Toggle */}
          <div 
            className="flex items-center justify-between p-3 cursor-pointer bg-gray-800/50 hover:bg-gray-800 transition-colors"
            onClick={() => setShowPanel(!showPanel)}
          >
            <div className="flex items-center gap-2 text-blue-400 font-bold text-sm">
              <Filter size={16} />
              {showPanel && <span>Graph Controls</span>}
            </div>
            {!showPanel && (
                <div className="absolute right-0 top-0 bottom-0 w-12 flex items-center justify-center">
                    {/* Tiny indicator if active filters? */}
                </div>
            )}
          </div>

          {/* Controls Body */}
          {showPanel && (
            <div className="p-4 space-y-4">
              
              {/* 1. Time Slider (Chapter Range) */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-gray-400 text-xs uppercase font-bold tracking-wider">
                  <Clock size={12} />
                  <span>Timeline Slice</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500 text-xs">Ch</span>
                    <input 
                      type="number" 
                      value={filters.startChapter}
                      onChange={(e) => setFilters(prev => ({ ...prev, startChapter: parseInt(e.target.value) || 0 }))}
                      className="w-full bg-gray-950 border border-gray-700 rounded px-2 pl-7 py-1 text-sm text-gray-200 focus:border-blue-500 outline-none"
                    />
                  </div>
                  <span className="text-gray-600">-</span>
                  <div className="relative flex-1">
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500 text-xs">Ch</span>
                    <input 
                      type="number" 
                      value={filters.endChapter}
                      onChange={(e) => setFilters(prev => ({ ...prev, endChapter: parseInt(e.target.value) || 0 }))}
                      className="w-full bg-gray-950 border border-gray-700 rounded px-2 pl-7 py-1 text-sm text-gray-200 focus:border-blue-500 outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* 2. Spotlight (Focus Entity) */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-gray-400 text-xs uppercase font-bold tracking-wider">
                  <Search size={12} />
                  <span>Spotlight Focus</span>
                </div>
                <div className="relative">
                  <input 
                    type="text" 
                    value={filters.focusNode}
                    onChange={(e) => setFilters(prev => ({ ...prev, focusNode: e.target.value }))}
                    placeholder="Enter character name..."
                    className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 focus:border-blue-500 outline-none placeholder-gray-600"
                  />
                  {filters.focusNode && (
                    <button 
                      onClick={() => setFilters(prev => ({ ...prev, focusNode: '' }))}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>

              {/* 3. Actions */}
              <div className="pt-2 border-t border-gray-800 flex gap-2">
                <button 
                  onClick={refreshGraph}
                  disabled={loading}
                  className="flex-1 bg-blue-600 hover:bg-blue-500 text-white py-1.5 rounded text-sm font-medium flex items-center justify-center gap-2 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                  {loading ? 'Syncing...' : 'Sync View'}
                </button>
              </div>

            </div>
          )}
        </div>
      </div>

      {/* Legend (Bottom Left) */}
      <div className="absolute bottom-4 left-4 z-10 bg-gray-900/80 p-3 rounded-lg border border-gray-700 backdrop-blur-sm pointer-events-none select-none">
        <h4 className="text-gray-500 text-[10px] font-bold mb-2 uppercase tracking-widest">Entity Types</h4>
        <div className="space-y-1.5">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full shadow-sm" style={{ backgroundColor: color }}></span>
              <span className="text-xs text-gray-300 font-mono">{type}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Zoom Controls (Bottom Right) */}
      <div className="absolute bottom-4 right-4 z-10 flex flex-col gap-2">
         <button 
            className="bg-gray-800 p-2 rounded-lg text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 transition-all"
            onClick={() => fgRef.current?.zoomIn()}
         >
            <ZoomIn size={18} />
         </button>
         <button 
            className="bg-gray-800 p-2 rounded-lg text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 transition-all"
            onClick={() => fgRef.current?.zoomOut()}
         >
            <ZoomOut size={18} />
         </button>
         <button 
            className="bg-gray-800 p-2 rounded-lg text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 transition-all"
            onClick={() => fgRef.current?.zoomToFit(400)}
            title="Fit to Screen"
         >
            <RefreshCw size={18} />
         </button>
      </div>

      <ForceGraph2D
        ref={fgRef}
        width={dimensions.w}
        height={dimensions.h}
        graphData={data}
        nodeLabel="name"
        nodeColor={(node: any) => node.color || NODE_COLORS[node.group] || NODE_COLORS.Unknown}
        linkColor={() => '#374151'} // Gray-700
        nodeRelSize={6}
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={1}
        linkCurvature={0.15}
        backgroundColor="#030712" // Gray-950
        
        // Particles for active links
        linkDirectionalParticles={2}
        linkDirectionalParticleSpeed={0.005}
        linkDirectionalParticleWidth={1}
        
        onNodeClick={handleNodeClick}
        
        // Improved engine settings
        cooldownTicks={100}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
      />
      
      {data.nodes.length === 0 && !loading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 pointer-events-none">
          <Filter size={48} className="mb-4 opacity-50" />
          <span className="font-mono text-sm">NO ENTITIES FOUND IN RANGE</span>
          <span className="text-xs mt-2">Try adjusting the timeline or filters</span>
        </div>
      )}
    </div>
  );
};

export default KnowledgeGraph;
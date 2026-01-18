import React, { useState } from 'react';
import { api } from '../api';
import { CheckCircle, XCircle, ArrowRight, Zap, RefreshCw } from 'lucide-react';

interface RetconModalProps {
  initialEntity?: string;
  onClose: () => void;
  onSuccess: () => void;
}

const RetconModal: React.FC<RetconModalProps> = ({ initialEntity, onClose, onSuccess }) => {
  const [instruction, setInstruction] = useState(initialEntity ? `修正关于 ${initialEntity} 的设定: ` : "");
  const [loading, setLoading] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [error, setError] = useState("");

  const handlePreview = async () => {
    if (!instruction.trim()) return;
    setLoading(true);
    setError("");
    setPreviewData(null);
    try {
      const res = await api.previewRetcon(instruction);
      setPreviewData(res);
    } catch (e: any) {
      setError("Analysis Failed: " + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  const handleApply = async () => {
    if (!previewData?.plan) return;
    setLoading(true);
    try {
      await api.applyRetcon(previewData.plan);
      onSuccess();
      onClose();
    } catch (e: any) {
      setError("Execution Failed: " + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="p-6 border-b border-gray-100 flex justify-between items-center bg-gray-50">
          <div className="flex items-center gap-3">
            <div className="bg-purple-100 p-2 rounded-lg">
               <RefreshCw className="text-purple-600" size={24} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Reality Retcon Tool</h2>
              <p className="text-xs text-gray-500 uppercase tracking-wider font-bold">Historical Correction & Taint Analysis</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <XCircle size={24} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          
          {/* Input Section */}
          <div className="space-y-2">
            <label className="block text-sm font-bold text-gray-700">Correction Instruction</label>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="e.g. 'Xiao Feng and Lin are actually enemies, not friends.' or 'The Broken Sword is actually a divine artifact.'"
              className="w-full h-24 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none resize-none text-gray-800"
            />
            <div className="flex justify-end">
              <button 
                onClick={handlePreview}
                disabled={loading || !instruction.trim()}
                className="bg-purple-600 text-white px-6 py-2 rounded-lg font-bold flex items-center gap-2 hover:bg-purple-700 disabled:opacity-50 transition-all"
              >
                {loading ? <RefreshCw className="animate-spin" size={16} /> : <Zap size={16} />}
                Analyze Impact
              </button>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded text-red-700 text-sm">
              <span className="font-bold block mb-1">Error</span>
              {error}
            </div>
          )}

          {/* Preview Section */}
          {previewData && (
            <div className="space-y-6 animate-in slide-in-from-bottom-4">
              
              {/* Rationale */}
              <div className="bg-blue-50 p-4 rounded-lg border border-blue-100">
                <h3 className="text-blue-900 font-bold text-sm mb-2 flex items-center gap-2">
                  <ArrowRight size={14} /> AI Rationale
                </h3>
                <p className="text-blue-800 text-sm leading-relaxed">{previewData.plan.rationale}</p>
              </div>

              {/* Impact Analysis (Logs) */}
              <div className="bg-gray-900 text-gray-300 p-4 rounded-lg font-mono text-xs overflow-x-auto border border-gray-800">
                 <h3 className="text-gray-500 font-bold mb-3 uppercase tracking-widest border-b border-gray-800 pb-2">Blast Radius Report</h3>
                 <div className="space-y-1.5">
                   {previewData.impact_analysis.map((log: string, i: number) => {
                     const isWarning = log.includes("Warning") || log.includes("IMPACT");
                     return (
                       <div key={i} className={`${isWarning ? 'text-yellow-400 font-bold' : 'text-gray-400'}`}>
                         {log}
                       </div>
                     )
                   })}
                 </div>
              </div>

              {/* Changes Summary */}
              <div className="grid grid-cols-2 gap-4">
                 <div className="border border-gray-200 rounded p-3">
                    <div className="text-xs font-bold text-gray-500 uppercase mb-2">Entity Updates</div>
                    {previewData.plan.entity_updates?.length ? (
                        <ul className="text-sm space-y-1">
                            {previewData.plan.entity_updates.map((u: any, i: number) => (
                                <li key={i} className="flex gap-2">
                                    <span className="font-bold text-gray-800">{u.name}</span>
                                    <span className="text-gray-400">.</span>
                                    <span className="text-purple-600">{u.field}</span>
                                </li>
                            ))}
                        </ul>
                    ) : <span className="text-xs text-gray-400 italic">None</span>}
                 </div>
                 <div className="border border-gray-200 rounded p-3">
                    <div className="text-xs font-bold text-gray-500 uppercase mb-2">Rel Updates</div>
                    {previewData.plan.relationship_updates?.length ? (
                        <ul className="text-sm space-y-1">
                            {previewData.plan.relationship_updates.map((u: any, i: number) => (
                                <li key={i} className="flex items-center gap-1 text-xs">
                                    <span className="font-bold">{u.source}</span>
                                    <span className={`px-1 rounded ${u.action === 'DELETE' ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600'}`}>{u.action === 'DELETE' ? '-|' : '+>'}</span>
                                    <span className="font-bold">{u.target}</span>
                                </li>
                            ))}
                        </ul>
                    ) : <span className="text-xs text-gray-400 italic">None</span>}
                 </div>
              </div>

            </div>
          )}

        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-100 bg-gray-50 flex justify-end gap-3">
          <button 
            onClick={onClose}
            className="px-4 py-2 text-gray-600 hover:bg-gray-200 rounded-lg text-sm font-bold transition-colors"
          >
            Cancel
          </button>
          {previewData && (
            <button 
                onClick={handleApply}
                disabled={loading}
                className="bg-red-600 text-white px-6 py-2 rounded-lg font-bold shadow-lg shadow-red-200 hover:bg-red-700 transition-all flex items-center gap-2"
            >
                {loading ? <RefreshCw className="animate-spin" size={16} /> : <CheckCircle size={16} />}
                Rewrite History (Execute)
            </button>
          )}
        </div>

      </div>
    </div>
  );
};

export default RetconModal;

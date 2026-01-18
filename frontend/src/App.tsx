import React, { useState, useEffect } from 'react';
import { api } from './api';
import type { WorkflowState } from './api';
import KnowledgeGraph from './components/KnowledgeGraph';
import ExportModal from './components/ExportModal'; // 🔥 New
import { Download } from 'lucide-react'; // Need to add lucide-react to App imports if not present, but App.tsx likely doesn't have it yet.

// --- Components ---

const StatCard = ({ label, value, color = "blue" }: { label: string, value: string | number, color?: string }) => (
  <div className={`p-4 bg-white border-l-4 border-${color}-500 shadow-sm rounded-r-lg`}>
    <div className="text-xs text-gray-500 uppercase font-bold">{label}</div>
    <div className="text-xl font-mono">{value}</div>
  </div>
);

// --- Helper: Parse Feedback JSON ---
const parseFeedback = (feedback: string | undefined) => {
  if (!feedback) return null;
  try {
    // If it's a JSON string, parse it
    if (feedback.trim().startsWith('{')) {
      return JSON.parse(feedback);
    }
  } catch (e) {
    // Fallback for plain text
  }
  return { suggestion: feedback }; // Treat as plain text suggestion
};

const AuditCard = ({ feedbackRaw }: { feedbackRaw: string }) => {
  const data = parseFeedback(feedbackRaw);
  if (!data) return null;

  const metrics = data.metrics || {};
  const isBlock = data.status === 'BLOCK';
  const suggestion = data.suggestion || "";
  
  // Extract specific reports from suggestion text if not structured
  // (The backend currently dumps reports into 'suggestion' string)
  
  return (
    <div className={`p-4 rounded-xl border ${isBlock ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'} space-y-4`}>
      <div className="flex items-center justify-between">
        <h3 className={`font-bold ${isBlock ? 'text-red-800' : 'text-green-800'} flex items-center gap-2`}>
          {isBlock ? '⛔ REVIEW BLOCKED' : '✅ REVIEW PASSED'}
        </h3>
        {metrics.style_score !== undefined && (
             <span className="text-xs font-mono px-2 py-1 bg-white/50 rounded text-gray-600">
               Style Score: <b>{metrics.style_score}</b>
             </span>
        )}
      </div>

      {/* Scores Grid */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-white/60 p-2 rounded">
           <div className="text-[10px] uppercase text-gray-500 font-bold">Plot Logic</div>
           <div className={`text-lg font-mono font-bold ${metrics.plot_logic_score < 60 ? 'text-red-600' : 'text-blue-600'}`}>
             {metrics.plot_logic_score ?? '-'}
           </div>
        </div>
        <div className="bg-white/60 p-2 rounded">
           <div className="text-[10px] uppercase text-gray-500 font-bold">Alignment</div>
           <div className={`text-lg font-mono font-bold ${metrics.alignment_score < 60 ? 'text-red-600' : 'text-blue-600'}`}>
             {metrics.alignment_score ?? '-'}
           </div>
        </div>
        <div className="bg-white/60 p-2 rounded">
           <div className="text-[10px] uppercase text-gray-500 font-bold">Physics/World</div>
           <div className={`text-lg font-mono font-bold ${metrics.physics_violation_count > 0 ? 'text-red-600' : 'text-green-600'}`}>
             {metrics.physics_violation_count > 0 ? `${metrics.physics_violation_count} Violations` : 'OK'}
           </div>
        </div>
      </div>

      {/* Suggestion / Report Body */}
      {suggestion && (
        <div className="text-sm font-mono whitespace-pre-wrap bg-white/40 p-3 rounded border border-black/5 text-gray-800 leading-relaxed max-h-60 overflow-y-auto">
          {suggestion}
        </div>
      )}
    </div>
  );
};

const App: React.FC = () => {
  const [chapterNum, setChapterNum] = useState(1);
  const [instruction, setInstruction] = useState("");
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  
  // View Mode: 'writer' | 'graph'
  const [viewMode, setViewMode] = useState<'writer' | 'graph'>('writer');
  const [showExport, setShowExport] = useState(false); // 🔥 New State

  // Auto-refresh state if active
  useEffect(() => {
    let interval: any;
    if (workflow?.status === 'active' && workflow.next_nodes.length === 0) {
      // If it's running but not paused yet, poll
      interval = setInterval(async () => {
        const newState = await api.getWorkflowState(chapterNum);
        setWorkflow(newState);
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [workflow, chapterNum]);

  const addLog = (msg: string) => setLogs(prev => [msg, ...prev].slice(0, 10));

  const handleStart = async () => {
    setLoading(true);
    addLog(`🚀 启动章节 ${chapterNum} 生成任务...`);
    try {
      const state = await api.startWorkflow(chapterNum, instruction);
      setWorkflow(state);
      addLog(`✅ 工作流已初始化，当前停在: ${state.next_nodes.join(', ')}`);
    } catch (e) {
      addLog(`❌ 启动失败: ${e}`);
    }
    setLoading(false);
  };

  const handleResume = async () => {
    setLoading(true);
    addLog(`⏭ 继续执行下一阶段...`);
    try {
      const state = await api.resumeWorkflow(chapterNum);
      setWorkflow(state);
      addLog(`✅ 已恢复，当前停在: ${state.next_nodes.join(', ')}`);
    } catch (e) {
      addLog(`❌ 恢复失败: ${e}`);
    }
    setLoading(false);
  };

  const handleUpdate = async (field: string, value: any) => {
    addLog(`🛠 正在手动修改状态: ${field}...`);
    try {
      await api.updateState(chapterNum, { [field]: value });
      const state = await api.getWorkflowState(chapterNum);
      setWorkflow(state);
      addLog(`✅ 状态已同步。`);
    } catch (e) {
      addLog(`❌ 修改失败: ${e}`);
    }
  };

  const handleForcePass = async () => {
    addLog(`🛡️ 正在执行上帝权限: 强制通过模拟器...`);
    try {
      // Set feedback to PASS to bypass the conditional edge logic
      await api.updateState(chapterNum, { "simulator_feedback": "PASS" });
      const state = await api.resumeWorkflow(chapterNum);
      setWorkflow(state);
      addLog(`✅ 已强行突破逻辑死锁。`);
    } catch (e) {
      addLog(`❌ 强制通过失败: ${e}`);
    }
  };

  const handleFixCharacter = async (name: string, field: string, value: any) => {
    addLog(`🛠 上帝模式: 正在修正角色 ${name} 的 ${field}...`);
    try {
      await api.updateCharacter(name, { [field]: value });
      addLog(`✅ 角色数据已修正。`);
      // After fixing character, we might want to reset the retry count and resume
      await api.updateState(chapterNum, { "simulator_retry_count": 0 });
      const state = await api.resumeWorkflow(chapterNum);
      setWorkflow(state);
    } catch (e) {
      addLog(`❌ 修正失败: ${e}`);
    }
  };

  const interventionReason = workflow?.state_values?.intervention_reason;

  return (
    <div className="min-h-screen bg-gray-50 p-8 font-sans text-gray-800 flex flex-col">
      {/* Intervention Overlay / God Mode Console */}
      {interventionReason && (
        <div className="fixed inset-x-0 top-0 z-50 bg-red-600 text-white p-4 shadow-2xl animate-in fade-in slide-in-from-top-4">
          <div className="max-w-7xl mx-auto flex items-start gap-6">
            <div className="bg-white/20 p-2 rounded-lg">
              <span className="text-2xl">⚠️</span>
            </div>
            <div className="flex-1">
              <h3 className="font-bold text-lg uppercase tracking-tight">Logic Deadlock Detected (Simulator Rejected 3x)</h3>
              <p className="text-sm opacity-90 font-mono mt-1 leading-relaxed">{interventionReason}</p>
              
              <div className="mt-4 flex gap-3">
                <button 
                  onClick={handleForcePass}
                  className="bg-white text-red-600 px-4 py-2 rounded font-bold text-xs hover:bg-gray-100 transition-colors"
                >
                  FORCE PASS (Ignore Logic)
                </button>
                
                {/* Context-Aware Quick Fixes (Heuristic) */}
                {interventionReason.includes('断剑') && interventionReason.includes('萧风') && (
                  <button 
                    onClick={() => handleFixCharacter("萧风", "inventory", ["铁剑", "断剑", "神秘黑戒(未激活)", "下品灵石x5"])}
                    className="bg-yellow-400 text-black px-4 py-2 rounded font-bold text-xs hover:bg-yellow-300 transition-colors"
                  >
                    FIX: Add "Broken Sword" to Xiao Feng
                  </button>
                )}

                {interventionReason.includes('已激活') && interventionReason.includes('戒指') && (
                   <button 
                    onClick={() => handleFixCharacter("萧风", "inventory", ["铁剑", "神秘黑戒(已激活)", "下品灵石x5"])}
                    className="bg-blue-400 text-white px-4 py-2 rounded font-bold text-xs hover:bg-blue-300 transition-colors"
                  >
                    FIX: Activate Mystery Ring
                  </button>
                )}

                <button 
                  onClick={() => handleUpdate('intervention_reason', null)}
                  className="border border-white/40 px-4 py-2 rounded font-bold text-xs hover:bg-white/10"
                >
                  DISMISS
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <header className="mb-6 flex justify-between items-center shrink-0">
        <div>
          <h1 className="text-3xl font-black tracking-tighter text-blue-900">INFINITE-FLOW <span className="text-blue-500">WRITER</span></h1>
          <p className="text-sm text-gray-500">2.0M Word Novel Studio | DeepSeek-R1 Inside</p>
        </div>
        
        {/* View Mode Switcher */}
        <div className="flex bg-gray-200 p-1 rounded-lg items-center">
           <button 
             onClick={() => setViewMode('writer')}
             className={`px-4 py-1 rounded-md text-sm font-bold transition-all ${viewMode === 'writer' ? 'bg-white shadow text-blue-600' : 'text-gray-500'}`}
           >
             WRITER
           </button>
           <button 
             onClick={() => setViewMode('graph')}
             className={`px-4 py-1 rounded-md text-sm font-bold transition-all ${viewMode === 'graph' ? 'bg-white shadow text-purple-600' : 'text-gray-500'}`}
           >
             GOD MODE
           </button>
           <div className="w-px h-4 bg-gray-300 mx-2"></div>
           <button
             onClick={() => setShowExport(true)}
             className="px-3 py-1 text-gray-500 hover:text-green-600 hover:bg-white/50 rounded-md transition-all flex items-center gap-1"
             title="Export Novel"
           >
             <Download size={16} />
           </button>
        </div>

        <div className="flex gap-4">
          <StatCard label="Chapter" value={chapterNum} />
          <StatCard label="Tension" value={workflow?.state_values?.reader_feedback?.tension_score || "0"} color="red" />
          <StatCard label="Status" value={workflow?.status || "Idle"} color="green" />
        </div>
      </header>

      <main className="grid grid-cols-12 gap-8 grow h-0">
        
        {/* Left Column: Control Panel */}
        <div className="col-span-4 flex flex-col gap-6 h-full">
          <section className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 shrink-0">
            <h2 className="text-lg font-bold mb-4 flex items-center">🎬 指挥中心</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-gray-400 mb-1">CHAPTER NUMBER</label>
                <input 
                  type="number" 
                  value={chapterNum} 
                  onChange={(e) => setChapterNum(parseInt(e.target.value))}
                  className="w-full p-2 border rounded font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-400 mb-1">DIRECTOR'S ORDER (OPTIONAL)</label>
                <textarea 
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="例如：这一章要重点刻画主角的挣扎..."
                  className="w-full p-2 border rounded text-sm h-24"
                />
              </div>
              <button 
                onClick={handleStart}
                disabled={loading}
                className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {workflow?.status === 'active' ? 'RESTART FLOW' : 'INITIALIZE CHAPTER'}
              </button>
            </div>
          </section>

          <section className="bg-gray-900 text-green-400 p-6 rounded-xl shadow-inner font-mono text-xs grow overflow-y-auto">
            <h2 className="text-gray-500 font-bold mb-2 uppercase tracking-widest">System Logs</h2>
            {logs.map((log, i) => <div key={i} className="mb-1">{`> ${log}`}</div>)}
          </section>
        </div>

        {/* Right Column: Dynamic Stage Area */}
        <div className="col-span-8 h-full flex flex-col">
          
          {/* View Mode Content */}
          {viewMode === 'graph' ? (
              <div className="grow h-full">
                  <KnowledgeGraph />
              </div>
          ) : (
            <div className="space-y-6 h-full overflow-y-auto pr-2 pb-4">
              {/* Workflow Stepper */}
              <div className="bg-white p-2 rounded-full shadow-sm flex items-center justify-around border border-gray-100 shrink-0">
                 {["director", "editor", "simulator", "writer", "reviewer", "archivist"].map((node) => {
                   const isActive = workflow?.next_nodes.includes(node);
                   return (
                     <div key={node} className={`px-4 py-1 rounded-full text-xs font-bold ${isActive ? 'bg-blue-100 text-blue-600 animate-pulse' : 'text-gray-300'}`}>
                       {node.toUpperCase()}
                     </div>
                   );
                 })}
              </div>

              {!workflow && (
                <div className="h-96 border-2 border-dashed border-gray-200 rounded-xl flex items-center justify-center text-gray-400 italic">
                  Ready to start your next masterpiece? Initialize above.
                </div>
              )}

              {workflow && (
                <>
                  {/* Context / Planning View */}
                  {workflow.next_nodes.includes('editor') && (
                    <div className="bg-blue-50 p-6 rounded-xl border border-blue-100">
                      <h3 className="font-bold text-blue-900 mb-2">Director's Decision</h3>
                      <p className="text-sm text-blue-800 italic">"{workflow.state_values.narrative_focus?.goal || 'Establishing context...'}"</p>
                      <button onClick={handleResume} className="mt-4 bg-blue-600 text-white px-6 py-2 rounded-lg font-bold text-sm">PROCEED TO PLANNING</button>
                    </div>
                  )}

                  {/* Editor View */}
                  {(workflow.state_values.outline_data || workflow.next_nodes.includes('writer')) && (
                    <section className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
                      <h2 className="text-lg font-bold mb-4 flex justify-between items-center">
                        📝 Narrative Outline
                        {workflow.next_nodes.includes('writer') && <span className="text-xs bg-yellow-100 text-yellow-600 px-2 py-1 rounded">PAUSED FOR REVIEW</span>}
                      </h2>
                      <textarea 
                        value={Array.isArray(workflow.state_values.outline_data?.outline) ? workflow.state_values.outline_data.outline.join('\n') : ""}
                        onChange={(e) => {
                           const lines = e.target.value.split('\n');
                           handleUpdate('outline_data', { ...workflow.state_values.outline_data, outline: lines });
                        }}
                        className="w-full h-48 p-4 bg-gray-50 font-mono text-sm border-none rounded-lg focus:ring-2 focus:ring-blue-500"
                      />
                      {workflow.next_nodes.includes('writer') && (
                        <button onClick={handleResume} className="mt-4 w-full bg-green-600 text-white py-3 rounded-lg font-bold hover:bg-green-700">CONFIRM & WRITE DRAFT</button>
                      )}
                    </section>
                  )}

                  {/* Writer View */}
                  {workflow.state_values.draft_content && (
                    <section className={`bg-white p-6 rounded-xl shadow-sm border ${workflow.next_nodes.includes('writer') ? 'border-yellow-300' : 'border-gray-100'}`}>
                      <h2 className="text-lg font-bold mb-4 flex justify-between items-center">
                        ✍️ Draft Content
                        {workflow.next_nodes.includes('writer') ? (
                            <span className="text-xs font-bold text-yellow-600 bg-yellow-100 px-2 py-1 rounded">
                                ⚠️ WILL BE OVERWRITTEN (Edit Outline Below)
                            </span>
                        ) : (
                            <span className="text-xs font-normal text-gray-400">You can edit this before proceeding</span>
                        )}
                      </h2>
                      <textarea
                        value={workflow.state_values.draft_content}
                        onChange={(e) => handleUpdate('draft_content', e.target.value)}
                        className={`w-full min-h-[24rem] p-6 rounded-lg font-serif leading-relaxed whitespace-pre-wrap border transition-all outline-none resize-y ${
                            workflow.next_nodes.includes('writer') 
                                ? 'bg-gray-100 text-gray-400 cursor-not-allowed focus:border-gray-200' 
                                : 'bg-gray-50 focus:border-blue-300 focus:bg-white'
                        }`}
                        readOnly={workflow.next_nodes.includes('writer')}
                      />
                      {workflow.next_nodes.includes('archivist') && (
                        <div className="mt-6 flex gap-4">
                          <button onClick={handleResume} className="flex-1 bg-blue-600 text-white py-3 rounded-lg font-bold hover:bg-blue-700 transition-colors">FINALIZE & ARCHIVE</button>
                          <button onClick={() => handleUpdate('revision_count', 0)} className="px-6 py-3 border border-gray-200 rounded-lg text-gray-500 font-bold hover:bg-gray-50">RE-WRITE</button>
                        </div>
                      )}
                    </section>
                  )}

                  {/* Reviewer Feedback */}
                  {workflow.state_values.review_feedback && (
                    <AuditCard feedbackRaw={workflow.state_values.review_feedback} />
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </main>

      {/* Modals */}
      {showExport && <ExportModal currentChapter={chapterNum} onClose={() => setShowExport(false)} />}
    </div>
  );
};

export default App;

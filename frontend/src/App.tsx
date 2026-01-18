import React, { useState, useEffect } from 'react';
import { api, WorkflowState } from './api';
import ChapterSidebar from './components/ChapterSidebar';
import WritingStudio from './components/WritingStudio';
import AIAssistantPanel from './components/AIAssistantPanel';
import WorldPanel from './components/WorldPanel';
import ExportModal from './components/ExportModal';
import {
  Settings,
  Download,
  Globe,
  Moon,
  Sun,
  Menu,
  X
} from 'lucide-react';

const App: React.FC = () => {
  const [currentChapter, setCurrentChapter] = useState(1);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [showWorldPanel, setShowWorldPanel] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [assistantCollapsed, setAssistantCollapsed] = useState(false);

  // Fetch workflow state for current chapter
  useEffect(() => {
    const fetchWorkflow = async () => {
      try {
        const state = await api.getWorkflowState(currentChapter);
        setWorkflow(state);
      } catch (e) {
        console.error('Failed to fetch workflow:', e);
      }
    };

    fetchWorkflow();
    const interval = setInterval(fetchWorkflow, 3000); // Poll every 3s
    return () => clearInterval(interval);
  }, [currentChapter]);

  const handleChapterChange = (num: number) => {
    setCurrentChapter(num);
  };

  const handleNewChapter = () => {
    // Find next available chapter number
    setCurrentChapter((prev) => prev + 1);
  };

  return (
    <div className={`h-screen flex flex-col ${darkMode ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-900'}`}>
      {/* Top Navigation Bar */}
      <header className={`border-b ${darkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} px-6 py-3 flex items-center justify-between shadow-sm z-10`}>
        <div className="flex items-center gap-4">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            {sidebarCollapsed ? <Menu size={20} /> : <X size={20} />}
          </button>

          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-xl">NS</span>
            </div>
            <div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                Novel Studio
              </h1>
              <p className="text-xs text-gray-500">AI-Powered Creative Writing</p>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowWorldPanel(true)}
            className="flex items-center gap-2 px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            title="世界观管理"
          >
            <Globe size={18} />
            <span className="text-sm font-medium hidden md:inline">世界观</span>
          </button>

          <button
            onClick={() => setShowExportModal(true)}
            className="flex items-center gap-2 px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            title="导出小说"
          >
            <Download size={18} />
            <span className="text-sm font-medium hidden md:inline">导出</span>
          </button>

          <div className="w-px h-6 bg-gray-300 dark:bg-gray-600" />

          <button
            onClick={() => setDarkMode(!darkMode)}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            title={darkMode ? '切换到日间模式' : '切换到夜间模式'}
          >
            {darkMode ? <Sun size={18} /> : <Moon size={18} />}
          </button>

          <button
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            title="设置"
          >
            <Settings size={18} />
          </button>

          <button
            onClick={() => setAssistantCollapsed(!assistantCollapsed)}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors md:hidden"
            title="切换AI助手面板"
          >
            <Menu size={18} />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Chapter List */}
        {!sidebarCollapsed && (
          <div className="w-80 flex-shrink-0 overflow-hidden">
            <ChapterSidebar
              currentChapter={currentChapter}
              onChapterSelect={handleChapterChange}
              onNewChapter={handleNewChapter}
            />
          </div>
        )}

        {/* Center - Writing Studio */}
        <div className="flex-1 overflow-hidden">
          <WritingStudio
            chapterNum={currentChapter}
            onChapterChange={handleChapterChange}
          />
        </div>

        {/* Right Sidebar - AI Assistant Panel */}
        {!assistantCollapsed && (
          <div className="w-96 flex-shrink-0 overflow-hidden hidden md:block">
            <AIAssistantPanel
              chapterNum={currentChapter}
              workflow={workflow}
            />
          </div>
        )}
      </div>

      {/* Modals */}
      <WorldPanel isOpen={showWorldPanel} onClose={() => setShowWorldPanel(false)} />
      {showExportModal && (
        <ExportModal
          currentChapter={currentChapter}
          onClose={() => setShowExportModal(false)}
        />
      )}

      {/* Emergency Alert Overlay (God Mode Interventions) */}
      {workflow?.state_values?.intervention_reason && (
        <div className="fixed inset-x-0 bottom-0 z-50 bg-red-600 text-white p-4 shadow-2xl animate-in slide-in-from-bottom-4">
          <div className="max-w-7xl mx-auto flex items-start gap-4">
            <div className="bg-white/20 p-2 rounded-lg">
              <span className="text-2xl">⚠️</span>
            </div>
            <div className="flex-1">
              <h3 className="font-bold text-lg uppercase tracking-tight mb-1">
                Logic Deadlock - Human Intervention Required
              </h3>
              <p className="text-sm opacity-90 font-mono leading-relaxed">
                {workflow.state_values.intervention_reason}
              </p>

              <div className="mt-3 flex gap-3">
                <button
                  onClick={async () => {
                    await api.updateState(currentChapter, { simulator_feedback: 'PASS' });
                    await api.resumeWorkflow(currentChapter);
                  }}
                  className="bg-white text-red-600 px-4 py-2 rounded font-bold text-xs hover:bg-gray-100 transition-colors"
                >
                  FORCE PASS (Ignore Logic)
                </button>

                <button
                  onClick={() => setShowWorldPanel(true)}
                  className="bg-yellow-400 text-black px-4 py-2 rounded font-bold text-xs hover:bg-yellow-300 transition-colors"
                >
                  FIX IN WORLD PANEL
                </button>

                <button
                  onClick={async () => {
                    await api.updateState(currentChapter, { intervention_reason: null });
                  }}
                  className="border border-white/40 px-4 py-2 rounded font-bold text-xs hover:bg-white/10"
                >
                  DISMISS
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;

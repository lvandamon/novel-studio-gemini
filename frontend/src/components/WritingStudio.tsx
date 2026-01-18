import React, { useState, useEffect } from 'react';
import { api, WorkflowState } from '../api';
import {
  BookOpen,
  Sparkles,
  Users,
  Map,
  Settings,
  ChevronLeft,
  ChevronRight,
  Play,
  Pause,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Loader
} from 'lucide-react';

interface WritingStudioProps {
  chapterNum: number;
  onChapterChange: (num: number) => void;
}

const WritingStudio: React.FC<WritingStudioProps> = ({ chapterNum, onChapterChange }) => {
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [content, setContent] = useState<string>('');
  const [outline, setOutline] = useState<string[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentAgent, setCurrentAgent] = useState<string>('');

  // Fetch workflow state
  useEffect(() => {
    const fetchState = async () => {
      try {
        const state = await api.getWorkflowState(chapterNum);
        setWorkflow(state);
        if (state.state_values?.draft_content) {
          setContent(state.state_values.draft_content);
        }
        if (state.state_values?.outline_data?.outline) {
          setOutline(state.state_values.outline_data.outline);
        }
      } catch (e) {
        console.error('Failed to fetch state:', e);
      }
    };

    fetchState();
    const interval = setInterval(fetchState, 3000); // Poll every 3s
    return () => clearInterval(interval);
  }, [chapterNum]);

  // Determine current agent
  useEffect(() => {
    if (workflow?.next_nodes && workflow.next_nodes.length > 0) {
      setCurrentAgent(workflow.next_nodes[0]);
    } else if (workflow?.status === 'active') {
      setCurrentAgent('processing');
    } else {
      setCurrentAgent('');
    }
  }, [workflow]);

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      await api.startWorkflow(chapterNum);
    } catch (e) {
      console.error('Generation failed:', e);
    }
    setIsGenerating(false);
  };

  const handleContinue = async () => {
    setIsGenerating(true);
    try {
      await api.resumeWorkflow(chapterNum);
    } catch (e) {
      console.error('Resume failed:', e);
    }
    setIsGenerating(false);
  };

  const handleContentChange = async (newContent: string) => {
    setContent(newContent);
    // Auto-save after 2 seconds of inactivity
    // TODO: Add debounced save
  };

  const getAgentStatus = () => {
    const agents = ['director', 'editor', 'writer', 'simulator', 'reviewer', 'archivist'];
    return agents.map(agent => ({
      name: agent,
      active: currentAgent === agent,
      completed: workflow?.state_values?.[`${agent}_completed`] || false
    }));
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Writing Header */}
      <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between bg-gradient-to-r from-blue-50 to-purple-50">
        <div className="flex items-center gap-4">
          <button
            onClick={() => onChapterChange(Math.max(1, chapterNum - 1))}
            className="p-2 hover:bg-white rounded-lg transition-colors"
            disabled={chapterNum <= 1}
          >
            <ChevronLeft size={20} />
          </button>

          <div className="flex flex-col">
            <span className="text-xs text-gray-500 font-medium">当前章节</span>
            <span className="text-2xl font-bold text-gray-800">第 {chapterNum} 章</span>
          </div>

          <button
            onClick={() => onChapterChange(chapterNum + 1)}
            className="p-2 hover:bg-white rounded-lg transition-colors"
          >
            <ChevronRight size={20} />
          </button>
        </div>

        {/* AI Status Indicator */}
        <div className="flex items-center gap-3">
          {isGenerating || currentAgent ? (
            <div className="flex items-center gap-2 px-4 py-2 bg-blue-100 text-blue-700 rounded-full animate-pulse">
              <Loader size={16} className="animate-spin" />
              <span className="text-sm font-medium">
                {currentAgent === 'director' && 'Director 规划中...'}
                {currentAgent === 'editor' && 'Editor 编排大纲...'}
                {currentAgent === 'writer' && 'Writer 撰写中...'}
                {currentAgent === 'simulator' && 'Simulator 验证逻辑...'}
                {currentAgent === 'reviewer' && 'Reviewer 审查质量...'}
                {currentAgent === 'archivist' && 'Archivist 归档数据...'}
                {currentAgent === 'processing' && 'AI 处理中...'}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-4 py-2 bg-green-100 text-green-700 rounded-full">
              <CheckCircle size={16} />
              <span className="text-sm font-medium">就绪</span>
            </div>
          )}

          {!content && (
            <button
              onClick={handleGenerate}
              disabled={isGenerating}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              <Sparkles size={16} />
              生成本章
            </button>
          )}

          {workflow?.next_nodes && workflow.next_nodes.length > 0 && (
            <button
              onClick={handleContinue}
              disabled={isGenerating}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50"
            >
              <Play size={16} />
              继续创作
            </button>
          )}
        </div>
      </div>

      {/* Outline Section (Collapsible) */}
      {outline.length > 0 && (
        <div className="border-b border-gray-200 bg-yellow-50 px-6 py-4">
          <div className="flex items-center gap-2 mb-2">
            <BookOpen size={18} className="text-yellow-700" />
            <span className="font-bold text-yellow-800">大纲</span>
          </div>
          <ul className="space-y-1 text-sm text-yellow-900 pl-6">
            {outline.map((line, idx) => (
              <li key={idx} className="list-disc">{line}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Main Editor */}
      <div className="flex-1 overflow-y-auto px-12 py-8">
        {content ? (
          <textarea
            value={content}
            onChange={(e) => handleContentChange(e.target.value)}
            className="w-full h-full resize-none border-none outline-none text-lg leading-relaxed font-serif text-gray-800"
            placeholder="AI将在此生成章节内容，您也可以直接编辑..."
            style={{ minHeight: '600px' }}
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-gray-400">
            <Sparkles size={64} className="mb-4 opacity-20" />
            <p className="text-lg">点击"生成本章"开始创作</p>
            <p className="text-sm mt-2">AI将根据剧情规划自动撰写内容</p>
          </div>
        )}
      </div>

      {/* AI Progress Bar */}
      {workflow?.status === 'active' && (
        <div className="border-t border-gray-200 px-6 py-3 bg-gray-50">
          <div className="flex items-center gap-4">
            {getAgentStatus().map((agent, idx) => (
              <div key={agent.name} className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full transition-all ${
                  agent.active ? 'bg-blue-500 animate-pulse' :
                  agent.completed ? 'bg-green-500' :
                  'bg-gray-300'
                }`} />
                <span className={`text-xs font-medium uppercase ${
                  agent.active ? 'text-blue-700' :
                  agent.completed ? 'text-green-700' :
                  'text-gray-400'
                }`}>
                  {agent.name}
                </span>
                {idx < getAgentStatus().length - 1 && (
                  <ChevronRight size={12} className="text-gray-400 ml-2" />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default WritingStudio;

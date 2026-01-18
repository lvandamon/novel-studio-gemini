import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { Plus, FileText, Check, Clock, AlertTriangle } from 'lucide-react';

interface Chapter {
  num: number;
  title?: string;
  status: 'draft' | 'completed' | 'error' | 'empty';
  wordCount?: number;
}

interface ChapterSidebarProps {
  currentChapter: number;
  onChapterSelect: (num: number) => void;
  onNewChapter: () => void;
}

const ChapterSidebar: React.FC<ChapterSidebarProps> = ({
  currentChapter,
  onChapterSelect,
  onNewChapter
}) => {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    // Fetch all chapters from API
    // For now, we'll simulate by checking workflow states
    const fetchChapters = async () => {
      const chapterList: Chapter[] = [];

      // Check chapters 1-100 (or fetch from a dedicated endpoint)
      for (let i = 1; i <= 50; i++) {
        try {
          const state = await api.getWorkflowState(i);
          chapterList.push({
            num: i,
            title: `第 ${i} 章`,
            status: state.status === 'completed' ? 'completed' :
                    state.status === 'active' ? 'draft' :
                    state.status === 'error' ? 'error' : 'empty',
            wordCount: state.state_values?.draft_content?.length || 0
          });
        } catch (e) {
          chapterList.push({
            num: i,
            title: `第 ${i} 章`,
            status: 'empty'
          });
        }
      }

      setChapters(chapterList);
    };

    // For performance, only fetch first 20 on mount
    const fetchLimited = async () => {
      const chapterList: Chapter[] = [];
      for (let i = 1; i <= 20; i++) {
        try {
          const state = await api.getWorkflowState(i);
          chapterList.push({
            num: i,
            title: `第 ${i} 章`,
            status: state.status === 'completed' ? 'completed' :
                    state.status === 'active' ? 'draft' :
                    state.status === 'error' ? 'error' : 'empty',
            wordCount: state.state_values?.draft_content?.length || 0
          });
        } catch (e) {
          chapterList.push({
            num: i,
            title: `第 ${i} 章`,
            status: 'empty'
          });
        }
      }
      setChapters(chapterList);
    };

    fetchLimited();
  }, []);

  const filteredChapters = chapters.filter(ch =>
    ch.title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    ch.num.toString().includes(searchTerm)
  );

  const getStatusIcon = (status: Chapter['status']) => {
    switch (status) {
      case 'completed':
        return <Check size={14} className="text-green-600" />;
      case 'draft':
        return <Clock size={14} className="text-yellow-600" />;
      case 'error':
        return <AlertTriangle size={14} className="text-red-600" />;
      default:
        return <FileText size={14} className="text-gray-400" />;
    }
  };

  const getStatusColor = (status: Chapter['status']) => {
    switch (status) {
      case 'completed':
        return 'border-l-green-500 bg-green-50';
      case 'draft':
        return 'border-l-yellow-500 bg-yellow-50';
      case 'error':
        return 'border-l-red-500 bg-red-50';
      default:
        return 'border-l-gray-300 bg-white';
    }
  };

  return (
    <div className="h-full flex flex-col bg-gray-50 border-r border-gray-200">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-bold text-gray-800">章节列表</h2>
          <button
            onClick={onNewChapter}
            className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            title="新建章节"
          >
            <Plus size={18} />
          </button>
        </div>

        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="搜索章节..."
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Chapter List */}
      <div className="flex-1 overflow-y-auto p-2">
        {filteredChapters.length === 0 ? (
          <div className="text-center text-gray-400 py-8 text-sm">
            暂无章节
          </div>
        ) : (
          <div className="space-y-1">
            {filteredChapters.map((chapter) => (
              <button
                key={chapter.num}
                onClick={() => onChapterSelect(chapter.num)}
                className={`w-full text-left px-3 py-3 rounded-lg border-l-4 transition-all ${
                  chapter.num === currentChapter
                    ? 'bg-blue-100 border-l-blue-600 shadow-sm'
                    : getStatusColor(chapter.status) + ' hover:shadow-sm'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-sm font-bold ${
                    chapter.num === currentChapter ? 'text-blue-900' : 'text-gray-700'
                  }`}>
                    {chapter.title}
                  </span>
                  {getStatusIcon(chapter.status)}
                </div>

                {chapter.wordCount && chapter.wordCount > 0 && (
                  <div className="text-xs text-gray-500">
                    {chapter.wordCount.toLocaleString()} 字
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Stats Footer */}
      <div className="p-4 border-t border-gray-200 bg-white">
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="p-2 bg-green-50 rounded">
            <div className="text-xs text-green-600 font-medium">已完成</div>
            <div className="text-lg font-bold text-green-700">
              {chapters.filter(c => c.status === 'completed').length}
            </div>
          </div>
          <div className="p-2 bg-yellow-50 rounded">
            <div className="text-xs text-yellow-600 font-medium">草稿</div>
            <div className="text-lg font-bold text-yellow-700">
              {chapters.filter(c => c.status === 'draft').length}
            </div>
          </div>
          <div className="p-2 bg-gray-50 rounded">
            <div className="text-xs text-gray-600 font-medium">总计</div>
            <div className="text-lg font-bold text-gray-700">
              {chapters.length}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChapterSidebar;

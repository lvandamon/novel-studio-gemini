import React, { useState, useEffect, useRef } from 'react';
import { 
  BookOpen, 
  PenTool, 
  Map, 
  Globe, 
  Activity, 
  Send, 
  Save, 
  Loader2,
  Menu,
  ChevronRight,
  Bot,
  User
} from 'lucide-react';
import { api } from './api';
import clsx from 'clsx';

// --- Types ---
interface Message {
  role: 'user' | 'assistant';
  content: string;
}

// --- Components ---

const Sidebar = () => (
  <div className="w-16 h-screen bg-gray-50 border-r border-gray-200 flex flex-col items-center py-6 gap-6 z-10">
    <div className="p-2 bg-gray-900 text-white rounded-lg mb-4">
      <BookOpen size={24} />
    </div>
    
    <NavIcon icon={<PenTool />} label="Write" active />
    <NavIcon icon={<Map />} label="Plot" />
    <NavIcon icon={<Globe />} label="World" />
    <NavIcon icon={<Activity />} label="Stats" />
  </div>
);

const NavIcon = ({ icon, label, active = false }: { icon: React.ReactNode, label: string, active?: boolean }) => (
  <div className={clsx(
    "p-3 rounded-xl cursor-pointer transition-all duration-200 group relative",
    active ? "bg-white shadow-sm text-gray-900" : "text-gray-400 hover:text-gray-600 hover:bg-gray-100"
  )}>
    {icon}
    <span className="absolute left-14 bg-gray-800 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
      {label}
    </span>
  </div>
);

// --- Main App ---

export default function App() {
  // State
  const [content, setContent] = useState("");
  const [chapterNum, setChapterNum] = useState(1);
  const [isGenerating, setIsGenerating] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'Director Online. 准备好开始了吗？' }
  ]);
  const [input, setInput] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load initial state
  useEffect(() => {
    loadState();
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadState = async () => {
    try {
      const state = await api.getState();
      setChapterNum(state.current_chapter);
      // Try to load content if it exists (previous chapter or current draft)
      try {
        const chap = await api.getChapter(state.current_chapter);
        if (chap.content) setContent(chap.content);
      } catch (e) {
        // No content yet, that's fine
      }
    } catch (e) {
      console.error("Failed to load state", e);
    }
  };

  const handleGenerate = async () => {
    if (!input.trim()) return;

    const userMsg = input;
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setInput("");
    setIsGenerating(true);

    // Add thinking placeholder
    setMessages(prev => [...prev, { role: 'assistant', content: 'Thinking...' }]);

    try {
      const res = await api.generate(userMsg);
      
      if (res.success) {
        // Update content
        setContent(res.content);
        // Update chat by replacing "Thinking..."
        setMessages(prev => [
          ...prev.slice(0, -1), 
          { role: 'assistant', content: `✅ Chapter ${res.chapter_num} Generated.` }
        ]);
        setChapterNum(res.chapter_num + 1); // Advance for next
      } else {
        setMessages(prev => [
          ...prev.slice(0, -1), 
          { role: 'assistant', content: `❌ Error: ${res.error}` }
        ]);
      }
    } catch (e) {
      setMessages(prev => [
        ...prev.slice(0, -1), 
        { role: 'assistant', content: `❌ System Error: ${e}` }
      ]);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSave = async () => {
    try {
      // We save to the current active chapter index (usually chapterNum - 1 if we just generated it)
      // This logic is a bit loose in the demo, let's assume we are editing "Current Head"
      // Ideally UI lets you select chapter.
      const targetChap = chapterNum > 1 ? chapterNum - 1 : 1; 
      await api.updateChapter(targetChap, content);
      setMessages(prev => [...prev, { role: 'assistant', content: "💾 Saved to disk." }]);
    } catch (e) {
      alert("Save failed");
    }
  };

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden font-sans">
      <Sidebar />

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* Editor Area (Left/Center) */}
        <div className="flex-1 flex flex-col relative min-w-0">
          {/* Toolbar */}
          <div className="h-16 border-b border-gray-200 flex items-center justify-between px-8 bg-white/50 backdrop-blur-sm z-10">
            <div className="flex items-center gap-2 text-gray-500">
              <span className="font-serif font-bold text-gray-800">Chapter {chapterNum > 1 ? chapterNum - 1 : 1}</span>
              <ChevronRight size={16} />
              <span className="text-sm">Draft</span>
            </div>
            
            <button 
              onClick={handleSave}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 bg-white border border-gray-200 rounded-full shadow-sm hover:shadow transition-all"
            >
              <Save size={16} />
              Save
            </button>
          </div>

          {/* Editor Paper */}
          <div className="flex-1 overflow-y-auto p-8 flex justify-center bg-[#f5f5f5]">
            <div className="w-full max-w-3xl h-full pb-20">
              <textarea
                className="editor-content"
                placeholder="Start writing or ask the Director to generate..."
                value={content}
                onChange={(e) => setContent(e.target.value)}
                spellCheck={false}
              />
            </div>
          </div>
        </div>

        {/* Chat / Copilot Area (Right) */}
        <div className="w-[400px] border-l border-gray-200 bg-white flex flex-col shadow-xl z-20">
          <div className="h-16 border-b border-gray-200 flex items-center px-6 bg-gray-50/50">
            <span className="font-semibold text-gray-700 flex items-center gap-2">
              <Bot size={18} className="text-indigo-600"/> 
              Director Co-Pilot
            </span>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-gray-50/30">
            {messages.map((msg, idx) => (
              <div key={idx} className={clsx("flex gap-3", msg.role === 'user' ? "flex-row-reverse" : "")}>
                <div className={clsx(
                  "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                  msg.role === 'assistant' ? "bg-indigo-100 text-indigo-600" : "bg-gray-200 text-gray-600"
                )}>
                  {msg.role === 'assistant' ? <Bot size={16} /> : <User size={16} />}
                </div>
                <div className={clsx(
                  "p-4 rounded-2xl max-w-[85%] text-sm leading-relaxed shadow-sm",
                  msg.role === 'assistant' ? "bg-white border border-gray-100 text-gray-700" : "bg-indigo-600 text-white"
                )}>
                  {msg.content === "Thinking..." ? (
                    <div className="flex items-center gap-2">
                      <Loader2 size={14} className="animate-spin" />
                      <span>Thinking...</span>
                    </div>
                  ) : msg.content}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div className="p-4 border-t border-gray-200 bg-white">
            <div className="relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleGenerate();
                  }
                }}
                placeholder="Give instructions to the Director..."
                className="w-full pl-4 pr-12 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none resize-none text-sm min-h-[50px] max-h-[150px]"
                rows={1}
                disabled={isGenerating}
              />
              <button 
                onClick={handleGenerate}
                disabled={!input.trim() || isGenerating}
                className="absolute right-2 bottom-2 p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:hover:bg-indigo-600 transition-colors"
              >
                {isGenerating ? <Loader2 size={16} className="animate-spin"/> : <Send size={16} />}
              </button>
            </div>
            <div className="text-xs text-center text-gray-400 mt-2">
              Cmd + Enter to send
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
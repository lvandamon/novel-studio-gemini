import React, { useState, useEffect } from 'react';
import { api, WorkflowState } from '../api';
import {
  Brain,
  Users,
  Map,
  Activity,
  TrendingUp,
  AlertCircle,
  CheckCircle,
  Clock,
  Zap
} from 'lucide-react';

interface AIAssistantPanelProps {
  chapterNum: number;
  workflow: WorkflowState | null;
}

const AIAssistantPanel: React.FC<AIAssistantPanelProps> = ({ chapterNum, workflow }) => {
  const [activeTab, setActiveTab] = useState<'agents' | 'characters' | 'metrics'>('agents');
  const [characters, setCharacters] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const chars = await api.listCharacters();
        setCharacters(chars);
      } catch (e) {
        console.error('Failed to fetch characters:', e);
      }
    };
    fetchData();
  }, [chapterNum]);

  // Parse metrics from workflow state
  useEffect(() => {
    if (workflow?.state_values?.review_feedback) {
      try {
        const feedback = JSON.parse(workflow.state_values.review_feedback);
        setMetrics(feedback.metrics);
      } catch (e) {
        // Plain text feedback
      }
    }
  }, [workflow]);

  const agentStages = [
    { name: 'Director', key: 'director', icon: Brain, color: 'purple', desc: '战略规划' },
    { name: 'Editor', key: 'editor', icon: Map, color: 'blue', desc: '大纲编排' },
    { name: 'Writer', key: 'writer', icon: Zap, color: 'yellow', desc: '内容撰写' },
    { name: 'Simulator', key: 'simulator', icon: Activity, color: 'green', desc: '逻辑验证' },
    { name: 'Reviewer', key: 'reviewer', icon: CheckCircle, color: 'indigo', desc: '质量审查' },
    { name: 'Archivist', key: 'archivist', icon: Clock, color: 'gray', desc: '数据归档' }
  ];

  const getAgentStatus = (key: string) => {
    if (!workflow) return 'pending';
    if (workflow.next_nodes.includes(key)) return 'active';
    if (workflow.state_values?.[`${key}_completed`]) return 'completed';
    return 'pending';
  };

  return (
    <div className="h-full flex flex-col bg-white border-l border-gray-200">
      {/* Header Tabs */}
      <div className="border-b border-gray-200 flex">
        <button
          onClick={() => setActiveTab('agents')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            activeTab === 'agents'
              ? 'bg-white text-blue-600 border-b-2 border-blue-600'
              : 'bg-gray-50 text-gray-600 hover:text-gray-800'
          }`}
        >
          AI Agents
        </button>
        <button
          onClick={() => setActiveTab('characters')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            activeTab === 'characters'
              ? 'bg-white text-blue-600 border-b-2 border-blue-600'
              : 'bg-gray-50 text-gray-600 hover:text-gray-800'
          }`}
        >
          角色
        </button>
        <button
          onClick={() => setActiveTab('metrics')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            activeTab === 'metrics'
              ? 'bg-white text-blue-600 border-b-2 border-blue-600'
              : 'bg-gray-50 text-gray-600 hover:text-gray-800'
          }`}
        >
          指标
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'agents' && (
          <div className="space-y-3">
            <div className="text-xs text-gray-500 uppercase font-bold mb-4">创作流程</div>
            {agentStages.map((agent) => {
              const status = getAgentStatus(agent.key);
              const Icon = agent.icon;

              return (
                <div
                  key={agent.key}
                  className={`p-4 rounded-lg border-2 transition-all ${
                    status === 'active'
                      ? `border-${agent.color}-500 bg-${agent.color}-50 shadow-md`
                      : status === 'completed'
                      ? 'border-green-300 bg-green-50'
                      : 'border-gray-200 bg-gray-50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`p-2 rounded-lg ${
                        status === 'active'
                          ? `bg-${agent.color}-500 text-white`
                          : status === 'completed'
                          ? 'bg-green-500 text-white'
                          : 'bg-gray-300 text-gray-600'
                      }`}
                    >
                      <Icon size={18} />
                    </div>

                    <div className="flex-1">
                      <div className="font-bold text-gray-800">{agent.name}</div>
                      <div className="text-xs text-gray-600">{agent.desc}</div>
                    </div>

                    {status === 'active' && (
                      <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                    )}
                    {status === 'completed' && (
                      <CheckCircle size={18} className="text-green-600" />
                    )}
                  </div>

                  {status === 'active' && workflow?.state_values && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <div className="text-xs text-gray-600">
                        {agent.key === 'writer' && workflow.state_values.revision_count > 0 && (
                          <div>第 {workflow.state_values.revision_count} 轮修订</div>
                        )}
                        {agent.key === 'simulator' && workflow.state_values.simulator_retry_count > 0 && (
                          <div className="text-yellow-600">
                            ⚠️ 逻辑验证失败 {workflow.state_values.simulator_retry_count} 次
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {activeTab === 'characters' && (
          <div className="space-y-3">
            <div className="text-xs text-gray-500 uppercase font-bold mb-4">活跃角色</div>
            {characters.length === 0 ? (
              <div className="text-center text-gray-400 py-8 text-sm">暂无角色数据</div>
            ) : (
              characters.slice(0, 10).map((char) => (
                <div
                  key={char.name}
                  className="p-4 bg-gray-50 rounded-lg border border-gray-200 hover:border-blue-300 transition-colors cursor-pointer"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-gray-800">{char.name}</span>
                    {char.realm && (
                      <span className="text-xs px-2 py-1 bg-purple-100 text-purple-700 rounded-full">
                        {char.realm}
                      </span>
                    )}
                  </div>

                  {char.motivation && (
                    <div className="text-xs text-gray-600 line-clamp-2">
                      {char.motivation}
                    </div>
                  )}

                  {char.inventory && char.inventory.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {char.inventory.slice(0, 3).map((item: string, idx: number) => (
                        <span
                          key={idx}
                          className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded"
                        >
                          {item}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === 'metrics' && (
          <div className="space-y-4">
            <div className="text-xs text-gray-500 uppercase font-bold mb-4">质量指标</div>

            {!metrics ? (
              <div className="text-center text-gray-400 py-8 text-sm">
                等待审查数据...
              </div>
            ) : (
              <>
                <div className="p-4 bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg border border-blue-200">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-blue-900">剧情逻辑</span>
                    <TrendingUp size={16} className="text-blue-600" />
                  </div>
                  <div className="text-3xl font-bold text-blue-700">
                    {metrics.plot_logic_score || 0}
                  </div>
                  <div className="mt-2 w-full bg-blue-200 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all"
                      style={{ width: `${metrics.plot_logic_score || 0}%` }}
                    />
                  </div>
                </div>

                <div className="p-4 bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg border border-purple-200">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-purple-900">风格一致性</span>
                    <TrendingUp size={16} className="text-purple-600" />
                  </div>
                  <div className="text-3xl font-bold text-purple-700">
                    {metrics.alignment_score || 0}
                  </div>
                  <div className="mt-2 w-full bg-purple-200 rounded-full h-2">
                    <div
                      className="bg-purple-600 h-2 rounded-full transition-all"
                      style={{ width: `${metrics.alignment_score || 0}%` }}
                    />
                  </div>
                </div>

                <div className="p-4 bg-gradient-to-br from-green-50 to-green-100 rounded-lg border border-green-200">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-green-900">物理规则</span>
                    {metrics.physics_violation_count === 0 ? (
                      <CheckCircle size={16} className="text-green-600" />
                    ) : (
                      <AlertCircle size={16} className="text-red-600" />
                    )}
                  </div>
                  <div className="text-3xl font-bold text-green-700">
                    {metrics.physics_violation_count === 0 ? '✓' : metrics.physics_violation_count}
                  </div>
                  <div className="text-xs text-green-700 mt-1">
                    {metrics.physics_violation_count === 0 ? '无违规' : '项违规'}
                  </div>
                </div>

                {workflow?.state_values?.reader_feedback?.tension_score && (
                  <div className="p-4 bg-gradient-to-br from-red-50 to-red-100 rounded-lg border border-red-200">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-red-900">张力值</span>
                      <Activity size={16} className="text-red-600" />
                    </div>
                    <div className="text-3xl font-bold text-red-700">
                      {workflow.state_values.reader_feedback.tension_score}
                    </div>
                    <div className="text-xs text-red-700 mt-1">
                      目标: 60-80
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AIAssistantPanel;

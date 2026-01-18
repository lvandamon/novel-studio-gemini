import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { Map, Users, Package, BookOpen, Globe, X } from 'lucide-react';
import KnowledgeGraph from './KnowledgeGraph';

interface WorldPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const WorldPanel: React.FC<WorldPanelProps> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<'graph' | 'characters' | 'items' | 'lore'>('graph');
  const [characters, setCharacters] = useState<any[]>([]);
  const [selectedCharacter, setSelectedCharacter] = useState<any>(null);

  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen]);

  const fetchData = async () => {
    try {
      const chars = await api.listCharacters();
      setCharacters(chars);
    } catch (e) {
      console.error('Failed to fetch world data:', e);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-2xl w-[90vw] h-[85vh] flex flex-col">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between bg-gradient-to-r from-purple-50 to-blue-50">
          <div className="flex items-center gap-3">
            <Globe size={24} className="text-purple-600" />
            <h2 className="text-2xl font-bold text-gray-800">世界观管理</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white rounded-lg transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 flex px-6">
          <button
            onClick={() => setActiveTab('graph')}
            className={`px-6 py-3 font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'graph'
                ? 'text-purple-600 border-b-2 border-purple-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <Map size={18} />
            知识图谱
          </button>
          <button
            onClick={() => setActiveTab('characters')}
            className={`px-6 py-3 font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'characters'
                ? 'text-purple-600 border-b-2 border-purple-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <Users size={18} />
            角色库
          </button>
          <button
            onClick={() => setActiveTab('items')}
            className={`px-6 py-3 font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'items'
                ? 'text-purple-600 border-b-2 border-purple-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <Package size={18} />
            物品系统
          </button>
          <button
            onClick={() => setActiveTab('lore')}
            className={`px-6 py-3 font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'lore'
                ? 'text-purple-600 border-b-2 border-purple-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <BookOpen size={18} />
            世界设定
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {activeTab === 'graph' && (
            <div className="h-full">
              <KnowledgeGraph />
            </div>
          )}

          {activeTab === 'characters' && (
            <div className="h-full flex">
              {/* Character List */}
              <div className="w-1/3 border-r border-gray-200 overflow-y-auto p-4">
                <div className="space-y-2">
                  {characters.map((char) => (
                    <button
                      key={char.name}
                      onClick={() => setSelectedCharacter(char)}
                      className={`w-full text-left p-4 rounded-lg border transition-all ${
                        selectedCharacter?.name === char.name
                          ? 'bg-purple-50 border-purple-300 shadow'
                          : 'bg-white border-gray-200 hover:border-purple-200'
                      }`}
                    >
                      <div className="font-bold text-gray-800 mb-1">{char.name}</div>
                      {char.realm && (
                        <div className="text-xs text-purple-600 mb-2">{char.realm}</div>
                      )}
                      {char.faction && (
                        <div className="text-xs text-gray-500">{char.faction}</div>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Character Detail */}
              <div className="flex-1 overflow-y-auto p-6">
                {selectedCharacter ? (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-3xl font-bold text-gray-800 mb-2">
                        {selectedCharacter.name}
                      </h3>
                      {selectedCharacter.realm && (
                        <div className="inline-block px-4 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
                          {selectedCharacter.realm}
                        </div>
                      )}
                    </div>

                    {selectedCharacter.motivation && (
                      <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                        <div className="text-xs text-blue-600 font-bold uppercase mb-2">动机</div>
                        <div className="text-gray-800">{selectedCharacter.motivation}</div>
                      </div>
                    )}

                    {selectedCharacter.appearance && (
                      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="text-xs text-gray-600 font-bold uppercase mb-2">外貌</div>
                        <div className="text-gray-800">{selectedCharacter.appearance}</div>
                      </div>
                    )}

                    {selectedCharacter.personality_golden && (
                      <div className="p-4 bg-yellow-50 rounded-lg border border-yellow-200">
                        <div className="text-xs text-yellow-700 font-bold uppercase mb-2">
                          ⭐ 黄金人格锚点
                        </div>
                        <div className="text-gray-800">{selectedCharacter.personality_golden}</div>
                      </div>
                    )}

                    {selectedCharacter.inventory && selectedCharacter.inventory.length > 0 && (
                      <div>
                        <div className="text-sm font-bold text-gray-700 mb-2">物品清单</div>
                        <div className="flex flex-wrap gap-2">
                          {selectedCharacter.inventory.map((item: string, idx: number) => (
                            <div
                              key={idx}
                              className="px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800"
                            >
                              {item}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {selectedCharacter.relationships && Object.keys(selectedCharacter.relationships).length > 0 && (
                      <div>
                        <div className="text-sm font-bold text-gray-700 mb-2">人物关系</div>
                        <div className="space-y-2">
                          {Object.entries(selectedCharacter.relationships).map(([name, relation]: [string, any]) => (
                            <div
                              key={name}
                              className="p-3 bg-purple-50 border border-purple-200 rounded-lg"
                            >
                              <div className="font-medium text-gray-800">{name}</div>
                              <div className="text-sm text-purple-700">{relation}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <div className="text-center">
                      <Users size={64} className="mx-auto mb-4 opacity-20" />
                      <p>选择一个角色查看详情</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'items' && (
            <div className="h-full flex items-center justify-center text-gray-400">
              <div className="text-center">
                <Package size={64} className="mx-auto mb-4 opacity-20" />
                <p>物品系统开发中...</p>
              </div>
            </div>
          )}

          {activeTab === 'lore' && (
            <div className="h-full flex items-center justify-center text-gray-400">
              <div className="text-center">
                <BookOpen size={64} className="mx-auto mb-4 opacity-20" />
                <p>世界设定开发中...</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default WorldPanel;

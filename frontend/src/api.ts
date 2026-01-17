import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

export interface WorkflowState {
  status: 'not_started' | 'active' | 'completed' | 'error';
  next_nodes: string[];
  state_values: any;
  created_at?: string;
}

export interface GraphData {
  nodes: any[];
  edges: any[];
}

export const api = {
  // --- Workflow Controls ---
  
  async startWorkflow(chapterNum: number, instruction?: string) {
    const res = await axios.post(`${API_BASE}/workflow/start`, {
      chapter_num: chapterNum,
      instruction: instruction
    });
    return res.data as WorkflowState;
  },

  async getWorkflowState(chapterNum: number) {
    const res = await axios.get(`${API_BASE}/workflow/${chapterNum}/state`);
    return res.data as WorkflowState;
  },

  async resumeWorkflow(chapterNum: number, userInput?: any) {
    const res = await axios.post(`${API_BASE}/workflow/resume`, {
      chapter_num: chapterNum,
      user_input: userInput
    });
    return res.data as WorkflowState;
  },

  async updateState(chapterNum: number, updates: any) {
    const res = await axios.post(`${API_BASE}/workflow/update`, {
      chapter_num: chapterNum,
      state_updates: updates
    });
    return res.data;
  },

  // --- Knowledge Graph ---

  async getGraphData(limit: number = 100) {
    const res = await axios.get(`${API_BASE}/graph/visualize?limit=${limit}`);
    return res.data as GraphData;
  },

  async getImpactGraph(entity: string) {
    const res = await axios.get(`${API_BASE}/graph/impact?entity=${entity}`);
    return res.data as GraphData;
  },

  // --- Traditional Data ---

  async getChapter(chapterNum: number) {
    const res = await axios.get(`${API_BASE}/chapters/${chapterNum}`);
    return res.data;
  },

  async listCharacters() {
    const res = await axios.get(`${API_BASE}/characters`);
    return res.data;
  },

  async updateCharacter(name: string, updates: any) {
    const res = await axios.post(`${API_BASE}/characters/${name}/update`, {
      updates: updates
    });
    return res.data;
  }
};
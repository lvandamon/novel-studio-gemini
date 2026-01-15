import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

export const api = {
  health: () => axios.get(`${API_BASE}/health`),
  
  getState: async () => {
    const res = await axios.get(`${API_BASE}/state`);
    return res.data;
  },
  
  generate: async (instruction: str, flashback?: str, forceDirector: boolean = true) => {
    const res = await axios.post(`${API_BASE}/generate`, {
      instruction,
      flashback,
      force_director: forceDirector
    });
    return res.data;
  },
  
  getChapter: async (num: number) => {
    const res = await axios.get(`${API_BASE}/chapters/${num}`);
    return res.data;
  },
  
  updateChapter: async (num: number, content: string) => {
    const res = await axios.put(`${API_BASE}/chapters/${num}`, { content });
    return res.data;
  }
};

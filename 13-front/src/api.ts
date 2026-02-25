import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:5101/api', // バックエンドAPIのURLに合わせて変更
  headers: {
    'Content-Type': 'application/json',
  },
});

export const sendMessage = async (message: string) => {
  const response = await api.post('/chat', { message });
  return response.data;
};

export default api;

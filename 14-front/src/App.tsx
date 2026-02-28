import React, { useState, useRef, useEffect } from 'react';
import ChatMessage from './components/ChatMessage';
import { sendMessage } from './api';

interface Message {
  sender: 'user' | 'bot';
  text: string;
}

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    { sender: 'bot', text: 'こんにちは！ご用件は？' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;
    const userMessage: Message = { sender: 'user', text: input };
    setMessages((msgs) => [...msgs, userMessage]);
    setInput('');
    setLoading(true);
    try {
      const data = await sendMessage(input);
      setMessages((msgs) => [...msgs, { sender: 'bot', text: data.reply || '...' }]);
    } catch (e) {
      setMessages((msgs) => [...msgs, { sender: 'bot', text: 'エラーが発生しました。' }]);
    }
    setLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSend();
  };

  return (
    <div style={{ maxWidth: 480, margin: '40px auto', border: '1px solid #ddd', borderRadius: 8, boxShadow: '0 2px 8px #eee', background: '#fff', display: 'flex', flexDirection: 'column', height: '80vh' }}>
      <div style={{ padding: 16, borderBottom: '1px solid #eee', fontWeight: 'bold', fontSize: 20 }}>AIチャットボット</div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 16, background: '#fafbfc' }}>
        {messages.map((msg, idx) => (
          <ChatMessage key={idx} sender={msg.sender} text={msg.text} />
        ))}
        <div ref={chatEndRef} />
      </div>
      <div style={{ display: 'flex', borderTop: '1px solid #eee', padding: 12 }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="メッセージを入力..."
          style={{ flex: 1, padding: 8, borderRadius: 6, border: '1px solid #ccc', marginRight: 8 }}
          disabled={loading}
        />
        <button onClick={handleSend} disabled={loading || !input.trim()} style={{ padding: '8px 20px', borderRadius: 6, background: '#007bff', color: '#fff', border: 'none', fontWeight: 'bold' }}>
          送信
        </button>
      </div>
    </div>
  );
};

export default App;

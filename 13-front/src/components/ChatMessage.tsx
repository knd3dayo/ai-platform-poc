import React from 'react';

type ChatMessageProps = {
  sender: 'user' | 'bot';
  text: string;
};

const ChatMessage: React.FC<ChatMessageProps> = ({ sender, text }) => {
  return (
    <div style={{
      textAlign: sender === 'user' ? 'right' : 'left',
      margin: '8px 0',
    }}>
      <span
        style={{
          display: 'inline-block',
          background: sender === 'user' ? '#DCF8C6' : '#F1F0F0',
          color: '#222',
          borderRadius: 12,
          padding: '8px 16px',
          maxWidth: '70%',
        }}
      >
        <b>{sender === 'user' ? 'あなた' : 'Bot'}:</b> {text}
      </span>
    </div>
  );
};

export default ChatMessage;

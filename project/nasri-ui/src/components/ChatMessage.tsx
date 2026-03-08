import { Message } from "../api/nasri";

interface Props {
  message: Message;
  isStreaming?: boolean;
}

export function ChatMessage({ message, isStreaming = false }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`chat-message ${isUser ? "chat-message--user" : "chat-message--assistant"}`}>
      <div className="chat-bubble">
        <span className="chat-bubble__role">
          {isUser ? "Sen" : "Nasri"}
        </span>
        <p className="chat-bubble__content">
          {message.content}
          {isStreaming && <span className="chat-cursor" aria-hidden />}
        </p>
      </div>
    </div>
  );
}

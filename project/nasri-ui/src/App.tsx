import { useEffect, useRef } from "react";
import { ChatInput } from "./components/ChatInput";
import { ChatMessage } from "./components/ChatMessage";
import { useChat } from "./hooks/useChat";

export default function App() {
  const { messages, status, error, sessionId, sendMessage, resetSession } =
    useChat();

  const bottomRef = useRef<HTMLDivElement>(null);

  // Yeni mesaj gelince en alta kaydır
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const isStreaming = status === "streaming";
  const isLoading = status === "loading";
  const isDisabled = isLoading || isStreaming;

  return (
    <div className="chat-layout">
      {/* Başlık */}
      <header className="chat-header">
        <div className="chat-header__left">
          <span className="chat-header__logo">Nasri</span>
          {sessionId && (
            <span className="chat-header__session" title={sessionId}>
              #{sessionId.slice(0, 8)}
            </span>
          )}
        </div>
        <button
          className="chat-header__reset"
          onClick={() => void resetSession()}
          disabled={isLoading}
          title="Yeni oturum başlat"
        >
          Yeni Sohbet
        </button>
      </header>

      {/* Mesaj listesi */}
      <main className="chat-messages">
        {isLoading && messages.length === 0 && (
          <div className="chat-status">Bağlanıyor…</div>
        )}

        {!isLoading && messages.length === 0 && (
          <div className="chat-empty">
            <p className="chat-empty__title">Merhaba, ben Nasri.</p>
            <p className="chat-empty__hint">Sana nasıl yardımcı olabilirim?</p>
          </div>
        )}

        {messages.map((msg, i) => {
          const isLastAssistant =
            i === messages.length - 1 && msg.role === "assistant";
          return (
            <ChatMessage
              key={i}
              message={msg}
              isStreaming={isLastAssistant && isStreaming}
            />
          );
        })}

        {error && (
          <div className="chat-error" role="alert">
            Hata: {error}
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* Giriş alanı */}
      <footer className="chat-footer">
        <ChatInput
          onSend={(text) => void sendMessage(text)}
          disabled={isDisabled}
        />
      </footer>
    </div>
  );
}

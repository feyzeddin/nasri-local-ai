/**
 * useChat — nasri-core ile konuşma state'ini yönetir.
 *
 * - Bileşen mount olunca oturum başlatır, geçmişi yükler.
 * - sendMessage(): SSE stream ile asistan yanıtını token token ekler.
 * - resetSession(): mevcut oturumu siler, yenisini başlatır.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteSession,
  getHistory,
  Message,
  startSession,
  streamChat,
} from "../api/nasri";

export type ChatStatus = "idle" | "loading" | "streaming" | "error";

export interface UseChatReturn {
  messages: Message[];
  status: ChatStatus;
  error: string | null;
  sessionId: string | null;
  sendMessage: (text: string) => Promise<void>;
  resetSession: () => Promise<void>;
}

export function useChat(systemPrompt?: string): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<ChatStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Aktif streaming'i iptal edebilmek için ref
  const abortRef = useRef(false);

  // ---------------------------------------------------------------------------
  // Oturum başlat
  // ---------------------------------------------------------------------------

  const initSession = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const session = await startSession(systemPrompt);
      setSessionId(session.session_id);
      const history = await getHistory(session.session_id);
      setMessages(history.filter((m) => m.role !== "system"));
      setStatus("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }, [systemPrompt]);

  useEffect(() => {
    void initSession();
    return () => {
      abortRef.current = true;
    };
  }, [initSession]);

  // ---------------------------------------------------------------------------
  // Mesaj gönder (SSE)
  // ---------------------------------------------------------------------------

  const sendMessage = useCallback(
    async (text: string) => {
      if (!sessionId || status === "streaming") return;

      const userMsg: Message = { role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);
      setStatus("streaming");
      setError(null);
      abortRef.current = false;

      // Asistan mesajını hemen boş olarak ekle (streaming dolduracak)
      const assistantMsg: Message = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, assistantMsg]);
      const assistantIndex = messages.length + 1; // user + assistant

      try {
        for await (const chunk of streamChat(sessionId, text)) {
          if (abortRef.current) break;
          setMessages((prev) => {
            const updated = [...prev];
            const idx = updated.length - 1; // her zaman son mesaj
            updated[idx] = {
              ...updated[idx],
              content: updated[idx].content + chunk,
            };
            return updated;
          });
        }
        setStatus("idle");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
        // Boş asistan mesajını kaldır
        setMessages((prev) => {
          const updated = [...prev];
          if (updated[updated.length - 1]?.content === "") {
            updated.pop();
          }
          return updated;
        });
      }

      void assistantIndex; // lint: kullanılmıyor uyarısını bastır
    },
    [sessionId, status, messages.length],
  );

  // ---------------------------------------------------------------------------
  // Oturumu sıfırla
  // ---------------------------------------------------------------------------

  const resetSession = useCallback(async () => {
    abortRef.current = true;
    if (sessionId) {
      try {
        await deleteSession(sessionId);
      } catch {
        // Sessizce geç
      }
    }
    setMessages([]);
    setSessionId(null);
    await initSession();
  }, [sessionId, initSession]);

  return { messages, status, error, sessionId, sendMessage, resetSession };
}

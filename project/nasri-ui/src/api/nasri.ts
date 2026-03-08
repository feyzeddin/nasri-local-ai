/**
 * nasri-core API istemcisi.
 *
 * Endpoints:
 *   POST   /chat/session            — oturum başlat
 *   POST   /chat/stream             — SSE ile yanıt al
 *   GET    /chat/{id}/history       — geçmiş oku
 *   DELETE /chat/{id}               — oturumu sil
 */

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

// ---------------------------------------------------------------------------
// Tipler
// ---------------------------------------------------------------------------

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface SessionInfo {
  session_id: string;
  system_prompt: string | null;
}

// ---------------------------------------------------------------------------
// Oturum
// ---------------------------------------------------------------------------

export async function startSession(
  system_prompt?: string,
): Promise<SessionInfo> {
  const resp = await fetch(`${API_BASE}/chat/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ system_prompt: system_prompt ?? null }),
  });
  if (!resp.ok) {
    throw new Error(`Oturum başlatılamadı: ${resp.status}`);
  }
  return resp.json() as Promise<SessionInfo>;
}

export async function deleteSession(session_id: string): Promise<void> {
  await fetch(`${API_BASE}/chat/${session_id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Geçmiş
// ---------------------------------------------------------------------------

export async function getHistory(session_id: string): Promise<Message[]> {
  const resp = await fetch(`${API_BASE}/chat/${session_id}/history`);
  if (!resp.ok) {
    throw new Error(`Geçmiş alınamadı: ${resp.status}`);
  }
  const data = (await resp.json()) as { messages: Message[] };
  return data.messages;
}

// ---------------------------------------------------------------------------
// SSE Streaming — POST /chat/stream
// ---------------------------------------------------------------------------

/**
 * Mesaj gönderir ve yanıt tokenlarını async generator olarak verir.
 * SSE formatı: `data: <token>\n\n`, sonunda `data: [DONE]\n\n`
 */
export async function* streamChat(
  session_id: string,
  message: string,
): AsyncGenerator<string, void, unknown> {
  const resp = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, message }),
  });

  if (!resp.ok || !resp.body) {
    throw new Error(`Stream isteği başarısız: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6);
        if (data === "[DONE]") return;
        if (data.startsWith("[ERROR]")) {
          throw new Error(data.slice(8));
        }
        if (data) yield data;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

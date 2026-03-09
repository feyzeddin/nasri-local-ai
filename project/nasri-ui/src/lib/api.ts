export type HealthReady = {
  status: string;
  checks?: Record<string, { ok: boolean; detail: string }>;
};

export type NetworkDevice = {
  ip: string;
  hostname?: string | null;
  source: string;
  ownership_score: number;
  ownership_label: string;
};

export type MaintenanceStatus = {
  enabled: boolean;
  interval_hours: number;
  last_run_at: number | null;
  last_result: string | null;
  due: boolean;
};

export type ChatPayload = {
  reply: string;
  session_id: string;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const SESSION_TOKEN = import.meta.env.VITE_SESSION_TOKEN || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (SESSION_TOKEN) headers.set("X-Session-Token", SESSION_TOKEN);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return (await response.json()) as T;
}

export function fetchHealthReady(): Promise<HealthReady> {
  return request<HealthReady>("/health/ready");
}

export async function fetchDevices(): Promise<NetworkDevice[]> {
  const data = await request<{ devices: NetworkDevice[] }>("/network/discover", {
    method: "POST",
    body: JSON.stringify({ include_mdns: true }),
  });
  return data.devices || [];
}

export async function fetchLogs(limit = 20): Promise<string[]> {
  const data = await request<{ items: { path: string }[] }>(`/files/list?path=.&limit=${limit}`);
  return (data.items || []).map((x) => x.path);
}

export function fetchMaintenanceStatus(): Promise<MaintenanceStatus> {
  return request<MaintenanceStatus>("/maintenance/status");
}

export function sendChat(message: string, sessionId?: string): Promise<ChatPayload> {
  return request<ChatPayload>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

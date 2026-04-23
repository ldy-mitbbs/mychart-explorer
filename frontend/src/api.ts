// Minimal typed fetch helper talking to the FastAPI backend.

const BASE = '';  // Vite dev proxies /api/* to 127.0.0.1:8765

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail || ''; } catch { /* ignore */ }
    throw new Error(`${res.status} ${res.statusText}${detail ? ': ' + detail : ''}`);
  }
  return res.json();
}

export interface Patient {
  name?: string;
  birthDate?: string;
  gender?: string;
  mrn?: string;
  address?: string;
  phones?: string[];
  emails?: string[];
  patTable?: Record<string, any>;
  patTable2?: Record<string, any>;
}

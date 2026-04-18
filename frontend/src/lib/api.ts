const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} at ${path}`);
  return (await r.json()) as T;
}

export const sseUrl = (path: string) => `${BASE}${path}`;

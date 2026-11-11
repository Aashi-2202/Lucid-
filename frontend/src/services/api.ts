const API_BASE = import.meta.env.VITE_API_URL ?? "";

/**
 * Typed fetch wrapper for backend API calls.
 * In dev, Vite proxy forwards /api/* to localhost:8000.
 * In production, VITE_API_URL points to the Render backend.
 */
export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }

  return res.json() as Promise<T>;
}

export function healthCheck() {
  return apiFetch<{ status: string; version: string }>("/api/health");
}

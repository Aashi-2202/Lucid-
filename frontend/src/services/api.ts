import { getToken } from "./auth";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

/**
 * Typed fetch wrapper for backend API calls.
 * In dev, Vite proxy forwards /api/* to localhost:8000.
 * In production, VITE_API_URL points to the Render backend.
 *
 * Automatically attaches the session JWT if available.
 */
export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
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

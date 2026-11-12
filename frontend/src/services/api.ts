import { getToken } from "./auth";

export const API_BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

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

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: options?.signal ?? AbortSignal.timeout(30000),
      headers,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error("The service took too long to respond. It may be starting; please try again.");
    }
    if (error instanceof TypeError) throw new Error("Could not reach the service. Check your connection and try again.");
    throw error;
  }

  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status}). Please try again.`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function healthCheck() {
  return apiFetch<{ status: string; version: string }>("/health");
}

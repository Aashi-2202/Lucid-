import { apiFetch } from "./api";

const TOKEN_KEY = "lucid_token";
const RECRUITER_KEY = "lucid_recruiter";

export interface RecruiterInfo {
  id: number;
  email: string | null;
  username?: string | null;
  name: string;
  picture: string | null;
}

export interface AuthResponse {
  token: string;
  recruiter: RecruiterInfo;
}

export interface VerificationChallenge { challenge_id: string; expires_in: number; resend_after: number }

function storeSession(data: AuthResponse): AuthResponse {
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(RECRUITER_KEY, JSON.stringify(data.recruiter));
  return data;
}

export async function signInWithPassword(username: string, password: string): Promise<AuthResponse> {
  return storeSession(await apiFetch<AuthResponse>("/auth/password", {
    method: "POST", body: JSON.stringify({ username, password }),
  }));
}

export function requestRegistration(username:string,password:string,email:string):Promise<VerificationChallenge> {
  return apiFetch("/auth/register",{method:"POST",body:JSON.stringify({username,password,email})});
}

export function resendVerification(challenge_id:string):Promise<VerificationChallenge> {
  return apiFetch("/auth/register/resend",{method:"POST",body:JSON.stringify({challenge_id})});
}

export async function verifyRegistration(challenge_id:string,code:string):Promise<AuthResponse> {
  return storeSession(await apiFetch<AuthResponse>("/auth/register/verify",{method:"POST",body:JSON.stringify({challenge_id,code})}));
}

/**
 * Send Google credential to the backend and store the session.
 */
export async function signInWithGoogle(
  credential: string
): Promise<AuthResponse> {
  const data = await apiFetch<AuthResponse>("/auth/google", {
    method: "POST",
    body: JSON.stringify({ credential }),
  });

  return storeSession(data);
}

/**
 * Get the stored session token, or null if not signed in.
 */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Get the stored recruiter profile, or null if not signed in.
 */
export function getRecruiter(): RecruiterInfo | null {
  const raw = localStorage.getItem(RECRUITER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as RecruiterInfo;
  } catch {
    return null;
  }
}

/**
 * Clear the session — sign out.
 */
export function signOut(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(RECRUITER_KEY);
}

/**
 * Check if the user is currently signed in.
 */
export function isSignedIn(): boolean {
  return getToken() !== null;
}

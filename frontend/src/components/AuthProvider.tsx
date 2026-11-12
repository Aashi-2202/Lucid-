import {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";
import type { ReactNode } from "react";
import {
  getRecruiter,
  getToken,
  isSignedIn as checkSignedIn,
  signInWithGoogle,
  signInWithPassword,
  signOut as clearSession,
} from "../services/auth";
import type { RecruiterInfo } from "../services/auth";

interface AuthContextType {
  recruiter: RecruiterInfo | null;
  token: string | null;
  signedIn: boolean;
  loading: boolean;
  error: string | null;
  handleGoogleCredential: (credential: string) => Promise<void>;
  handlePassword: (username: string, password: string, register: boolean) => Promise<void>;
  clearError: () => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [recruiter, setRecruiter] = useState<RecruiterInfo | null>(
    getRecruiter()
  );
  const [token, setToken] = useState<string | null>(getToken());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signedIn = checkSignedIn() && recruiter !== null;

  const handleGoogleCredential = useCallback(async (credential: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await signInWithGoogle(credential);
      setRecruiter(data.recruiter);
      setToken(data.token);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Sign-in failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    setRecruiter(null);
    setToken(null);
    setError(null);
  }, []);

  const handlePassword = useCallback(async (username: string, password: string, register: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const data = await signInWithPassword(username, password, register);
      setRecruiter(data.recruiter);
      setToken(data.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);
  const clearError = useCallback(() => setError(null), []);

  return (
    <AuthContext.Provider
      value={{
        recruiter,
        token,
        signedIn,
        loading,
        error,
        handleGoogleCredential,
        handlePassword,
        clearError,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

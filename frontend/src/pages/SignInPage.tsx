import { useEffect, useRef, useState } from "react";
import { useAuth } from "../components/AuthProvider";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
            auto_select?: boolean;
          }) => void;
          renderButton: (
            element: HTMLElement,
            config: { theme?: string; size?: string; text?: string; width?: number }
          ) => void;
        };
      };
    };
  }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";
let sdkPromise: Promise<void> | undefined;

// Share one SDK request across React StrictMode's setup/cleanup cycle.
function loadGoogleSdk(): Promise<void> {
  if (window.google?.accounts.id) return Promise.resolve();
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    const fail = () => {
      clearTimeout(timeout);
      script.remove();
      sdkPromise = undefined;
      reject(new Error("Google sign-in could not load. Check your connection and try again."));
    };
    const timeout = window.setTimeout(fail, 15000);
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      if (!window.google?.accounts.id) return fail();
      clearTimeout(timeout);
      resolve();
    };
    script.onerror = fail;
    document.head.appendChild(script);
  });
  return sdkPromise;
}

export default function SignInPage() {
  const { loading, error, handleGoogleCredential } = useAuth();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [sdkLoading, setSdkLoading] = useState(true);
  const [sdkError, setSdkError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setSdkLoading(true);
    setSdkError(null);
    if (!GOOGLE_CLIENT_ID || GOOGLE_CLIENT_ID.startsWith("your-client-id")) {
      setSdkError("Sign-in is not available yet. Contact the administrator.");
      setSdkLoading(false);
      return;
    }
    loadGoogleSdk().then(() => {
      if (cancelled || !buttonRef.current || !window.google) return;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response) => {
          if (!cancelled) void handleGoogleCredential(response.credential);
        },
        auto_select: false,
      });
      buttonRef.current.replaceChildren();
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline", size: "large", text: "signin_with", width: 300,
      });
      setSdkLoading(false);
    }).catch((err: unknown) => {
      if (cancelled) return;
      setSdkError(err instanceof Error ? err.message : "Google sign-in could not load. Please try again.");
      setSdkLoading(false);
    });
    return () => { cancelled = true; };
  }, [handleGoogleCredential, attempt]);

  return (
    <main style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", minHeight: "100vh", padding: "1rem",
      boxSizing: "border-box", fontFamily: "system-ui, sans-serif",
    }}>
      <h1 style={{ marginBottom: "0.5rem" }}>Lucid</h1>
      <p style={{ color: "#666", marginBottom: "2rem", textAlign: "center" }}>
        AI-powered resume screening
      </p>
      {(loading || sdkLoading) && <p role="status">{loading ? "Signing in…" : "Loading Google sign-in…"}</p>}
      {(error || sdkError) && (
        <p role="alert" style={{ color: "#b00020", marginBottom: "1rem", maxWidth: 400, textAlign: "center" }}>
          {sdkError || error}
        </p>
      )}
      <div ref={buttonRef} style={{ display: loading ? "none" : "block", minHeight: 44 }} />
      {sdkError && GOOGLE_CLIENT_ID && !GOOGLE_CLIENT_ID.startsWith("your-client-id") && (
        <button onClick={() => setAttempt(value => value + 1)} style={{ minHeight: 44, padding: "0.5rem 1rem" }}>
          Try again
        </button>
      )}
    </main>
  );
}

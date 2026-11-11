import { useEffect, useRef } from "react";
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
            config: {
              theme?: string;
              size?: string;
              text?: string;
              width?: number;
            }
          ) => void;
        };
      };
    };
  }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";

export default function SignInPage() {
  const { signedIn, loading, error, handleGoogleCredential, recruiter, signOut } =
    useAuth();
  const buttonRef = useRef<HTMLDivElement>(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (signedIn || initialized.current) return;

    const initGsi = () => {
      if (!window.google || !buttonRef.current) return;

      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response) => {
          handleGoogleCredential(response.credential);
        },
      });

      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
        text: "signin_with",
        width: 300,
      });

      initialized.current = true;
    };

    // If the GSI script is already loaded
    if (window.google) {
      initGsi();
      return;
    }

    // Otherwise load it
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = initGsi;
    document.head.appendChild(script);

    return () => {
      // Cleanup only if we added the script
      if (document.head.contains(script)) {
        document.head.removeChild(script);
      }
    };
  }, [signedIn, handleGoogleCredential]);

  if (signedIn && recruiter) {
    return (
      <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
        <h1>Welcome, {recruiter.name}</h1>
        <p>{recruiter.email}</p>
        {recruiter.picture && (
          <img
            src={recruiter.picture}
            alt="Profile"
            style={{ width: 64, height: 64, borderRadius: "50%" }}
          />
        )}
        <br />
        <button onClick={signOut} style={{ marginTop: "1rem" }}>
          Sign out
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ marginBottom: "0.5rem" }}>Lucid</h1>
      <p style={{ color: "#666", marginBottom: "2rem" }}>
        AI-powered resume screening
      </p>

      {loading && <p>Signing in…</p>}
      {error && (
        <p style={{ color: "#c00", marginBottom: "1rem", maxWidth: 400, textAlign: "center" }}>
          {error}
        </p>
      )}

      <div ref={buttonRef} />

      {!GOOGLE_CLIENT_ID && (
        <p style={{ color: "#c00", marginTop: "1rem", fontSize: "0.875rem" }}>
          Missing VITE_GOOGLE_CLIENT_ID — set it in frontend/.env
        </p>
      )}
    </div>
  );
}

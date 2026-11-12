import { useEffect, useRef, useState } from "react";
import { useAuth } from "../components/AuthProvider";
import "./SignInPage.css";

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
  const { loading, error, handleGoogleCredential, handlePassword, clearError } = useAuth();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [sdkLoading, setSdkLoading] = useState(true);
  const [sdkError, setSdkError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [confirmationError, setConfirmationError] = useState(false);
  const confirmationRef = useRef<HTMLInputElement>(null);
  const submitting = useRef(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading || submitting.current) return;
    setConfirmationError(false);
    if (register && password !== confirmation) {
      setConfirmationError(true);
      confirmationRef.current?.focus();
      return;
    }
    submitting.current = true;
    try { await handlePassword(username.trim(), password, register); }
    finally { submitting.current = false; }
  }

  function switchMode() {
    if (loading) return;
    setRegister(value => !value);
    setPassword("");
    setConfirmation("");
    setConfirmationError(false);
    setShowPassword(false);
    clearError();
  }

  useEffect(() => {
    let cancelled = false;
    setSdkLoading(true);
    setSdkError(null);
    if (!GOOGLE_CLIENT_ID || GOOGLE_CLIENT_ID.startsWith("your-client-id")) {
      setSdkError("Google sign-in is not configured. You can use a username and password.");
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
    <main className="signin-page">
      <section className="signin-panel" aria-labelledby="signin-title">
        <h1>Lucid</h1>
        <p className="signin-subtitle">AI-powered resume screening</p>
        <h2 id="signin-title">{register ? "Create account" : "Sign in"}</h2>
        <form onSubmit={submit} aria-busy={loading}>
          <label htmlFor="signin-username">Username</label>
          <input id="signin-username" name="username" value={username} onChange={e => setUsername(e.target.value)}
            autoComplete="username" autoCapitalize="none" spellCheck={false} required minLength={3} maxLength={40}
            pattern="[a-zA-Z0-9][a-zA-Z0-9_.\-]*" aria-describedby={register ? "username-help" : undefined} readOnly={loading} />
          {register && <p className="signin-help" id="username-help">3–40 letters, numbers, dots, underscores or hyphens. Start with a letter or number.</p>}
          <label htmlFor="signin-password">Password</label>
          <input id="signin-password" name="password" type={showPassword ? "text" : "password"} value={password}
            onChange={e => setPassword(e.target.value)} autoComplete={register ? "new-password" : "current-password"}
            required minLength={register ? 12 : 1} maxLength={128} readOnly={loading}
            aria-describedby={register ? "password-help" : undefined} />
          {register && <p className="signin-help" id="password-help">Use 12–128 characters. A long passphrase works well.</p>}
          {register && <>
            <label htmlFor="signin-confirmation">Confirm password</label>
            <input ref={confirmationRef} id="signin-confirmation" name="password-confirmation" type={showPassword ? "text" : "password"}
              value={confirmation} onChange={e => { setConfirmation(e.target.value); setConfirmationError(false); }}
              autoComplete="new-password" required maxLength={128} readOnly={loading}
              aria-invalid={confirmationError || undefined} aria-describedby={confirmationError ? "confirmation-error" : undefined} />
            {confirmationError && <p id="confirmation-error" className="signin-error" role="alert">Passwords do not match.</p>}
          </>}
          <label className="signin-show-password"><input type="checkbox" checked={showPassword} onChange={e => setShowPassword(e.target.checked)} />Show password</label>
          {error && <p role="alert" className="signin-error">{error}</p>}
          <button className="signin-submit" type="submit" aria-disabled={loading}>{loading ? (register ? "Creating account…" : "Signing in…") : register ? "Create account" : "Sign in"}</button>
        </form>
        <p className="signin-switch">{register ? "Already have an account?" : "New to Lucid?"} <button type="button" onClick={switchMode} aria-disabled={loading}>{register ? "Sign in" : "Create account"}</button></p>
        <div className="signin-divider"><span>or continue with Google</span></div>
        <div className="signin-google" aria-busy={loading} inert={loading}>
          {sdkLoading && <p role="status" className="signin-help">Loading Google sign-in…</p>}
          {sdkError && <p role="status" className="signin-error">{sdkError}</p>}
          <div ref={buttonRef} style={{ minHeight: 44 }} />
          {sdkError && GOOGLE_CLIENT_ID && !GOOGLE_CLIENT_ID.startsWith("your-client-id") && (
            <button type="button" className="signin-retry" onClick={() => setAttempt(value => value + 1)}>Retry Google sign-in</button>
          )}
        </div>
      </section>
    </main>
  );
}

import { useEffect, useRef, useState } from "react";
import { useAuth } from "../components/AuthProvider";
import { requestRegistration, resendVerification } from "../services/auth";
import type { VerificationChallenge } from "../services/auth";
import { validNewPassword } from "../services/passwordPolicy";
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
  const { loading, error, handleGoogleCredential, handlePassword, handleVerification, clearError } = useAuth();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [sdkLoading, setSdkLoading] = useState(true);
  const [sdkError, setSdkError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [challenge, setChallenge] = useState<(VerificationChallenge & {email:string;sentAt:number}) | null>(null);
  const [code, setCode] = useState("");
  const [registrationBusy, setRegistrationBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [now, setNow] = useState(Date.now());
  const codeRef = useRef<HTMLInputElement>(null);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [confirmationError, setConfirmationError] = useState(false);
  const confirmationRef = useRef<HTMLInputElement>(null);
  const submitting = useRef(false);
  const busy = loading || registrationBusy;
  const resendWait = challenge ? Math.max(0, Math.ceil(challenge.resend_after - (now - challenge.sentAt)/1000)) : 0;

  useEffect(() => {
    if (!challenge) return;
    codeRef.current?.focus();
    const timer=window.setInterval(()=>setNow(Date.now()),1000);
    return ()=>window.clearInterval(timer);
  },[challenge]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || submitting.current) return;
    setFormError(""); setNotice(""); clearError();
    if (challenge) {
      submitting.current=true;
      try { await handleVerification(challenge.challenge_id,code.trim()); }
      finally { submitting.current=false; }
      return;
    }
    setConfirmationError(false);
    if (register && password !== confirmation) {
      setConfirmationError(true);
      confirmationRef.current?.focus();
      return;
    }
    if (register && !validNewPassword(password)) {
      setFormError("Use 8–128 characters and at least one special character, such as !, @, # or _.");
      return;
    }
    submitting.current = true;
    try {
      if (register) {
        setRegistrationBusy(true);
        const next=await requestRegistration(username.trim(),password,email.trim());
        const sentAt=Date.now();setNow(sentAt);setChallenge({...next,email:email.trim(),sentAt});
        setCode("");setPassword("");setConfirmation("");setShowPassword(false);
      } else await handlePassword(username.trim(), password);
    } catch(err) { setFormError(err instanceof Error?err.message:"Could not send your verification code. Please try again."); }
    finally { submitting.current = false; setRegistrationBusy(false); }
  }

  async function resend() {
    if (!challenge || busy || resendWait>0 || submitting.current) return;
    submitting.current=true;setRegistrationBusy(true);setFormError("");clearError();setNotice("");
    try {
      const next=await resendVerification(challenge.challenge_id);
      const sentAt=Date.now();setNow(sentAt);setChallenge({...next,email:challenge.email,sentAt});
      setCode("");setNotice("A new code was sent. Use the newest email.");
    } catch(err) { setFormError(err instanceof Error?err.message:"Could not resend the code. Please try again later."); }
    finally { submitting.current=false;setRegistrationBusy(false); }
  }

  function changeDetails() {
    if(busy)return;
    setChallenge(null);setCode("");setFormError("");setNotice("");clearError();
  }

  function switchMode() {
    if (busy) return;
    changeDetails();
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
        <h2 id="signin-title">{challenge ? "Verify your Gmail" : register ? "Create account" : "Sign in"}</h2>
        {challenge&&<p className="signin-help">Enter the six-digit code sent to <strong>{challenge.email}</strong>. The code expires in 10 minutes.</p>}
        <form onSubmit={submit} aria-busy={busy}>
          {challenge?<>
            <label htmlFor="signup-code">Verification code</label>
            <input ref={codeRef} id="signup-code" name="verification-code" value={code} onChange={e=>setCode(e.target.value)}
              autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" required minLength={6} maxLength={6} readOnly={busy} />
          </>:<>
          <label htmlFor="signin-username">Username</label>
          <input id="signin-username" name="username" value={username} onChange={e => setUsername(e.target.value)}
            autoComplete="username" autoCapitalize="none" spellCheck={false} required minLength={3} maxLength={40}
            pattern="[a-zA-Z0-9][a-zA-Z0-9_.\-]*" aria-describedby={register ? "username-help" : undefined} readOnly={busy} />
          {register && <p className="signin-help" id="username-help">3–40 letters, numbers, dots, underscores or hyphens. Start with a letter or number.</p>}
          {register&&<>
            <label htmlFor="signup-email">Gmail address</label>
            <input id="signup-email" name="email" type="email" autoComplete="email" autoCapitalize="none" spellCheck={false}
              value={email} onChange={e=>setEmail(e.target.value)} required maxLength={254} readOnly={busy} aria-describedby="email-help" />
            <p className="signin-help" id="email-help">We’ll email a code to link this Gmail address to your username.</p>
          </>}
          <label htmlFor="signin-password">Password</label>
          <input id="signin-password" name="password" type={showPassword ? "text" : "password"} value={password}
            onChange={e => setPassword(e.target.value)} autoComplete={register ? "new-password" : "current-password"}
            required minLength={register ? 8 : 1} maxLength={128} readOnly={busy}
            aria-describedby={register ? "password-help" : undefined} />
          {register && <p className="signin-help" id="password-help">Use 8–128 characters with at least one special character, such as !, @, # or _.</p>}
          {register && <>
            <label htmlFor="signin-confirmation">Confirm password</label>
            <input ref={confirmationRef} id="signin-confirmation" name="password-confirmation" type={showPassword ? "text" : "password"}
              value={confirmation} onChange={e => { setConfirmation(e.target.value); setConfirmationError(false); }}
              autoComplete="new-password" required maxLength={128} readOnly={busy}
              aria-invalid={confirmationError || undefined} aria-describedby={confirmationError ? "confirmation-error" : undefined} />
            {confirmationError && <p id="confirmation-error" className="signin-error" role="alert">Passwords do not match.</p>}
          </>}
          <label className="signin-show-password"><input type="checkbox" checked={showPassword} onChange={e => setShowPassword(e.target.checked)} />Show password</label>
          </>}
          {(formError||error)&&<p role="alert" className="signin-error">{formError||error}</p>}
          {notice&&<p role="status" className="signin-help">{notice}</p>}
          <button className="signin-submit" type="submit" disabled={busy} aria-busy={busy}>{busy ? (challenge ? "Verifying…" : register ? "Sending code…" : "Signing in…") : challenge ? "Verify and create account" : register ? "Send verification code" : "Sign in"}</button>
        </form>
        {challenge&&<div className="signin-verification-actions">
          <button type="button" className="signin-retry" onClick={resend} disabled={busy||resendWait>0}>{resendWait>0?`Resend code in ${resendWait}s`:"Resend code"}</button>
          <button type="button" className="signin-retry" onClick={changeDetails} disabled={busy}>Change signup details</button>
        </div>}
        <p className="signin-switch">{register ? "Already have an account?" : "New to Lucid?"} <button type="button" onClick={switchMode} disabled={busy}>{register ? "Sign in" : "Create account"}</button></p>
        <div className="signin-divider"><span>or continue with Google</span></div>
        <div className="signin-google" aria-busy={busy} inert={busy}>
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

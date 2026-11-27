"use client";

import { useEffect, useState, type FormEvent } from "react";
import { AlertCircle, ArrowLeft, Check, KeyRound, LoaderCircle, LockKeyhole, Mail, Moon, Sun } from "lucide-react";

import { ApiError } from "@/data/client";
import { acceptInvitation, login, requestPasswordReset, resetPassword, type Session } from "@/data/session";
import { Button } from "@/presentation/components";

export function SignIn({
  theme,
  onThemeChange,
  onComplete,
  mode = "login",
}: {
  theme: "light" | "dark";
  onThemeChange: () => void;
  onComplete: (session: Session) => void;
  mode?: "login" | "reset" | "invite";
}) {
  const [view, setView] = useState<"login" | "forgot" | "reset" | "invite">(mode);
  const [token, setToken] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [banner, setBanner] = useState("");
  const [resetSent, setResetSent] = useState(false);
  const [finished, setFinished] = useState("");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("token") || "");
  }, []);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    setBanner("");
    if (!email.includes("@") || password.length < 8) return;
    setLoading(true);
    try {
      onComplete(await login(email, password));
    } catch (error) {
      setBanner(error instanceof ApiError ? error.message : "Sign-in failed.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmReset(event: FormEvent) {
    event.preventDefault();
    setBanner("");
    if (token.length < 20 || password.length < 8) {
      setBanner("Enter the reset token and a password of at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      await resetPassword(token, password);
      setPassword("");
      setFinished("Password updated. Sign in with the new password.");
      setView("login");
    } catch (error) {
      setBanner(error instanceof ApiError ? error.message : "The password was not reset.");
    } finally {
      setLoading(false);
    }
  }

  async function accept(event: FormEvent) {
    event.preventDefault();
    setBanner("");
    if (token.length < 20 || fullName.trim().length < 2 || password.length < 8) {
      setBanner("Enter the invitation token, your name, and a password of at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      const accepted = await acceptInvitation(token, fullName.trim(), password);
      setPassword("");
      setFinished(`${accepted.organization_name} is ready. Sign in with the new account.`);
      setView("login");
    } catch (error) {
      setBanner(error instanceof ApiError ? error.message : "The invitation was not accepted.");
    } finally {
      setLoading(false);
    }
  }

  async function reset(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    setBanner("");
    if (!email.includes("@")) return;
    setLoading(true);
    try {
      await requestPasswordReset(email);
      setResetSent(true);
    } catch (error) {
      setBanner(error instanceof ApiError ? error.message : "The reset request failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <header className="auth-header">
        <div className="auth-brand"><span>A</span><strong>ATLAS</strong></div>
        <Button size="icon" variant="ghost" aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`} onClick={onThemeChange}>
          {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
        </Button>
      </header>
      <section className="auth-card" aria-live="polite">
        {view !== "login" && (
          <button className="auth-back" onClick={() => { setView("login"); setSubmitted(false); setBanner(""); setResetSent(false); }}>
            <ArrowLeft size={14} /> Back to sign in
          </button>
        )}
        {view === "login" && (
          <>
            <div className="auth-icon"><LockKeyhole size={20} /></div>
            <h1>Welcome back</h1>
            <p>Sign in to your ATLAS workspace.</p>
            {finished && <div className="auth-notice"><Check size={15} /><span><strong>Ready to sign in</strong><small>{finished}</small></span></div>}
            {banner && <div className="auth-error" role="alert"><AlertCircle size={15} />{banner}</div>}
            <form onSubmit={(event) => void signIn(event)}>
              <label className="field"><span>Email address</span><input autoFocus type="email" value={email} onChange={(event) => setEmail(event.target.value)} aria-invalid={submitted && !email.includes("@")} /></label>
              <label className="field"><span>Password</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" aria-invalid={submitted && password.length < 8} /></label>
              {submitted && (!email.includes("@") || password.length < 8) && <div className="auth-error" role="alert"><AlertCircle size={15} /> Enter a valid email and a password of at least 8 characters.</div>}
              <Button variant="primary" disabled={loading}>{loading ? <LoaderCircle className="spinning" size={15} /> : null} Sign in</Button>
            </form>
            <div className="auth-links"><button onClick={() => { setView("forgot"); setSubmitted(false); setBanner(""); }}>Forgot password?</button></div>
            <div className="auth-notice"><KeyRound size={15} /><span><strong>Organization account</strong><small>Sign in with the account for this workspace.</small></span></div>
          </>
        )}
        {(view === "reset" || view === "invite") && (
          <>
            <div className="auth-icon">{view === "invite" ? <Mail size={20} /> : <KeyRound size={20} />}</div>
            <h1>{view === "invite" ? "Accept invitation" : "Choose a new password"}</h1>
            <p>{view === "invite" ? "Create the account for this organization invitation." : "Use the token from the reset message."}</p>
            {banner && <div className="auth-error" role="alert"><AlertCircle size={15} />{banner}</div>}
            <form onSubmit={(event) => void (view === "invite" ? accept(event) : confirmReset(event))}>
              <label className="field"><span>Token</span><input value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" /></label>
              {view === "invite" && <label className="field"><span>Full name</span><input value={fullName} onChange={(event) => setFullName(event.target.value)} /></label>}
              <label className="field"><span>Password</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" /></label>
              <Button variant="primary" disabled={loading}>{loading ? <LoaderCircle className="spinning" size={15} /> : null} {view === "invite" ? "Accept invitation" : "Update password"}</Button>
            </form>
          </>
        )}
        {view === "forgot" && (
          <>
            <div className="auth-icon"><Mail size={20} /></div>
            <h1>Reset your password</h1>
            <p>Enter your account email to request a reset.</p>
            {banner && <div className="auth-error" role="alert"><AlertCircle size={15} />{banner}</div>}
            <form onSubmit={(event) => void reset(event)}>
              <label className="field"><span>Email address</span><input autoFocus type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
              {resetSent ? <div className="auth-notice"><Check size={15} /><span><strong>Request sent</strong><small>If the account exists, the reset message was queued.</small></span></div> : <Button variant="primary" disabled={loading || !email.includes("@")}>{loading ? <LoaderCircle className="spinning" size={15} /> : null} Continue</Button>}
            </form>
          </>
        )}
      </section>
      <footer className="auth-footer">ATLAS</footer>
    </main>
  );
}

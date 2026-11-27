import { useState } from "react";
import { AlertCircle, ArrowLeft, Building2, Check, ChevronRight, KeyRound, LoaderCircle, LockKeyhole, Mail, Moon, Sun, Users } from "lucide-react";
import { appConfig } from "./appConfig";
import { Badge, Button } from "./components";

export type AuthView = "login" | "forgot" | "reset" | "invitation" | "organizations" | "setup";

export function AuthWorkspace({
  initialView = "login",
  theme,
  onThemeChange,
  onComplete,
  banner,
}: {
  initialView?: AuthView;
  theme: "light" | "dark";
  onThemeChange: () => void;
  onComplete: (message: string) => void;
  banner?: string;
}) {
  const [view, setView] = useState<AuthView>(initialView);
  const [email, setEmail] = useState(appConfig.user.email);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [orgName, setOrgName] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [expired, setExpired] = useState(false);
  const run = (message: string) => {
    setLoading(true);
    window.setTimeout(() => {
      setLoading(false);
      onComplete(message);
    }, 500);
  };
  const changeView = (next: AuthView) => {
    setSubmitted(false);
    setPassword("");
    setConfirm("");
    setView(next);
  };
  return (
    <main className="auth-page">
      <header className="auth-header">
        <div className="auth-brand"><span>A</span><strong>ATLAS</strong></div>
        <Button size="icon" variant="ghost" aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`} onClick={onThemeChange}>{theme === "light" ? <Moon size={17} /> : <Sun size={17} />}</Button>
      </header>
      <section className="auth-card" aria-live="polite">
        {view !== "login" && <button className="auth-back" onClick={() => changeView("login")}><ArrowLeft size={14} /> Back to sign in</button>}
        {view === "login" && <>
          <div className="auth-icon"><LockKeyhole size={20} /></div><h1>Welcome back</h1><p>Sign in to your ATLAS workspace.</p>
          {banner && <div className="auth-error" role="alert"><AlertCircle size={15} />{banner}</div>}
          <form onSubmit={(event) => { event.preventDefault(); setSubmitted(true); if (email.includes("@") && password.length >= 8) run("Signed in to the local prototype"); }}>
            <label className="field"><span>Email address</span><input autoFocus type="email" value={email} onChange={(event) => setEmail(event.target.value)} aria-invalid={submitted && !email.includes("@")} /></label>
            <label className="field"><span>Password</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" aria-invalid={submitted && password.length < 8} /></label>
            {submitted && (!email.includes("@") || password.length < 8) && <div className="auth-error" role="alert"><AlertCircle size={15} /> Enter a valid email and a password of at least 8 characters.</div>}
            <Button variant="primary" disabled={loading}>{loading ? <LoaderCircle className="spinning" size={15} /> : null} Sign in</Button>
          </form>
          <div className="auth-links"><button onClick={() => changeView("forgot")}>Forgot password?</button><button onClick={() => changeView("invitation")}>Accept an invitation</button></div>
          <div className="auth-notice"><KeyRound size={15} /><span><strong>Local prototype</strong><small>No authentication service or server session is connected.</small></span></div>
        </>}
        {view === "forgot" && <>
          <div className="auth-icon"><Mail size={20} /></div><h1>Reset your password</h1><p>Enter your account email to prepare a reset request.</p>
          <form onSubmit={(event) => { event.preventDefault(); setSubmitted(true); }}>
            <label className="field"><span>Email address</span><input autoFocus type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            {submitted ? <div className="auth-notice"><Check size={15} /><span><strong>Request prepared</strong><small>Email delivery is unavailable without an authentication backend.</small></span></div> : <Button variant="primary" disabled={!email.includes("@")}>Continue</Button>}
          </form>
          {submitted && <Button onClick={() => changeView("reset")}>Open local reset form</Button>}
        </>}
        {view === "reset" && <>
          <div className="auth-icon"><KeyRound size={20} /></div><h1>Choose a new password</h1><p>This form validates locally and does not update a server account.</p>
          <form onSubmit={(event) => { event.preventDefault(); setSubmitted(true); if (password.length >= 8 && password === confirm) changeView("login"); }}>
            <label className="field"><span>New password</span><input autoFocus type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <label className="field"><span>Confirm password</span><input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label>
            {submitted && (password.length < 8 || password !== confirm) && <div className="auth-error" role="alert"><AlertCircle size={15} /> Passwords must match and contain at least 8 characters.</div>}
            <Button variant="primary">Validate password</Button>
          </form>
        </>}
        {view === "invitation" && <>
          <div className="auth-icon"><Users size={20} /></div><h1>{expired ? "Invitation expired" : `Join ${appConfig.organization.name}`}</h1>
          {expired ? <><div className="auth-error" role="alert"><AlertCircle size={15} /> This invitation is no longer valid. Ask an organization administrator for a new invitation.</div><Button disabled>Accept invitation</Button><button className="text-button centered" onClick={() => setExpired(false)}>Return to active invitation</button></> : <>
            <p>Olivia Martin has been invited as a Staff member.</p>
            <div className="invitation-summary"><span className="org-logo">{appConfig.organization.initials}</span><span><strong>{appConfig.organization.name}</strong><small>Staff access · {appConfig.user.email}</small></span><Badge tone="amber">Pending</Badge></div>
            <Button variant="primary" onClick={() => changeView("organizations")}>Accept and continue</Button>
            <button className="text-button centered" onClick={() => setExpired(true)}>View expired invitation state</button>
          </>}
        </>}
        {view === "organizations" && <>
          <div className="auth-icon"><Building2 size={20} /></div><h1>Choose an organization</h1><p>Select a workspace or create a new organization.</p>
          <button className="organization-option" onClick={() => onComplete(`Opened ${appConfig.organization.name}`)}><span className="org-logo">{appConfig.organization.initials}</span><span><strong>{appConfig.organization.name}</strong><small>Admin · Current organization</small></span><ChevronRight size={16} /></button>
          <button className="organization-option" onClick={() => changeView("setup")}><span className="org-logo muted-logo">+</span><span><strong>Create organization</strong><small>Start with a new local workspace</small></span><ChevronRight size={16} /></button>
        </>}
        {view === "setup" && <>
          <div className="auth-icon"><Building2 size={20} /></div><h1>Set up your organization</h1><p>Create local workspace details. Provisioning is not connected.</p>
          <form onSubmit={(event) => { event.preventDefault(); setSubmitted(true); if (orgName.trim().length >= 3) run(`${orgName.trim()} was created locally`); }}>
            <label className="field"><span>Organization name</span><input autoFocus value={orgName} onChange={(event) => setOrgName(event.target.value)} placeholder="Organization name" /></label>
            <label className="field"><span>Default time zone</span><select defaultValue="America/New_York"><option value="America/New_York">Eastern Time</option><option value="America/Los_Angeles">Pacific Time</option><option value="Europe/London">London</option></select></label>
            {submitted && orgName.trim().length < 3 && <div className="auth-error" role="alert"><AlertCircle size={15} /> Enter at least 3 characters.</div>}
            <Button variant="primary" disabled={loading}>{loading ? <LoaderCircle className="spinning" size={15} /> : null} Create organization</Button>
          </form>
        </>}
      </section>
      <footer className="auth-footer">ATLAS workspace prototype · Server authentication is unavailable</footer>
    </main>
  );
}

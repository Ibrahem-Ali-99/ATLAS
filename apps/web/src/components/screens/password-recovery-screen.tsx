"use client";

import { useMutation } from "@tanstack/react-query";
import { LockKeyhole } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { RequestError } from "@/components/request-error";
import { AuthFrame } from "@/components/screens/auth-frame";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { confirmPasswordReset, requestPasswordReset } from "@/lib/api";

const authLink = "mt-4 inline-block text-sm font-medium text-primary hover:underline";

export function ForgotPasswordScreen() {
  const [email, setEmail] = useState("");
  const request = useMutation({ mutationFn: requestPasswordReset });
  return (
    <AuthFrame title="Forgot password" description="Request a password reset link for your ATLAS account." icon={<LockKeyhole size={20} />}>
      <form className="mt-6 grid gap-4" onSubmit={(event) => {
        event.preventDefault();
        if (!request.isPending) request.mutate(email.trim());
      }}>
        <label className="grid gap-2 text-sm">Email
          <Input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <Button type="submit" disabled={request.isPending}>{request.isPending ? "Sending…" : "Send reset link"}</Button>
      </form>
      {request.isError ? <div className="mt-4"><RequestError error={request.error} /></div> : null}
      {request.isSuccess ? <p className="mt-4 text-sm text-muted-foreground" role="status">{request.data.detail}</p> : null}
      <Link href="/login" className={authLink}>Back to sign in</Link>
    </AuthFrame>
  );
}

export function ResetPasswordScreen() {
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");
  const reset = useMutation({
    mutationFn: ({ token, next }: { token: string; next: string }) => confirmPasswordReset(token, next),
    onSuccess: () => {
      setPassword("");
      setRepeat("");
      window.history.replaceState(null, "", "/reset-password");
    },
  });
  return (
    <AuthFrame title="Reset password" description="Choose a new password for your ATLAS account." icon={<LockKeyhole size={20} />}>
      {reset.isSuccess ? <p className="mt-4 text-sm text-success" role="status">Password updated. Sign in with your new password.</p> : (
        <form className="mt-6 grid gap-4" onSubmit={(event) => {
          event.preventDefault();
          if (reset.isPending) return;
          reset.reset();
          const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
          if (!token) { setError("Open the password reset link from your email."); return; }
          if (password !== repeat) { setError("The passwords do not match."); return; }
          setError("");
          reset.mutate({ token, next: password });
        }}>
          <label className="grid gap-2 text-sm">New password
            <Input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <label className="grid gap-2 text-sm">Confirm new password
            <Input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={repeat} onChange={(event) => setRepeat(event.target.value)} />
          </label>
          {error ? <p className="text-sm text-destructive" role="alert">{error}</p> : null}
          {reset.isError ? <RequestError error={reset.error} /> : null}
          <Button type="submit" disabled={reset.isPending}>{reset.isPending ? "Updating…" : "Update password"}</Button>
          <Link href="/forgot-password" className="text-sm font-medium text-primary hover:underline">Request another link</Link>
        </form>
      )}
      <Link href="/login" className={authLink}>Back to sign in</Link>
    </AuthFrame>
  );
}

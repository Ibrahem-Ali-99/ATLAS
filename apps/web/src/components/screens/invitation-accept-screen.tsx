"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { acceptInvitation } from "@/lib/invitations";
import { login } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function InvitationAcceptScreen() {
  const token = useSearchParams().get("token") ?? "";
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) { setMessage("This invitation link is missing its token."); return; }
    setPending(true);
    setMessage(null);
    try {
      const accepted = await acceptInvitation(token, name, password);
      await login({ email: accepted.user.email, password });
      window.location.assign("/overview");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "This invitation could not be accepted.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <section className="w-full max-w-md rounded-xl bg-muted p-6">
        <h1 className="text-2xl text-foreground">Join your ATLAS workspace</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Accept the invitation to create or connect your staff account.</p>
        <form className="mt-6 space-y-4" onSubmit={submit}>
          <label className="grid gap-2 text-sm"><span>Full name</span><Input value={name} onChange={(event) => setName(event.target.value)} required autoComplete="name" /></label>
          <label className="grid gap-2 text-sm"><span>Password</span><Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete="new-password" /></label>
          <Button type="submit" disabled={pending || !token}>{pending ? "Accepting…" : "Accept invitation"}</Button>
          {message ? <p role="alert" className="text-sm text-destructive">{message}</p> : null}
        </form>
      </section>
    </main>
  );
}

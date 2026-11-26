"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useState, useSyncExternalStore } from "react";
import { Users } from "lucide-react";
import Link from "next/link";

import { AuthFrame } from "@/components/screens/auth-frame";
import { acceptInvitation } from "@/lib/invitations";
import { login, sessionQueryKey } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function watchHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function hashToken() {
  return new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
}

export function InvitationAcceptScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const fragmentToken = useSyncExternalStore(watchHash, hashToken, () => "");
  const queryToken = useSearchParams().get("token");
  const token = fragmentToken || queryToken || "";
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
      const session = await login({ email: accepted.user.email, password });
      queryClient.clear();
      queryClient.setQueryData(sessionQueryKey, session);
      router.replace("/overview");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "This invitation could not be accepted.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthFrame title="Join your ATLAS workspace" description="Accept the invitation to create or connect your account." icon={<Users size={20} />}>
        <Link href="/login" className="mt-4 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline">Back to sign in</Link>
        {!token ? <p role="alert" className="mt-4 text-sm text-destructive">This invitation link is missing its token. Open the link from your invitation email.</p> : null}
        <form className="mt-6 space-y-4" onSubmit={submit}>
          <label className="grid gap-2 text-sm"><span>Full name</span><Input value={name} onChange={(event) => setName(event.target.value)} required autoComplete="name" /></label>
          <label className="grid gap-2 text-sm"><span>Password</span><Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete="new-password" /></label>
          <Button type="submit" disabled={pending || !token}>{pending ? "Accepting…" : "Accept invitation"}</Button>
          {message ? <p role="alert" className="text-sm text-destructive">{message}</p> : null}
        </form>
    </AuthFrame>
  );
}

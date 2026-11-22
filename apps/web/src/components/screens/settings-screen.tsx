"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ProviderNotice } from "@/components/provider-notice";
import { MembershipTable } from "@/components/membership-table";
import { RequestError } from "@/components/request-error";
import { SignOutDialog } from "@/components/sign-out-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { sessionQueryOptions } from "@/lib/api";
import { getAutomations } from "@/lib/automations";
import { useWorkspace } from "@/lib/use-workspace";

export function SettingsScreen() {
  const session = useQuery(sessionQueryOptions);
  const { organizationId } = useWorkspace();
  const automations = useQuery({
    queryKey: ["automations", organizationId],
    queryFn: () => getAutomations(organizationId ?? ""),
    enabled: Boolean(organizationId),
  });
  const [signOutOpen, setSignOutOpen] = useState(false);
  const user = session.data?.user;

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <div>
        <h1 className="text-[31px] leading-none text-foreground">Settings</h1>
        <p className="mt-3 max-w-3xl text-sm text-muted-foreground">
          Account, organization, models, and delivery status. Nothing on this page can be saved, and secrets are not shown.
        </p>
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-2">
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Account</h2>
        <p className="mt-1 text-sm text-muted-foreground">Read-only fields returned by the session.</p>
        <div className="mt-4">
          {session.isPending || !user ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <div className="grid gap-4">
              <label className="grid gap-2 text-sm">
                <span className="font-medium">Name</span>
                <input
                  readOnly
                  aria-readonly="true"
                  value={user.full_name}
                  className="h-10 cursor-default rounded-[10px] border-0 bg-secondary px-3 text-sm text-foreground"
                />
                <span className="text-xs text-muted-foreground">Read only</span>
              </label>
              <label className="grid gap-2 text-sm">
                <span className="font-medium">Email</span>
                <input
                  readOnly
                  aria-readonly="true"
                  value={user.email}
                  className="h-10 cursor-default rounded-[10px] border-0 bg-secondary px-3 text-sm text-foreground"
                />
                <span className="text-xs text-muted-foreground">Read only</span>
              </label>
            </div>
          )}
        </div>
      </section>
      {organizationId ? <ProviderNotice organizationId={organizationId} detail /> : null}
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Organization</h2>
        <p className="mt-1 text-sm text-muted-foreground">Roles are stored on the membership, not chosen in the browser.</p>
        <div className="mt-4">
          {session.isPending || !session.data ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <MembershipTable memberships={session.data.memberships} />
          )}
        </div>
      </section>
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Delivery</h2>
        <p className="mt-1 text-sm text-muted-foreground">Read only. Webhook keys and model keys are not shown.</p>
        {automations.isPending ? <Skeleton className="mt-4 h-16 w-full" /> : null}
        {automations.isError ? <div className="mt-4"><RequestError error={automations.error} /></div> : null}
        {automations.data ? (
          <dl className="mt-4 space-y-2 text-sm text-muted-foreground">
            <div>Email mode: {automations.data.email_mode}</div>
            <div>Calendar: {automations.data.calendar_provider}</div>
            <div>n8n: {automations.data.n8n_configured ? "configured" : "not configured"}</div>
            <div>Webhook key: {automations.data.webhook_configured ? "configured" : "not configured"}</div>
          </dl>
        ) : null}
      </section>
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Session</h2>
        <p className="mt-1 text-sm text-muted-foreground">Signing out revokes the server session for this browser.</p>
        <Button className="mt-4" variant="outline" onClick={() => setSignOutOpen(true)}>
          Sign out
        </Button>
      </section>
      <SignOutDialog open={signOutOpen} onOpenChange={setSignOutOpen} />
      </div>
    </div>
  );
}

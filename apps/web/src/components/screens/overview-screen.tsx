"use client";

import { useQuery } from "@tanstack/react-query";

import { MembershipTable } from "@/components/membership-table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getHealth, getReady, sessionQueryOptions } from "@/lib/api";
import { getAnalytics } from "@/lib/intelligence";
import { useWorkspace } from "@/lib/use-workspace";

function Probe({
  label,
  isPending,
  isError,
  message,
  okLabel,
}: {
  label: string;
  isPending: boolean;
  isError: boolean;
  message: string | null;
  okLabel: string;
}) {
  if (isPending) {
    return (
      <div className="flex items-center justify-between gap-4">
        <span className="text-sm">{label}</span>
        <Skeleton className="h-5 w-16" />
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex items-start justify-between gap-4">
        <span className="text-sm">{label}</span>
        <span className="text-right text-sm text-red-300">{message ?? "Check failed"}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm">{label}</span>
      <Badge>{okLabel}</Badge>
    </div>
  );
}

export function OverviewScreen() {
  const session = useQuery(sessionQueryOptions);
  const workspace = useWorkspace();
  const analytics = useQuery({
    queryKey: ["analytics", workspace.organizationId],
    queryFn: () => getAnalytics(workspace.organizationId ?? ""),
    enabled: Boolean(workspace.organizationId),
  });
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const ready = useQuery({ queryKey: ["ready"], queryFn: getReady, retry: false });
  const user = session.data?.user;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
          {user ? `Signed in as ${user.full_name}. ` : null}
          Account membership and API status below come from the live API. CRM, knowledge, and the assistant use the same session.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Account</CardTitle>
            <CardDescription>The signed-in user returned by the session endpoint.</CardDescription>
          </CardHeader>
          <CardContent>
            {session.isPending || !user ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-4 w-56" />
              </div>
            ) : (
              <dl className="grid gap-3 text-sm">
                <div>
                  <dt className="text-muted-foreground">Name</dt>
                  <dd className="mt-1">{user.full_name}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Email</dt>
                  <dd className="mt-1">{user.email}</dd>
                </div>
              </dl>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>API status</CardTitle>
            <CardDescription>Liveness and database readiness from the running API.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Probe
              label="Health"
              isPending={health.isPending}
              isError={health.isError}
              message={health.error instanceof Error ? health.error.message : null}
              okLabel={health.data?.status ?? "ok"}
            />
            <Probe
              label="Database"
              isPending={ready.isPending}
              isError={ready.isError}
              message={ready.error instanceof Error ? ready.error.message : null}
              okLabel={ready.data?.database ?? "ok"}
            />
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Memberships</CardTitle>
          <CardDescription>Organizations returned for this session. Other tenants are not listed.</CardDescription>
        </CardHeader>
        <CardContent>
          {session.isPending || !session.data ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <MembershipTable memberships={session.data.memberships} />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Operations</CardTitle>
          <CardDescription>
            Counts from stored records for this organization. {analytics.data?.synthetic_notice}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {analytics.isPending ? <Skeleton className="h-16 w-full" /> : null}
          {analytics.isError ? <p className="text-sm text-red-300">Analytics could not be loaded.</p> : null}
          {analytics.data ? (
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">Leads</dt>
                <dd className="mt-1 text-lg font-medium">{analytics.data.leads_total}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Inquiries</dt>
                <dd className="mt-1 text-lg font-medium">{analytics.data.inquiries_total}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Pending approvals</dt>
                <dd className="mt-1 text-lg font-medium">{analytics.data.approvals.pending}</dd>
              </div>
            </dl>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

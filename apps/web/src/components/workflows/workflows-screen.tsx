"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cancelBooking, getAutomations } from "@/lib/automations";
import { useWorkspace } from "@/lib/use-workspace";

export function WorkflowsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const queryClient = useQueryClient();
  const automations = useQuery({
    queryKey: ["automations", organizationId],
    queryFn: () => getAutomations(organizationId ?? ""),
    enabled: Boolean(organizationId),
  });
  const cancel = useMutation({
    mutationFn: (bookingId: string) => cancelBooking(organizationId ?? "", bookingId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["automations", organizationId] });
    },
  });
  if (!organizationId || automations.isPending) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (automations.isError) {
    return <RequestError error={automations.error} />;
  }
  const data = automations.data;
  const emailLabel = data.email_mode === "live" ? "Live email" : "Sandbox email";
  const calendarLabel =
    data.calendar_provider === "simulation" ? "Simulated calendar" : data.calendar_provider;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Workflows</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
          n8n starts these automations. ATLAS records the outcome. Outbound email and calendar
          bookings wait for an admin approval. Simulated bookings are stored in ATLAS.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Badge>{emailLabel}</Badge>
        <Badge variant="secondary">{calendarLabel}</Badge>
        <Badge variant="secondary">{data.n8n_configured ? "n8n webhook configured" : "n8n webhook not configured"}</Badge>
        <Badge variant="secondary">{data.webhook_configured ? "Webhook key installed" : "No webhook key"}</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {data.automations.map((automation) => (
          <article key={automation.name} className="rounded-xl border border-border bg-card p-4">
            <h2 className="font-medium">{automation.name}</h2>
            <p className="mt-1 text-sm text-muted-foreground">Trigger: {automation.trigger.replaceAll("_", " ")}</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{automation.description}</p>
          </article>
        ))}
      </div>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Recent executions</h2>
        {data.runs.length === 0 ? <p className="text-sm text-muted-foreground">No workflow runs yet.</p> : null}
        <div className="space-y-3">
          {data.runs.map((run) => (
            <article key={run.id} className="rounded-xl border border-border bg-card p-4 text-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-medium">{run.kind.replaceAll("_", " ")}</h3>
                  <p className="text-muted-foreground">{new Date(run.created_at).toLocaleString()}</p>
                </div>
                <Badge>{run.status.replaceAll("_", " ")}</Badge>
              </div>
              <p className="mt-2 text-muted-foreground">
                {run.attempt_count} attempt{run.attempt_count === 1 ? "" : "s"}
                {run.lead_id ? (
                  <>
                    {" "}
                    · lead {run.lead_id}
                  </>
                ) : null}
                {run.agent_run_id ? (
                  <>
                    {" "}
                    · <Link className="underline" href="/agent-runs">agent run</Link>
                  </>
                ) : null}
              </p>
              {run.last_error ? <p className="mt-2 text-red-300">{run.last_error}</p> : null}
              {run.attempts.length > 0 ? (
                <ul className="mt-2 space-y-1 text-muted-foreground">
                  {run.attempts.map((attempt) => (
                    <li key={`${run.id}-${attempt.started_at}`}>
                      {attempt.outcome}
                      {attempt.error ? `: ${attempt.error}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Email deliveries</h2>
        {data.emails.length === 0 ? <p className="text-sm text-muted-foreground">No email has been sent.</p> : null}
        {data.emails.map((email) => (
          <article key={email.id} className="rounded-xl border border-border bg-card p-4 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span>{email.mode === "live" ? "Live provider" : "Sandbox"}</span>
              <Badge>{email.status.replaceAll("_", " ")}</Badge>
            </div>
            {email.provider_message_id ? (
              <p className="mt-2 text-muted-foreground">Message {email.provider_message_id}</p>
            ) : null}
            {email.sent_at ? <p className="text-muted-foreground">Sent {new Date(email.sent_at).toLocaleString()}</p> : null}
            {email.error ? <p className="mt-2 text-red-300">{email.error}</p> : null}
          </article>
        ))}
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Calendar bookings</h2>
        <p className="text-sm text-muted-foreground">
          {calendarLabel} entries are ATLAS records. A simulated booking has no provider event id.
        </p>
        {data.bookings.length === 0 ? <p className="text-sm text-muted-foreground">No bookings yet.</p> : null}
        {data.bookings.map((booking) => (
          <article key={booking.id} className="rounded-xl border border-border bg-card p-4 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span>{booking.provider === "simulation" ? "Simulated calendar" : booking.provider}</span>
              <Badge>{booking.status}</Badge>
            </div>
            <p className="mt-2 text-muted-foreground">
              {new Date(booking.starts_at).toLocaleString()} – {new Date(booking.ends_at).toLocaleString()}
            </p>
            <p className="text-muted-foreground">Lead {booking.lead_id}</p>
            <p className="text-muted-foreground">
              {booking.provider_event_id
                ? `Provider event ${booking.provider_event_id}`
                : "Stored in ATLAS only."}
            </p>
            {workspace.role === "admin" && booking.status === "booked" ? (
              <Button
                type="button"
                className="mt-3"
                variant="outline"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate(booking.id)}
              >
                Cancel booking
              </Button>
            ) : null}
          </article>
        ))}
        {cancel.isError ? <RequestError error={cancel.error} /> : null}
      </section>
    </div>
  );
}

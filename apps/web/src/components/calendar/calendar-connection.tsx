"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";
import { useState } from "react";

import { ConfirmButton } from "@/components/confirm-button";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { checkCalendarAvailability, connectCalendar, disconnectCalendar, type CalendarConnection } from "@/lib/calendar";

export function CalendarConnectionCard({ organizationId, isAdmin, connection, callback }: {
  organizationId: string;
  isAdmin: boolean;
  connection: CalendarConnection | undefined;
  callback: string | null;
}) {
  const client = useQueryClient();
  const [testing, setTesting] = useState(false);
  const connect = useMutation({
    mutationFn: () => connectCalendar(organizationId),
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const disconnect = useMutation({
    mutationFn: () => disconnectCalendar(organizationId),
    onSuccess: () => {
      setTesting(false);
      test.reset();
      void client.invalidateQueries({ queryKey: ["calendar-connection", organizationId] });
      void client.invalidateQueries({ queryKey: ["automations", organizationId] });
    },
  });
  const test = useMutation({
    mutationFn: () => {
      const now = new Date();
      return checkCalendarAvailability(organizationId, {
        starts_at: now.toISOString(),
        ends_at: new Date(now.getTime() + 3600_000).toISOString(),
      });
    },
    onSettled: () => void client.invalidateQueries({ queryKey: ["calendar-connection", organizationId] }),
  });
  const status = !connection ? "Checking" : !connection.available ? "Unavailable" :
    connection.connection_error === "calendar_reconnect_required" ? "Reconnect required" :
    connection.connection_error ? "Check failed" : connection.connected ? "Connected" : "Not connected";
  return (
    <article className="flex min-w-0 flex-col rounded-xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="rounded-lg bg-accent p-2.5 text-accent-foreground"><CalendarDays size={20} aria-hidden /></span>
        <Badge variant="secondary">{status}</Badge>
      </div>
      <h2 className="mt-4 font-semibold">Google Calendar</h2>
      <p className="mb-4 mt-2 flex-1 break-words text-sm text-muted-foreground">
        {connection?.connected ? connection.calendar_name : "Check availability and add approved customer appointments to a workspace calendar."}
      </p>
      {callback === "failed" ? <p className="mb-3 text-sm text-destructive" role="alert">Connection failed. Reconnect and grant Calendar access.</p> : null}
      {callback === "cancelled" ? <p className="mb-3 text-sm text-muted-foreground" role="status">Google authorization was cancelled.</p> : null}
      {isAdmin && connection ? <div className="flex flex-wrap gap-2">
        {connection.available ? <Button size="sm" variant="outline" disabled={connect.isPending} onClick={() => connect.mutate()}>{connection.connected ? "Reconnect" : "Connect Google"}</Button> : null}
        {connection.connected ? <>
          <Button size="sm" variant="outline" disabled={test.isPending || !connection.available} onClick={() => { setTesting(true); test.mutate(); }}>Test connection</Button>
          <ConfirmButton size="sm" label="Disconnect" confirmLabel="Confirm disconnect" pendingLabel="Disconnecting" pending={disconnect.isPending} onConfirm={() => disconnect.mutate()} />
        </> : null}
      </div> : null}
      {testing && test.isSuccess ? <p role="status" className="mt-3 text-sm text-muted-foreground">Google responded to the availability check.</p> : null}
      {disconnect.data ? <p role="status" className="mt-3 text-sm text-muted-foreground">{disconnect.data.grant_revoked ? "Calendar disconnected." : "Calendar disconnected. Remove ATLAS access in your Google Account to revoke the grant."}</p> : null}
      {connect.error || disconnect.error || test.error ? <div className="mt-3"><RequestError error={connect.error ?? disconnect.error ?? test.error} /></div> : null}
    </article>
  );
}

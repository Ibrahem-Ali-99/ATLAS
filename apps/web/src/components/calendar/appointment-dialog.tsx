"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { checkCalendarAvailability, requestAppointment } from "@/lib/calendar";

export function AppointmentDialog({ organizationId, leadId }: { organizationId: string; leadId: string }) {
  const cache = useQueryClient();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const dates = () => ({ starts_at: new Date(start).toISOString(), ends_at: new Date(end).toISOString() });
  const valid = Boolean(start && end && Number.isFinite(Date.parse(start)) && Date.parse(start) < Date.parse(end));
  const check = useMutation({ mutationFn: () => checkCalendarAvailability(organizationId, dates()) });
  const submit = useMutation({
    mutationFn: () => requestAppointment(organizationId, leadId, dates()),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["approvals", organizationId] }),
  });
  const pending = check.isPending || submit.isPending;
  return (
    <Dialog onOpenChange={(open) => { if (open) { check.reset(); submit.reset(); } }}>
      <DialogTrigger asChild><Button type="button" variant="outline">Request appointment</Button></DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Request an appointment</DialogTitle>
          <DialogDescription>Choose times in your local timezone. An administrator approves the request before booking.</DialogDescription>
        </DialogHeader>
        {submit.isSuccess ? <p role="status" className="text-sm">
          Appointment requested. <Link className="font-medium text-primary underline" href={`/approvals?approval=${submit.data.approval_id}`}>Open approval</Link>
        </p> : <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); if (valid && check.data?.available) submit.mutate(); }}>
          <label className="grid gap-1 text-sm">Starts at<Input required type="datetime-local" value={start} disabled={pending} onChange={(event) => { setStart(event.target.value); check.reset(); }} /></label>
          <label className="grid gap-1 text-sm">Ends at<Input required type="datetime-local" value={end} disabled={pending} onChange={(event) => { setEnd(event.target.value); check.reset(); }} /></label>
          {check.data ? <p role="status" className="text-sm text-muted-foreground">
            {check.data.available ? "Available" : "Busy"} on {check.data.provider === "google" ? "Google Calendar and in ATLAS" : "the ATLAS workspace calendar"}.
          </p> : null}
          {check.error || submit.error ? <RequestError error={submit.error ?? check.error} /> : null}
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={!valid || pending} onClick={() => check.mutate()}>{check.isPending ? "Checking…" : "Check availability"}</Button>
            <Button type="submit" disabled={!valid || pending || !check.data?.available}>{submit.isPending ? "Submitting…" : "Request approval"}</Button>
          </div>
        </form>}
      </DialogContent>
    </Dialog>
  );
}

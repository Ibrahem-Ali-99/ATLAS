"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cancelCampaign, getCampaign, getCampaignTransport, listCampaignRecipients, scheduleCampaign, type Campaign, type CampaignDeliveryStatus } from "@/lib/campaigns";
import { useWorkspace } from "@/lib/use-workspace";

const outcomes: Record<CampaignDeliveryStatus, string> = {
  queued: "Queued",
  sending: "In progress",
  accepted: "Accepted by sandbox",
  delivered: "Delivered",
  bounced: "Bounced",
  complained: "Spam complaint",
  skipped: "No longer eligible",
  failed: "Failed",
  needs_attention: "Needs review",
  cancelled: "Cancelled",
};

function isActive(status?: string) {
  return status === "scheduled" || status === "dispatching";
}

export function CampaignDelivery({ organizationId, campaign, eligible }: {
  organizationId: string;
  campaign: Campaign;
  eligible: number;
}) {
  const { role } = useWorkspace();
  const client = useQueryClient();
  const [action, setAction] = useState<"schedule" | "cancel" | null>(null);
  const [timing, setTiming] = useState<"now" | "later">("now");
  const [date, setDate] = useState("");
  const [showRecipients, setShowRecipients] = useState(false);
  const [offset, setOffset] = useState(0);
  const [confirmedMode, setConfirmedMode] = useState<Campaign["delivery_mode"]>("sandbox");
  const key = ["campaign-delivery", organizationId, campaign.id];
  const detail = useQuery({
    queryKey: key,
    queryFn: () => getCampaign(organizationId, campaign.id),
    enabled: campaign.status !== "draft",
    refetchInterval: (query) => isActive(query.state.data?.status ?? campaign.status) ||
      Boolean(query.state.data?.deliveries.sending) ? 2_000 :
      query.state.data?.delivery_mode === "live" ? 15_000 : false,
    staleTime: 0,
  });
  const delivery = useMutation({
    mutationFn: () => action === "cancel"
      ? cancelCampaign(organizationId, campaign.id)
      : scheduleCampaign(organizationId, campaign.id, timing === "now" ? null : new Date(date).toISOString(), confirmedMode),
    onSuccess: (saved) => {
      client.setQueryData(key, saved);
      void client.invalidateQueries({ queryKey: ["campaigns", organizationId] });
      setAction(null);
    },
  });
  const status = detail.data?.status ?? campaign.status;
  const scheduledAt = detail.data?.scheduled_at ?? campaign.scheduled_at;
  const isDraft = status === "draft";
  const transport = useQuery({
    queryKey: ["campaign-transport", organizationId],
    queryFn: () => getCampaignTransport(organizationId),
    enabled: role === "admin" && isDraft,
  });
  const mode = isDraft ? transport.data?.mode : detail.data?.delivery_mode ?? campaign.delivery_mode;
  const labels = { ...outcomes, accepted: mode === "live" ? "Accepted by provider" : outcomes.accepted };
  const recipients = useQuery({
    queryKey: ["campaign-recipients", organizationId, campaign.id, offset],
    queryFn: () => listCampaignRecipients(organizationId, campaign.id, offset),
    enabled: role === "admin" && !isDraft && showRecipients,
    refetchInterval: isActive(status) ? 2_000 : mode === "live" ? 15_000 : false,
  });
  const ready = eligible > 0 && eligible <= 1_000 && Boolean(campaign.subject?.trim() && campaign.body?.trim());
  const validTime = timing === "now" || Boolean(date);

  return (
    <section aria-label="Campaign delivery" className="grid gap-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{mode === "live" ? "Live delivery" : mode === "sandbox" ? "Sandbox delivery" : "Campaign delivery"}</h3>
        {!isDraft ? <span className="text-xs capitalize text-muted-foreground" role="status">{status.replaceAll("_", " ")}</span> : null}
      </div>
      {scheduledAt ? (
        <p className="text-xs text-muted-foreground">Scheduled for <time dateTime={scheduledAt}>{new Date(scheduledAt).toLocaleString()}</time></p>
      ) : null}
      {isDraft ? (
        <p className="text-xs text-muted-foreground">
          {role === "admin"
            ? "Send to the local mail sandbox now or schedule for later. Add a subject, message and 1–1,000 eligible recipients."
            : "A workspace admin can schedule this campaign."}
        </p>
      ) : null}
      {detail.error ? <RequestError error={detail.error} /> : null}
      {transport.error ? <RequestError error={transport.error} /> : null}
      {isDraft && role === "admin" && transport.isPending ? <p role="status" className="text-xs text-muted-foreground">Checking delivery readiness…</p> : null}
      {isDraft && transport.data?.detail ? <p role="status" className="text-sm text-muted-foreground">{transport.data.detail}</p> : null}
      {detail.data && Object.keys(detail.data.deliveries).length ? (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {Object.entries(labels).map(([state, label]) => {
            const count = detail.data?.deliveries[state as CampaignDeliveryStatus];
            return count ? <div key={state} className="rounded-md border border-border px-3 py-2">
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="text-sm font-medium tabular-nums">{count}</dd>
            </div> : null;
          })}
        </dl>
      ) : null}
      {role === "admin" && !isDraft ? (
        <details onToggle={(event) => setShowRecipients(event.currentTarget.open)} className="rounded-md border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">Recipient delivery status</summary>
          {showRecipients && recipients.isPending ? <p role="status" className="mt-3 text-sm">Loading recipients…</p> : null}
          {recipients.error ? <RequestError error={recipients.error} /> : null}
          {recipients.data ? (
            <>
              {recipients.data.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">No recipients on this page.</p> : null}
              <ul className="mt-2 divide-y divide-border" aria-label="Campaign recipients">
                {recipients.data.map((row) => <li key={row.id} className="grid gap-1 py-2 text-sm sm:grid-cols-[minmax(0,1fr)_auto]">
                  <span className="break-all">{row.email}</span>
                  <span className="text-muted-foreground">{labels[row.status]}</span>
                </li>)}
              </ul>
              <div className="flex gap-2">
                {offset > 0 ? <Button size="sm" variant="outline" onClick={() => setOffset(offset - 50)}>Previous</Button> : null}
                {recipients.data.length === 50 ? <Button size="sm" variant="outline" onClick={() => setOffset(offset + 50)}>Next</Button> : null}
              </div>
            </>
          ) : null}
        </details>
      ) : null}
      {role === "admin" && (isDraft || isActive(status)) ? (
        <Dialog open={action !== null} onOpenChange={(open) => {
          if (open) {
            delivery.reset();
            if (transport.data?.mode) setConfirmedMode(transport.data.mode);
            setAction(isDraft ? "schedule" : "cancel");
          } else if (!delivery.isPending) {
            setAction(null);
          }
        }}>
          <DialogTrigger asChild>
            <Button className="justify-self-start" variant={isDraft ? "default" : "outline"} disabled={isDraft && (!ready || !transport.data?.ready)}>
              {isDraft ? "Schedule delivery" : "Cancel delivery"}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{action === "cancel" ? "Cancel campaign delivery" : confirmedMode === "live" ? "Schedule live delivery" : "Schedule sandbox delivery"}</DialogTitle>
              <DialogDescription>
                {action === "cancel"
                  ? "Cancel queued messages. A message already being sent may still arrive."
                  : confirmedMode === "live"
                    ? "This sends email to real recipients. Consent and suppression are checked again before each message."
                    : "The campaign is locked after scheduling. Consent and suppression are checked again before each message."}
              </DialogDescription>
            </DialogHeader>
            <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); delivery.mutate(); }}>
              {action === "schedule" ? (
                <fieldset className="grid gap-2 text-sm">
                  <legend className="mb-2 font-medium">Delivery time</legend>
                  <label className="flex items-center gap-2"><input type="radio" name="timing" checked={timing === "now"} onChange={() => setTiming("now")} /> Send now</label>
                  <label className="flex items-center gap-2"><input type="radio" name="timing" checked={timing === "later"} onChange={() => setTiming("later")} /> Schedule for later</label>
                  {timing === "later" ? <label className="grid gap-1">Local date and time
                    <Input type="datetime-local" required value={date} onChange={(event) => setDate(event.target.value)} />
                  </label> : null}
                </fieldset>
              ) : null}
              {delivery.error ? <RequestError error={delivery.error} /> : null}
              <Button type="submit" disabled={delivery.isPending || (action === "schedule" && !validTime)}>
                {delivery.isPending ? "Saving…" : action === "cancel" ? "Confirm cancellation" : timing === "now" ? (confirmedMode === "live" ? "Send live campaign" : "Send to sandbox") : "Confirm schedule"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  );
}

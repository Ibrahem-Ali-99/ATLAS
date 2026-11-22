"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { RequestError } from "@/components/request-error";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getAnalytics, type AnalyticsSnapshot } from "@/lib/intelligence";
import { useWorkspace } from "@/lib/use-workspace";

export function AnalyticsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const analytics = useQuery({
    queryKey: ["analytics", organizationId],
    queryFn: () => getAnalytics(organizationId ?? ""),
    enabled: Boolean(organizationId),
  });
  if (!organizationId || analytics.isPending) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (analytics.isError) {
    return <RequestError error={analytics.error} />;
  }
  return <AnalyticsBody data={analytics.data} />;
}

function AnalyticsBody({ data }: { data: AnalyticsSnapshot }) {
  if (data.leads_total === 0 && data.inquiries_total === 0) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="max-w-2xl text-sm leading-6 text-muted-foreground">{data.synthetic_notice}</p>
        <p className="text-sm text-muted-foreground">No leads or inquiries are stored for this organization yet.</p>
      </div>
    );
  }
  const rate = data.conversion.rate === null ? "unavailable" : `${Math.round(data.conversion.rate * 1000) / 10}%`;
  const automation =
    data.automation.success_rate === null ? "unavailable" : `${Math.round(data.automation.success_rate * 1000) / 10}%`;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
          {data.synthetic_notice} Lead trend uses the last {data.window_days} days. {data.conversion.definition}
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Leads" value={String(data.leads_total)} />
        <Metric label="Inquiries" value={String(data.inquiries_total)} />
        <Metric label="Conversion" value={rate} detail={`${data.conversion.won} won, ${data.conversion.lost} lost`} />
        <Metric label="Automation success" value={automation} detail={data.automation.definition} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Lead status</CardTitle>
            <CardDescription>{data.qualification.definition}</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.lead_status}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="status" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="currentColor" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Leads created</CardTitle>
            <CardDescription>Daily counts for the last {data.window_days} days, including days with zero.</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.lead_trend}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" hide />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="currentColor" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Metric label="Approvals pending" value={String(data.approvals.pending)} detail={`${data.approvals.completed} completed`} />
        <Metric label="Follow-ups" value={String(data.follow_ups.approval_requests)} detail={`${data.follow_ups.interactions} interactions`} />
        <Metric
          label="Sandbox email sent"
          value={String(data.email.sandbox_sent)}
          detail={`${data.email.failed} failed. Calendar bookings: ${data.calendar.booked}. ${data.calendar.notice}`}
        />
      </div>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle>{value}</CardTitle>
      </CardHeader>
      {detail ? (
        <CardContent>
          <p className="text-xs leading-5 text-muted-foreground">{detail}</p>
        </CardContent>
      ) : null}
    </Card>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PageHeader } from "@/components/page-header";
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
      <div className="w-full space-y-3">
        <PageHeader title="Analytics">{data.synthetic_notice}</PageHeader>
        <p className="text-sm text-muted-foreground">No leads or inquiries are stored for this organization yet. Charts appear after the first record is saved.</p>
      </div>
    );
  }
  const rate = data.conversion.rate === null ? "unavailable" : `${Math.round(data.conversion.rate * 1000) / 10}%`;
  const automation =
    data.automation.success_rate === null ? "unavailable" : `${Math.round(data.automation.success_rate * 1000) / 10}%`;
  return (
    <div className="w-full space-y-6">
      <div>
        <PageHeader title="Analytics">
          {data.synthetic_notice} Lead trend uses the last {data.window_days} days. {data.conversion.definition}
        </PageHeader>
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
            {data.lead_status.length === 0 ? (
              <p className="text-sm text-muted-foreground">No lead statuses are stored in this window.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.lead_status}>
                  <CartesianGrid stroke="#2a303b" vertical={false} />
                  <XAxis dataKey="status" tick={{ fill: "#a7b0be", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: "#a7b0be", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={chartTooltip} />
                  <Bar dataKey="count" fill="#4c8dff" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
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
                <CartesianGrid stroke="#2a303b" vertical={false} />
                <XAxis dataKey="day" tickFormatter={shortDay} minTickGap={28} tick={{ fill: "#a7b0be", fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: "#a7b0be", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={chartTooltip} />
                <Line type="monotone" dataKey="count" stroke="#4c8dff" strokeWidth={2} dot={false} />
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

const chartTooltip = {
  background: "#11141a",
  border: "1px solid #2a303b",
  borderRadius: 8,
  color: "#fafafa",
};

function shortDay(value: string): string {
  return value.length >= 10 ? value.slice(5) : value;
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl tabular-nums">{value}</CardTitle>
      </CardHeader>
      {detail ? (
        <CardContent>
          <p className="text-xs leading-5 text-muted-foreground">{detail}</p>
        </CardContent>
      ) : null}
    </Card>
  );
}
